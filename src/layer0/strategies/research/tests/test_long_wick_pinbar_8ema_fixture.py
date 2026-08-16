"""GOLDEN FIXTURE — the deliverable shape every Wave-2 strategy must copy."""

from __future__ import annotations

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.long_wick_pinbar_8ema import LongWickPinbar8Ema

# ---------------------------------------------------------------------------
# 1. The bars, and why these bars
# ---------------------------------------------------------------------------
# 31 D1 bars.
# Bars 0-5: Warmup for the EMA, steady uptrend. EMA2 > EMA4.
# Bar 6: A long pinbar wick that dips down to touch EMA2, while EMA2 > EMA4.
# Bars 7-10: Upward continuation.
# Bars 11-17: Steady downtrend, crossing EMA2 below EMA4.
# Bar 18: A short pinbar wick that rises up to touch EMA2, while EMA2 < EMA4.
# Bars 19-30: Downward continuation to end.

CLOSES = [
    1.1000,
    1.1010,
    1.1020,
    1.1030,
    1.1040,
    1.1050,
    1.1100,
    1.1200,
    1.1300,
    1.1400,
    1.1500,
    1.0800,
    1.0700,
    1.0600,
    1.0500,
    1.0400,
    1.0300,
    1.0200,
    1.0100,
    1.0000,
    0.9900,
    0.9800,
    0.9700,
    0.9600,
    0.9500,
    0.9500,
    0.9500,
    0.9500,
    0.9500,
    0.9500,
    0.9500,
]

OPENS = CLOSES.copy()
HIGHS = [c + 0.0001 for c in CLOSES]
LOWS = [c - 0.0001 for c in CLOSES]

# Bar 6: Long Setup
# Close = 1.1100
# Open = 1.1100
# High = 1.1150
# Low = 1.0900
OPENS[6] = 1.1100
HIGHS[6] = 1.1150
LOWS[6] = 1.0900

# Bar 18: Short Setup
# Close = 1.0100
# Open = 1.0100
# High = 1.0400
# Low = 1.0050
OPENS[18] = 1.0100
HIGHS[18] = 1.0400
LOWS[18] = 1.0050


class _FixtureScale(LongWickPinbar8Ema):
    """Production logic, fixture-sized lookbacks."""

    FAST_EMA = 2
    SLOW_EMA = 4

    @property
    def warmup_bars(self) -> int:
        return 6


@pytest.fixture(scope="module")
def frames() -> dict:
    idx = pd.date_range("2020-01-01", periods=len(CLOSES), freq="1D", tz="UTC")
    d1 = pd.DataFrame(
        {
            "Open": OPENS,
            "High": HIGHS,
            "Low": LOWS,
            "Close": CLOSES,
            "Volume": 1.0,
        },
        index=idx,
    )
    return {"D1": d1}


@pytest.fixture(scope="module")
def orders(frames) -> list:
    return list(_FixtureScale().generate_orders(frames))


# ---------------------------------------------------------------------------
# 2 + 3. Expected values, computed by hand, then asserted
# ---------------------------------------------------------------------------


def test_emits_exactly_the_expected_setups(orders) -> None:
    """Rule: fire only when EMA filter matches, wick size >= 2/3 range, and touches EMA.

    Bar 6 (index 6, 2020-01-07) meets all Long conditions.
    Bar 18 (index 18, 2020-01-19) meets all Short conditions.
    """
    assert [str(o.decision_bar) for o in orders] == [
        "2020-01-07 00:00:00+00:00",
        "2020-01-19 00:00:00+00:00",
    ]


def test_long_order_matches_hand_computed_arithmetic(orders) -> None:
    """The full trade plan for a long, derived from the spec.

    At 2020-01-07 (bar 6):
      Close_t = 1.1100
      Low_t   = 1.0900

      # §6 stop = Low[t] - 2 pips = 1.0900 - 0.0002 = 1.0898
      # risk = Close[t] - stop = 1.1100 - 1.0898 = 0.0202
      # §7 TP = Close[t] + 2 * risk = 1.1100 + 0.0404 = 1.1504
    """
    o = orders[0]

    assert o.direction == 1
    assert o.entry == "market"
    assert o.entry_price is None
    assert o.decision_close == pytest.approx(1.1100, abs=1e-9)
    assert o.stop.price == pytest.approx(1.0898, abs=1e-9)

    assert [leg.label for leg in o.exits] == ["TP1"]
    assert [leg.price for leg in o.exits] == pytest.approx([1.1504], abs=1e-9)
    assert [leg.fraction for leg in o.exits] == pytest.approx([1.0], abs=1e-9)
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)

    assert o.expires_after_bars is None


def test_short_order_matches_hand_computed_arithmetic(orders) -> None:
    """The full trade plan for a short, derived from the spec.

    At 2020-01-19 (bar 18):
      Close_t = 1.0100
      High_t  = 1.0400

      # §6 stop = High[t] + 2 pips = 1.0400 + 0.0002 = 1.0402
      # risk = stop - Close[t] = 1.0402 - 1.0100 = 0.0302
      # §7 TP = Close[t] - 2 * risk = 1.0100 - 0.0604 = 0.9496
    """
    o = orders[1]

    assert o.direction == -1
    assert o.entry == "market"
    assert o.entry_price is None
    assert o.decision_close == pytest.approx(1.0100, abs=1e-9)
    assert o.stop.price == pytest.approx(1.0402, abs=1e-9)

    assert [leg.label for leg in o.exits] == ["TP1"]
    assert [leg.price for leg in o.exits] == pytest.approx([0.9496], abs=1e-9)
    assert [leg.fraction for leg in o.exits] == pytest.approx([1.0], abs=1e-9)
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)

    assert o.expires_after_bars is None


def test_risk_reward_ratios_hold_for_every_order(orders) -> None:
    """Rule: leg sits at exactly 2R from decision_close. Derived, so a changed buffer is caught."""
    for o in orders:
        if o.direction == 1:
            risk = o.decision_close - o.stop.price
            assert risk > 0
            assert o.exits[0].price == pytest.approx(
                o.decision_close + 2.0 * risk, abs=1e-9
            )
        else:
            risk = o.stop.price - o.decision_close
            assert risk > 0
            assert o.exits[0].price == pytest.approx(
                o.decision_close - 2.0 * risk, abs=1e-9
            )


# ---------------------------------------------------------------------------
# 4. The non-negotiable check
# ---------------------------------------------------------------------------


def test_strategy_is_free_of_lookahead(frames) -> None:
    """Every Wave-2 strategy must pass this on real data too."""
    assert_no_lookahead_v2(_FixtureScale(), frames)
