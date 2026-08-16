"""GOLDEN FIXTURE — strong_weak_analysis (SPEC-strong_weak_analysis.md).

Every expected number is derived from the spec's formulas before the code was run,
and the arithmetic is shown so a reviewer can check it against the spec.

The bars are built so the ATR is exact rather than approximate. Each bar carries
``High = Close + 20 pip`` and ``Low = Close - 20 pip`` and no close moves more than
20 pip, so the true range of every bar is exactly ``High - Low = 40 pip``:
``|High - Close_prev| <= 40 pip`` and ``|Low - Close_prev| <= 40 pip`` can never
exceed it. An EWM of a constant series is that constant, so **ATR(14) = 0.00400 on
every bar**, which makes §4.4's entry zone exactly 10 pip (0.25 x ATR) and §6's
stop offset exactly 40 pip (1.0 x ATR).

The fixture subclasses the strategy to shrink TREND_PERIOD 50 -> 3, STALENESS_BARS
60 -> 8 and warmup 55 -> 10. Periods only — no formula, threshold, level or
multiple is touched. SWING_PERIOD stays at the production 5, so the confirmation
lag under test is the real one.

The cross-sectional helpers (§3) are tested directly: they are unreachable from
``generate_orders`` by design (see the module docstring), so a fixture that only
exercised the order path would leave the spec's headline mechanism unpinned.
"""

from __future__ import annotations

from typing import Dict, List

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.strong_weak_analysis import (
    StrongWeakAnalysis,
    candidate_instrument,
    currency_strength,
    twenty_bar_return,
)

PIP = 0.0001
BAND = 20 * PIP  # High/Low offset on every bar -> TR = 40 pip, ATR = 0.00400
ATR = 40 * PIP

# ---------------------------------------------------------------------------
# 1. The bars, and why these bars
# ---------------------------------------------------------------------------
# 40 D1 closes. Two setups, one per direction, with everything else deliberately
# out of reach of a signal:
#   bars 3-10   a decline into the swing low at bar 10 (Low 1.09000)
#   bars 11-15  a shallow bounce whose lows all hold above it -> the swing
#               CONFIRMS at bar 15 (occurrence 10 + SWING_PERIOD 5)
#   bar 16      dips into the entry zone but closes DOWN -> §4.2 trend gate blocks
#   bar 17      dips into the zone and closes up -> THE LONG
#   bars 21-25  a rally to the swing high at bar 25 (High 1.10750)
#   bars 26-30  a shallow dip whose highs all hold below it -> CONFIRMS at bar 30
#   bar 32      rallies back into the zone and closes down -> THE SHORT
#   bars 33-39  a steady decline; every structure level is either stale or far away
CLOSES = [
    1.1000,
    1.1000,
    1.1000,
    1.0990,
    1.0980,
    1.0970,
    1.0960,
    1.0950,
    1.0945,
    1.0940,
    1.0920,  # bar 10 — swing low, Low = 1.09000
    1.0930,
    1.0940,
    1.0940,
    1.0935,
    1.0930,  # bar 15 — the swing low confirms here
    1.0910,  # bar 16 — in the zone, but closes down
    1.0925,  # bar 17 — THE LONG
    1.0945,
    1.0965,
    1.0985,
    1.1005,
    1.1020,
    1.1030,
    1.1040,
    1.1055,  # bar 25 — swing high, High = 1.10750
    1.1045,
    1.1040,
    1.1035,
    1.1040,
    1.1045,  # bar 30 — the swing high confirms here
    1.1060,
    1.1050,  # bar 32 — THE SHORT
    1.1035,
    1.1020,
    1.1005,
    1.0990,
    1.0975,
    1.0960,
    1.0945,
]


class _FixtureScale(StrongWeakAnalysis):
    """Production logic, fixture-sized lookbacks (periods only)."""

    TREND_PERIOD = 3
    STALENESS_BARS = 8

    @property
    def warmup_bars(self) -> int:
        return 10


class _TightStaleness(_FixtureScale):
    """Same bars, staleness tightened to 5 — the bar-17 level is 7 bars old."""

    STALENESS_BARS = 5


@pytest.fixture(scope="module")
def frames() -> Dict[str, pd.DataFrame]:
    idx = pd.date_range("2021-03-01 21:00", periods=len(CLOSES), freq="B", tz="UTC")
    d1 = pd.DataFrame(
        {
            "Open": CLOSES,
            "High": [c + BAND for c in CLOSES],
            "Low": [c - BAND for c in CLOSES],
            "Close": CLOSES,
            "Volume": 1.0,
        },
        index=idx,
    )
    return {"D1": d1}


@pytest.fixture(scope="module")
def orders(frames: Dict[str, pd.DataFrame]) -> List:
    return list(_FixtureScale().generate_orders(frames))


def _bar(n: int) -> pd.Timestamp:
    return pd.date_range("2021-03-01 21:00", periods=len(CLOSES), freq="B", tz="UTC")[n]


# ---------------------------------------------------------------------------
# 2 + 3. Expected values, computed by hand, then asserted
# ---------------------------------------------------------------------------


def test_emits_exactly_the_two_expected_setups(orders) -> None:
    """§4/§5: one long, one short, and nothing else in 40 bars.

    Bar 16 is the control: Low = 1.08900 is inside the zone and its close 1.09100
    is above S, so §4.3 and §4.4 both hold — but SMA(3) at bar 16 is
    (1.09350 + 1.09300 + 1.09100)/3 = 1.09250 and the close is below it, so §4.2
    refuses. If the trend gate were dropped this test fails with three orders.
    """
    assert [(o.decision_bar, o.direction) for o in orders] == [
        (_bar(17), 1),
        (_bar(32), -1),
    ]


def test_long_matches_hand_computed_arithmetic(orders) -> None:
    """The bar-17 trade plan, from §4, §6 and §7.

    §4.3 S      = Low of the swing-low bar 10 = 1.09200 - 0.00200 = 1.09000,
                  confirmed at bar 15 (occurrence 10 + lag 5), age at bar 17 = 7
    §4.4 zone   = 0.25 x ATR = 0.25 x 0.00400 = 0.00100
                  Low[17] = 1.09250 - 0.00200 = 1.09050 <= 1.09000 + 0.00100 = 1.09100
                  Close[17] = 1.09250 > S = 1.09000
    §4.2 trend  = SMA(3) = (1.09300 + 1.09100 + 1.09250)/3 = 1.0921666...,
                  close 1.09250 is above it
    §6   stop   = S - 1.0 x ATR = 1.09000 - 0.00400 = 1.08600
    §7   exits  = one leg, fraction 1.0, trailing, atr_multiple 3.0
    """
    o = orders[0]

    assert o.direction == 1
    assert o.entry == "market"
    assert o.entry_price is None
    assert o.decision_close == pytest.approx(1.09250, abs=1e-9)
    assert o.stop.price == pytest.approx(1.08600, abs=1e-9)
    assert o.stop.price < o.decision_close
    assert o.stop.move_to_breakeven_on is None  # §6: no breakeven
    assert o.stop.trail_atr_multiple is None  # §6: the trail lives in the exit leg

    assert [leg.kind for leg in o.exits] == ["trailing"]
    assert [leg.label for leg in o.exits] == ["TRAIL"]
    assert [leg.fraction for leg in o.exits] == pytest.approx([1.0])
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)
    assert o.exits[0].atr_multiple == pytest.approx(3.0)
    assert o.expires_after_bars is None  # §4: a market intent is never pending


def test_short_matches_hand_computed_arithmetic(orders) -> None:
    """The bar-32 trade plan, from §5, §6 and §7 — the exact mirror.

    §5.3 R      = High of the swing-high bar 25 = 1.10550 + 0.00200 = 1.10750,
                  confirmed at bar 30, age at bar 32 = 7
    §5.4 zone   = 0.00100; High[32] = 1.10500 + 0.00200 = 1.10700 >= 1.10750 - 0.00100
                  Close[32] = 1.10500 < R = 1.10750
    §5.2 trend  = SMA(3) = (1.10450 + 1.10600 + 1.10500)/3 = 1.1051666...,
                  close 1.10500 is below it
    §6   stop   = R + 1.0 x ATR = 1.10750 + 0.00400 = 1.11150
    """
    o = orders[1]

    assert o.direction == -1
    assert o.entry == "market"
    assert o.decision_close == pytest.approx(1.10500, abs=1e-9)
    assert o.stop.price == pytest.approx(1.11150, abs=1e-9)
    assert o.stop.price > o.decision_close
    assert [leg.fraction for leg in o.exits] == pytest.approx([1.0])
    assert o.exits[0].kind == "trailing"
    assert o.exits[0].atr_multiple == pytest.approx(3.0)
    assert o.tag == "sw_trend_pullback_norank"  # the missing rank gate, per trade


def test_staleness_guard_is_live(frames) -> None:
    """§10 #6 measured on the OCCURRENCE bar, not the confirmation bar.

    The bar-17 long uses a level that occurred at bar 10 — 7 bars earlier, 2 bars
    after its confirmation. Tighten STALENESS_BARS to 5 and the same bars must
    produce no orders at all; if the guard were measured against the confirmation
    bar (age 2) the long would survive.
    """
    assert list(_TightStaleness().generate_orders(frames)) == []


def test_cross_sectional_helpers_match_the_spec() -> None:
    """§3.3-§3.6, the part the single-pair interface cannot reach.

    §3.3 orientation: EUR_USD z=+1.0 gives EUR +1.0 and USD -1.0; USD_JPY z=+0.5
    gives USD +0.5 and JPY -0.5; GBP_USD z=+0.25 gives GBP +0.25 and USD -0.25.
    §3.4 sums per currency: EUR +1.00, GBP +0.25, JPY -0.50,
    USD = -1.00 + 0.50 - 0.25 = -0.75.
    §3.5 best = EUR, worst = USD; §3.6 the instrument joining them is EUR_USD.
    """
    close = pd.Series([1.0, 1.1, 1.2, 1.32])
    assert twenty_bar_return(close, period=2).tolist() == pytest.approx(
        [float("nan"), float("nan"), 0.2, 0.2], nan_ok=True
    )

    strength = currency_strength(
        {"EUR_USD": 1.0, "USD_JPY": 0.5, "GBP_USD": 0.25},
    )
    assert strength == pytest.approx(
        {"EUR": 1.0, "GBP": 0.25, "JPY": -0.5, "USD": -0.75}
    )

    assert candidate_instrument(strength) == ("EUR_USD", "EUR")
    # DECISION (module docstring): §3.5 fixes the tie-break as alphabetical but not
    # which end of a tie is "worst". One descending ranking is built and worst is
    # its last entry, so of two currencies tied at the bottom the alphabetically
    # LAST is worst: EUR / {JPY, USD} tied at -0.5 -> worst USD -> EUR_USD.
    assert candidate_instrument({"EUR": 1.0, "JPY": -0.5, "USD": -0.5}) == (
        "EUR_USD",
        "EUR",
    )
    # §3.6: a {best, worst} pair with no instrument in the universe is skipped,
    # never synthesised from two USD legs (§10 #4).
    assert candidate_instrument({"NZD": 2.0, "CAD": -1.0}) is None
    # NaN z-scores contribute nothing rather than poisoning a currency's sum.
    assert currency_strength({"EUR_USD": float("nan")}) == {}


# ---------------------------------------------------------------------------
# 4. The non-negotiable check
# ---------------------------------------------------------------------------


def test_strategy_is_free_of_lookahead(frames) -> None:
    """Every Wave-2 strategy must pass this on real data too."""
    assert_no_lookahead_v2(_FixtureScale(), frames)
