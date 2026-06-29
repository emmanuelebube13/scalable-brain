"""MODEL-006 threshold-calibration + OOS-uplift unit tests (no DB/network/model)."""
from __future__ import annotations

import numpy as np

from src.system1.gatekeeper import thresholds as TH


def test_approval_rate():
    assert TH.approval_rate([0.1, 0.6, 0.9], 0.5) == 2 / 3


def test_calibrate_respects_turnover_band():
    rng = np.random.RandomState(0)
    scores = rng.uniform(0, 1, 1000)
    # returns higher for higher scores → threshold should be > 0 and approval in band
    returns = (scores - 0.5) + rng.normal(0, 0.1, 1000)
    thr, rate = TH.calibrate_threshold(scores, returns, min_turnover=0.1, max_turnover=0.5)
    assert 0.1 <= rate <= 0.5


def test_uplift_significant_when_separated():
    rng = np.random.RandomState(1)
    approved = rng.normal(0.5, 1.0, 500)   # higher mean
    rejected = rng.normal(-0.5, 1.0, 500)  # lower mean
    uplift, p, sig = TH.oos_uplift_test(approved, rejected, n_bootstrap=2000)
    assert uplift > 0 and sig and p < 0.05


def test_uplift_not_significant_when_same():
    rng = np.random.RandomState(2)
    a = rng.normal(0.0, 1.0, 500)
    b = rng.normal(0.0, 1.0, 500)
    _, p, sig = TH.oos_uplift_test(a, b, n_bootstrap=2000)
    assert not sig


def test_degenerate_detection():
    assert TH.is_degenerate(0.0, 0.05, 0.60)   # approves none
    assert TH.is_degenerate(1.0, 0.05, 0.60)   # approves all
    assert not TH.is_degenerate(0.3, 0.05, 0.60)
