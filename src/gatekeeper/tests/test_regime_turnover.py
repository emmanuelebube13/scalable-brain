"""FIX-S1-010 — per-regime turnover band guard.

The aggregate band could sit comfortably mid-range while one regime starved to zero
approval, silently stopping trading in that market condition with nothing in the manifest
or logs recording it. These tests pin the per-regime enforcement.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.gatekeeper import train as T


def _frame(regimes: Dict[str, int]) -> pd.DataFrame:
    """Build a calibration-tail-shaped frame from {regime: n_rows}."""
    regs = []
    for reg, n in regimes.items():
        regs += [reg] * n
    df = pd.DataFrame(
        {
            "regime_structural": regs,
            "r_multiple": np.zeros(len(regs)),
        }
    )
    # Mirror the real call site: cal_df is frame.iloc[cut:], so the index does NOT start
    # at 0. A positional/label mix-up here is exactly the kind of bug that would make the
    # guard silently measure the wrong rows.
    df.index = np.arange(1000, 1000 + len(df))
    return df


def test_per_regime_approval_is_index_safe():
    df = _frame({"Ranging": 40, "Trending-Up": 40})
    # Ranging (first 40 rows) all approve; Trending-Up none do.
    scores = np.concatenate([np.full(40, 0.9), np.full(40, 0.1)])
    out = T.per_regime_approval(df, scores, {"fallback": 0.5})

    assert out["Ranging"]["approval"] == 1.0
    assert out["Trending-Up"]["approval"] == 0.0
    assert out["Ranging"]["n"] == 40


def test_starved_regime_is_flagged():
    approvals = {
        "Ranging": {"n": 5000, "approval": 0.30},
        "Trending-Up": {"n": 3000, "approval": 0.001},  # starved
    }
    problems = T.check_regime_turnover(approvals)
    assert len(problems) == 1 and "Trending-Up" in problems[0]


def test_saturated_regime_is_flagged():
    approvals = {"High-Vol": {"n": 500, "approval": 0.95}}
    problems = T.check_regime_turnover(approvals)
    assert len(problems) == 1 and "High-Vol" in problems[0]


def test_thin_regime_is_not_guarded():
    """Below MIN_REGIME_N the approval estimate is noise — failing on it would be a coin
    flip, not a safety guarantee. It is reported but must not fail the run."""
    approvals = {
        "Ranging": {"n": 5000, "approval": 0.30},
        "High-Vol": {"n": T.MIN_REGIME_N - 1, "approval": 0.0},
    }
    assert T.check_regime_turnover(approvals) == []


def test_observed_2026_07_24_calibration_passes():
    """The real recalibrated model must pass: this guard closes a LATENT gap, and if it
    rejected the model that motivated the fix, the band would be miscalibrated."""
    approvals = {
        "High-Vol": {"n": 1450, "approval": 0.3959},
        "Ranging": {"n": 13420, "approval": 0.3052},
        "Trending-Down": {"n": 9021, "approval": 0.1043},
        "Trending-Up": {"n": 3013, "approval": 0.0660},
    }
    assert T.check_regime_turnover(approvals) == []


def test_aggregate_can_pass_while_a_regime_starves():
    """The exact hole this closes: aggregate mid-band, one regime at zero."""
    approvals = {
        "Ranging": {"n": 9000, "approval": 0.50},
        "Trending-Up": {"n": 1000, "approval": 0.00},
    }
    aggregate = (9000 * 0.50 + 1000 * 0.0) / 10000  # 0.45 — comfortably inside the band
    from src.gatekeeper import thresholds as TH

    assert not TH.is_degenerate(aggregate, T.MIN_TURNOVER, T.MAX_TURNOVER)
    assert T.check_regime_turnover(approvals)  # ...but the per-regime guard catches it


@pytest.mark.parametrize("rate", [T.MIN_TURNOVER, T.MAX_TURNOVER])
def test_band_edges_are_inclusive(rate):
    assert T.check_regime_turnover({"Ranging": {"n": 100, "approval": rate}}) == []
