"""FIX-S3-004 — the 2% risk cap must be in ACCOUNT currency, not quote currency.

Every expected value below is hand-computed and written out in the docstring or
comment beside it. Units are the entire bug, so each assertion names the currency
it is asserting in.

Account: USD 10,000 · risk cap 2% = USD 200.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from fx_units import (
    Instrument,
    LEGACY_pip_distance,
    LEGACY_position_size_units,
    pip_distance,
    position_size_units,
    realised_risk_account_ccy,
)

RISK_USD = Decimal("200")

# quote_to_account_rate = value of 1 unit of quote currency in USD
EUR_USD = Instrument("EUR_USD", 4, Decimal("1.0"))            # quote USD
USD_JPY = Instrument("USD_JPY", 2, Decimal("1") / Decimal("150"))  # quote JPY @150
USD_CAD = Instrument("USD_CAD", 4, Decimal("1") / Decimal("1.36"))  # quote CAD @1.36
EUR_GBP = Instrument("EUR_GBP", 4, Decimal("1.27"))           # cross: quote GBP, GBPUSD 1.27


# --- USD-quoted pair: the case that accidentally worked ----------------------

def test_usd_quoted_pair_is_unchanged_by_the_fix():
    """EUR_USD, SL 0.0050 USD. 200 / 0.0050 = 40,000 units. Quote IS account."""
    sl = Decimal("0.0050")
    fixed = position_size_units(
        risk_capital_account_ccy=RISK_USD, sl_distance_quote_ccy=sl, instrument=EUR_USD
    )
    legacy = LEGACY_position_size_units(
        risk_capital_account_ccy=RISK_USD, sl_distance_quote_ccy=sl
    )
    assert fixed == 40_000
    assert legacy == 40_000, "USD-quoted pairs were coincidentally correct before"

    risk = realised_risk_account_ccy(units=fixed, sl_distance_quote_ccy=sl, instrument=EUR_USD)
    assert risk == Decimal("200.0000")  # USD


# --- JPY-quoted pair: the ~150x under-risk -----------------------------------

def test_jpy_pair_legacy_underrisks_by_the_fx_rate():
    """USD_JPY @150, ATR 0.30 JPY.

    Legacy: units = 200 / 0.30 = 666.
            loss  = 666 x 0.30 = 199.8 JPY = 199.8/150 = USD 1.332  <-- not $200.
    """
    sl = Decimal("0.30")
    legacy_units = LEGACY_position_size_units(
        risk_capital_account_ccy=RISK_USD, sl_distance_quote_ccy=sl
    )
    assert legacy_units == 666

    legacy_risk_usd = realised_risk_account_ccy(
        units=legacy_units, sl_distance_quote_ccy=sl, instrument=USD_JPY
    )
    # 666 * 0.30 / 150 = 1.332 USD
    assert legacy_risk_usd == pytest.approx(Decimal("1.332"), abs=Decimal("0.001"))
    assert legacy_risk_usd < RISK_USD / 100, "legacy risks <1% of the intended cap"


def test_jpy_pair_fixed_hits_the_intended_account_risk():
    """Correct: risk per unit = 0.30 JPY x (1/150) = 0.002 USD.
               units = 200 / 0.002 = 100,000.
               loss  = 100,000 x 0.30 = 30,000 JPY = USD 200.  <-- exactly the cap.
    """
    sl = Decimal("0.30")
    units = position_size_units(
        risk_capital_account_ccy=RISK_USD, sl_distance_quote_ccy=sl, instrument=USD_JPY
    )
    assert units == 100_000

    risk_usd = realised_risk_account_ccy(
        units=units, sl_distance_quote_ccy=sl, instrument=USD_JPY
    )
    assert risk_usd == pytest.approx(RISK_USD, abs=Decimal("0.01"))  # USD, not JPY


def test_jpy_fix_changes_size_by_the_fx_rate():
    """The correction factor is exactly the USDJPY rate — 150x more units."""
    sl = Decimal("0.30")
    legacy = LEGACY_position_size_units(
        risk_capital_account_ccy=RISK_USD, sl_distance_quote_ccy=sl
    )
    fixed = position_size_units(
        risk_capital_account_ccy=RISK_USD, sl_distance_quote_ccy=sl, instrument=USD_JPY
    )
    assert fixed / legacy == pytest.approx(150.0, rel=0.01)


# --- CAD-quoted pair: the ~1.36x error ---------------------------------------

def test_cad_pair_legacy_underrisks_by_the_cad_rate():
    """USD_CAD @1.36, SL 0.0040 CAD.

    Legacy: units = 200 / 0.0040 = 50,000. loss = 200 CAD = USD 147.06.
    Fixed : risk/unit = 0.0040/1.36 = 0.00294 USD; units = 68,000; loss = USD 200.
    """
    sl = Decimal("0.0040")
    legacy_units = LEGACY_position_size_units(
        risk_capital_account_ccy=RISK_USD, sl_distance_quote_ccy=sl
    )
    assert legacy_units == 50_000
    legacy_risk = realised_risk_account_ccy(
        units=legacy_units, sl_distance_quote_ccy=sl, instrument=USD_CAD
    )
    assert legacy_risk == pytest.approx(Decimal("147.06"), abs=Decimal("0.01"))  # USD

    fixed_units = position_size_units(
        risk_capital_account_ccy=RISK_USD, sl_distance_quote_ccy=sl, instrument=USD_CAD
    )
    assert fixed_units == 68_000
    assert realised_risk_account_ccy(
        units=fixed_units, sl_distance_quote_ccy=sl, instrument=USD_CAD
    ) == pytest.approx(RISK_USD, abs=Decimal("0.01"))


# --- cross pair: the case that OVER-risks ------------------------------------

def test_cross_pair_legacy_overrisks():
    """EUR_GBP, SL 0.0040 GBP, GBPUSD 1.27.

    Legacy: units = 200/0.0040 = 50,000. loss = 200 GBP = USD 254  <-- 27% OVER the cap.
    Fixed : risk/unit = 0.0040 x 1.27 = 0.00508 USD; units = 39,370; loss = USD 200.

    This is the direction that matters for account safety: the legacy formula does
    not merely under-size, it can breach the hard cap outright.
    """
    sl = Decimal("0.0040")
    legacy_units = LEGACY_position_size_units(
        risk_capital_account_ccy=RISK_USD, sl_distance_quote_ccy=sl
    )
    legacy_risk = realised_risk_account_ccy(
        units=legacy_units, sl_distance_quote_ccy=sl, instrument=EUR_GBP
    )
    assert legacy_risk == pytest.approx(Decimal("254.00"), abs=Decimal("0.01"))
    assert legacy_risk > RISK_USD, "legacy BREACHES the hard risk cap on cross pairs"

    fixed_units = position_size_units(
        risk_capital_account_ccy=RISK_USD, sl_distance_quote_ccy=sl, instrument=EUR_GBP
    )
    assert fixed_units == 39_370
    assert realised_risk_account_ccy(
        units=fixed_units, sl_distance_quote_ccy=sl, instrument=EUR_GBP
    ) <= RISK_USD, "the fix must never exceed the cap (rounds DOWN)"


# --- the invariant, stated once ----------------------------------------------

@pytest.mark.parametrize("inst", [EUR_USD, USD_JPY, USD_CAD, EUR_GBP])
def test_realised_risk_never_exceeds_the_cap_for_any_instrument(inst):
    sl = Decimal("0.0035") if inst.pip_decimal_places == 4 else Decimal("0.35")
    units = position_size_units(
        risk_capital_account_ccy=RISK_USD, sl_distance_quote_ccy=sl, instrument=inst
    )
    risk = realised_risk_account_ccy(units=units, sl_distance_quote_ccy=sl, instrument=inst)
    assert risk <= RISK_USD, f"{inst.name}: realised USD risk {risk} exceeds the cap"
    assert risk > RISK_USD * Decimal("0.999"), f"{inst.name}: wastefully under-risked"


# --- the cosmetic symptom that confirms the unit blindness -------------------

def test_pip_distance_is_wrong_by_100x_for_jpy_pairs_in_legacy():
    """`sl_distance * 10000` assumes every pair is 4-decimal."""
    sl = Decimal("0.30")  # JPY
    assert LEGACY_pip_distance(sl) == Decimal("3000")     # claims 3000 pips
    assert pip_distance(sl_distance_quote_ccy=sl, instrument=USD_JPY) == Decimal("30")
    # 0.30 JPY on a 2-decimal pair is 30 pips, not 3000.


def test_pip_distance_correct_for_four_decimal_pairs():
    sl = Decimal("0.0050")
    assert LEGACY_pip_distance(sl) == Decimal("50")
    assert pip_distance(sl_distance_quote_ccy=sl, instrument=EUR_USD) == Decimal("50")


# --- guards -------------------------------------------------------------------

def test_zero_or_negative_sl_is_rejected():
    for bad in (Decimal("0"), Decimal("-0.001")):
        with pytest.raises(ValueError):
            position_size_units(
                risk_capital_account_ccy=RISK_USD,
                sl_distance_quote_ccy=bad,
                instrument=EUR_USD,
            )


def test_missing_conversion_rate_is_rejected_not_defaulted():
    """A rate of 0 must raise, never silently behave like the old code."""
    broken = Instrument("BROKEN", 4, Decimal("0"))
    with pytest.raises(ValueError):
        position_size_units(
            risk_capital_account_ccy=RISK_USD,
            sl_distance_quote_ccy=Decimal("0.005"),
            instrument=broken,
        )
