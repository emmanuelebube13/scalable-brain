"""Experiment: route each strategy to its declared granularity, and give the MultiTF
variant a REAL (causal) multi-timeframe filter — then re-run attribution + the vetting gates.

Why this exists
---------------
Two defects were found on 2026-08-15 while auditing the legacy ten:

1. ``persist_trade_outcomes`` backtests every strategy on BOTH H1 and H4 and never reads
   ``config.primary_granularity``. So ``Range_Bollinger_H1`` and ``Range_Bollinger_H4`` —
   identical parameters, differing only in that ignored field — produce byte-identical
   trades (all 13,934 rows match under INTERSECT ALL). Same for ``Trend_EMA_ADX_H4`` vs
   ``Trend_EMA_ADX_MultiTF`` (6,306 rows).
2. ``config.use_multi_timeframe`` is set but never read in the legacy path. The engine is
   handed ONE dataframe, so the "multi-timeframe" variant has never done anything
   multi-timeframe.

This script fixes both *in an experiment*, not in production: it writes NOTHING to the
database. It reads prices, backtests, and prints the gate decision.

Do not use ``MultiTimeframeStrategy.get_macro_trend``
----------------------------------------------------
That helper reads ``df['EMA_50'].iloc[-1]`` — the last bar of the ENTIRE dataframe, not the
bar in force at trade time. Wiring MTF through it would leak the end of history into every
signal, which is the same look-ahead that disqualified ``Range_Stochastic_Divergence``
(FIX-S1-014). The macro filter here is built with ``merge_asof``-style forward-fill over
*closed* D1 bars plus a defensive ``shift(1)``, so a signal at bar t can only see D1 bars
that closed strictly before t.

Usage
-----
    source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate
    cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain

    # the fix alone: each strategy on its own declared granularity
    python task/2026-August-week2/mtf-experiment/run_mtf_experiment.py

    # plus a real causal D1 macro-trend filter on the MTF-declaring strategies
    python task/2026-August-week2/mtf-experiment/run_mtf_experiment.py --mtf

    # the current production behaviour, for a like-for-like baseline
    python task/2026-August-week2/mtf-experiment/run_mtf_experiment.py --baseline
"""

from __future__ import annotations

import argparse
import copy
import logging
import sys
import uuid
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

from src.common.db import get_engine, get_psycopg2_connection  # noqa: E402
from src.layer0.backtest_engine import BacktestConfig, BacktestEngine  # noqa: E402
from src.layer0.qualify_strategies import (  # noqa: E402
    get_all_strategies,
    preload_historical_data,
)
from src.attribution.attribute import (  # noqa: E402
    compute_attribution,
    tag_regime_at_entry,
)
from src.validation import walk_forward as WF  # noqa: E402
from src.vetting import gates as G  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s | %(message)s")
logger = logging.getLogger("mtf_experiment")

LOOKBACK_YEARS = 10
FRAMES = ["H1", "H4", "D1"]


# ---------------------------------------------------------------- causal macro filter


def build_macro_direction(d1: pd.DataFrame) -> pd.Series:
    """+1 / -1 / 0 macro trend per D1 bar, usable only from the NEXT bar onward.

    EMA(50) vs EMA(200) on daily closes. ``shift(1)`` is the causality guard: the value
    carried into intraday bar ``t`` is derived from D1 bars that closed strictly before the
    D1 bar containing ``t``. Bars before EMA-200 warmup yield 0 (no opinion), which the
    caller treats as "do not trade".
    """
    close = d1["Close"]
    ema_fast = close.ewm(span=50, adjust=False).mean()
    ema_slow = close.ewm(span=200, adjust=False).mean()
    direction = pd.Series(0, index=d1.index, dtype="int64")
    direction[ema_fast > ema_slow] = 1
    direction[ema_fast < ema_slow] = -1
    direction[: 200] = 0  # EMA-200 warmup: no opinion
    return direction.shift(1).fillna(0).astype("int64")


def attach_macro_filter(strat, macro: pd.Series):
    """Wrap ``strat.generate_signals`` so a signal survives only if it agrees with macro.

    ``reindex(..., method='ffill')`` carries the last *already-shifted* D1 value forward onto
    the intraday index — no future bar can be selected. Signals with macro 0 (warmup or flat)
    are dropped.
    """
    original = strat.generate_signals

    def filtered(df: pd.DataFrame, asset: str, granularity: str) -> pd.Series:
        signals = original(df, asset, granularity)
        aligned = macro.reindex(df.index, method="ffill").fillna(0)
        keep = np.sign(signals) == aligned
        return signals.where(keep, 0)

    strat.generate_signals = filtered  # type: ignore[method-assign]
    return strat


# ---------------------------------------------------------------- backtest sweep


def granularities_for(strat, baseline: bool) -> List[str]:
    """Which frames this strategy trades. Baseline = production's 'everything' behaviour."""
    if baseline:
        return ["H1", "H4"]
    declared = getattr(strat.config, "primary_granularity", None)
    return [declared] if declared in ("H1", "H4") else ["H1", "H4"]


def run_sweep(baseline: bool, use_mtf: bool) -> pd.DataFrame:
    conn = get_psycopg2_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT symbol, asset_id FROM dim_asset WHERE is_active = true ORDER BY asset_id"
    )
    asset_map = {s: a for s, a in cur.fetchall()}
    cur.execute("SELECT strategy_name, strategy_id FROM dim_strategy_registry")
    name_to_id = {n: i for n, i in cur.fetchall()}
    symbols = list(asset_map)

    print(f"Loading {LOOKBACK_YEARS}y of {FRAMES} for {len(symbols)} pairs…")
    data = preload_historical_data(
        asset_symbols=symbols,
        asset_symbol_map=asset_map,
        granularities=FRAMES,
        use_db=True,
        conn=conn,
        lookback_years=LOOKBACK_YEARS,
    )
    conn.close()

    macro_by_symbol: Dict[str, pd.Series] = {}
    if use_mtf:
        for sym in symbols:
            d1 = data.get(sym, {}).get("D1")
            if d1 is not None and len(d1):
                macro_by_symbol[sym] = build_macro_direction(d1)
        print(f"Built causal D1 macro filter for {len(macro_by_symbol)} pairs")

    engine = BacktestEngine(BacktestConfig())
    rows: List[dict] = []
    for strat in get_all_strategies():
        name = strat.config.name
        sid = name_to_id.get(name)
        if sid is None:
            print(f"  SKIP {name}: not in dim_strategy_registry")
            continue
        wants_mtf = bool(getattr(strat.config, "use_multi_timeframe", False))
        frames = granularities_for(strat, baseline)
        for symbol in symbols:
            for gran in frames:
                df = data.get(symbol, {}).get(gran)
                if df is None or df.empty:
                    continue
                run_strat = copy.deepcopy(strat)
                if use_mtf and wants_mtf and symbol in macro_by_symbol:
                    run_strat = attach_macro_filter(run_strat, macro_by_symbol[symbol])
                result = engine.run_backtest(
                    run_strat,
                    df,
                    symbol,
                    gran,
                    warmup_bars=run_strat.get_required_warmup_bars(),
                )
                for t in result.trades:
                    if t.exit_time is None:
                        continue
                    ts = t.entry_time
                    if getattr(ts, "tzinfo", None) is None:
                        ts = ts.tz_localize("UTC")
                    rows.append(
                        {
                            "entry_time": ts,
                            "asset_id": asset_map[symbol],
                            "strategy_id": sid,
                            "granularity": gran,
                            "is_winner": 1 if (t.pnl or 0.0) > 0 else 0,
                            "r_multiple": t.r_multiple,
                        }
                    )
        traded = [r for r in rows if r["strategy_id"] == sid]
        print(f"  {name:<28} {'+'.join(frames):<7} {len(traded):>7} trades")

    trades = pd.DataFrame(rows)
    if trades.empty:
        return trades
    trades["entry_time"] = pd.to_datetime(trades["entry_time"], utc=True)
    return trades.dropna(subset=["r_multiple"])


def label_oos(trades: pd.DataFrame) -> pd.DataFrame:
    """Walk-forward is_oos / fold_id, anchored per granularity — same rule as production."""
    trades = trades.copy()
    trades["is_oos"] = False
    trades["fold_id"] = pd.array([pd.NA] * len(trades), dtype="Int64")
    for gran, sub in trades.groupby("granularity"):
        smin, smax = WF.series_bounds(sub["entry_time"])
        folds = WF.default_folds(smin, smax)
        if not folds:
            continue
        is_oos, fold_id = WF.assign_oos(sub["entry_time"], folds)
        trades.loc[sub.index, "is_oos"] = is_oos.to_numpy()
        trades.loc[sub.index, "fold_id"] = fold_id
    return trades


# ---------------------------------------------------------------- report


def report(cells: pd.DataFrame, id_to_name: Dict[int, str]) -> None:
    passed = []
    print(
        f"\n{'strategy':<28} {'regime':<14} {'gr':<3} {'n':>6} {'PF':>6} "
        f"{'Sharpe':>7} {'win%':>6} {'maxDD%':>7} {'OOSmo':>6}  verdict"
    )
    print("-" * 108)
    for _, c in cells.sort_values(
        ["profit_factor"], ascending=False
    ).iterrows():
        cell = c.to_dict()
        ok, failures = G.evaluate_gates(cell)
        if ok:
            passed.append(cell)
        verdict = "PASS" if ok else "; ".join(failures[:2])
        print(
            f"{id_to_name.get(int(c['strategy_id']), c['strategy_id']):<28} "
            f"{c['regime']:<14} {c['granularity']:<3} {int(c['trade_count']):>6} "
            f"{c['profit_factor']:>6.2f} {c['sharpe']:>7.2f} {c['win_rate']*100:>6.1f} "
            f"{c['max_drawdown']*100:>7.1f} {c['oos_months']:>6.1f}  {verdict}"
        )
    print("-" * 108)
    print(f"cells evaluated: {len(cells)}   QUALIFYING: {len(passed)}")
    if passed:
        print("\n*** QUALIFIERS ***")
        for c in passed:
            print(
                f"  {id_to_name.get(int(c['strategy_id']))} @ {c['granularity']} "
                f"in {c['regime']}: PF {c['profit_factor']:.2f}, Sharpe {c['sharpe']:.2f}"
            )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--baseline",
        action="store_true",
        help="reproduce production: every strategy on both H1 and H4 (keeps the duplicates)",
    )
    ap.add_argument(
        "--mtf",
        action="store_true",
        help="apply the causal D1 macro-trend filter to strategies declaring use_multi_timeframe",
    )
    args = ap.parse_args()

    mode = (
        "BASELINE (production behaviour)"
        if args.baseline
        else "granularity-routed" + (" + causal D1 MTF filter" if args.mtf else "")
    )
    print(f"=== MTF/granularity experiment — {mode} ===")
    print("NOTHING is written to the database.\n")

    trades = run_sweep(args.baseline, args.mtf)
    if trades.empty:
        print("No trades produced — nothing to score.")
        return
    trades = label_oos(trades)
    print(
        f"\ntotal trades {len(trades):,}   OOS {int(trades['is_oos'].sum()):,}   "
        f"span {trades['entry_time'].min().date()} → {trades['entry_time'].max().date()}"
    )

    engine = get_engine()
    tagged = tag_regime_at_entry(trades, engine)
    cells = compute_attribution(tagged, run_id=str(uuid.uuid4()))
    cells = cells[cells["strategy_id"] != 10]  # integrity-disqualified, FIX-S1-014

    conn = get_psycopg2_connection()
    cur = conn.cursor()
    cur.execute("SELECT strategy_id, strategy_name FROM dim_strategy_registry")
    id_to_name = {i: n for i, n in cur.fetchall()}
    conn.close()

    report(cells, id_to_name)


if __name__ == "__main__":
    main()
