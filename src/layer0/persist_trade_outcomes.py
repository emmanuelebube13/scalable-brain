"""Layer 0 → DB bridge: persist backtested trades to fact_trade_outcomes + seed dim_strategy.

The qualification engine (``qualify_strategies.py``) backtests strategies but only emits
JSON reports (and obsolete T-SQL) — it never writes the Postgres trade tables. This
script reuses the *same* backtest path (``get_all_strategies`` + ``BacktestEngine`` +
``preload_historical_data``) and persists per-trade outcomes, unblocking MODEL-004
(per-regime attribution) and MODEL-006 (gatekeeper). Default strategy params (no
optimization) — representative real trades across regimes.

Idempotent: clears prior rows for the loaded strategies before inserting.

Usage:
    python -m src.layer0.persist_trade_outcomes
    python -m src.layer0.persist_trade_outcomes --granularities H1,H4 --lookback-years 5
"""

from __future__ import annotations

import argparse
import logging
from datetime import timezone
from typing import Dict, List, Optional

import pandas as pd
import psycopg2.extensions
from psycopg2.extras import execute_values

from src.common.db import get_psycopg2_connection
from src.layer0.backtest_engine import BacktestConfig, BacktestEngine
from src.layer0.qualify_strategies import get_all_strategies, preload_historical_data
from src.system1.validation import walk_forward as WF

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)
logger = logging.getLogger("layer0.persist_trade_outcomes")


_TRADE_COLUMNS = [
    "timestamp",
    "asset_id",
    "strategy_id",
    "granularity",
    "trade_horizon",
    "is_winner",
    "r_multiple",
    "holding_bars",
    "atr_sl_multiplier",
    "atr_tp_multiplier",
    "entry_signal_type",
    "exit_reason",
]


def ensure_oos_columns(conn: Optional[psycopg2.extensions.connection] = None) -> bool:
    """Idempotently add the FIX-S1-002 walk-forward OOS columns + index to fact_trade_outcomes.

    Adds ``is_oos boolean`` and ``fold_id integer`` (``ADD COLUMN IF NOT EXISTS``) plus a
    ``(strategy_id, granularity, is_oos)`` index. Mirrors the additive-column pattern in
    ``src/system1/attribution/schema.py``. ``is_oos IS NULL`` marks an **unclassified legacy
    row** (inserted before this fix and not yet backfilled); :func:`backfill_oos` clears that.

    Returns True (columns ensured). Safe to run repeatedly.
    """
    own = conn is None
    if conn is None:
        conn = get_psycopg2_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "ALTER TABLE fact_trade_outcomes ADD COLUMN IF NOT EXISTS is_oos boolean"
        )
        cur.execute(
            "ALTER TABLE fact_trade_outcomes ADD COLUMN IF NOT EXISTS fold_id integer"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS ix_trade_outcomes_oos "
            "ON fact_trade_outcomes (strategy_id, granularity, is_oos)"
        )
        conn.commit()
        logger.info("Ensured fact_trade_outcomes.is_oos / fold_id (+ index)")
    finally:
        if own:
            conn.close()
    return True


def backfill_oos(
    conn: Optional[psycopg2.extensions.connection] = None,
) -> Dict[str, Dict[str, int]]:
    """One-shot backfill of is_oos/fold_id for legacy rows from their existing entry_times.

    Pure, no re-backtest: for each granularity it derives ``series_start = min(entry)`` /
    ``series_end = max(entry)``, builds the locked walk-forward folds, then UPDATEs rows by
    time range using the SAME boundary rule as :func:`walk_forward.assign_oos` (in-sample =
    entry < cutoff; OOS fold = the contiguous window whose ``oos_start`` is the greatest one
    ``<= entry``; the final window catches everything at/after the last ``oos_start``).

    Idempotent: deterministic range UPDATEs, so re-running yields identical is_oos/fold_id.

    Returns per-granularity ``{"oos": n, "in_sample": n}`` counts.
    """
    own = conn is None
    if conn is None:
        conn = get_psycopg2_connection()
    try:
        ensure_oos_columns(conn)
        cur = conn.cursor()
        cur.execute(
            'SELECT granularity, MIN("timestamp"), MAX("timestamp") '
            "FROM fact_trade_outcomes GROUP BY granularity"
        )
        bounds = cur.fetchall()
        stats: Dict[str, Dict[str, int]] = {}
        for gran, smin, smax in bounds:
            folds = WF.default_folds(smin, smax)
            if not folds:
                # No OOS period at all (history <= min_train): everything is in-sample.
                cur.execute(
                    "UPDATE fact_trade_outcomes SET is_oos = false, fold_id = NULL "
                    "WHERE granularity = %s",
                    (gran,),
                )
                conn.commit()
                stats[gran] = {"oos": 0, "in_sample": cur.rowcount}
                continue
            cutoff = folds[0].oos_start
            cur.execute(
                "UPDATE fact_trade_outcomes SET is_oos = false, fold_id = NULL "
                'WHERE granularity = %s AND "timestamp" < %s',
                (gran, cutoff),
            )
            in_sample = cur.rowcount
            oos_total = 0
            for i, f in enumerate(folds):
                upper = folds[i + 1].oos_start if i + 1 < len(folds) else None
                if (
                    upper is None
                ):  # final window catches all trailing trades (incl. series_end)
                    cur.execute(
                        "UPDATE fact_trade_outcomes SET is_oos = true, fold_id = %s "
                        'WHERE granularity = %s AND "timestamp" >= %s',
                        (f.fold_id, gran, f.oos_start),
                    )
                else:
                    cur.execute(
                        "UPDATE fact_trade_outcomes SET is_oos = true, fold_id = %s "
                        'WHERE granularity = %s AND "timestamp" >= %s AND "timestamp" < %s',
                        (f.fold_id, gran, f.oos_start, upper),
                    )
                oos_total += cur.rowcount
            conn.commit()
            stats[gran] = {"oos": oos_total, "in_sample": in_sample}
        logger.info("Backfilled is_oos/fold_id: %s", stats)
        return stats
    finally:
        if own:
            conn.close()


def _assign_oos_columns(rows: List[tuple]) -> List[tuple]:
    """Append (is_oos, fold_id) to each persisted trade tuple via the walk-forward rule.

    ``rows`` are tuples in ``_TRADE_COLUMNS`` order. Folds are computed per granularity from
    the in-batch entry-time bounds (the same anchor the backfill uses), so the INSERT path
    and :func:`backfill_oos` agree exactly. ``fold_id`` is emitted as a Python int or None.
    """
    if not rows:
        return rows
    df = pd.DataFrame(rows, columns=_TRADE_COLUMNS)
    df["is_oos"] = False
    df["fold_id"] = pd.array([pd.NA] * len(df), dtype="Int64")
    for gran, sub in df.groupby("granularity"):
        smin, smax = WF.series_bounds(sub["timestamp"])
        folds = WF.default_folds(smin, smax)
        is_oos, fold_id = WF.assign_oos(sub["timestamp"], folds)
        df.loc[sub.index, "is_oos"] = is_oos.to_numpy()
        df.loc[sub.index, "fold_id"] = fold_id
    out: List[tuple] = []
    for rec in df.itertuples(index=False):
        d = rec._asdict()
        fid = d["fold_id"]
        out.append(
            tuple(d[c] for c in _TRADE_COLUMNS)
            + (bool(d["is_oos"]), None if pd.isna(fid) else int(fid))
        )
    return out


def _asset_symbol_map(conn) -> Dict[str, int]:
    cur = conn.cursor()
    cur.execute(
        "SELECT symbol, asset_id FROM dim_asset WHERE is_active = true ORDER BY asset_id"
    )
    return {sym: aid for sym, aid in cur.fetchall()}


def _seed_strategies(conn, strategies) -> Dict[str, int]:
    """Insert each strategy into dim_strategy (assigning ids); return name→strategy_id."""
    cur = conn.cursor()
    cur.execute("SELECT strategy_name, strategy_id FROM dim_strategy")
    existing = {name: sid for name, sid in cur.fetchall()}
    cur.execute("SELECT COALESCE(MAX(strategy_id), 0) FROM dim_strategy")
    next_id = cur.fetchone()[0] + 1

    name_to_id: Dict[str, int] = {}
    new_rows = []
    for strat in strategies:
        cfg = strat.config
        name = cfg.name
        if name in existing:
            name_to_id[name] = existing[name]
            continue
        sid = next_id
        next_id += 1
        name_to_id[name] = sid
        stype = (
            getattr(cfg, "strategy_type", None)
            or getattr(cfg, "category", None)
            or "BACKTEST"
        )
        new_rows.append(
            (sid, name, str(stype), getattr(cfg, "description", "") or "", True)
        )
    if new_rows:
        execute_values(
            cur,
            "INSERT INTO dim_strategy (strategy_id, strategy_name, strategy_type, description, is_active) "
            "VALUES %s ON CONFLICT (strategy_id) DO NOTHING",
            new_rows,
        )
    # fact_trade_outcomes.strategy_id FK references dim_strategy_registry — ensure ALL
    # loaded strategies are present there (idempotent), not only the newly-added ones.
    execute_values(
        cur,
        "INSERT INTO dim_strategy_registry (strategy_id, strategy_name) VALUES %s "
        "ON CONFLICT (strategy_id) DO NOTHING",
        [(sid, name) for name, sid in name_to_id.items()],
    )
    conn.commit()
    logger.info(
        "Seeded %d new strategies; registry covers %d", len(new_rows), len(name_to_id)
    )
    return name_to_id


def _trade_rows(
    trades, asset_id: int, strategy_id: int, granularity: str
) -> List[tuple]:
    rows = []
    for t in trades:
        if t.exit_time is None:  # closed trades only
            continue
        ts = t.entry_time
        if getattr(ts, "tzinfo", None) is None:
            ts = ts.replace(tzinfo=timezone.utc)
        rows.append(
            (
                ts,
                asset_id,
                strategy_id,
                granularity,
                granularity,  # trade_horizon (timeframe of the trade)
                1 if (t.pnl or 0.0) > 0 else 0,  # is_winner
                float(t.r_multiple) if t.r_multiple is not None else None,
                int(t.bars_held or 0),
                None,  # atr_sl_multiplier (strategy SL not ATR-multiple here)
                None,  # atr_tp_multiplier
                "long" if t.direction > 0 else "short",  # entry_signal_type
                str(t.exit_reason) if t.exit_reason else None,
            )
        )
    return rows


INSERT_SQL = """
    INSERT INTO fact_trade_outcomes
        (timestamp, asset_id, strategy_id, granularity, trade_horizon, is_winner,
         r_multiple, holding_bars, atr_sl_multiplier, atr_tp_multiplier,
         entry_signal_type, exit_reason, is_oos, fold_id)
    VALUES %s
"""


def run(granularities: List[str], lookback_years: int = 5) -> Dict[str, int]:
    conn = get_psycopg2_connection()
    ensure_oos_columns(
        conn
    )  # FIX-S1-002: is_oos / fold_id columns must exist before insert
    asset_map = _asset_symbol_map(conn)
    symbols = list(asset_map.keys())
    strategies = get_all_strategies()
    name_to_id = _seed_strategies(conn, strategies)

    # Idempotency: clear prior outcomes for the strategies we are about to load.
    strat_ids = tuple(name_to_id.values())
    cur = conn.cursor()
    cur.execute("DELETE FROM fact_trade_outcomes WHERE strategy_id IN %s", (strat_ids,))
    conn.commit()

    # Preload prices once (shared across strategies).
    logger.info(
        "Preloading prices: %s x %s (%dy)…", symbols, granularities, lookback_years
    )
    data = preload_historical_data(
        asset_symbols=symbols,
        asset_symbol_map=asset_map,
        granularities=granularities,
        use_db=True,
        conn=conn,
        lookback_years=lookback_years,
    )

    engine = BacktestEngine(BacktestConfig())
    total = {"strategies": len(strategies), "backtests": 0, "trades": 0}
    # Accumulate ALL trade rows first: the walk-forward anchor (series_start) is the
    # per-granularity MIN entry time across every strategy/asset, so OOS labelling must see
    # the full population before assigning is_oos/fold_id (FIX-S1-002).
    collected: List[tuple] = []
    for strat in strategies:
        sid = name_to_id[strat.config.name]
        import copy

        for symbol in symbols:
            if symbol not in data:
                continue
            aid = asset_map[symbol]
            for gran in granularities:
                if gran not in data.get(symbol, {}):
                    continue
                df = data[symbol][gran]
                run_strat = copy.deepcopy(strat)
                result = engine.run_backtest(
                    run_strat,
                    df,
                    symbol,
                    gran,
                    warmup_bars=run_strat.get_required_warmup_bars(),
                )
                total["backtests"] += 1
                rows = _trade_rows(result.trades, aid, sid, gran)
                collected.extend(rows)
                logger.info(
                    "  %s %s %s: %d trades backtested",
                    strat.config.name,
                    symbol,
                    gran,
                    len(rows),
                )

    # Walk-forward OOS labelling (per-granularity folds) then a single bulk insert.
    labelled = _assign_oos_columns(collected)
    if labelled:
        execute_values(cur, INSERT_SQL, labelled, page_size=2000)
        conn.commit()
        total["trades"] = len(labelled)
    conn.close()
    logger.info("DONE: %s", total)
    return total


def main() -> None:
    p = argparse.ArgumentParser(
        description="Persist backtested trades → fact_trade_outcomes"
    )
    p.add_argument("--granularities", default="H1,H4")
    p.add_argument("--lookback-years", type=int, default=5)
    args = p.parse_args()
    run([g.strip() for g in args.granularities.split(",")], args.lookback_years)


if __name__ == "__main__":
    main()
