"""Unit tests for MODEL-003 pure regime helpers (no DB / no network)."""

from __future__ import annotations

import numpy as np

from src.system1.regime import mapping as M

FN = ["atr_14", "adx_14", "volatility_20", "returns_1"]


def test_map_states_deterministic_and_complete():
    # rows: [atr, adx, vol, ret]
    means = np.array(
        [
            [0.1, 20, 0.1, 0.002],  # up: positive return, low vol
            [0.1, 20, 0.1, -0.002],  # down: negative return
            [0.1, 20, 0.1, 0.0],  # ranging: ~0 return
            [0.9, 30, 0.9, 0.0],  # high-vol: highest vol+atr
        ]
    )
    m = M.map_states_to_labels(means, FN)
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
