"""Unit tests for MODEL-003 pure regime helpers (no DB / no network)."""

from __future__ import annotations

import numpy as np

from src.system1.regime import mapping as M

FN = ["atr_14", "adx_14", "volatility_20", "returns_1"]


def test_map_states_deterministic_and_complete():
    # rows: [atr, adx, vol, ret]. FIX-S1-012: direction labels are assigned by VALUE
    # against +/- tau, so tau must be below the drift being distinguished here.
    means = np.array(
        [
            [0.1, 20, 0.1, 0.002],  # up: return above +tau, low vol
            [0.1, 20, 0.1, -0.002],  # down: return below -tau
            [0.1, 20, 0.1, 0.0],  # ranging: inside the band
            [0.9, 30, 0.9, 0.0],  # high-vol: highest vol+atr
        ]
    )
    m = M.map_states_to_labels(means, FN, tau=0.001)
    assert m[3] == "High-Vol"
    assert m[0] == "Trending-Up"
    assert m[1] == "Trending-Down"
    assert m[2] == "Ranging"
    assert set(m.values()) == set(M.SEMANTIC_ORDER)


def test_order_probabilities_sums_to_one():
    posteriors = np.array([[0.1, 0.2, 0.3, 0.4], [0.25, 0.25, 0.25, 0.25]])
    mapping = {0: "Trending-Up", 1: "Trending-Down", 2: "Ranging", 3: "High-Vol"}
    ordered = M.order_probabilities(posteriors, mapping)
    assert np.allclose(ordered.sum(axis=1), 1.0, atol=1e-9)


def test_map_states_trend_first_sensitivity_report_reproduction():
    # Reproduce the 9 numbers in the table for TASK 2.
    def build_means(data):
        means = np.zeros((4, 4))
        for s, (trend, volat) in data.items():
            means[s, 2] = volat  # volatility_20
            means[s, 3] = trend  # returns_1 (used as direction feature in FN)
        return means

    # D1 (tau 0.25)
    d1_data = {
        0: (+0.0529, -0.625),
        1: (+0.2146, 0.329),
        2: (-1.7277, 3.050),
        3: (+0.5520, 2.542),
    }
    d1_shares = {0: 75.1, 1: 8.9, 2: 6.4, 3: 9.6}
    d1_map = M.map_states_to_labels(
        build_means(d1_data), FN, tau=0.25, order="trend_first"
    )
    d1_res = {
        lbl: sum(d1_shares[s] for s, l in d1_map.items() if l == lbl)
        for lbl in M.SEMANTIC_ORDER
    }

    assert round(d1_res["Trending-Up"], 1) == 9.6
    assert round(d1_res["Trending-Down"], 1) == 6.4
    assert round(d1_res["Ranging"], 1) == 75.1
    assert round(d1_res["High-Vol"], 1) == 8.9

    # H4 (tau 0.25)
    h4_data = {
        0: (+0.1352, 2.180),
        1: (+0.3041, 0.189),
        2: (+0.0292, -0.613),
        3: (-0.7974, 3.157),
    }
    h4_shares = {0: 9.2, 1: 8.6, 2: 74.6, 3: 7.5}
    h4_map = M.map_states_to_labels(
        build_means(h4_data), FN, tau=0.25, order="trend_first"
    )
    h4_res = {
        lbl: sum(h4_shares[s] for s, l in h4_map.items() if l == lbl)
        for lbl in M.SEMANTIC_ORDER
    }

    assert round(h4_res["Trending-Up"], 1) == 8.6
    assert round(h4_res["Trending-Down"], 1) == 7.5
    assert round(h4_res["Ranging"], 1) == 74.6
    assert round(h4_res["High-Vol"], 1) == 9.2

    # H1 (tau 0.10)
    h1_data = {
        0: (+0.0377, -0.974),
        1: (+0.2047, 0.825),
        2: (-0.4956, 3.822),
        3: (-0.0281, 0.029),
    }
    h1_shares = {0: 43.4, 1: 15.0, 2: 7.5, 3: 34.0}
    h1_map = M.map_states_to_labels(
        build_means(h1_data), FN, tau=0.10, order="trend_first"
    )
    h1_res = {
        lbl: sum(h1_shares[s] for s, l in h1_map.items() if l == lbl)
        for lbl in M.SEMANTIC_ORDER
    }

    assert round(h1_res["Trending-Up"], 1) == 15.0
    assert round(h1_res["Trending-Down"], 1) == 7.5
    assert round(h1_res["Ranging"], 1) == 43.4
    assert round(h1_res["High-Vol"], 1) == 34.0


def test_persistence_smooth_no_short_segments():
    labels = ["A", "A", "B", "A", "A", "A", "C", "C", "C"]  # 'B' is a 1-bar flicker
    sm = M.persistence_smooth(labels, min_bars=3)
    # No segment shorter than 3 bars.
    segs, i = [], 0
    while i < len(sm):
        j = i
        while j < len(sm) and sm[j] == sm[i]:
            j += 1
        segs.append(j - i)
        i = j
    assert all(s >= 3 for s in segs), (sm, segs)


def test_persistence_smooth_leading_short_segment():
    # A short, unique opening segment must be merged forward (no <3 segment at start).
    labels = ["A", "A", "B", "B", "B", "B"]  # leading 'A' run is length 2
    sm = M.persistence_smooth(labels, min_bars=3)
    segs, i = [], 0
    while i < len(sm):
        j = i
        while j < len(sm) and sm[j] == sm[i]:
            j += 1
        segs.append(j - i)
        i = j
    assert all(s >= 3 for s in segs), (sm, segs)


def test_persistence_smooth_is_causal():
    labels = ["A", "A", "A", "B", "A", "A"]
    sm = M.persistence_smooth(labels, 3)
    sm_ext = M.persistence_smooth(labels + ["B"], 3)
    assert sm == sm_ext[: len(sm)]  # appending a bar does not rewrite the past


def test_persistence_smooth_trailing_run_looks_ahead():
    """DEFECT, pinned (recorded in FIX-S1-012 §7; needs its own fix).

    ``persistence_smooth`` decides a segment's fate from its TOTAL length, which it can
    only know once the segment has ended. For a run still IN PROGRESS at the last bar,
    the emitted label therefore depends on bars that have not happened yet: the trailing
    ``B, B`` below is suppressed while it is 2 bars long and reinstated once a third ``B``
    arrives. The docstring's claim that "the smoothed label at bar t depends only on bars
    0..t" holds for interior bars only — the last ``min_bars - 1`` bars are provisional.

    This is independent of the FIX-S1-012 relabelling (it reproduces on plain strings)
    and is why ``test_causal_labels.py`` compares smoothed labels only up to
    ``t - (min_bars - 1)``. Asserting the CURRENT behaviour so that a future causal fix
    to the smoother fails here loudly instead of silently.
    """
    base = ["A", "A", "A", "B", "B"]
    assert M.persistence_smooth(base, 3) == ["A", "A", "A", "A", "A"]
    # One more B, and bars 3-4 are rewritten -> the past changed.
    assert M.persistence_smooth(base + ["B"], 3) == ["A", "A", "A", "B", "B", "B"]
    # A different future bar leaves them suppressed.
    assert M.persistence_smooth(base + ["C"], 3) == ["A", "A", "A", "A", "A", "A"]


def test_persistence_smooth_causal_prefix_invariance():
    import random

    random.seed(42)
    for _ in range(200):
        length = random.randint(10, 50)
        labels = [random.choice(["A", "B", "C"]) for _ in range(length)]
        full_smoothed, full_settled = M.persistence_smooth_causal(labels, 3)
        for k in range(1, length + 1):
            prefix_smoothed, prefix_settled = M.persistence_smooth_causal(labels[:k], 3)
            assert prefix_smoothed == full_smoothed[:k]
            assert prefix_settled == full_settled[:k]


def test_persistence_smooth_causal_semantics():
    labels = ["A", "A", "A", "B", "B", "C", "C", "C"]
    smoothed, settled = M.persistence_smooth_causal(labels, 3)
    # A reaches 3 at index 2
    # B is size 2, C reaches 3 at index 7
    assert smoothed == ["A", "A", "A", "A", "A", "A", "A", "C"]
    assert settled == [False, False, True, False, False, False, False, True]


def test_flicker_rate_monotonic():
    raw = ["A", "B", "A", "B", "A"]
    sm = ["A", "A", "A", "A", "A"]
    assert M.flicker_rate(sm) < M.flicker_rate(raw)


def test_quality_gate_detects_unpopulated():
    covars = np.ones((4, 4)) * 0.5
    labels = np.array([0, 0, 0, 1, 1, 2])  # state 3 never used
    ok, reason = M.check_hmm_quality(True, covars, labels, 4)
    assert not ok and "state" in reason.lower()


def test_quality_gate_pass():
    covars = np.ones((4, 4)) * 0.5
    labels = np.array([0, 1, 2, 3] * 25)
    ok, reason = M.check_hmm_quality(True, covars, labels, 4)
    assert ok and reason is None


# ----------------------------------------------- FIX-S1-005: filtered_posteriors helper


def _hand_rolled_forward(startprob, transmat, framelogprob):
    """Reference log-domain forward recursion (alpha[t,i]=log P(x_1..x_t, s_t=i))."""
    T, K = framelogprob.shape
    log_start = np.log(startprob)
    log_trans = np.log(transmat)
    alpha = np.zeros((T, K))
    alpha[0] = log_start + framelogprob[0]
    for t in range(1, T):
        for j in range(K):
            m = (alpha[t - 1] + log_trans[:, j]).max()
            alpha[t, j] = (
                m
                + np.log(np.exp(alpha[t - 1] + log_trans[:, j] - m).sum())
                + framelogprob[t, j]
            )
    # Row-normalize -> filtered posterior P(s_t | x_1..x_t).
    row_max = alpha.max(axis=1, keepdims=True)
    log_norm = row_max + np.log(np.exp(alpha - row_max).sum(axis=1, keepdims=True))
    return np.exp(alpha - log_norm)


def test_filtered_posteriors_match_hand_rolled_forward():
    """Cross-check the hmmlearn private-API wrapper against an independent forward
    recursion. If an hmmlearn upgrade changes the forward_log signature/convention,
    this fails loudly instead of silently corrupting the causal label."""
    rng = np.random.RandomState(7)
    startprob = np.array([0.6, 0.4])
    transmat = np.array([[0.7, 0.3], [0.35, 0.65]])
    framelogprob = np.log(rng.uniform(0.05, 1.0, size=(12, 2)))
    got = M.filtered_posteriors(startprob, transmat, framelogprob)
    expected = _hand_rolled_forward(startprob, transmat, framelogprob)
    assert got.shape == (12, 2)
    assert np.allclose(got.sum(axis=1), 1.0, atol=1e-12)
    assert np.allclose(got, expected, atol=1e-10)


def test_filtered_posteriors_are_causal():
    """The filtered posterior at bar t is invariant to bars strictly after t."""
    rng = np.random.RandomState(11)
    startprob = np.array([0.5, 0.3, 0.2])
    transmat = np.array([[0.6, 0.3, 0.1], [0.2, 0.6, 0.2], [0.1, 0.3, 0.6]])
    flp = np.log(rng.uniform(0.05, 1.0, size=(20, 3)))
    t0 = 9
    post_full = M.filtered_posteriors(startprob, transmat, flp)
    # Forward variable at t depends only on rows 0..t, so truncating the future must
    # leave rows 0..t0 identical.
    post_trunc = M.filtered_posteriors(startprob, transmat, flp[: t0 + 1])
    assert np.allclose(post_full[: t0 + 1], post_trunc, atol=1e-12)
