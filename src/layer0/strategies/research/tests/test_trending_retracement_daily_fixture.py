import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.trending_retracement_daily import (
    TrendingRetracementDaily,
)

PIP = 0.0001

# ---------------------------------------------------------------------------
# 1. The bars, and why these bars
# ---------------------------------------------------------------------------
# We need to test both Long and Short entries.
# Warmup bars: 10
# Bars 0-7: Flat market, closes at 1.0000 to initialize SMMA3 and SMMA8 to 1.0000.
# Bar 4: A swing low is formed (L=0.9900), confirmed at bar 6.
# Bar 8: A large upward spike (C=1.0500), forming a swing high (H=1.0600) and a bullish SMMA3 > SMMA8 cross.
# Bar 9: A shallow red pullback candle whose body sits entirely within the upper envelope band [1.01213, 1.01716].
#        This triggers the Long setup.
# Bar 10: A large downward crash (C=0.9500) that confirms the swing high at Bar 8 and creates a bearish cross.
# Bar 11: A shallow green pullback candle whose body sits entirely within the lower envelope band [0.98897, 0.99397].
#         This triggers the Short setup.
OPENS = [1.000] * 12
HIGHS = [1.000] * 12
LOWS = [1.000] * 12
CLOSES = [1.000] * 8

# Fill the rest
CLOSES.extend([1.050, 1.013, 0.950, 0.992])

# Bar 4: swing low for long (confirms at bar 6)
HIGHS[4] = 1.000
LOWS[4] = 0.990
LOWS[3] = 0.995
LOWS[5] = 0.995

# Bar 8: swing high for short (confirms at bar 10)
HIGHS[8] = 1.060
LOWS[8] = 1.040
HIGHS[7] = 1.000
HIGHS[9] = 1.0165  # required for entry buffer calculation
LOWS[9] = 1.010
OPENS[9] = 1.016  # red candle (1.016 -> 1.013)

# Bar 11: setup short
OPENS[11] = 0.989  # green candle (0.989 -> 0.992)
HIGHS[11] = 0.995
LOWS[11] = 0.988

# Add some trailing bars to prevent index out of bounds on confirmation, though not strictly needed
OPENS.extend([1.0] * 5)
HIGHS.extend([1.0] * 5)
LOWS.extend([1.0] * 5)
CLOSES.extend([1.0] * 5)


class _FixtureScale(TrendingRetracementDaily):
    """Production logic, fixture-sized lookbacks."""

    SWING_PERIOD = 2

    @property
    def warmup_bars(self) -> int:
        return 8


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
    """Rule: fire only on valid setup candles within 4 bars of a trend cross.

    Bar 9 is a long setup (bullish cross at bar 8).
    Bar 11 is a short setup (bearish cross at bar 10).
    """
    assert [str(o.decision_bar) for o in orders] == [
        "2020-01-10 00:00:00+00:00",  # Bar 9
        "2020-01-12 00:00:00+00:00",  # Bar 11
    ]


def test_long_order_matches_hand_computed_arithmetic(orders) -> None:
    """The full trade plan for a long setup, derived from the spec.

    At Bar 9:
      §4.3 Location: UI_9 = 1.01213, UO_9 = 1.01716
                     Close_9 = 1.01300, Open_9 = 1.01600. Inside band!
      §4.4 Stop availability: most recent confirmed swing low is at Bar 4. Level = 0.99000.

      §4 Entry = High_9 + 4 pip = 1.01650 + 0.00040 = 1.01690
      §6 Stop = exact level of the confirmed swing low = 0.99000
      §7 BE_70 = entry + 70 pip = 1.01690 + 0.00700 = 1.02390 (fraction 0.01)
      §7 TP_150 = entry + 150 pip = 1.01690 + 0.01500 = 1.03190 (fraction 0.99)
    """
    o = orders[0]

    assert o.direction == 1
    assert o.entry == "buy_stop"
    assert o.entry_price == pytest.approx(1.01690, abs=1e-9)
    assert o.stop.price == pytest.approx(0.99000, abs=1e-9)

    assert [leg.label for leg in o.exits] == ["BE_70", "TP_150"]
    assert [leg.price for leg in o.exits] == pytest.approx([1.02390, 1.03190], abs=1e-9)
    assert [leg.fraction for leg in o.exits] == pytest.approx([0.01, 0.99], abs=1e-9)
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)

    # Breakeven moves stop to entry
    assert o.stop.move_to_breakeven_on == "BE_70"
    assert o.stop.breakeven_offset_pips == pytest.approx(0.0)
    assert o.expires_after_bars == 1


def test_short_order_matches_hand_computed_arithmetic(orders) -> None:
    """The full trade plan for a short setup, derived from the spec.

    At Bar 11:
      §5.3 Location: LI_11 = 0.99397, LO_11 = 0.98897
                     Open_11 = 0.98900, Close_11 = 0.99200. Inside band!
      §5.4 Stop availability: most recent confirmed swing high is at Bar 8. Level = 1.06000.

      §5 Entry = Low_11 - 4 pip = 0.98800 - 0.00040 = 0.98760
      §6 Stop = exact level of the confirmed swing high = 1.06000
      §7 BE_70 = entry - 70 pip = 0.98760 - 0.00700 = 0.98060 (fraction 0.01)
      §7 TP_150 = entry - 150 pip = 0.98760 - 0.01500 = 0.97260 (fraction 0.99)
    """
    o = orders[1]

    assert o.direction == -1
    assert o.entry == "sell_stop"
    assert o.entry_price == pytest.approx(0.98760, abs=1e-9)
    assert o.stop.price == pytest.approx(1.06000, abs=1e-9)

    assert [leg.label for leg in o.exits] == ["BE_70", "TP_150"]
    assert [leg.price for leg in o.exits] == pytest.approx([0.98060, 0.97260], abs=1e-9)
    assert [leg.fraction for leg in o.exits] == pytest.approx([0.01, 0.99], abs=1e-9)
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)

    # Breakeven moves stop to entry
    assert o.stop.move_to_breakeven_on == "BE_70"
    assert o.stop.breakeven_offset_pips == pytest.approx(0.0)
    assert o.expires_after_bars == 1


def test_pending_entry_sits_above_or_below_the_market(frames, orders) -> None:
    """Rule: A pending order should sit appropriately away from the current close.
    For buy_stop, entry > close. For sell_stop, entry < close.
    """
    close = frames["D1"]["Close"]
    for o in orders:
        c = float(close.loc[o.decision_bar])
        if o.direction == 1:
            assert o.entry_price > c
        else:
            assert o.entry_price < c


def test_strategy_is_free_of_lookahead(frames) -> None:
    """Every Wave-2 strategy must pass this on real data too."""
    assert_no_lookahead_v2(_FixtureScale(), frames)
