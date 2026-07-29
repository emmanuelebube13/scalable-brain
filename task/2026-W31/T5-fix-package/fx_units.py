"""Reference implementation of the two unit-correct money-layer calculations.

This module is the *specification* for FIX-S3-002 and FIX-S3-004, expressed as
pure arithmetic with no I/O, no broker, and no System-3 imports. It exists so
the corrected formulas can be proven on this machine — testing arithmetic is not
"running System 3".

Apply the equivalent change on Computer 3 as described in `APPLY.md`; the tests
in this package pin the expected numbers.

Both defects share one root cause: **a quantity's units were never written down**,
so a count was compared against a percentage and a quote-currency amount was
treated as account currency.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

# --- FIX-S3-004: risk cap must be expressed in ACCOUNT currency ---------------


@dataclass(frozen=True)
class Instrument:
    """Everything sizing needs to know about an instrument's units.

    `quote_to_account_rate` is the value of 1 unit of the quote currency in
    account currency. For a USD account:
      EUR_USD -> quote USD -> 1.0
      USD_JPY -> quote JPY -> 1/USDJPY  (e.g. 1/150 = 0.006667)
      USD_CAD -> quote CAD -> 1/USDCAD  (e.g. 1/1.36 = 0.735294)
      EUR_GBP -> quote GBP -> GBPUSD    (e.g. 1.27)
    """

    name: str
    pip_decimal_places: int  # 4 for most pairs, 2 for JPY-quoted
    quote_to_account_rate: Decimal

    @property
    def pip_size(self) -> Decimal:
        return Decimal(1).scaleb(-self.pip_decimal_places)


def position_size_units(
    *,
    risk_capital_account_ccy: Decimal,
    sl_distance_quote_ccy: Decimal,
    instrument: Instrument,
) -> int:
    """Units such that the loss at stop equals the intended ACCOUNT-currency risk.

    The defect (`oanda_executor.py:246`):

        units = risk_capital / sl_distance          # WRONG

    `risk_capital` is account currency; `sl_distance` is a price difference, i.e.
    quote currency per unit. Dividing them yields units only if quote == account.
    For USD_JPY the "$200 risk" became 200 JPY (~$1.33) — ~150x under-risked. For
    USD_CAD, 200 CAD (~$147).

    Correct:

        loss_account = units * sl_distance_quote * quote_to_account_rate
        => units = risk_capital_account / (sl_distance_quote * quote_to_account_rate)

    Rounded DOWN so the realised risk never exceeds the cap.
    """
    if sl_distance_quote_ccy <= 0:
        raise ValueError("stop-loss distance must be positive")
    if instrument.quote_to_account_rate <= 0:
        raise ValueError("quote_to_account_rate must be positive")

    risk_per_unit_account = sl_distance_quote_ccy * instrument.quote_to_account_rate
    units = risk_capital_account_ccy / risk_per_unit_account
    return int(units.quantize(Decimal("1"), rounding=ROUND_DOWN))


def realised_risk_account_ccy(
    *, units: int, sl_distance_quote_ccy: Decimal, instrument: Instrument
) -> Decimal:
    """What the position actually loses, in ACCOUNT currency, if the stop is hit.

    This is the invariant the cap is supposed to enforce. Any sizing formula can
    be checked against it.
    """
    return Decimal(units) * sl_distance_quote_ccy * instrument.quote_to_account_rate


def pip_distance(*, sl_distance_quote_ccy: Decimal, instrument: Instrument) -> Decimal:
    """SL distance in pips, using the instrument's own pip size.

    The defect (`oanda_executor.py:402`) hardcoded `* 10000`, which is wrong by
    100x for JPY-quoted pairs.
    """
    return sl_distance_quote_ccy / instrument.pip_size


# --- FIX-S3-002: exposure must be a fraction of equity, not a position count ---


@dataclass(frozen=True)
class OpenPosition:
    """A live position, carrying the size the exposure gate actually needs."""

    instrument: Instrument
    units: int
    entry_price: Decimal  # quote currency per unit

    @property
    def notional_account_ccy(self) -> Decimal:
        return (
            Decimal(self.units)
            * self.entry_price
            * self.instrument.quote_to_account_rate
        )


def portfolio_exposure_pct(
    positions: list[OpenPosition], account_equity: Decimal
) -> Decimal:
    """Summed notional as a true fraction of equity.

    The defect (`live_pipeline.py:1108-1112`):

        total_exposure = len(open_positions)              # a COUNT
        if total_exposure >= MAX_TOTAL_EXPOSURE_PCT * 10: # >= 2.5 -> fires at 3
            exposure_pct = total_exposure / 10            # 2 positions -> "0.2"

    No position's size was ever summed, so "25% exposure" actually meant "reject
    the 3rd position" regardless of whether those positions risked $10 or
    $10,000. The `* 10` and `/ 10` were a fabricated unit bridge between a count
    and a percentage.
    """
    if account_equity <= 0:
        raise ValueError("account equity must be positive")
    return sum(
        (p.notional_account_ccy for p in positions), Decimal(0)
    ) / account_equity


def exposure_gate(
    positions: list[OpenPosition],
    account_equity: Decimal,
    *,
    max_total_exposure_pct: Decimal = Decimal("0.25"),
    max_concurrent_positions: int | None = None,
) -> tuple[bool, Decimal, str]:
    """Return (approved, exposure_pct, reason).

    The count cap is kept as its own explicitly-named parameter so behaviour is
    never *weaker* than today, but it is no longer smuggled inside a constant
    whose name says "percent".
    """
    exposure = portfolio_exposure_pct(positions, account_equity)
    if exposure > max_total_exposure_pct:
        return (
            False,
            exposure,
            f"portfolio exposure {exposure:.4f} exceeds cap {max_total_exposure_pct}",
        )
    if max_concurrent_positions is not None and len(positions) >= max_concurrent_positions:
        return (
            False,
            exposure,
            f"concurrent position count {len(positions)} at cap {max_concurrent_positions}",
        )
    return True, exposure, "approved"


# --- the defective originals, for red-before evidence -------------------------


def LEGACY_position_size_units(
    *, risk_capital_account_ccy: Decimal, sl_distance_quote_ccy: Decimal
) -> int:
    """Verbatim logic of `oanda_executor.calculate_position_size` step 6."""
    if sl_distance_quote_ccy == 0:
        raise ValueError("Stop loss distance cannot be zero")
    units = risk_capital_account_ccy / sl_distance_quote_ccy
    return max(1, int(units.quantize(Decimal("1"), rounding=ROUND_DOWN)))


def LEGACY_exposure_pct(positions: list[OpenPosition]) -> Decimal:
    """Verbatim logic of `live_pipeline.evaluate_correlation_gate`."""
    return Decimal(len(positions)) / Decimal(10)


def LEGACY_pip_distance(sl_distance_quote_ccy: Decimal) -> Decimal:
    """Verbatim logic of `oanda_executor.py:402`."""
    return sl_distance_quote_ccy * Decimal("10000")
