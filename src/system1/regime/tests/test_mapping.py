"""Unit tests for MODEL-003 pure regime helpers (no DB / no network)."""
from __future__ import annotations

import numpy as np

from src.system1.regime import mapping as M

FN = ["atr_14", "adx_14", "volatility_20", "returns_1"]


def test_map_states_deterministic_and_complete():
    # rows: [atr, adx, vol, ret]
    means = np.array(
        [
            [0.1, 20, 0.1, 0.002],   # up: positive return, low vol
            [0.1, 20, 0.1, -0.002],  # down: negative return
            [0.1, 20, 0.1, 0.0],     # ranging: ~0 return
            [0.9, 30, 0.9, 0.0],     # high-vol: highest vol+atr
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
