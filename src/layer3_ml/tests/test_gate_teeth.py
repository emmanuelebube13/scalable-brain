"""FIX-S1-008 Fix 3 — the gates must be able to reject.

Before Fix 3, ``choose_threshold`` fabricated an adaptive/percentile threshold
when no threshold satisfied the gates, and ``MIN_EXPECTANCY_UNIT_R`` was -0.05, so
a negative-expectancy model still slipped through. These tests assert the gates
now fire: no positive-expectancy threshold -> ``None`` (candidate dropped), and a
-0.02R model is flagged degenerate.
"""

from __future__ import annotations

import os
import sys

import numpy as np

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.layer3_ml.training.train_ml_gatekeeper import (  # noqa: E402
    MAX_TURNOVER,
    MIN_EXPECTANCY_UNIT_R,
    MIN_TURNOVER,
    choose_threshold,
    compute_trading_metrics,
    is_degenerate_metrics,
)


def _labels():
    # 80 winners / 120 losers -> 0.40 base win rate.
    return np.array([1] * 80 + [0] * 120)


def test_expectancy_gate_default_is_non_negative():
    """The relaxed -0.05 allowance was removed (Fix 3.1)."""
    assert MIN_EXPECTANCY_UNIT_R == 0.0


def test_choose_threshold_returns_none_when_no_positive_expectancy():
    """Contract: anti-correlated scores -> no gate-satisfying threshold -> None.

    Confirms the fabrication path is gone: choose_threshold never invents a
    threshold for a model with no positive-expectancy operating point (the caller
    then drops it). The behavioural flip that lets a -0.02R model be *rejected*
    (previously promoted) is proven by ``test_expectancy_gate_default_is_non_negative``
    and ``test_is_degenerate_flags_negative_expectancy``.
    """
    rng = np.random.default_rng(0)
    y = _labels()
    # Winners get LOW scores, losers HIGH scores (strictly separated).
    prob = np.where(
        y == 1, rng.uniform(0.05, 0.35, y.size), rng.uniform(0.55, 0.90, y.size)
    )

    t = choose_threshold(y, prob, min_expectancy=0.0)
    assert t is None, f"gate failed to fire: got threshold {t} on a no-edge model"


def test_choose_threshold_finds_valid_threshold_when_edge_exists():
    """Positive control: a real edge yields a gate-satisfying threshold."""
    rng = np.random.default_rng(1)
    y = _labels()
    prob = np.where(
        y == 1, rng.uniform(0.60, 0.95, y.size), rng.uniform(0.05, 0.40, y.size)
    )

    t = choose_threshold(y, prob, min_expectancy=0.0)
    assert t is not None, "gate rejected a genuinely profitable model"

    m = compute_trading_metrics(y, prob, t)
    assert m["expectancy_unit_r"] > 0.0
    assert MIN_TURNOVER <= m["turnover"] <= MAX_TURNOVER


def test_is_degenerate_flags_negative_expectancy():
    """A -0.02R candidate is degenerate (previously promotable at -0.05 gate)."""
    bad = {"turnover": 0.20, "expectancy_unit_r": -0.02}
    good = {"turnover": 0.20, "expectancy_unit_r": 0.02}
    assert is_degenerate_metrics(bad, MIN_TURNOVER, MAX_TURNOVER, 0.0) is True
    assert is_degenerate_metrics(good, MIN_TURNOVER, MAX_TURNOVER, 0.0) is False


def test_is_degenerate_flags_zero_expectancy_and_turnover_bounds():
    """Exactly-zero expectancy is degenerate (strict >), as are turnover breaches."""
    assert (
        is_degenerate_metrics(
            {"turnover": 0.20, "expectancy_unit_r": 0.0},
            MIN_TURNOVER,
            MAX_TURNOVER,
            0.0,
        )
        is True
    )
    assert (
        is_degenerate_metrics(
            {"turnover": 0.0, "expectancy_unit_r": 0.5}, MIN_TURNOVER, MAX_TURNOVER, 0.0
        )
        is True
    )
    assert (
        is_degenerate_metrics(
            {"turnover": 0.99, "expectancy_unit_r": 0.5},
            MIN_TURNOVER,
            MAX_TURNOVER,
            0.0,
        )
        is True
    )
