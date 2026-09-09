"""B3 — quantify v1's contemporaneous-fill optimism (read-only).

`backtest_engine.py:229` fills at `df["Close"].iloc[i]` — the close of the bar
whose data produced the signal. Live execution can act no earlier than bar
`i+1`'s open. This script re-runs the v1 bank with the fill moved to
`Open[i+1]` (adverse slippage unchanged) and reports the delta in mean R per
granularity and per strategy.

The production engine is NOT modified: `_NextOpenFillEngine` subclasses
`BacktestEngine` and overrides only the entry leg of `_simulate_trades`.
"""

from __future__ import annotations

import copy
import logging
import sys
import warnings
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from src.common.db import get_psycopg2_connection  # noqa: E402
from src.layer0.core_engine.backtest_engine import BacktestConfig, BacktestEngine  # noqa: E402
from src.layer0.core_engine.strategy_base import Trade  # noqa: E402
from src.layer0.data_access.indicators import get_pip_value  # noqa: E402
from src.layer0.qualify_strategies import preload_historical_data  # noqa: E402
from src.registry.catalog import all_strategies, instantiate  # noqa: E402
from src.validation import walk_forward as WF  # noqa: E402

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("ev2.b3")
OUT = _REPO / "audit" / "reports" / "engine_validation_2"

SKIP = {"Range_Stochastic_Divergence", "Trend_EMA_ADX_MultiTF"}


class _NextOpenFillEngine(BacktestEngine):
    """Identical to BacktestEngine except the entry fills at Open[i+1]."""

    def _simulate_trades(self, strategy, df, signals, asset, granularity) -> List[Trade]:
        trades: List[Trade] = []
        current: Optional[Trade] = None
        for i in range(len(df)):
            timestamp = df.index[i]
            signal = signals.iloc[i]

            if current is not None:
                closed = self._check_exit(current, df, i, timestamp, signal, asset, strategy)
                if closed:
                    trades.append(closed)
                    current = None

            if current is None and signal != 0 and i + 1 < len(df):
                if strategy.config.volatility_filter:
                    if not strategy.check_volatility_filter(df.iloc[max(0, i - 100): i + 1]):
                        continue
                # THE ONLY CHANGE: fill at the NEXT bar's open, not this bar's close.
                entry_price = df["Open"].iloc[i + 1]
                entry_time = df.index[i + 1]
                slip = self.config.slippage_pips * get_pip_value(asset)
                entry_price += slip if signal == 1 else -slip

                window = df.iloc[max(0, i - 100): i + 1]
                current = Trade(
                    entry_time=entry_time,
                    entry_price=entry_price,
                    direction=signal,
                    stop_loss=strategy.calculate_stop_loss(window, signal, entry_price, asset),
                    take_profit=strategy.calculate_take_profit(window, signal, entry_price, asset),
                    asset=asset, strategy=strategy.config.name,
                    granularity=granularity, size=1.0,
                )

        if current is not None and current.exit_time is None:
            last = len(df) - 1
            current.exit_time = df.index[last]
            current.exit_price = df["Close"].iloc[last]
            current.exit_reason = "end_of_data"
            diff = current.exit_price - current.entry_price
            if current.direction == -1:
                diff = -diff
            risk = abs(current.entry_price - current.stop_loss)
            if risk > 0:
                current.r_multiple = diff / risk
            trades.append(current)
        return trades


def main() -> None:
    conn = get_psycopg2_connection()
    cur = conn.cursor()
    cur.execute("SELECT symbol, asset_id FROM dim_asset WHERE is_active=true ORDER BY asset_id")
    amap = {s: a for s, a in cur.fetchall()}
    symbols = list(amap)
    recs = [r for r in all_strategies()
            if r.engine == "backtest_engine_v1" and r.strategy_key not in SKIP]
    data = preload_historical_data(asset_symbols=symbols, asset_symbol_map=amap,
                                   granularities=["H1", "H4", "D1"], use_db=True,
                                   conn=conn, lookback_years=10)

    engines = {"as_is_close_i": BacktestEngine(BacktestConfig()),
               "next_open_i1": _NextOpenFillEngine(BacktestConfig())}
    rows = []
    for rec in recs:
        try:
            obj = instantiate(rec)
        except Exception as e:  # noqa: BLE001
            log.warning("skip %s: %s", rec.strategy_key, e)
            continue
        gran = rec.primary_granularity or getattr(obj.config, "primary_granularity", "H1")
        for sym in symbols:
            if sym not in data or gran not in data[sym]:
                continue
            df = data[sym][gran]
            warm = obj.get_required_warmup_bars()
            for name, eng in engines.items():
                res = eng.run_backtest(copy.deepcopy(obj), df, sym, gran, warm)
                for t in res.trades:
                    if t.exit_time is None or t.r_multiple is None:
                        continue
                    rows.append({"fill_rule": name, "strategy_key": rec.strategy_key,
                                 "symbol": sym, "granularity": gran,
                                 "entry_time": t.entry_time, "r_multiple": float(t.r_multiple),
                                 "exit_reason": str(t.exit_reason)})
        log.info("  %s done", rec.strategy_key)

    d = pd.DataFrame(rows)
    d["entry_time"] = pd.to_datetime(d["entry_time"], utc=True)
    keep = []
    for (rule, gran), sub in d.groupby(["fill_rule", "granularity"]):
        smin, smax = WF.series_bounds(sub["entry_time"])
        is_oos, _ = WF.assign_oos(sub["entry_time"], WF.default_folds(smin, smax))
        s = sub.copy()
        s["is_oos"] = np.asarray(is_oos)
        keep.append(s)
    d = pd.concat(keep, ignore_index=True)
    oos = d[d.is_oos]

    by_gran = (oos.pivot_table(index="granularity", columns="fill_rule",
                               values="r_multiple", aggfunc=["count", "mean"]))
    by_gran.columns = [f"{a}_{b}" for a, b in by_gran.columns]
    by_gran["delta_mean_R"] = by_gran["mean_next_open_i1"] - by_gran["mean_as_is_close_i"]
    by_gran = by_gran.reset_index()

    by_strat = (oos.pivot_table(index=["strategy_key", "granularity"], columns="fill_rule",
                                values="r_multiple", aggfunc=["count", "mean"]))
    by_strat.columns = [f"{a}_{b}" for a, b in by_strat.columns]
    by_strat["delta_mean_R"] = by_strat["mean_next_open_i1"] - by_strat["mean_as_is_close_i"]
    by_strat = by_strat.reset_index()

    by_gran.to_csv(OUT / "b3_fill_timing_by_granularity.csv", index=False)
    by_strat.to_csv(OUT / "b3_fill_timing_by_strategy.csv", index=False)
    log.info("\n%s", by_gran.round(5).to_string(index=False))
    log.info("\n%s", by_strat.round(5).to_string(index=False))


if __name__ == "__main__":
    main()
