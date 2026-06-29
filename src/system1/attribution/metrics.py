"""MODEL-004/005 — pure financial metrics (no DB/network). See skill financial-metrics.md.

Per-trade P/L is expressed in R-multiples (``r_multiple`` from fact_trade_outcomes);
win/loss is the integer ``is_winner`` flag.

Capital model (see docs/proposedchanges/METRICS_REMEDIATION_PROPOSAL.md): R-multiples are
turned into a real equity curve by risking a fixed fraction of equity per trade
(``DEFAULT_RISK_FRACTION``), compounding. This makes drawdown a true bounded fraction in
[0, 1) and recovery a return%/drawdown% ratio that matches the vetting gate's units.

Sharpe is annualized by the *realized trade frequency* (trades per year), NOT by bar
frequency — a per-trade return series must be scaled by how often trades actually occur.
"""
from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

import numpy as np

# Fraction of equity risked per trade (a -1R trade => -f equity). Default 1%, aligned with
# the system's "Quarter-Kelly, 2% risk cap" execution philosophy. Configurable per run.
DEFAULT_RISK_FRACTION = 0.01

# Sanity bounds: any cell breaching these indicates a measurement bug, not a real strategy.
MAX_PLAUSIBLE_DRAWDOWN = 1.0   # a fraction of capital; cannot exceed 100%
MAX_PLAUSIBLE_SHARPE = 10.0    # |annualized Sharpe| above this is not physically attainable


def win_rate(is_winner: Sequence[int]) -> float:
    n = len(is_winner)
    return float(np.sum(is_winner) / n) if n else 0.0


def profit_factor(r_multiples: Sequence[float]) -> float:
    r = np.asarray(r_multiples, dtype="float64")
    gross_profit = float(r[r > 0].sum())
    gross_loss = float(abs(r[r < 0].sum()))
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def annualized_sharpe(r_multiples: Sequence[float], trades_per_year: float) -> float:
    """Annualized Sharpe of a per-trade return series.

    ``trades_per_year`` is the realized trade cadence (trade_count / years_spanned), so the
    per-trade Sharpe is scaled by sqrt(trades_per_year). Annualizing by bar frequency (the old
    bug) overstated Sharpe by ~sqrt(bars_per_year / trades_per_year).
    """
    r = np.asarray(r_multiples, dtype="float64")
    if len(r) < 2:
        return float("nan")
    std = np.std(r, ddof=1)
    if std < 1e-12:  # constant (or float-noise-constant) series => undefined risk-adjusted return
        return 0.0
    tpy = max(float(trades_per_year), 0.0)
    return float((np.mean(r) / std) * np.sqrt(tpy))


def expectancy(r_multiples: Sequence[float]) -> float:
    r = np.asarray(r_multiples, dtype="float64")
    return float(np.mean(r)) if len(r) else 0.0


def equity_curve(r_multiples: Sequence[float], risk_fraction: float = DEFAULT_RISK_FRACTION) -> np.ndarray:
    """Compounding fixed-fractional equity curve from R-multiples, starting at 1.0.

    equity_i = equity_{i-1} * (1 + risk_fraction * r_i). The curve includes the starting
    capital 1.0 as its first point, so a losing first trade is a drawdown from 1.0. A small
    positive floor keeps the curve strictly positive even for adversarial inputs, guaranteeing
    drawdown stays in [0, 1).
    """
    r = np.asarray(r_multiples, dtype="float64")
    if len(r) == 0:
        return np.asarray([1.0], dtype="float64")
    growth = np.maximum(1.0 + risk_fraction * r, 1e-9)
    return np.concatenate(([1.0], np.cumprod(growth)))


def max_drawdown(r_multiples: Sequence[float], risk_fraction: float = DEFAULT_RISK_FRACTION) -> float:
    """Max drawdown of the fixed-fractional equity curve, as a fraction of peak in [0, 1)."""
    r = np.asarray(r_multiples, dtype="float64")
    if len(r) == 0:
        return 0.0
    equity = equity_curve(r, risk_fraction)
    peak = np.maximum.accumulate(equity)  # strictly positive by construction
    dd = (peak - equity) / peak
    return float(np.max(dd))


def max_drawdown_absolute(r_multiples: Sequence[float]) -> float:
    """Max drawdown in absolute R (peak-to-trough of cumulative R), positive. Reporting only."""
    r = np.asarray(r_multiples, dtype="float64")
    if len(r) == 0:
        return 0.0
    equity = np.cumsum(r)
    peak = np.maximum.accumulate(equity)
    return float(np.max(peak - equity))


def recovery_factor(r_multiples: Sequence[float], risk_fraction: float = DEFAULT_RISK_FRACTION) -> float:
    """total_return% / max_drawdown% on the fixed-fractional equity curve (unit-consistent)."""
    r = np.asarray(r_multiples, dtype="float64")
    if len(r) == 0:
        return 0.0
    equity = equity_curve(r, risk_fraction)
    total_return = float(equity[-1] - 1.0)
    mdd = max_drawdown(r, risk_fraction)
    if mdd == 0:
        return float("inf") if total_return > 0 else 0.0
    return total_return / mdd


def avg_r(r_multiples: Sequence[float]) -> float:
    r = np.asarray(r_multiples, dtype="float64")
    wins = r[r > 0]
    losses = r[r < 0]
    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(abs(losses.mean())) if len(losses) else 0.0
    if avg_loss == 0:
        return float("inf") if avg_win > 0 else 0.0
    return avg_win / avg_loss


def validate_metrics(cell: Dict[str, float]) -> List[str]:
    """Return a list of sanity-bound violations for a computed metric cell (empty == OK).

    Guards against the class of bug this module was built to fix: a drawdown above 100% or a
    Sharpe above ~10 means the math is wrong, so callers should fail the run rather than ship it.
    """
    problems: List[str] = []
    mdd = cell.get("max_drawdown")
    if mdd is not None and np.isfinite(mdd) and (mdd < 0.0 or mdd > MAX_PLAUSIBLE_DRAWDOWN):
        problems.append(f"max_drawdown={mdd:.4f} outside [0, {MAX_PLAUSIBLE_DRAWDOWN}]")
    sh = cell.get("sharpe")
    if sh is not None and np.isfinite(sh) and abs(sh) > MAX_PLAUSIBLE_SHARPE:
        problems.append(f"|sharpe|={abs(sh):.2f} > {MAX_PLAUSIBLE_SHARPE}")
    return problems


def bayesian_shrinkage(
    cell_metric: float, global_metric: float, cell_n: int, min_n: int = 20
) -> Tuple[float, bool]:
    """Shrink a per-cell metric toward the global metric when sample size is small.

    Returns (value, low_confidence). For cell_n >= min_n: no shrinkage, high confidence.
    The shrunk value always lies between cell_metric and global_metric.
    """
    if cell_n >= min_n:
        return cell_metric, False
    # Guard non-finite metrics (e.g., inf profit factor) before blending.
    cm = cell_metric if np.isfinite(cell_metric) else global_metric
    gm = global_metric if np.isfinite(global_metric) else cm
    weight = cell_n / (cell_n + min_n)
    return float(weight * cm + (1 - weight) * gm), True
