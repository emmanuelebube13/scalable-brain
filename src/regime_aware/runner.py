"""A/B runner: the same strategy, with and without sight of the regime.

Both arms share everything that could otherwise explain a difference — the same price frames, the
same backtest engine and cost model, the same walk-forward folds, and the production gate
thresholds imported from ``src.system1.vetting.gates`` rather than re-declared here. The only
difference between the arms is whether the strategy's parameter blocks vary by regime.

Output goes to ``results/regime_aware/``. Nothing is written to the database — the connection is
opened read-only (see :mod:`src.regime_aware.context`).

Usage::

    source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate
    cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain
    python -m src.regime_aware.runner                 # Trend_Donchian_VCP
    python -m src.regime_aware.runner --lookback-years 10
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from src.layer0.backtest_engine import BacktestConfig, BacktestEngine
from src.layer0.qualify_strategies import preload_historical_data
from src.regime_aware.context import (
    attach_regime,
    build_trend_labels,
    load_regime_labels,
    readonly_connection,
    regime_coverage,
)
import importlib
STRATEGIES_LIST = [
    ("donchian_vcp", "Trend_Donchian_VCP"),
    ("donchian_h1", "Trend_Donchian_H1"),
    ("donchian_h4", "Trend_Donchian_H4"),
    ("ema_adx_h1", "Trend_EMA_ADX_H1"),
    ("ema_adx_h4", "Trend_EMA_ADX_H4"),
    ("ema_adx_multitf", "Trend_EMA_ADX_MultiTF"),
    ("bollinger_h1", "Range_Bollinger_H1"),
    ("bollinger_h4", "Range_Bollinger_H4"),
    ("bollinger_aggressive", "Range_Bollinger_Aggressive"),
]
from src.system1.attribution import metrics as MET
from src.system1.gatekeeper.thresholds import oos_uplift_test
from src.system1.validation import walk_forward as WF
from src.system1.vetting import gates as G

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
)
logger = logging.getLogger("regime_aware.runner")

_REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = _REPO_ROOT / "results" / "regime_aware"

#: Cells thinner than this are reported but flagged low-confidence, matching the production
#: attribution guard (``bayesian_shrinkage(min_n=20)``).
MIN_TRADES = 20


def run_arm(
    strategy,
    data: Mapping[str, Mapping[str, pd.DataFrame]],
    labels: Mapping[int, pd.DataFrame],
    asset_map: Mapping[str, int],
    granularity: str,
) -> pd.DataFrame:
    """Backtest one arm across every pair; return its trades with entry regime attached."""
    engine = BacktestEngine(BacktestConfig())
    rows: List[dict] = []
    for symbol, asset_id in asset_map.items():
        frame = data.get(symbol, {}).get(granularity)
        if frame is None or frame.empty:
            continue
        framed = attach_regime(frame, labels.get(asset_id))
        result = engine.run_backtest(
            strategy,
            framed,
            symbol,
            granularity,
            warmup_bars=strategy.get_required_warmup_bars(),
        )
        regime_at = framed["regime"]
        for t in result.trades:
            if t.exit_time is None or t.r_multiple is None:
                continue
            entry = pd.Timestamp(t.entry_time)
            if entry.tzinfo is None:
                entry = entry.tz_localize("UTC")
            rows.append(
                {
                    "entry_time": entry,
                    "symbol": symbol,
                    "asset_id": asset_id,
                    "regime": str(regime_at.get(t.entry_time, "UNKNOWN")),
                    "granularity": granularity,
                    "is_winner": 1 if (t.pnl or 0.0) > 0 else 0,
                    "r_multiple": float(t.r_multiple),
                    "exit_reason": str(t.exit_reason),
                }
            )
    trades = pd.DataFrame(rows)
    if trades.empty:
        return trades
    return label_oos(trades.sort_values("entry_time").reset_index(drop=True))


def label_oos(trades: pd.DataFrame) -> pd.DataFrame:
    """Walk-forward OOS labels using the production fold design, anchored per granularity."""
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


def _folds_for(trades: pd.DataFrame) -> Dict[int, WF.Fold]:
    smin, smax = WF.series_bounds(trades["entry_time"])
    return {f.fold_id: f for f in WF.default_folds(smin, smax)}


def bootstrap_ci(
    r: "np.ndarray", statistic, n_boot: int = 2000, alpha: float = 0.05, seed: int = 42
) -> Tuple[float, float]:
    """Percentile bootstrap interval for a per-trade statistic.

    A point estimate of profit factor says nothing about how much of it is sampling noise. With
    100-odd trades the interval is wide enough to change decisions, which is exactly why it is
    reported: a cell whose PF interval straddles 1.0 has not demonstrated an edge, however
    attractive its point estimate looks.
    """
    if len(r) < 2:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(r), size=(n_boot, len(r)))
    stats = np.array([statistic(r[row]) for row in idx], dtype="float64")
    stats = stats[np.isfinite(stats)]
    if stats.size == 0:
        return (float("nan"), float("nan"))
    lo, hi = np.percentile(stats, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return (round(float(lo), 4), round(float(hi), 4))


def compare_arms(a: pd.DataFrame, b: pd.DataFrame) -> dict:
    """Permutation test on per-trade r-multiples between two arms.

    Reuses the gatekeeper's ``oos_uplift_test`` rather than a second implementation, so an
    "improvement" here means the same thing it means at promotion time. The null is that the two
    arms' trades are draws from one distribution — i.e. the intervention did nothing.
    """
    if a.empty or b.empty:
        return {"mean_uplift_r": 0.0, "p_value": 1.0, "significant": False}
    uplift, p, sig = oos_uplift_test(
        b["r_multiple"].to_numpy(dtype="float64"),
        a["r_multiple"].to_numpy(dtype="float64"),
    )
    return {
        "mean_uplift_r": round(float(uplift), 4),
        "p_value": round(float(p), 4),
        "significant": bool(sig),
    }


def score_cell(oos: pd.DataFrame, folds: Mapping[int, WF.Fold], label: str) -> dict:
    """Gate metrics on the OOS subset, computed exactly as production attribution does."""
    r = oos["r_multiple"].to_numpy(dtype="float64")
    n = len(oos)
    fids = sorted({int(f) for f in oos["fold_id"].dropna().unique()})
    cell_folds = [folds[f] for f in fids if f in folds]
    oos_months = round(WF.oos_month_span(cell_folds), 2)
    oos_years = oos_months / 12.0
    trades_per_year = (n / oos_years) if oos_years > 0 else 0.0
    cell = {
        "label": label,
        "trade_count": n,
        "win_rate": MET.win_rate(oos["is_winner"].to_numpy()),
        "profit_factor": MET.profit_factor(r),
        "sharpe": MET.annualized_sharpe(r, trades_per_year),
        "expectancy": MET.expectancy(r),
        "max_drawdown": MET.max_drawdown(r),
        "recovery_factor": MET.recovery_factor(r),
        "avg_r": MET.avg_r(r),
        "oos_months": oos_months,
        "low_confidence": n < MIN_TRADES,
    }
    pf_lo, pf_hi = bootstrap_ci(r, MET.profit_factor)
    cell["pf_ci95"] = [pf_lo, pf_hi]
    # The honest edge test: a PF interval containing 1.0 has not shown the strategy makes money.
    cell["pf_ci_excludes_1"] = bool(pf_lo == pf_lo and pf_lo > 1.0)
    passed, failures = G.evaluate_gates(cell)
    cell["passed"] = passed
    cell["failed_gates"] = failures
    return cell


def score_arm(trades: pd.DataFrame, arm: str) -> Dict[str, List[dict]]:
    """Overall, per-regime and per-pair cells for one arm — all on OOS trades only."""
    if trades.empty:
        return {"overall": [], "by_regime": [], "by_pair": []}
    folds = _folds_for(trades)
    oos = trades[trades["is_oos"]]
    out = {
        "overall": [score_cell(oos, folds, f"{arm} · ALL")],
        "by_regime": [
            score_cell(g, folds, f"{arm} · {regime}")
            for regime, g in oos.groupby("regime")
            if len(g)
        ],
        "by_pair": [
            score_cell(g, folds, f"{arm} · {symbol}")
            for symbol, g in oos.groupby("symbol")
            if len(g)
        ],
    }
    return out


def _fmt(cells: Sequence[dict]) -> str:
    lines = [
        f"{'cell':<34} {'n':>6} {'PF':>6} {'PF 95% CI':>16} {'Sharpe':>7} "
        f"{'maxDD%':>7}  verdict"
    ]
    for c in cells:
        verdict = "PASS" if c["passed"] else "; ".join(c["failed_gates"][:2])
        lo, hi = c.get("pf_ci95", [float("nan")] * 2)
        ci = f"[{lo:.2f}, {hi:.2f}]" if lo == lo else "[--]"
        lines.append(
            f"{c['label']:<34} {c['trade_count']:>6} {c['profit_factor']:>6.2f} "
            f"{ci:>16} {c['sharpe']:>7.2f} "
            f"{c['max_drawdown'] * 100:>7.1f}  {verdict}"
        )
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lookback-years", type=int, default=10)
    args = ap.parse_args(argv)

    conn = readonly_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT symbol, asset_id FROM dim_asset WHERE is_active = true ORDER BY asset_id"
    )
    asset_map = {s: a for s, a in cur.fetchall()}
    
    # Pre-load data for all granularities we might need
    needed_gran = set()
    for mod_name, strat_name in STRATEGIES_LIST:
        mod = importlib.import_module(f"src.regime_aware.strategies.{mod_name}")
        needed_gran.add(mod.build_baseline().config.primary_granularity)
    
    logger.info(f"Loading data for granularities: {needed_gran}")
    data = preload_historical_data(
        asset_symbols=list(asset_map),
        asset_symbol_map=asset_map,
        granularities=list(needed_gran.union({"D1"})),
        use_db=True,
        conn=conn,
        lookback_years=args.lookback_years,
    )
    
    hmm_labels_by_gran = {g: load_regime_labels(conn, g) for g in needed_gran}
    conn.close()
    
    trend_labels = {
        asset_id: build_trend_labels(data[symbol]["D1"])
        for symbol, asset_id in asset_map.items()
        if data.get(symbol, {}).get("D1") is not None
    }
    
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    for mod_name, strat_name in STRATEGIES_LIST:
        print(f"\n{'='*80}\nRUNNING STRATEGY: {strat_name}\n{'='*80}")
        mod = importlib.import_module(f"src.regime_aware.strategies.{mod_name}")
        
        blind = mod.build_baseline()
        granularity = blind.config.primary_granularity
        hmm_labels = hmm_labels_by_gran[granularity]
        
        coverage = {}
        for name, labels in (("hmm", hmm_labels), ("d1_trend", trend_labels)):
            coverage[name] = {}
            for symbol, asset_id in asset_map.items():
                frame = data.get(symbol, {}).get(granularity)
                if frame is not None and not frame.empty:
                    coverage[name][symbol] = regime_coverage(
                        attach_regime(frame, labels.get(asset_id))
                    )
        
        arm_specs = (
            ("blind", blind, hmm_labels),
            ("hmm_aware", mod.build_regime_aware(), hmm_labels),
            ("trend_aware", mod.build_trend_aware(), trend_labels),
        )
        arms = {}
        for arm_name, strategy, labels in arm_specs:
            trades = run_arm(strategy, data, labels, asset_map, granularity)
            logger.info("%s arm: %d trades", arm_name, len(trades))
            arms[arm_name] = {"trades": trades, "cells": score_arm(trades, arm_name)}
        
        for name, cov in coverage.items():
            print(f"\n=== CONTEXT COVERAGE — {name} (share of bars per pair) ===")
            for symbol, c in cov.items():
                print(f"  {symbol:<9} {c}")
        
        print("\n=== INTERVENTION vs BASELINE (permutation test on per-trade R) ===")
        comparisons = {}
        for arm in ("hmm_aware", "trend_aware"):
            c = compare_arms(arms["blind"]["trades"], arms[arm]["trades"])
            comparisons[arm] = c
            verdict = "SIGNIFICANT" if c["significant"] else "not significant"
            print(
                f"  {arm:<14} mean uplift {c['mean_uplift_r']:+.4f} R   "
                f"p={c['p_value']:.4f}   {verdict}"
            )

        for section in ("overall", "by_regime", "by_pair"):
            print(f"\n=== {section.upper().replace('_', ' ')} ===")
            cells = [c for a in arms.values() for c in a["cells"][section]]
            print(_fmt(sorted(cells, key=lambda c: c["label"])))
        
        report = {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "strategy": strat_name,
            "granularity": granularity,
            "lookback_years": args.lookback_years,
            "gates": G.GATES,
            "context_coverage_pct": coverage,
            "params": {name: s.describe() for name, s, _ in arm_specs},
            "comparisons_vs_blind": comparisons,
            "arms": {
                name: {
                    "n_trades": int(len(a["trades"])),
                    "n_oos": int(a["trades"]["is_oos"].sum()) if len(a["trades"]) else 0,
                    "cells": a["cells"],
                }
                for name, a in arms.items()
            },
        }
        path = RESULTS_DIR / f"{mod_name}_ab_{stamp}.json"
        path.write_text(json.dumps(report, indent=2, default=str))
        print(f"\nreport → {path}")
    
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
