"""FIX-S3-002 — "25% portfolio exposure" must be a fraction of equity, not a count.

The legacy gate compares `len(open_positions)` against `0.25 * 10` and reports
`count / 10` as "exposure_pct". These tests demonstrate that the reported number
is completely independent of position size — the defining property of the bug.

Account equity: USD 10,000.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from fx_units import (
    Instrument,
    LEGACY_exposure_pct,
    OpenPosition,
    exposure_gate,
    portfolio_exposure_pct,
)

EQUITY = Decimal("10000")
EUR_USD = Instrument("EUR_USD", 4, Decimal("1.0"))
USD_JPY = Instrument("USD_JPY", 2, Decimal("1") / Decimal("150"))

MAX_EXPOSURE = Decimal("0.25")


def tiny():
    """1,000 units of EUR_USD @1.10 = USD 1,100 notional = 11% of equity."""
    return OpenPosition(EUR_USD, 1_000, Decimal("1.10"))


def huge():
    """100,000 units of EUR_USD @1.10 = USD 110,000 notional = 1100% of equity."""
    return OpenPosition(EUR_USD, 100_000, Decimal("1.10"))


# --- the defining defect ------------------------------------------------------

def test_legacy_reports_identical_exposure_for_wildly_different_sizes():
    """Two $1,100 positions and two $110,000 positions both report 0.2.

    This single assertion is the whole bug: the number the risk gate acts on
    does not depend on how much money is at risk.
    """
    small = [tiny(), tiny()]
    massive = [huge(), huge()]
    assert LEGACY_exposure_pct(small) == LEGACY_exposure_pct(massive) == Decimal("0.2")

    # The true fractions differ by 100x.
    assert portfolio_exposure_pct(small, EQUITY) == pytest.approx(
        Decimal("0.22"), abs=Decimal("0.0001")
    )
    assert portfolio_exposure_pct(massive, EQUITY) == pytest.approx(
        Decimal("22.0"), abs=Decimal("0.01")
    )


def test_legacy_approves_a_2200_percent_exposure():
    """Two maximal positions = 2200% of equity, and the legacy gate lets them through.

    Legacy fires only at the 3rd position (count >= 2.5), so any two positions of
    any size are approved.
    """
    massive = [huge(), huge()]
    assert LEGACY_exposure_pct(massive) == Decimal("0.2")
    assert LEGACY_exposure_pct(massive) < MAX_EXPOSURE, "legacy would APPROVE this"

    approved, exposure, reason = exposure_gate(massive, EQUITY,
                                               max_total_exposure_pct=MAX_EXPOSURE)
    assert approved is False
    assert exposure > Decimal("20")
    assert "exceeds cap" in reason


# --- the corrected gate -------------------------------------------------------

def test_exposure_is_a_true_fraction_of_equity():
    """1,000 units EUR_USD @1.10 = $1,100 / $10,000 = 0.11 exactly."""
    assert portfolio_exposure_pct([tiny()], EQUITY) == pytest.approx(
        Decimal("0.11"), abs=Decimal("0.0001")
    )


def test_gate_approves_below_the_cap_and_rejects_above():
    """Two 11% positions = 22% < 25% -> approve. Three = 33% > 25% -> reject."""
    two = [tiny(), tiny()]
    approved, exposure, _ = exposure_gate(two, EQUITY, max_total_exposure_pct=MAX_EXPOSURE)
    assert approved is True
    assert exposure == pytest.approx(Decimal("0.22"), abs=Decimal("0.0001"))

    three = [tiny(), tiny(), tiny()]
    approved, exposure, reason = exposure_gate(three, EQUITY,
                                               max_total_exposure_pct=MAX_EXPOSURE)
    assert approved is False
    assert exposure == pytest.approx(Decimal("0.33"), abs=Decimal("0.0001"))
    assert "exceeds cap" in reason


def test_one_oversized_position_is_rejected_where_legacy_approved_it():
    """A single 1100% position. Legacy reports 0.1 and approves; the fix rejects."""
    one = [huge()]
    assert LEGACY_exposure_pct(one) == Decimal("0.1")  # "10% exposure" — fiction

    approved, exposure, _ = exposure_gate(one, EQUITY, max_total_exposure_pct=MAX_EXPOSURE)
    assert approved is False
    assert exposure == pytest.approx(Decimal("11.0"), abs=Decimal("0.01"))


def test_notional_uses_the_quote_conversion_for_non_usd_pairs():
    """10,000 units USD_JPY @150 = 1,500,000 JPY = USD 10,000 = 100% of equity.

    Ties FIX-S3-002 to FIX-S3-004: exposure is meaningless without the same
    quote->account conversion the sizing formula was missing.
    """
    pos = OpenPosition(USD_JPY, 10_000, Decimal("150.00"))
    assert pos.notional_account_ccy == pytest.approx(Decimal("10000"), abs=Decimal("0.01"))
    assert portfolio_exposure_pct([pos], EQUITY) == pytest.approx(
        Decimal("1.0"), abs=Decimal("0.0001")
    )


# --- the count cap is preserved, but named honestly ---------------------------

def test_count_cap_still_available_as_its_own_parameter():
    """Behaviour must never be weaker than today: the count cap survives.

    Three tiny positions are 33% and would be rejected on exposure anyway, so use
    positions small enough to pass the fraction test and prove the count cap
    fires independently.
    """
    small = [OpenPosition(EUR_USD, 100, Decimal("1.10"))] * 3  # 3 x $110 = 3.3%
    approved, exposure, _ = exposure_gate(small, EQUITY, max_total_exposure_pct=MAX_EXPOSURE)
    assert approved is True, "well under the exposure cap"

    approved, _, reason = exposure_gate(
        small, EQUITY, max_total_exposure_pct=MAX_EXPOSURE, max_concurrent_positions=3
    )
    assert approved is False
    assert "concurrent position count" in reason


def test_no_magic_ten():
    """The `* 10` / `/ 10` fudge must be gone: exposure of an empty book is 0."""
    assert portfolio_exposure_pct([], EQUITY) == Decimal(0)
    assert LEGACY_exposure_pct([]) == Decimal(0)  # the one case they agree on


def test_zero_equity_is_rejected_not_divided_by():
    with pytest.raises(ValueError):
        portfolio_exposure_pct([tiny()], Decimal("0"))
