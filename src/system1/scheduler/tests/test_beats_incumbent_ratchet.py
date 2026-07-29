"""FIX-S1-011 — the `beats_incumbent` gate must not ratchet.

Background. The gate was `candidate_accuracy >= incumbent_accuracy`, and every
promotion republishes the challenger's own accuracy as the next baseline. That
makes the baseline monotonically non-decreasing — a high-water mark over a
*noisy* estimate, which converges on the luckiest draw ever observed and then
blocks everything behind it, including genuinely better models that happened to
sample lower.

It had never bound in production: all three real retrains (2026-07-01, 07-19,
07-26) promoted through the fail-open branch because the incumbent could not be
resolved. By 2026-07-29 `system1/latest.json` resolved correctly with
`regime_accuracy: 0.965`, so the next retrain would have been the first to
enforce it — against a bar that had climbed 0.717 → 0.8603 → 0.965.

See `task/2026-W31/deliverables/T3/`.
"""

from __future__ import annotations

import pytest

from src.system1.scheduler.orchestrator import (
    BEATS_INCUMBENT_TOLERANCE,
    REGIME_ACCURACY_FLOOR,
    deployment_gates,
)


def candidate(acc, *, uplift=0.04, significant=True, n_qualified=4):
    return {
        "regime_accuracy": acc,
        "oos_uplift": uplift,
        "oos_uplift_significant": significant,
        "n_qualified_strategies": n_qualified,
    }


def incumbent(acc):
    return {"metrics": {"regime_accuracy": acc}, "resolution": "prefixed"}


# --- the three cases T3 asks for ---------------------------------------------

def test_strictly_better_challenger_promotes():
    passed, gates = deployment_gates(candidate(0.98), incumbent(0.965))
    assert gates["beats_incumbent"] is True
    assert passed


def test_marginally_worse_challenger_does_not_flap():
    """Inside the band the incumbent is retained rather than churned."""
    # 0.95 is a ~1.6% regression on 0.965 — noise, not decay.
    passed, gates = deployment_gates(candidate(0.95), incumbent(0.965))
    assert gates["beats_incumbent"] is True, (
        "a sub-tolerance regression should not block promotion; blocking on noise "
        "is what makes the bar ratchet"
    )
    assert passed


def test_three_successive_promotions_do_not_raise_the_bar():
    """The bar must track the LIVE incumbent, never a historical maximum.

    Simulates the ratchet directly: each promoted challenger becomes the next
    incumbent. Under the old bare `>=` the required accuracy could only climb.
    """
    live = 0.965
    required_over_time = []

    # A noisy but non-improving sequence — exactly what defeats a high-water mark.
    for drawn in (0.98, 0.955, 0.97):
        required = live * BEATS_INCUMBENT_TOLERANCE
        required_over_time.append(required)
        passed, gates = deployment_gates(candidate(drawn), incumbent(live))
        assert gates["beats_incumbent"] is True, f"{drawn} blocked against live {live}"
        assert passed
        live = drawn  # promotion republishes the challenger's own metric

    # The requirement never exceeds the live incumbent scaled by the tolerance,
    # and crucially does not compound upward across promotions.
    assert max(required_over_time) <= 0.98 * BEATS_INCUMBENT_TOLERANCE
    assert required_over_time[-1] < required_over_time[0] or required_over_time[-1] <= 0.98 * BEATS_INCUMBENT_TOLERANCE


# --- the ratchet itself, stated as an invariant -------------------------------

def test_the_bar_can_fall_not_only_rise():
    """The defining anti-ratchet property."""
    high = deployment_gates(candidate(0.99), incumbent(0.99))[1]["beats_incumbent_detail"]
    after_decline = deployment_gates(candidate(0.90), incumbent(0.93))[1][
        "beats_incumbent_detail"
    ]
    assert after_decline["required"] < high["required"], (
        "once a lower model is live the bar must come down with it; a bar that only "
        "climbs is the ratchet"
    )


def test_real_regression_is_still_blocked():
    """Tolerance is for noise, not for decay."""
    passed, gates = deployment_gates(candidate(0.80), incumbent(0.965))
    assert gates["beats_incumbent"] is False
    assert not passed


def test_downward_drift_is_bounded_by_the_absolute_floor():
    """Repeated in-band regressions must not walk the model below the floor."""
    live = REGIME_ACCURACY_FLOOR + 0.01
    drawn = live * BEATS_INCUMBENT_TOLERANCE  # in-band, but under the absolute floor
    passed, gates = deployment_gates(candidate(drawn), incumbent(live))
    assert gates["beats_incumbent"] is True, "in-band by construction"
    assert gates["regime_accuracy_ok"] is False, "the absolute floor must catch it"
    assert not passed, "the floor bounds any downward drift the band allows"


# --- fail-open / fail-closed semantics ----------------------------------------

def test_missing_incumbent_fails_open_but_absolute_gates_still_bind():
    passed, gates = deployment_gates(candidate(0.75), {"resolution": "absent"})
    assert gates["beats_incumbent"] is True
    assert passed

    # ...but a candidate that fails an absolute gate gets no free ride.
    passed, gates = deployment_gates(
        candidate(0.60), {"resolution": "absent"}
    )
    assert gates["beats_incumbent"] is True
    assert gates["regime_accuracy_ok"] is False
    assert not passed


def test_missing_candidate_accuracy_fails_closed():
    """An unmeasurable challenger must never pass a comparison gate."""
    passed, gates = deployment_gates(candidate(None), incumbent(0.965))
    assert gates["beats_incumbent"] is False
    assert not passed


# --- the detail block must not be able to pass a gate -------------------------

def test_detail_block_is_evidence_not_a_gate():
    _, gates = deployment_gates(candidate(0.80), incumbent(0.965))
    assert isinstance(gates["beats_incumbent_detail"], dict)
    # A truthy dict must not be counted as a passing gate.
    assert deployment_gates(candidate(0.80), incumbent(0.965))[0] is False


def test_detail_records_the_required_number():
    _, gates = deployment_gates(candidate(0.98), incumbent(0.965))
    d = gates["beats_incumbent_detail"]
    assert d["incumbent_regime_accuracy"] == 0.965
    assert d["candidate_regime_accuracy"] == 0.98
    assert d["required"] == pytest.approx(0.965 * BEATS_INCUMBENT_TOLERANCE, abs=1e-6)
