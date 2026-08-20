"""MODEL-006 — pure threshold calibration + OOS uplift (no DB/network/model). Skill: financial-metrics.md."""
from __future__ import annotations

from typing import Optional, Sequence, Tuple

import numpy as np


def approval_rate(scores: Sequence[float], threshold: float) -> float:
    s = np.asarray(scores, dtype="float64")
    return float((s >= threshold).mean()) if len(s) else 0.0


def calibrate_threshold(
    scores: Sequence[float],
    returns: Sequence[float],
    min_turnover: float = 0.05,
    max_turnover: float = 0.60,
    grid: Optional[Sequence[float]] = None,
) -> Tuple[float, float]:
    """Pick the threshold maximizing mean approved return, keeping approval in the
    turnover band. Returns (threshold, approval_rate). Falls back to the median score
    if no grid point satisfies the band."""
    s = np.asarray(scores, dtype="float64")
    r = np.asarray(returns, dtype="float64")
    if len(s) == 0:
        return 0.5, 0.0
    grid = grid if grid is not None else np.linspace(0.05, 0.95, 19)
    best_thr, best_rate, best_score = None, 0.0, -np.inf
    for thr in grid:
        mask = s >= thr
        rate = float(mask.mean())
        if rate < min_turnover or rate > max_turnover:
            continue
        mean_ret = float(r[mask].mean()) if mask.any() else -np.inf
        if mean_ret > best_score:
            best_thr, best_rate, best_score = float(thr), rate, mean_ret
    if best_thr is None:  # band unsatisfiable → median score (keeps ~50% approval)
        best_thr = float(np.median(s))
        best_rate = approval_rate(s, best_thr)
    return best_thr, best_rate


def oos_uplift_test(
    approved_returns: Sequence[float],
    rejected_returns: Sequence[float],
    n_bootstrap: int = 10000,
    alpha: float = 0.05,
    seed: int = 42,
) -> Tuple[float, float, bool]:
    """Bootstrap test that approved per-trade return > rejected. Returns
    (mean_uplift, p_value, is_significant)."""
    a = np.asarray(approved_returns, dtype="float64")
    rj = np.asarray(rejected_returns, dtype="float64")
    if len(a) == 0 or len(rj) == 0:
        return 0.0, 1.0, False
    observed = float(a.mean() - rj.mean())
    pooled = np.concatenate([a, rj])
    n_a = len(a)
    rng = np.random.RandomState(seed)
    diffs = np.empty(n_bootstrap)
    for i in range(n_bootstrap):
        rng.shuffle(pooled)  # permute group labels under the null of no difference
        diffs[i] = pooled[:n_a].mean() - pooled[n_a:].mean()
    # One-sided permutation p: how often the NULL diff reaches the observed uplift.
    p_value = float((np.sum(diffs >= observed) + 1) / (n_bootstrap + 1))
    return observed, p_value, bool(p_value < alpha and observed > 0)


def is_degenerate(approval: float, min_turnover: float, max_turnover: float) -> bool:
    """A gatekeeper that approves ~none or ~all signals is degenerate (refuse)."""
    return approval < min_turnover or approval > max_turnover
