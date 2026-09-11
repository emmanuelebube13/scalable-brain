import argparse
import json
import logging
import os
import tempfile
import pandas as pd
from datetime import datetime, timezone
from psycopg2.extras import execute_values
from src.common.db import get_psycopg2_connection
from src.outcomes.geometry import REFERENCE_BY_ENGINE, GeometryLookup
from src.registry.catalog import all_strategies, instantiate
from src.validation import walk_forward as WF
from src.layer0.qualify_strategies import preload_historical_data
from src.layer0.core_engine.backtest_engine import BacktestEngine, BacktestConfig

# For v2
from src.layer0.strategies.position_engine import PositionEngine
from src.layer0.strategies.v2_harness import assert_no_lookahead_v2

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)
logger = logging.getLogger("outcomes.persist_all")

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STATE_PATH = os.path.join(_REPO_ROOT, "results", "state", "outcomes_writer_state.json")

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
    "is_oos",
    "is_holdout",
    "fold_id",
    "leg_index",
    "is_terminal_leg",
]

_SL_IDX = _TRADE_COLUMNS.index("atr_sl_multiplier")
_TP_IDX = _TRADE_COLUMNS.index("atr_tp_multiplier")

INSERT_SQL = f"""
    INSERT INTO fact_trade_outcomes ({", ".join(_TRADE_COLUMNS)})
    VALUES %s
    ON CONFLICT ("timestamp", asset_id, strategy_id, granularity, leg_index)
    DO UPDATE SET
        trade_horizon = EXCLUDED.trade_horizon,
        is_winner = EXCLUDED.is_winner,
        r_multiple = EXCLUDED.r_multiple,
        holding_bars = EXCLUDED.holding_bars,
        atr_sl_multiplier = EXCLUDED.atr_sl_multiplier,
        atr_tp_multiplier = EXCLUDED.atr_tp_multiplier,
        entry_signal_type = EXCLUDED.entry_signal_type,
        exit_reason = EXCLUDED.exit_reason,
        is_oos = EXCLUDED.is_oos,
        is_holdout = EXCLUDED.is_holdout,
        fold_id = EXCLUDED.fold_id,
        is_terminal_leg = EXCLUDED.is_terminal_leg
"""


def _asset_symbol_map(conn):
    cur = conn.cursor()
    cur.execute(
        "SELECT symbol, asset_id FROM dim_asset WHERE is_active = true ORDER BY asset_id"
    )
    return {sym: aid for sym, aid in cur.fetchall()}


def _assign_oos_columns(rows):
    if not rows:
        return rows
    df = pd.DataFrame(rows, columns=_TRADE_COLUMNS)
    df["is_oos"] = False
    df["is_holdout"] = False
    df["fold_id"] = pd.array([pd.NA] * len(df), dtype="Int64")
    for gran, sub in df.groupby("granularity"):
        smin, smax = WF.series_bounds(sub["timestamp"])
        folds = WF.default_folds(smin, smax)
        is_oos, fold_id = WF.assign_oos(sub["timestamp"], folds)
        is_holdout = WF.assign_holdout(sub["timestamp"], sub["holding_bars"], gran)
        df.loc[sub.index, "is_oos"] = is_oos.to_numpy() & ~is_holdout.to_numpy()
        df.loc[sub.index, "is_holdout"] = is_holdout.to_numpy()
        df.loc[sub.index, "fold_id"] = fold_id
    out = []
    for rec in df.itertuples(index=False):
        d = rec._asdict()
        fid = d["fold_id"]
        # _TRADE_COLUMNS indices: is_oos=12, is_holdout=13, fold_id=14
        row = list(d[c] for c in _TRADE_COLUMNS)
        row[12] = bool(d["is_oos"])
        row[13] = bool(d["is_holdout"])
        row[14] = None if pd.isna(fid) else int(fid)
        # The DataFrame round-trip above turns a Python None in a float column into NaN,
        # and psycopg2 sends NaN to a `double precision` column as the FLOAT VALUE NaN,
        # not as NULL. That would make "no take-profit was declared" indistinguishable
        # from a target at an undefined distance, and every downstream `count(col)` would
        # report the column as fully populated while the values were unusable.
        for idx in (_SL_IDX, _TP_IDX):
            if row[idx] is not None and pd.isna(row[idx]):
                row[idx] = None
        out.append(tuple(row))
    return out


def run(
    lookback_years: int = 10,
    dry_run: bool = False,
    only_strat: str = None,
    reconcile: bool = False,
):
    started = datetime.now(timezone.utc)
    conn = get_psycopg2_connection()
    asset_map = _asset_symbol_map(conn)
    symbols = list(asset_map.keys())

    strats = all_strategies()
    if only_strat:
        strats = [s for s in strats if s.strategy_key == only_strat]

    # Every strategy that fails below is one whose trades silently stop being refreshed
    # while its OLD rows stay in the table (the upsert never deletes). Counted, named and
    # published in the state file — an ERROR line in a log nobody tails is not a signal.
    failed_instantiate: list[dict] = []
    skipped_symbols: list[dict] = []

    granularities = set()
    for s in strats:
        if s.primary_granularity:
            granularities.add(s.primary_granularity)
        elif s.universe == "v2_research":
            try:
                obj = instantiate(s)
                granularities.add(obj.metadata.primary_granularity)
                granularities.update(obj.metadata.context_granularities)
            except Exception:
                pass

    if not granularities:
        granularities = {"H1", "H4"}
    else:
        granularities.update({"H1", "H4", "D1"})

    logger.info(
        "Preloading prices: %s x %s (%dy)...", symbols, granularities, lookback_years
    )
    data = preload_historical_data(
        asset_symbols=symbols,
        asset_symbol_map=asset_map,
        granularities=list(granularities),
        use_db=True,
        conn=conn,
        lookback_years=lookback_years,
    )

    collected = []
    v1_engine = BacktestEngine(BacktestConfig())
    v2_engine = PositionEngine()

    # One ATR reference per (symbol x granularity), built once and shared by every
    # strategy that trades that series. Building it inside the strategy loop would
    # recompute the same EWM recursion dozens of times, and — because ewm(adjust=False)
    # seeds from the first row it is handed — would only be guaranteed to agree if every
    # caller passed an identical frame. Compute once, read many; the same rule the
    # structural labeller now follows (R2).
    #
    # Keyed by engine as well as series: the two engines fill differently, so a different
    # ATR bar is knowable at entry in each (see geometry.REFERENCE_BY_ENGINE).
    geometry: dict = {}

    def _geometry(symbol: str, gran: str, engine: str):
        reference = REFERENCE_BY_ENGINE.get(engine)
        if reference is None:
            logger.warning(
                "No ATR reference declared for engine %r — writing NULL geometry for "
                "its trades rather than guessing a fill model",
                engine,
            )
            return None
        key = (symbol, gran, reference)
        if key not in geometry:
            frame = data.get(symbol, {}).get(gran)
            geometry[key] = (
                None if frame is None else GeometryLookup(frame, reference=reference)
            )
        return geometry[key]

    for record in strats:
        try:
            obj = instantiate(record)
        except Exception as e:
            logger.error("Failed to instantiate %s: %s", record.strategy_key, e)
            failed_instantiate.append(
                {
                    "strategy_key": record.strategy_key,
                    "strategy_id": record.strategy_id,
                    "error": str(e),
                }
            )
            continue

        sid = record.strategy_id

        if record.engine == "backtest_engine_v1":
            gran = record.primary_granularity or getattr(
                obj.config, "primary_granularity", "H1"
            )
            for symbol in symbols:
                if symbol not in data or gran not in data[symbol]:
                    continue
                import copy

                run_strat = copy.deepcopy(obj)
                res = v1_engine.run_backtest(
                    run_strat,
                    data[symbol][gran],
                    symbol,
                    gran,
                    run_strat.get_required_warmup_bars(),
                )
                geo = _geometry(symbol, gran, record.engine)
                for t in res.trades:
                    if t.exit_time is None:
                        continue
                    ts = t.entry_time
                    # Resolve the geometry BEFORE the tz stamp below: the price frames
                    # are tz-naive UTC and the lookup is an exact index match.
                    sl_mult, tp_mult = (
                        geo.for_trade(ts, t.entry_price, t.stop_loss, t.take_profit)
                        if geo is not None
                        else (None, None)
                    )
                    if getattr(ts, "tzinfo", None) is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    collected.append(
                        (
                            ts,
                            asset_map[symbol],
                            sid,
                            gran,
                            gran,
                            1 if (t.pnl or 0.0) > 0 else 0,
                            float(t.r_multiple) if t.r_multiple is not None else None,
                            int(t.bars_held or 0),
                            sl_mult,
                            tp_mult,
                            "long" if t.direction > 0 else "short",
                            str(t.exit_reason) if t.exit_reason else None,
                            False,
                            False,
                            None,
                            0,
                            True,
                        )
                    )

        elif record.engine == "position_engine_v2":
            meta = obj.metadata
            gran = meta.primary_granularity
            for symbol in meta.pairs:
                if symbol not in data:
                    continue
                frames = {gran: data[symbol][gran]}
                skip = False
                for cg in meta.context_granularities:
                    if cg not in data[symbol]:
                        skip = True
                        break
                    frames[cg] = data[symbol][cg]
                if skip:
                    continue

                try:
                    assert_no_lookahead_v2(obj, frames)
                    intents = list(obj.generate_orders(frames))
                except Exception as e:
                    logger.warning(
                        "Skipping %s on %s: %s", record.strategy_key, symbol, e
                    )
                    skipped_symbols.append(
                        {
                            "strategy_key": record.strategy_key,
                            "strategy_id": record.strategy_id,
                            "symbol": symbol,
                            "error": str(e),
                        }
                    )
                    continue

                if not intents:
                    continue

                res = v2_engine.run(
                    frames[gran],
                    intents,
                    pair=symbol,
                    warmup_bars=obj.warmup_bars,
                    strategy=obj,
                    granularity=gran,
                )

                geo = _geometry(symbol, gran, record.engine)
                for _, t in res.trades.iterrows():
                    if pd.isna(t["exit_time"]):
                        continue
                    ts = t["entry_time"]
                    # `initial_stop_price`, not `final_stop_price`: the geometry the
                    # trade was ENTERED with. v2 moves its stop to breakeven and trails
                    # it, so the final stop is a function of how the trade went — using
                    # it would leak the outcome into a feature meant to predict it. It is
                    # also the r_multiple's own risk denominator (module docstring), so
                    # the two stay the same quantity.
                    tp = t.get("take_profit_price")
                    sl_mult, tp_mult = (
                        geo.for_trade(
                            ts,
                            t["entry_price"],
                            t["initial_stop_price"],
                            None if tp is None or pd.isna(tp) else float(tp),
                        )
                        if geo is not None
                        else (None, None)
                    )
                    if getattr(ts, "tzinfo", None) is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    collected.append(
                        (
                            ts,
                            asset_map[symbol],
                            sid,
                            gran,
                            gran,
                            1 if t["r_multiple"] > 0 else 0,
                            float(t["r_multiple"]),
                            int(t["bars_held"]),
                            sl_mult,
                            tp_mult,
                            "long" if t["direction"] > 0 else "short",
                            str(t["exit_reason"]),
                            False,
                            False,
                            None,
                            0,
                            True,
                        )
                    )

    logger.info("Assigning OOS columns for %d trades...", len(collected))
    labelled = _assign_oos_columns(collected)

    produced_ids = sorted({row[2] for row in labelled})
    ghost_rows = _ghost_rows(conn, produced_ids) if not only_strat else {}
    if ghost_rows:
        logger.warning(
            "%d rows in fact_trade_outcomes belong to %d strategies this run did not "
            "produce (%s). The upsert never deletes, so these keep feeding attribution "
            "and vetting. Re-run with --reconcile to remove them.",
            sum(ghost_rows.values()),
            len(ghost_rows),
            ", ".join(str(s) for s in sorted(ghost_rows)),
        )

    reconciled = 0
    if not dry_run and labelled:
        logger.info("Persisting to database...")
        cur = conn.cursor()
        execute_values(cur, INSERT_SQL, labelled, page_size=2000)
        if reconcile and ghost_rows:
            # Same transaction as the insert: the table is either fully reconciled to
            # this run or untouched. A partial state would be worse than a stale one.
            cur.execute(
                "DELETE FROM fact_trade_outcomes WHERE strategy_id = ANY(%s)",
                (list(ghost_rows),),
            )
            reconciled = cur.rowcount
            logger.warning("Reconciled: deleted %d orphaned rows", reconciled)
        conn.commit()

    outcome = _classify(labelled, failed_instantiate, dry_run)
    # Only a full, committing run may publish the state file. A --dry-run or a --only
    # run measures a fraction of the registry, so writing its record would replace the
    # scheduled rebuild's diagnostics with a narrower and misleadingly clean set —
    # exactly the "the monitor lost the finding" failure this state file exists to stop.
    # Caught in review: a one-strategy dry run blanked `failed_instantiate` (12 entries)
    # and `ghost_rows` (17,583 rows), silently clearing the heartbeat WARN.
    if dry_run or only_strat:
        logger.info(
            "Partial run (%s) — %s left untouched",
            "dry-run" if dry_run else f"--only {only_strat}",
            os.path.basename(STATE_PATH),
        )
    else:
        _write_state(
            started=started,
            outcome=outcome,
            rows_written=len(labelled),
            strategies_attempted=len(strats),
            strategies_ok=len(produced_ids),
            failed_instantiate=failed_instantiate,
            skipped_symbols=skipped_symbols,
            ghost_rows=ghost_rows,
            reconciled_rows=reconciled,
        )
    conn.close()

    print(f"Total trades collected: {len(labelled)}")
    return {
        "outcome": outcome,
        "rows": len(labelled),
        "failed_instantiate": len(failed_instantiate),
        "ghost_rows": sum(ghost_rows.values()),
    }


def _ghost_rows(conn, produced_ids) -> dict:
    """Rows already in the table for strategies this run produced nothing for.

    A strategy whose code stops loading does not remove its history: ``ON CONFLICT DO
    UPDATE`` only ever adds or refreshes. So its trades stay, keep their original
    ``created_at``, and continue to qualify in vetting long after the strategy itself
    became unrunnable — the same shape as FIX-S1-013, arrived at by a different route.
    """
    if not produced_ids:
        return {}
    cur = conn.cursor()
    cur.execute(
        "SELECT strategy_id, count(*) FROM fact_trade_outcomes "
        "WHERE NOT (strategy_id = ANY(%s)) GROUP BY strategy_id",
        (list(produced_ids),),
    )
    return {int(sid): int(n) for sid, n in cur.fetchall()}


def _classify(labelled, failed_instantiate, dry_run) -> str:
    if not labelled:
        return "no_trades_produced"
    if dry_run:
        return "dry_run"
    if failed_instantiate:
        return "ok_with_failures"
    return "ok"


def _write_state(**fields) -> None:
    """Publish the run record so a dead writer is distinguishable from a quiet one.

    Without this, ``max(created_at)`` is the only liveness signal available, and it
    cannot tell "never scheduled" from "scheduled and crashing every night" — both
    leave the table untouched. That ambiguity is what let outcomes go stale unnoticed.
    """
    started = fields.pop("started")
    now = datetime.now(timezone.utc)
    prior = {}
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, encoding="utf-8") as fh:
                prior = json.load(fh)
        except (OSError, json.JSONDecodeError):
            prior = {}

    faults = prior.get("consecutive_faults", 0)
    ok = fields["outcome"] in ("ok", "ok_with_failures")
    state = {
        "last_run_at": now.isoformat().replace("+00:00", "Z"),
        "last_run_duration_s": round((now - started).total_seconds(), 1),
        "consecutive_faults": 0 if ok else faults + 1,
        "last_healthy_run_at": (
            now.isoformat().replace("+00:00", "Z")
            if ok
            else prior.get("last_healthy_run_at")
        ),
        **fields,
    }
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(STATE_PATH), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, sort_keys=False)
            fh.write("\n")
        os.replace(tmp, STATE_PATH)  # atomic: readers never see a half-written record
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


if __name__ == "__main__":
    import sys

    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--lookback-years", type=int, default=10)
    parser.add_argument("--only")
    parser.add_argument(
        "--reconcile",
        action="store_true",
        help="delete rows for strategies this run produced nothing for (destructive)",
    )
    args = parser.parse_args()
    result = run(args.lookback_years, args.dry_run, args.only, args.reconcile)
    # Non-zero only when nothing was written at all. Individual strategy failures are
    # reported in the state file and surfaced by the heartbeat; failing the cron nightly
    # on a known-broken strategy would make the exit code noise instead of signal.
    sys.exit(0 if result["outcome"] != "no_trades_produced" else 1)
