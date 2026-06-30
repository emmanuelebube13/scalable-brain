"""MODEL-003 — pure regime helpers (no DB / no network): deterministic state→label
mapping, causal persistence smoothing, quality gate, probability ordering, heuristic
labels, flicker rate. See skill `hmm-semantic-mapping.md`.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np

SEMANTIC_ORDER: List[str] = ["Trending-Up", "Trending-Down", "Ranging", "High-Vol"]
PROB_COLUMNS = [
    "prob_trending_up",
    "prob_trending_down",
    "prob_ranging",
    "prob_high_vol",
]


def map_states_to_labels(
    means: np.ndarray, feature_names: List[str], direction_feature: str = "returns_1"
) -> Dict[int, str]:
    """Deterministic state→semantic mapping by component means.

    High-Vol = highest (volatility_20 + atr_14); among the rest, Trending-Up = highest
    mean ``direction_feature`` (a persistent trend signal), Trending-Down = lowest,
    Ranging = remaining.
    """
    n = means.shape[0]
    vol_i = feature_names.index("volatility_20")
    atr_i = feature_names.index("atr_14")
    ret_i = feature_names.index(direction_feature)

    vol_scores = means[:, vol_i] + means[:, atr_i]
    high_vol = int(np.argmax(vol_scores))
    remaining = [i for i in range(n) if i != high_vol]
    ret_scores = {i: means[i, ret_i] for i in remaining}
    up = max(ret_scores, key=ret_scores.get)
    down = min(ret_scores, key=ret_scores.get)
    ranging = [i for i in remaining if i not in (up, down)][0]
    return {
        high_vol: "High-Vol",
        up: "Trending-Up",
        down: "Trending-Down",
        ranging: "Ranging",
    }


def order_probabilities(posteriors: np.ndarray, mapping: Dict[int, str]) -> np.ndarray:
    """Reorder raw state posteriors into SEMANTIC_ORDER columns."""
    semantic_to_state = {v: k for k, v in mapping.items()}
    return np.column_stack(
        [posteriors[:, semantic_to_state[label]] for label in SEMANTIC_ORDER]
    )


def filtered_posteriors(
    startprob: np.ndarray, transmat: np.ndarray, framelogprob: np.ndarray
) -> np.ndarray:
    """Forward-only **filtered** posteriors ``P(state_t | x_1..x_t)`` for one sequence.

    This is the causal regime-inference primitive (FIX-S1-005). It wraps hmmlearn's
    private ``_hmmc.forward_log`` — the *same* forward recursion ``BaseHMM._score_log``
    uses internally — and row-normalises the forward lattice. The forward variable
    ``fwdlattice[t, i] = log P(x_1..x_t, state_t=i)`` depends only on bars ``0..t``,
    never on bars after ``t``, so the row-normalised posterior at ``t`` is causal by
    construction. There is **no** backward pass and **no** Viterbi here — that is the
    whole point versus ``GaussianHMM.predict_proba`` / ``predict`` (forward-backward
    smoothing over the entire sequence), which leak the future into a past bar's label.

    API note (hmmlearn 0.3.3): ``forward_log`` takes the **non-log** ``startprob`` and
    ``transmat`` plus the **log** emission matrix ``framelogprob`` (the convention used
    by ``BaseHMM._score_log``). This is cross-checked against a hand-rolled log-domain
    forward recursion in ``regime/tests/test_mapping.py`` so that an hmmlearn upgrade
    which changes the private signature/convention fails loudly rather than silently
    corrupting the causal label.

    Args:
        startprob: Initial state distribution, shape ``(K,)`` (regular probabilities).
        transmat: Row-stochastic transition matrix, shape ``(K, K)`` (regular probs).
        framelogprob: Per-bar log emission likelihoods, shape ``(T, K)`` =
            ``log P(x_t | state_t)`` (e.g. ``model._compute_log_likelihood(X)``).

    Returns:
        Filtered posteriors, shape ``(T, K)``; every row sums to 1.0 (within fp error).
    """
    from hmmlearn import _hmmc  # private API — isolated to this single wrapper.

    _, fwdlattice = _hmmc.forward_log(
        np.asarray(startprob, dtype="float64"),
        np.asarray(transmat, dtype="float64"),
        np.ascontiguousarray(framelogprob, dtype="float64"),
    )
    # Stable per-row log-normalize, then exponentiate -> filtered posterior per bar.
    row_max = fwdlattice.max(axis=1, keepdims=True)
    log_norm = row_max + np.log(np.exp(fwdlattice - row_max).sum(axis=1, keepdims=True))
    return np.exp(fwdlattice - log_norm)


def persistence_smooth(labels: List[str], min_bars: int = 3) -> List[str]:
    """Causal debounce: suppress regime segments shorter than ``min_bars``.

    The smoothed label at bar t depends only on bars 0..t (never future).
    """
    smoothed = list(labels)
    n = len(labels)
    i = 0
    while i < n:
        j = i
        while j < n and labels[j] == labels[i]:
            j += 1
        if (j - i) < min_bars and i > 0:
            smoothed[i:j] = [smoothed[i - 1]] * (j - i)
        i = j
    # Leading boundary: a short opening segment has no prior to absorb into, so it
    # adopts the next confirmed regime (one-time fixup at the very start of history).
    if n:
        k = 0
        while k < n and smoothed[k] == smoothed[0]:
            k += 1
        if k < min_bars and k < n:
            smoothed[:k] = [smoothed[k]] * k
    return smoothed


def check_hmm_quality(
    converged: bool, covars: np.ndarray, labels: np.ndarray, n_components: int
) -> Tuple[bool, Optional[str]]:
    """Convergence + non-degenerate covariance + all states populated (>1%)."""
    if not converged:
        return False, "HMM did not converge"
    for k in range(n_components):
        cov = covars[k]
        cov = np.diag(cov) if cov.ndim == 1 else cov
        if np.any(np.linalg.eigvalsh(cov) < 1e-8):
            return False, f"Degenerate covariance in component {k}"
    _, counts = np.unique(labels, return_counts=True)
    if len(counts) < n_components:
        return False, f"Only {len(counts)} of {n_components} states populated"
    if counts.min() / len(labels) < 0.01:
        return False, f"A component has <1% of samples ({counts.min()/len(labels):.3%})"
    return True, None


def flicker_rate(labels: List[str]) -> float:
    arr = np.asarray(labels)
    if len(arr) < 2:
        return 0.0
    return float((arr[1:] != arr[:-1]).sum()) / (len(arr) - 1)


def heuristic_labels(
    vol: np.ndarray,
    trend: np.ndarray,
    vol_thr: float,
    trend_hi: float,
    trend_lo: float,
) -> List[str]:
    """Rule-based reference regime labels for the accuracy holdout (no model).

    Regimes are defined by quantiles of the *persistent* features the model also
    clusters on, so a good unsupervised model can recover them:
      * High-Vol  : volatility_20 above its high quantile;
      * Trending-Up   : (not high-vol) trend_20 above its high quantile;
      * Trending-Down : (not high-vol) trend_20 below its low quantile;
      * Ranging   : the calm middle.
    """
    out: List[str] = []
    for v, t in zip(vol, trend):
        if v >= vol_thr:
            out.append("High-Vol")
        elif t >= trend_hi:
            out.append("Trending-Up")
        elif t <= trend_lo:
            out.append("Trending-Down")
        else:
            out.append("Ranging")
    return out


def aligned_accuracy(
    states: np.ndarray, ref_labels: List[str], train_mask: np.ndarray
) -> Tuple[float, Dict[int, str]]:
    """Clustering-vs-reference accuracy via majority state→label alignment on train.

    Standard unsupervised evaluation: each model state is assigned the reference label
    it most overlaps with on the *train* split; accuracy is then measured on the
    *holdout* (~train_mask == False). Independent of the stored semantic mapping.
    """
    ref = np.asarray(ref_labels)
    state_to_ref: Dict[int, str] = {}
    for s in np.unique(states):
        sel = (states == s) & train_mask
        if sel.sum() == 0:
            sel = states == s
        vals, counts = np.unique(ref[sel], return_counts=True)
        state_to_ref[int(s)] = str(vals[int(np.argmax(counts))])
    holdout = ~train_mask
    if holdout.sum() == 0:
        return 0.0, state_to_ref
    mapped = np.array([state_to_ref[int(s)] for s in states[holdout]])
    acc = float((mapped == ref[holdout]).mean())
    return acc, state_to_ref
