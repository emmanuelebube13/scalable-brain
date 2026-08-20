"""FIX-S1-012 — regime labels must describe values, not ranks (pure; no DB / no network).

The defect: :func:`mapping.map_states_to_labels` assigned direction labels by *rank* among
the three non-High-Vol states, so exactly one state was always called ``Trending-Down``
even when every state had positive mean trend. On the 2026-08-11 fit that mislabelled
state held ~75% of D1 and H4 bars (fix doc §1).

Fixtures below are the component means reported in **FIX-S1-012 §1**, extracted from the
live ``models/hmm_model.joblib``. Only two quantities drive the mapping — the mean
direction feature and the ``volatility_20 + atr_pct_14`` sum — so each state is materialised
as a row carrying exactly those, with the vol sum placed in ``atr_pct_14``.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pytest

from src.regime import mapping as M

FN: List[str] = ["atr_pct_14", "adx_14", "volatility_20", "returns_1", "trend_20"]
DIRECTION = "trend_20"

# (state, trend_20 mean, vol+atr, share of bars, label the OLD rank rule assigned)
# Source: FIX-S1-012 §1, live fit 2026-08-11.
DOC_STATES: Dict[str, List[Tuple[int, float, float, float, str]]] = {
    "D1": [
        (0, +0.0529, -0.625, 0.751, "Trending-Down"),
        (1, +0.2146, 0.329, 0.089, "Ranging"),
        (2, -1.7277, 3.050, 0.064, "High-Vol"),
        (3, +0.5520, 2.542, 0.096, "Trending-Up"),
    ],
    "H4": [
        (0, +0.1352, 2.180, 0.092, "Ranging"),
        (1, +0.3041, 0.189, 0.086, "Trending-Up"),
        (2, +0.0292, -0.613, 0.746, "Trending-Down"),
        (3, -0.7974, 3.157, 0.075, "High-Vol"),
    ],
    "H1": [
        (0, +0.0377, -0.974, 0.434, "Ranging"),
        (1, +0.2047, 0.825, 0.150, "Trending-Up"),
        (2, -0.4956, 3.822, 0.075, "High-Vol"),
        (3, -0.0281, 0.029, 0.340, "Trending-Down"),
    ],
}


def _means(gran: str) -> np.ndarray:
    """Component-mean matrix for a granularity, ordered by state index."""
    rows = []
    for _state, trend, vol_sum, _share, _old in sorted(DOC_STATES[gran]):
        # vol+atr is what the rule uses; carry the whole sum in atr_pct_14, vol at 0.0.
        rows.append([vol_sum, 0.0, 0.0, 0.0, trend])
    return np.array(rows, dtype="float64")


def _old_rank_mapping(means: np.ndarray) -> Dict[int, str]:
    """The pre-fix rank-based rule, reproduced verbatim as the DEFECT under test."""
    n = means.shape[0]
    vol_i, atr_i, ret_i = (
        FN.index("volatility_20"),
        FN.index("atr_pct_14"),
        FN.index(DIRECTION),
    )
    high_vol = int(np.argmax(means[:, vol_i] + means[:, atr_i]))
    remaining = [i for i in range(n) if i != high_vol]
    scores = {i: means[i, ret_i] for i in remaining}
    up = max(scores, key=scores.get)
    down = min(scores, key=scores.get)  # LOWEST of the three — even if positive
    ranging = [i for i in remaining if i not in (up, down)][0]
    return {
        high_vol: "High-Vol",
        up: "Trending-Up",
        down: "Trending-Down",
        ranging: "Ranging",
    }


# ------------------------------------------------------------------ the headline guarantee


@pytest.mark.parametrize(
    "tau", [0.0, 1e-9, 0.01, 0.0292, 0.05, 0.10, 0.25, 0.50, 1.0, 5.0]
)
def test_positive_trend_state_is_never_trending_down(tau: float) -> None:
    """The real H4 case: a state whose mean trend is **+0.0292** must not be called
    ``Trending-Down`` at any ``tau >= 0``. This is FIX-S1-012 §6's pinned assertion —
    under the old rank rule this state carried 74.6% of H4 bars under that label."""
    mapping = M.map_states_to_labels(_means("H4"), FN, DIRECTION, tau=tau)
    assert mapping[2] != "Trending-Down", (tau, mapping)


@pytest.mark.parametrize("gran", ["D1", "H4", "H1"])
def test_no_positive_trend_state_is_ever_trending_down(gran: str) -> None:
    """Generalised: across all three granularities, no state with a positive mean trend
    is labelled Trending-Down, at any tau."""
    means = _means(gran)
    ret_i = FN.index(DIRECTION)
    for tau in (0.0, 0.05, 0.10, 0.25, 0.50, 0.75, 2.0):
        mapping = M.map_states_to_labels(means, FN, DIRECTION, tau=tau)
        for state, label in mapping.items():
            if label == "Trending-Down":
                assert means[state, ret_i] < 0.0, (gran, tau, state, label)


# ------------------------------------------------------------------ full per-granularity maps


@pytest.mark.parametrize(
    "gran,expected",
    [
        (
            # +0.0529 and +0.2146 are inside the band -> Ranging; +0.5520 -> Trending-Up;
            # the true downtrend (-1.7277) is still absorbed by High-Vol (deferred, §5).
            "D1",
            {0: "Ranging", 1: "Ranging", 2: "High-Vol", 3: "Trending-Up"},
        ),
        (
            "H4",
            {0: "Ranging", 1: "Trending-Up", 2: "Ranging", 3: "High-Vol"},
        ),
        (
            "H1",
            {0: "Ranging", 1: "Ranging", 2: "High-Vol", 3: "Ranging"},
        ),
    ],
)
def test_doc_state_configurations_at_default_tau(
    gran: str, expected: Dict[int, str]
) -> None:
    """All four states of each D1/H4/H1 configuration in FIX-S1-012 §1, at the
    provisional default ``tau=0.25``."""
    assert M.map_states_to_labels(_means(gran), FN, DIRECTION) == expected
    assert M.DEFAULT_TAU == 0.25  # the fixture above is written for this default


@pytest.mark.parametrize(
    "gran,expected",
    [
        ("D1", {0: "Ranging", 1: "Trending-Up", 2: "High-Vol", 3: "Trending-Up"}),
        ("H4", {0: "Trending-Up", 1: "Trending-Up", 2: "Ranging", 3: "High-Vol"}),
        ("H1", {0: "Ranging", 1: "Trending-Up", 2: "High-Vol", 3: "Ranging"}),
    ],
)
def test_doc_state_configurations_at_tau_010(
    gran: str, expected: Dict[int, str]
) -> None:
    """Same configurations at ``tau=0.10`` — the value the sensitivity report recommends
    (``FIX-S1-012-tau-sensitivity.txt``): the only tau at which all three granularities
    keep three live labels."""
    assert M.map_states_to_labels(_means(gran), FN, DIRECTION, tau=0.10) == expected


@pytest.mark.parametrize("gran", ["D1", "H4", "H1"])
def test_high_vol_assignment_is_unchanged(gran: str) -> None:
    """High-Vol is still the single argmax of volatility_20 + atr_pct_14 — the fix does not
    touch that step, nor the deferred question of it absorbing downtrends (§5)."""
    means = _means(gran)
    expected = int(
        np.argmax(means[:, FN.index("volatility_20")] + means[:, FN.index("atr_pct_14")])
    )
    for tau in (0.0, 0.10, 0.25, 1.0):
        mapping = M.map_states_to_labels(means, FN, DIRECTION, tau=tau)
        assert [s for s, l in mapping.items() if l == "High-Vol"] == [expected]


def test_mapping_covers_every_state_and_uses_only_known_labels() -> None:
    for gran in DOC_STATES:
        means = _means(gran)
        for tau in (0.0, 0.10, 0.25, 0.75):
            mapping = M.map_states_to_labels(means, FN, DIRECTION, tau=tau)
            assert set(mapping) == set(range(means.shape[0]))
            assert set(mapping.values()) <= set(M.SEMANTIC_ORDER)


def test_negative_tau_rejected() -> None:
    with pytest.raises(ValueError):
        M.map_states_to_labels(_means("D1"), FN, DIRECTION, tau=-0.01)


# ------------------------------------------------------------------ regression: the old defect


@pytest.mark.parametrize("gran,dominant_state", [("D1", 0), ("H4", 2)])
def test_regression_old_rank_rule_mislabelled_a_positive_state(
    gran: str, dominant_state: int
) -> None:
    """DEFECT UNDER TEST (FIX-S1-012 §1) — the old rank-based rule.

    It always named exactly one state ``Trending-Down``: the *least upward* of the three
    non-High-Vol states, even when all three had positive mean trend. On D1 (state 0,
    +0.0529, 75.1% of bars) and H4 (state 2, +0.0292, 74.6% of bars) that label described
    the dominant quiet drift, not a falling market. The value-based rule must not
    reproduce it.
    """
    means = _means(gran)
    ret_i = FN.index(DIRECTION)

    old = _old_rank_mapping(means)
    assert old[dominant_state] == "Trending-Down"  # the bug, reproduced
    assert means[dominant_state, ret_i] > 0.0  # on a POSITIVE mean trend
    assert sorted(old.values()) == sorted(M.SEMANTIC_ORDER)  # forced bijection

    new = M.map_states_to_labels(means, FN, DIRECTION)
    assert new[dominant_state] != "Trending-Down"
    # And the label is simply not used, rather than forced onto some state.
    assert "Trending-Down" in M.unused_labels(new)


def test_unused_labels_reports_the_degenerate_taxonomy() -> None:
    """A threshold mapping may legitimately produce <4 cells; that must be visible."""
    assert M.unused_labels(
        {0: "High-Vol", 1: "Ranging", 2: "Ranging", 3: "Ranging"}
    ) == [
        "Trending-Up",
        "Trending-Down",
    ]
    full = {0: "Trending-Up", 1: "Trending-Down", 2: "Ranging", 3: "High-Vol"}
    assert M.unused_labels(full) == []


# ------------------------------------------------------------------ order_probabilities


def test_order_probabilities_sums_states_sharing_a_label() -> None:
    """Many-to-one: two states labelled Ranging contribute their SUM, not one of them."""
    posteriors = np.array([[0.10, 0.20, 0.30, 0.40], [0.25, 0.25, 0.25, 0.25]])
    mapping = {0: "Trending-Up", 1: "Ranging", 2: "Ranging", 3: "High-Vol"}
    ordered = M.order_probabilities(posteriors, mapping)
    # columns are SEMANTIC_ORDER: Trending-Up, Trending-Down, Ranging, High-Vol
    assert np.allclose(ordered[0], [0.10, 0.0, 0.50, 0.40])
    assert np.allclose(ordered[1], [0.25, 0.0, 0.50, 0.25])


def test_order_probabilities_absent_label_is_a_zero_column() -> None:
    posteriors = np.array([[0.1, 0.2, 0.3, 0.4]])
    mapping = {0: "Ranging", 1: "Ranging", 2: "Ranging", 3: "High-Vol"}
    ordered = M.order_probabilities(posteriors, mapping)
    up_i, down_i = M.SEMANTIC_ORDER.index("Trending-Up"), M.SEMANTIC_ORDER.index(
        "Trending-Down"
    )
    assert ordered[:, up_i].tolist() == [0.0]
    assert ordered[:, down_i].tolist() == [0.0]


@pytest.mark.parametrize(
    "mapping",
    [
        {0: "Trending-Up", 1: "Trending-Down", 2: "Ranging", 3: "High-Vol"},
        {0: "Trending-Up", 1: "Ranging", 2: "Ranging", 3: "High-Vol"},
        {0: "Ranging", 1: "Ranging", 2: "Ranging", 3: "High-Vol"},
        {0: "High-Vol", 1: "High-Vol", 2: "High-Vol", 3: "High-Vol"},
    ],
)
def test_order_probabilities_rows_still_sum_to_one(mapping: Dict[int, str]) -> None:
    rng = np.random.RandomState(5)
    raw = rng.uniform(0.01, 1.0, size=(50, 4))
    posteriors = raw / raw.sum(axis=1, keepdims=True)
    ordered = M.order_probabilities(posteriors, mapping)
    assert ordered.shape == (50, len(M.SEMANTIC_ORDER))
    assert np.allclose(ordered.sum(axis=1), 1.0, atol=1e-12)


def test_order_probabilities_column_order_is_semantic_order() -> None:
    """One-hot per state, so each column can be read off directly."""
    posteriors = np.eye(4)
    mapping = {0: "High-Vol", 1: "Ranging", 2: "Trending-Down", 3: "Trending-Up"}
    ordered = M.order_probabilities(posteriors, mapping)
    for state, label in mapping.items():
        assert ordered[state, M.SEMANTIC_ORDER.index(label)] == 1.0


def test_order_probabilities_rejects_out_of_range_state() -> None:
    with pytest.raises(ValueError):
        M.order_probabilities(np.eye(4), {0: "Ranging", 7: "High-Vol"})


# ------------------------------------------------------------------ cohens_kappa


def test_kappa_perfect_agreement_is_one() -> None:
    a = ["Ranging", "High-Vol", "Trending-Up", "Ranging", "Trending-Up"]
    assert M.cohens_kappa(a, list(a)) == pytest.approx(1.0)


def test_kappa_at_chance_is_about_zero() -> None:
    """Two independent labellers over the same skewed marginals score ~0."""
    rng = np.random.RandomState(19)
    p = [0.75, 0.10, 0.10, 0.05]
    a = rng.choice(M.SEMANTIC_ORDER, size=200_000, p=p)
    b = rng.choice(M.SEMANTIC_ORDER, size=200_000, p=p)
    kappa = M.cohens_kappa(a, b)
    # Raw agreement is high (dominant class) while kappa correctly reports no structure.
    assert float((a == b).mean()) > 0.5
    assert abs(kappa) < 0.01, kappa


def test_kappa_total_disagreement_is_negative() -> None:
    a = ["Ranging"] * 50 + ["High-Vol"] * 50
    b = ["High-Vol"] * 50 + ["Ranging"] * 50
    assert M.cohens_kappa(a, b) == pytest.approx(-1.0)


def test_kappa_of_two_constant_labellings() -> None:
    """p_e == 1 — the ratio is undefined; agreement carries no information."""
    assert M.cohens_kappa(["Ranging"] * 10, ["Ranging"] * 10) == pytest.approx(1.0)
    assert M.cohens_kappa(["Ranging"] * 10, ["High-Vol"] * 10) == pytest.approx(0.0)


def test_kappa_empty_and_mismatched_inputs() -> None:
    assert M.cohens_kappa([], []) == 0.0
    with pytest.raises(ValueError):
        M.cohens_kappa(["a", "b"], ["a"])


def _synthetic_pair(shares: List[float], p_obs: float, n: int = 200_000):
    """Two labellings with the given marginals and observed agreement.

    Uses the quasi-independence joint ``P = k*diag(p) + (1-k)*p p'`` — both margins are
    exactly ``p`` and the diagonal sums to ``p_obs`` — then materialises the label pairs
    from the resulting contingency counts.
    """
    p = np.asarray(shares, dtype="float64")
    p_exp = float((p**2).sum())
    k = (p_obs - p_exp) / (1.0 - p_exp)
    joint = k * np.diag(p) + (1.0 - k) * np.outer(p, p)
    counts = np.round(joint * n).astype(int)
    a: List[str] = []
    b: List[str] = []
    for i, lab_i in enumerate(M.SEMANTIC_ORDER):
        for j, lab_j in enumerate(M.SEMANTIC_ORDER):
            a.extend([lab_i] * counts[i, j])
            b.extend([lab_j] * counts[i, j])
    return np.array(a), np.array(b)


@pytest.mark.parametrize(
    "gran,shares,observed,chance,expected_kappa",
    [
        # FIX-S1-012 §3 (observed/chance/kappa) with §1's per-label bar shares as marginals.
        ("D1", [0.751, 0.089, 0.096, 0.064], 0.9389, 0.5848, 0.853),
        ("H4", [0.746, 0.092, 0.086, 0.075], 0.7143, 0.5784, 0.322),
        ("H1", [0.340, 0.434, 0.150, 0.075], 0.9644, 0.3326, 0.947),
    ],
)
def test_kappa_reproduces_the_documented_values(
    gran: str,
    shares: List[float],
    observed: float,
    chance: float,
    expected_kappa: float,
) -> None:
    """The three kappas reported in FIX-S1-012 §3 fall out of §1's marginals."""
    a, b = _synthetic_pair(shares, observed)
    assert float((a == b).mean()) == pytest.approx(observed, abs=1e-3), gran
    assert float((np.asarray(shares) ** 2).sum()) == pytest.approx(
        chance, abs=1e-3
    ), gran
    assert round(M.cohens_kappa(a, b), 2) == round(expected_kappa, 2), gran


def test_h4_is_the_case_the_raw_gate_misses() -> None:
    """H4 clears a 0.70 raw-agreement bar on 0.578 chance agreement, but fails a 0.40
    kappa bar — the reason the gate is chance-corrected (FIX-S1-012 §3)."""
    from src.regime import hmm_regime as H

    a, b = _synthetic_pair([0.746, 0.092, 0.086, 0.075], 0.7143)
    acc = float((a == b).mean())
    kappa = M.cohens_kappa(a, b)
    assert acc >= H.ACCURACY_GATE  # the old gate passes it
    assert kappa < H.KAPPA_GATE  # the chance-corrected gate does not
    failures = H._stability_gate_failures(acc, kappa)
    assert len(failures) == 1 and "kappa" in failures[0]
    assert f"{kappa:.3f}" in failures[0] and str(H.KAPPA_GATE) in failures[0]


def test_stability_gate_requires_both_metrics() -> None:
    from src.regime import hmm_regime as H

    assert H._stability_gate_failures(0.95, 0.85) == []
    both = H._stability_gate_failures(0.50, 0.10)
    assert len(both) == 2
    assert "accuracy" in both[0] and "0.500" in both[0]
    assert "kappa" in both[1] and "0.100" in both[1]
    only_acc = H._stability_gate_failures(0.50, 0.85)
    assert len(only_acc) == 1 and "accuracy" in only_acc[0]


def test_aligned_agreement_returns_accuracy_and_kappa() -> None:
    """The gate's inputs come from one pass; the legacy accuracy view still agrees."""
    states = np.array([0, 0, 0, 1, 1, 2, 2, 3, 3, 3])
    ref = ["Ranging"] * 3 + ["Trending-Up"] * 2 + ["High-Vol"] * 2 + ["Ranging"] * 3
    train_mask = np.array([True] * 6 + [False] * 4)
    acc, kappa, state_to_ref = M.aligned_agreement(states, ref, train_mask)
    legacy_acc, legacy_map = M.aligned_accuracy(states, ref, train_mask)
    assert acc == legacy_acc and state_to_ref == legacy_map
    assert 0.0 <= acc <= 1.0 and -1.0 <= kappa <= 1.0
