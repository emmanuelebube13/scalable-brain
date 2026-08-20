"""MODEL-003 — pure regime helpers (no DB / no network): deterministic state→label
mapping, causal persistence smoothing, quality gate, probability ordering, heuristic
labels, flicker rate. See skill `hmm-semantic-mapping.md`.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple, Literal

import numpy as np

SEMANTIC_ORDER: List[str] = ["Trending-Up", "Trending-Down", "Ranging", "High-Vol"]
PROB_COLUMNS = [
    "prob_trending_up",
    "prob_trending_down",
    "prob_ranging",
    "prob_high_vol",
]

# FIX-S1-012 — direction threshold, in the SAME units as the fitted component means
# (standardised *and* feature-weighted space; ``trend_20`` carries weight 3.0 in
# hmm_regime.FEATURE_WEIGHTS, so 0.25 here is ~0.083 SD of raw trend_20).
#
# PROVISIONAL. See ``docs/proposed-fixes/system-1/FIX-S1-012-tau-sensitivity.txt``.
DEFAULT_TAU: float = 0.25


def map_states_to_labels(
    means: np.ndarray,
    feature_names: List[str],
    direction_feature: str = "returns_1",
    *,
    tau: float = DEFAULT_TAU,
    order: Literal["volatility_first", "trend_first"] = "volatility_first",
) -> Dict[int, str]:
    """Deterministic state→semantic mapping by component means (FIX-S1-012).

    ``High-Vol`` is the single state with the highest ``volatility_20 + atr_14`` mean
    (unchanged). Every **remaining** state is then labelled by the *value* of its mean
    ``direction_feature``, not by its rank among siblings:

    * ``Trending-Up``   if mean direction ``> +tau``
    * ``Trending-Down`` if mean direction ``< -tau``
    * ``Ranging``       otherwise

    The returned mapping is therefore **not necessarily a bijection**: several states may
    carry the same label and a label may be absent entirely. That is deliberate — the
    previous rank-based rule always named exactly one state ``Trending-Down`` even when
    all three non-High-Vol states had *positive* mean trend (FIX-S1-012 §1: on the
    2026-08-11 fit that mislabelled state held ~75% of D1/H4 bars). Callers must not
    assume all four labels are present; use :func:`order_probabilities` (which sums
    across states sharing a label and emits 0.0 for an absent one) and
    :func:`unused_labels` to surface a degenerate taxonomy.

    Args:
        means: Component means, shape ``(K, F)`` — ``GaussianHMM.means_`` or
            ``KMeans.cluster_centers_``, in the model's own (scaled/weighted) space.
        feature_names: Column names of ``means``, in order.
        direction_feature: Name of the persistent-direction column (e.g. ``trend_20``).
        tau: Non-negative direction threshold, in the units of ``means``.
            **Provisional default of 0.25** pending the sensitivity report
            (``docs/proposed-fixes/system-1/FIX-S1-012-tau-sensitivity.txt``); the fix
            doc explicitly defers the final choice to that evidence. ``tau=0`` makes any
            non-zero drift directional and is not recommended.
        order: Mapping strategy. If "volatility_first", assign High-Vol first, then trend.
            If "trend_first", assign trend labels first, then High-Vol from remaining.

    Returns:
        ``{state_index: label}`` covering every state, keyed in state order.

    Raises:
        ValueError: if ``tau`` is negative or ``order`` is unknown.
    """
    if tau < 0:
        raise ValueError(f"tau must be non-negative, got {tau!r}")
    n = means.shape[0]
    vol_i = feature_names.index("volatility_20")
    atr_i = feature_names.index("atr_pct_14")
    ret_i = feature_names.index(direction_feature)

    mapping: Dict[int, str] = {}
    vol_scores = means[:, vol_i] + means[:, atr_i]

    if order == "volatility_first":
        high_vol = int(np.argmax(vol_scores))
        for i in range(n):
            if i == high_vol:
                mapping[i] = "High-Vol"
                continue
            direction = float(means[i, ret_i])
            if direction > tau:
                mapping[i] = "Trending-Up"
            elif direction < -tau:
                mapping[i] = "Trending-Down"
            else:
                mapping[i] = "Ranging"
    elif order == "trend_first":
        neutral_states = []
        for i in range(n):
            direction = float(means[i, ret_i])
            if direction > tau:
                mapping[i] = "Trending-Up"
            elif direction < -tau:
                mapping[i] = "Trending-Down"
            else:
                neutral_states.append(i)

        if neutral_states:
            high_vol = max(neutral_states, key=lambda i: vol_scores[i])
            for i in neutral_states:
                if i == high_vol:
                    mapping[i] = "High-Vol"
                else:
                    mapping[i] = "Ranging"
    else:
        raise ValueError(f"Unknown order: {order}")

    return mapping


def unused_labels(mapping: Dict[int, str]) -> List[str]:
    """Labels in :data:`SEMANTIC_ORDER` that no state carries (FIX-S1-012 §5.4).

    A non-empty result means the fit produced a degenerate (<4 cell) taxonomy; it is
    reported in the run summary so this is visible rather than silent.
    """
    present = set(mapping.values())
    return [label for label in SEMANTIC_ORDER if label not in present]


def order_probabilities(posteriors: np.ndarray, mapping: Dict[int, str]) -> np.ndarray:
    """Aggregate raw state posteriors into SEMANTIC_ORDER columns (FIX-S1-012 §4).

    Many-states-to-one-label: each output column is the **sum** of the posteriors of all
    states carrying that label, and an all-zero column where no state carries it. Row
    sums are preserved (1.0 for a proper posterior), so ``argmax`` over the result is
    still a valid regime call.

    This replaces the old ``{v: k for k, v in mapping.items()}`` inversion, which
    required a bijection: it silently dropped one of two states sharing a label and
    raised ``KeyError`` when a label was absent.
    """
    post = np.asarray(posteriors, dtype="float64")
    if post.ndim != 2:
        raise ValueError(f"posteriors must be 2-D, got shape {post.shape}")
    n_rows, n_states = post.shape
    unknown = [s for s in mapping if not (0 <= int(s) < n_states)]
    if unknown:
        raise ValueError(f"mapping references states outside posteriors: {unknown}")

    columns = []
    for label in SEMANTIC_ORDER:
        states = [int(s) for s in sorted(mapping) if mapping[s] == label]
        if states:
            columns.append(post[:, states].sum(axis=1))
        else:
            columns.append(np.zeros(n_rows, dtype="float64"))
    return np.column_stack(columns)


def cohens_kappa(labels_a, labels_b) -> float:
    """Cohen's kappa — chance-corrected agreement between two labellings (FIX-S1-012 §3).

    ``kappa = (p_o - p_e) / (1 - p_e)`` where ``p_o`` is observed agreement and ``p_e``
    is the agreement expected from the two labellers' independent marginals. Raw
    agreement is inflated by a dominant class: on the 2026-08-11 H4 fit, 0.578 of the
    0.714 agreement was chance, giving kappa 0.322 — weak structure that clears a 0.70
    raw-agreement gate.

    Returns 0.0 for an empty input, and 1.0 when both labellings are single-valued and
    identical (``p_e == 1``, where the ratio is undefined).
    """
    a = np.asarray(labels_a)
    b = np.asarray(labels_b)
    if a.shape != b.shape:
        raise ValueError(f"label arrays must be the same shape: {a.shape} vs {b.shape}")
    n = a.size
    if n == 0:
        return 0.0
    p_o = float((a == b).mean())
    categories = np.unique(np.concatenate([a.ravel(), b.ravel()]))
    p_e = float(sum((a == c).mean() * (b == c).mean() for c in categories))
    if p_e >= 1.0 - 1e-12:
        # Both labellers are degenerate on one class: agreement carries no information.
        return 1.0 if p_o >= 1.0 - 1e-12 else 0.0
    return float((p_o - p_e) / (1.0 - p_e))


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


def persistence_smooth_causal(
    labels: List[str], min_bars: int = 3
) -> Tuple[List[str], List[bool]]:
    """Debounce that is causal at every bar, including the trailing edge.

    Returns (smoothed, settled). ``settled[t]`` is False where the label at t is
    still provisional — i.e. the current run is shorter than ``min_bars`` and could
    still be absorbed by what happens next.
    """
    if not labels:
        return [], []

    smoothed = []
    settled = []

    last_confirmed = None
    current_run_label = None
    current_run_length = 0

    for label in labels:
        if label == current_run_label:
            current_run_length += 1
        else:
            current_run_label = label
            current_run_length = 1

        is_settled = current_run_length >= min_bars
        if is_settled:
            last_confirmed = current_run_label

        if last_confirmed is None:
            # Leading edge: before any run has reached min_bars
            smoothed.append(label)
            settled.append(False)
        else:
            smoothed.append(last_confirmed)
            settled.append(is_settled)

    return smoothed, settled


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


def aligned_agreement(
    states: np.ndarray, ref_labels: List[str], train_mask: np.ndarray
) -> Tuple[float, float, Dict[int, str]]:
    """Holdout agreement between a model's states and a reference labelling.

    Each model state is assigned the reference label it most overlaps with on the
    *train* split; the two labellings are then compared on the *holdout*
    (``~train_mask``). Independent of the stored semantic mapping.

    **This is a stability metric, not accuracy** (FIX-S1-012 §3): the reference is
    another unsupervised labelling, not ground truth. Raw agreement is inflated by a
    dominant class, so the chance-corrected kappa is returned alongside it and is what
    the quality gate should key on.

    Returns:
        ``(observed_agreement, cohens_kappa, state_to_ref)``.
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
        return 0.0, 0.0, state_to_ref
    mapped = np.array([state_to_ref[int(s)] for s in states[holdout]])
    acc = float((mapped == ref[holdout]).mean())
    kappa = cohens_kappa(mapped, ref[holdout])
    return acc, kappa, state_to_ref


def aligned_accuracy(
    states: np.ndarray, ref_labels: List[str], train_mask: np.ndarray
) -> Tuple[float, Dict[int, str]]:
    """Backwards-compatible view of :func:`aligned_agreement` (agreement only)."""
    acc, _kappa, state_to_ref = aligned_agreement(states, ref_labels, train_mask)
    return acc, state_to_ref
