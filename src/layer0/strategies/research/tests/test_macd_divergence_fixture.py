import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.macd_divergence import MacdDivergence

# 1. The bars, and why these bars
# 48 H4 bars.
# First, a long setup:
# Price forms a fast drop to 0.50 (bar 9), making MACD very negative.
# Then a bounce to 0.70 (bar 11).
# Then a slow drop to a lower low 0.45 (bar 16). Because it's slower, MACD is less negative than at bar 9.
# This confirms a bullish MACD divergence at bar 18.
# The trigger is a close above High[18] (0.5510). Bar 19 closes at 0.60.
#
# Then a short setup:
# Price forms a fast rise to 1.50 (bar 33). MACD is very positive.
# Then a bounce down to 1.30 (bar 35).
# Then a slow rise to a higher high 1.55 (bar 40). MACD is less positive.
# This confirms a bearish MACD divergence at bar 42.
# The trigger is a close below Low[42] (1.4490). Bar 43 closes at 1.40.

CLOSES = [
    # Warmup
    1.00,
    1.00,
    1.00,
    1.00,
    1.00,
    # Long Setup
    0.90,
    0.80,
    0.70,
    0.60,
    0.50,  # Bar 9: L1
    0.60,
    0.70,  # Bar 11: R*
    0.65,
    0.60,
    0.55,
    0.50,
    0.45,  # Bar 16: L2 (lower low)
    0.50,
    0.55,  # Bar 18: L2 confirmed here
    0.60,
    0.70,
    0.80,
    0.90,
    1.00,  # Bar 19: trigger
    # Spacer
    1.00,
    1.00,
    1.00,
    1.00,
    1.00,
    # Short Setup
    1.10,
    1.20,
    1.30,
    1.40,
    1.50,  # Bar 33: H1
    1.40,
    1.30,  # Bar 35: S*
    1.35,
    1.40,
    1.45,
    1.50,
    1.55,  # Bar 40: H2 (higher high)
    1.50,
    1.45,  # Bar 42: H2 confirmed here
    1.40,
    1.30,
    1.20,
    1.10,
    1.00,  # Bar 43: trigger
]


class _FixtureScale(MacdDivergence):
    """Production logic, fixture-sized lookbacks."""

    SWING_PERIOD = 2
    MACD_FAST = 3
    MACD_SLOW = 6
    MACD_SIGNAL = 3

    @property
    def warmup_bars(self) -> int:
        return 5


@pytest.fixture(scope="module")
def frames() -> dict:
    idx = pd.date_range("2026-08-01", periods=len(CLOSES), freq="4h", tz="UTC")
    h4 = pd.DataFrame(
        {
            "Open": CLOSES,
            "High": [c + 0.0010 for c in CLOSES],
            "Low": [c - 0.0010 for c in CLOSES],
            "Close": CLOSES,
            "Volume": 1.0,
        },
        index=idx,
    )
    return {"H4": h4}


@pytest.fixture(scope="module")
def orders(frames) -> list:
    return list(_FixtureScale().generate_orders(frames))


# ---------------------------------------------------------------------------
# Expected values, computed by hand, then asserted
# ---------------------------------------------------------------------------


def test_emits_exactly_two_orders(orders) -> None:
    """Rule: Fire on the bullish divergence at bar 19, and bearish at bar 43."""
    assert len(orders) == 2
    assert str(orders[0].decision_bar) == "2026-08-04 04:00:00+00:00"  # Bar 19
    assert str(orders[1].decision_bar) == "2026-08-08 04:00:00+00:00"  # Bar 43


def test_first_order_long_divergence(orders) -> None:
    """The full trade plan for the long entry.

    At Bar 19 (2026-08-04 04:00):
      §4 cond 2: L1 (bar 9) = 0.50 - 0.0010 = 0.4990
                 L2 (bar 16) = 0.45 - 0.0010 = 0.4490 -> L2 < L1
      §4 cond 3,4: MACD[L2] > MACD[L1], both < 0 (verified by script)
      §4 cond 5: trigger is first close > High[c]. c=18.
                 Close[19] = 0.60. High[18] = 0.5510. 0.60 > 0.5510
      §4 entry: market fill at next open

      §6 stop: L2 = 0.4490 exactly.
      §7 TP: nearest confirmed swing high above Close[19]
             R* = High[11] = 0.70 + 0.0010 = 0.7010
             0.7010 > 0.60
    """
    o = orders[0]
    assert o.direction == 1
    assert o.entry == "market"
    assert o.stop.price == pytest.approx(0.4490, abs=1e-9)
    assert len(o.exits) == 1
    assert o.exits[0].label == "TP1"
    assert o.exits[0].price == pytest.approx(0.7010, abs=1e-9)
    assert o.exits[0].fraction == pytest.approx(1.0, abs=1e-9)


def test_second_order_short_divergence(orders) -> None:
    """The full trade plan for the short entry.

    At Bar 43 (2026-08-08 04:00):
      §5 cond 2: H1 (bar 33) = 1.50 + 0.0010 = 1.5010
                 H2 (bar 40) = 1.55 + 0.0010 = 1.5510 -> H2 > H1
      §5 cond 3,4: MACD[H2] < MACD[H1], both > 0 (verified by script)
      §5 cond 5: trigger is first close < Low[c]. c=42.
                 Close[43] = 1.40. Low[42] = 1.45 - 0.0010 = 1.4490. 1.40 < 1.4490
      §5 entry: market fill at next open

      §6 stop: H2 = 1.5510 exactly.
      §7 TP: nearest confirmed swing low below Close[43]
             S* = Low[35] = 1.30 - 0.0010 = 1.2990
             1.2990 < 1.40
    """
    o = orders[1]
    assert o.direction == -1
    assert o.entry == "market"
    assert o.stop.price == pytest.approx(1.5510, abs=1e-9)
    assert len(o.exits) == 1
    assert o.exits[0].label == "TP1"
    assert o.exits[0].price == pytest.approx(1.2990, abs=1e-9)
    assert o.exits[0].fraction == pytest.approx(1.0, abs=1e-9)


def test_strategy_is_free_of_lookahead(frames) -> None:
    """Every Wave-2 strategy must pass this on real data too."""
    assert_no_lookahead_v2(_FixtureScale(), frames)
