import argparse
import logging
import pandas as pd
from datetime import timezone
from psycopg2.extras import execute_values
from src.common.db import get_psycopg2_connection
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
    "fold_id",
    "leg_index",
    "is_terminal_leg",
]

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
    df["fold_id"] = pd.array([pd.NA] * len(df), dtype="Int64")
    for gran, sub in df.groupby("granularity"):
        smin, smax = WF.series_bounds(sub["timestamp"])
        folds = WF.default_folds(smin, smax)
        is_oos, fold_id = WF.assign_oos(sub["timestamp"], folds)
        df.loc[sub.index, "is_oos"] = is_oos.to_numpy()
        df.loc[sub.index, "fold_id"] = fold_id
    out = []
    for rec in df.itertuples(index=False):
        d = rec._asdict()
        fid = d["fold_id"]
        # _TRADE_COLUMNS indices: is_oos=12, fold_id=13
        row = list(d[c] for c in _TRADE_COLUMNS)
        row[12] = bool(d["is_oos"])
        row[13] = None if pd.isna(fid) else int(fid)
        out.append(tuple(row))
    return out


def run(lookback_years: int = 10, dry_run: bool = False, only_strat: str = None):
    conn = get_psycopg2_connection()
    asset_map = _asset_symbol_map(conn)
    symbols = list(asset_map.keys())

    strats = all_strategies()
    if only_strat:
        strats = [s for s in strats if s.strategy_key == only_strat]

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

    for record in strats:
        try:
            obj = instantiate(record)
        except Exception as e:
            logger.error("Failed to instantiate %s: %s", record.strategy_key, e)
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
                for t in res.trades:
                    if t.exit_time is None:
                        continue
                    ts = t.entry_time
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
                            None,
                            None,
                            "long" if t.direction > 0 else "short",
                            str(t.exit_reason) if t.exit_reason else None,
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
                            None,
                            None,
                            "long" if t["direction"] > 0 else "short",
                            str(t["exit_reason"]),
                            False,
                            None,
                            0,
                            True,
                        )
                    )

    logger.info("Assigning OOS columns for %d trades...", len(collected))
    labelled = _assign_oos_columns(collected)
    if not dry_run and labelled:
        logger.info("Persisting to database...")
        cur = conn.cursor()
        execute_values(cur, INSERT_SQL, labelled, page_size=2000)
        conn.commit()
    conn.close()

    print(f"Total trades collected: {len(labelled)}")

    # Optional per-strategy report logic can be added here or just rely on log


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--lookback-years", type=int, default=10)
    parser.add_argument("--only")
    args = parser.parse_args()
    run(args.lookback_years, args.dry_run, args.only)
