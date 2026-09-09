"""Engine Validation Pass 2 — trade-level REPLAY harness (read-only).

`fact_trade_outcomes` stores no prices (no entry_price, exit_price or stop_loss;
`atr_sl_multiplier` / `atr_tp_multiplier` are 100% NULL — verified). Every pass-2
question that needs a *measured* stop distance, a *measured* slippage, or an
intrabar level reconstruction therefore requires re-running the engines.

This script replays the EXACT dispatch of `src/outcomes/persist_all.py` (same
catalog, same preload, same engines, same walk-forward OOS labelling) and keeps
the price columns that persist_all discards. It writes ONE parquet:

    audit/reports/engine_validation_2/replay_trades.parquet

No production table, artifact or config is written.

Usage:
    python src/audit/engine_validation2_replay.py [--lookback-years 10]
"""

from __future__ import annotations

import argparse
import copy
import logging
import sys
import warnings
from datetime import timezone
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from src.common.db import get_psycopg2_connection  # noqa: E402
from src.layer0.core_engine.backtest_engine import BacktestConfig, BacktestEngine  # noqa: E402
from src.layer0.qualify_strategies import preload_historical_data  # noqa: E402
from src.layer0.strategies.position_engine import PositionEngine  # noqa: E402
from src.layer0.strategies.v2_harness import assert_no_lookahead_v2  # noqa: E402
from src.registry.catalog import all_strategies, instantiate  # noqa: E402
from src.validation import walk_forward as WF  # noqa: E402

warnings.filterwarnings("ignore")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ev2.replay")

OUT = _REPO / "audit" / "reports" / "engine_validation_2"
OUT.mkdir(parents=True, exist_ok=True)


def _asset_symbol_map(conn):
    cur = conn.cursor()
    cur.execute(
        "SELECT symbol, asset_id FROM dim_asset WHERE is_active = true ORDER BY asset_id"
    )
    return {sym: aid for sym, aid in cur.fetchall()}


def _assign_oos(df: pd.DataFrame) -> pd.DataFrame:
    """Replicate persist_all._assign_oos_columns exactly (per-granularity folds)."""
    df = df.copy()
    df["is_oos"] = False
    df["fold_id"] = pd.array([pd.NA] * len(df), dtype="Int64")
    for gran, sub in df.groupby("granularity"):
        smin, smax = WF.series_bounds(sub["entry_time"])
        folds = WF.default_folds(smin, smax)
        is_oos, fold_id = WF.assign_oos(sub["entry_time"], folds)
        df.loc[sub.index, "is_oos"] = is_oos.to_numpy()
        df.loc[sub.index, "fold_id"] = fold_id
    return df


def run(lookback_years: int = 10) -> pd.DataFrame:
    conn = get_psycopg2_connection()
    asset_map = _asset_symbol_map(conn)
    symbols = list(asset_map.keys())
    strats = all_strategies()
    log.info("catalog: %d strategies, %d symbols", len(strats), len(symbols))

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
    granularities.update({"H1", "H4", "D1"})

    log.info("preloading %s x %s (%dy)", symbols, sorted(granularities), lookback_years)
    data = preload_historical_data(
        asset_symbols=symbols,
        asset_symbol_map=asset_map,
        granularities=list(granularities),
        use_db=True,
        conn=conn,
        lookback_years=lookback_years,
    )

    v1_engine = BacktestEngine(BacktestConfig())
    v2_engine = PositionEngine()
    rows: list[dict] = []
    failures: list[dict] = []

    for rec in strats:
        try:
            obj = instantiate(rec)
        except Exception as e:  # noqa: BLE001
            failures.append({"key": rec.strategy_key, "stage": "instantiate", "err": str(e)})
            continue

        if rec.engine == "backtest_engine_v1":
            gran = rec.primary_granularity or getattr(obj.config, "primary_granularity", "H1")
            for symbol in symbols:
                if symbol not in data or gran not in data[symbol]:
                    continue
                run_strat = copy.deepcopy(obj)
                res = v1_engine.run_backtest(
                    run_strat,
                    data[symbol][gran],
                    symbol,
                    gran,
                    run_strat.get_required_warmup_bars(),
                )
                for t in res.trades:
                    if t.exit_time is None:
                        continue
                    ts = t.entry_time
                    if getattr(ts, "tzinfo", None) is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    xt = t.exit_time
                    if getattr(xt, "tzinfo", None) is None:
                        xt = xt.replace(tzinfo=timezone.utc)
                    rows.append(
                        {
                            "engine": "backtest_engine_v1",
                            "strategy_id": rec.strategy_id,
                            "strategy_key": rec.strategy_key,
                            "symbol": symbol,
                            "granularity": gran,
                            "direction": int(t.direction),
                            "entry_time": ts,
                            "exit_time": xt,
                            "entry_price": float(t.entry_price),
                            "exit_price": float(t.exit_price),
                            "initial_stop_price": float(t.stop_loss),
                            "final_stop_price": float(t.stop_loss),
                            "take_profit_price": float(t.take_profit)
                            if t.take_profit is not None
                            else np.nan,
                            "exit_reason": str(t.exit_reason),
                            "r_multiple": float(t.r_multiple)
                            if t.r_multiple is not None
                            else np.nan,
                            "bars_held": int(t.bars_held or 0),
                            "gapped": np.nan,
                        }
                    )

        elif rec.engine == "position_engine_v2":
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
                except Exception as e:  # noqa: BLE001
                    failures.append(
                        {"key": rec.strategy_key, "stage": f"orders/{symbol}", "err": str(e)}
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
                for _, t in res.trades.iterrows():
                    if pd.isna(t["exit_time"]):
                        continue
                    ts = t["entry_time"]
                    if getattr(ts, "tzinfo", None) is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    xt = t["exit_time"]
                    if getattr(xt, "tzinfo", None) is None:
                        xt = xt.replace(tzinfo=timezone.utc)
                    rows.append(
                        {
                            "engine": "position_engine_v2",
                            "strategy_id": rec.strategy_id,
                            "strategy_key": rec.strategy_key,
                            "symbol": symbol,
                            "granularity": gran,
                            "direction": int(t["direction"]),
                            "entry_time": ts,
                            "exit_time": xt,
                            "entry_price": float(t["entry_price"]),
                            "exit_price": float(t["exit_price"]),
                            "initial_stop_price": float(t["initial_stop_price"]),
                            "final_stop_price": float(t["final_stop_price"]),
                            "take_profit_price": np.nan,
                            "exit_reason": str(t["exit_reason"]),
                            "r_multiple": float(t["r_multiple"]),
                            "bars_held": int(t["bars_held"]),
                            "gapped": bool(t["gapped"]),
                        }
                    )
        log.info("  %-40s -> %d rows cumulative", rec.strategy_key, len(rows))

    df = pd.DataFrame(rows)
    log.info("replayed %d trades; %d strategy/symbol failures", len(df), len(failures))
    df = _assign_oos(df)
    df.to_parquet(OUT / "replay_trades.parquet", index=False)
    pd.DataFrame(failures).to_csv(OUT / "replay_failures.csv", index=False)
    log.info("wrote %s", OUT / "replay_trades.parquet")
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lookback-years", type=int, default=10)
    a = ap.parse_args()
    run(a.lookback_years)
