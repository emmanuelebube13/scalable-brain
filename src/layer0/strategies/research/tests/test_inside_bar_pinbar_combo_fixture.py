"""GOLDEN FIXTURE for inside_bar_pinbar_combo."""

from __future__ import annotations

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.inside_bar_pinbar_combo import (
    InsideBarPinbarCombo,
)

# ---------------------------------------------------------------------------
# 1. The bars, and why these bars
# ---------------------------------------------------------------------------
# Need bars that form an inside bar, followed by a pin bar at a confirmed level.
# To warm up, we need EMA50 = 50 bars, ATR14 = 14 bars, SWING_PERIOD = 5 bars.
# Let's scale down:
# EMA_PERIOD = 5, ATR_PERIOD = 5, SWING_PERIOD = 2, RECENCY_WINDOW = 10, EXPIRY = 2.
# So warmup = max(5, 5, 2*3) + 10 = 16 bars.
# Let's build ~30 bars.

CLOSES = []
HIGHS = []
LOWS = []
OPENS = []

# Bars 0-10: Establish a downtrend and a swing low (support).
# Prices go down.
for i in range(5):
    CLOSES.append(1.2000 - i * 0.0050)
    HIGHS.append(1.2000 - i * 0.0050 + 0.0020)
    LOWS.append(1.2000 - i * 0.0050 - 0.0020)
    OPENS.append(1.2000 - i * 0.0050 + 0.0010)

# Bar 5: The swing low at 1.1750 (Low = 1.1730).
CLOSES.append(1.1750)
HIGHS.append(1.1770)
LOWS.append(1.1730)
OPENS.append(1.1760)

# Bars 6-10: Pullback up to form a swing high (resistance) and confirm the low.
for i in range(1, 6):
    CLOSES.append(1.1750 + i * 0.0050)
    HIGHS.append(1.1750 + i * 0.0050 + 0.0020)
    LOWS.append(1.1750 + i * 0.0050 - 0.0020)
    OPENS.append(1.1750 + i * 0.0050 - 0.0010)

# Bar 11: The swing high at 1.2000 (High = 1.2020)
CLOSES.append(1.2000)
HIGHS.append(1.2020)
LOWS.append(1.1980)
OPENS.append(1.1990)

# Bars 12-16: Down again to retest the support low.
for i in range(1, 6):
    CLOSES.append(1.2000 - i * 0.0050)
    HIGHS.append(1.2000 - i * 0.0050 + 0.0020)
    LOWS.append(1.2000 - i * 0.0050 - 0.0020)
    OPENS.append(1.2000 - i * 0.0050 + 0.0010)

# Now we are at bar 16. The close is 1.1750.
# The support level is Low[5] = 1.1730.
# Let's form the long setup.
# Bar 17 (t-2): Mother bar.
OPENS.append(1.1750)
HIGHS.append(1.1800)
LOWS.append(1.1740)
CLOSES.append(1.1790)

# Bar 18 (t-1): Inside bar.
OPENS.append(1.1780)
HIGHS.append(1.1790)  # <= 1.1800
LOWS.append(1.1750)  # >= 1.1740
CLOSES.append(1.1760)

# Bar 19 (t): Pin bar (Bullish).
# Pin bar must have lower tail >= 0.6*R, upper tail <= 0.25*R, close > low + 0.6*R
# It must close within the inside bar's range [1.1750, 1.1790]
# Must be at confirmed support. Support is 1.1730. Pin bar low must be within 0.25*ATR of 1.1730.
# Let's say Low = 1.1730. High = 1.1780. Range = 0.0050.
# 60% of Range = 0.0030. 25% of Range = 0.00125.
# Open = 1.1770, Close = 1.1775.
# min(Open, Close) - Low = 1.1770 - 1.1730 = 0.0040 (0.0040 >= 0.0030) - lower tail OK.
# High - max(Open, Close) = 1.1780 - 1.1775 = 0.0005 (0.0005 <= 0.00125) - upper tail OK.
# Close (1.1775) is inside [1.1750, 1.1790] - OK.
# Strong bullish close: Close - Low = 1.1775 - 1.1730 = 0.0045 (0.0045 > 0.0030) - OK.
# EMA50 filter: price must be < EMA50. EMA50 will be around 1.1850 - OK.
OPENS.append(1.1770)
HIGHS.append(1.1780)
LOWS.append(1.1730)
CLOSES.append(1.1775)

# This will trigger a LONG order at bar 19.

# Next, let's create a SHORT setup.
# Bars 20-25: Move up to resistance (High[11] = 1.2020).
for i in range(1, 7):
    CLOSES.append(1.1775 + i * 0.0040)
    HIGHS.append(1.1775 + i * 0.0040 + 0.0020)
    LOWS.append(1.1775 + i * 0.0040 - 0.0020)
    OPENS.append(1.1775 + i * 0.0040 - 0.0010)

# Currently at bar 25. Close = 1.2015.
# Resistance is 1.2020.
# Bar 26 (t-2): Mother bar.
OPENS.append(1.2015)
HIGHS.append(1.2040)
LOWS.append(1.1980)
CLOSES.append(1.1990)

# Bar 27 (t-1): Inside bar.
OPENS.append(1.1990)
HIGHS.append(1.2030)  # <= 1.2040
LOWS.append(1.1990)  # >= 1.1980
CLOSES.append(1.2010)

# Bar 28 (t): Pin bar (Bearish).
# Must close inside [1.1990, 1.2030].
# High around 1.2020 (resistance is 1.2020).
# Let High = 1.2025. Low = 1.1975. Range = 0.0050.
# Open = 1.1985. Close = 1.1980. (Wait, Close must be inside IB range, so >= 1.1990).
# Let's adjust Low so Close can be >= 1.1990.
# High = 1.2025. Low = 1.1975. Range = 0.0050.
# Let Open = 1.1995. Close = 1.1990. (Close is inside [1.1990, 1.2030]).
# min(Open, Close) = 1.1990. max(Open, Close) = 1.1995.
# Upper tail = High - max(O,C) = 1.2025 - 1.1995 = 0.0030. (0.0030 >= 0.6*R = 0.0030) - OK.
# Lower tail = min(O,C) - Low = 1.1990 - 1.1975 = 0.0015. (0.0015 > 0.25*R = 0.00125).
# Wait, lower tail must be <= 0.25*R. So lower tail must be <= 0.00125.
# Let's set Low = 1.1980. Range = 1.2025 - 1.1980 = 0.0045.
# 60% of 0.0045 = 0.0027. 25% of 0.0045 = 0.001125.
# Let Open = 1.1995. Close = 1.1990.
# min(O,C) = 1.1990. lower tail = 1.1990 - 1.1980 = 0.0010 <= 0.001125. OK.
# max(O,C) = 1.1995. upper tail = 1.2025 - 1.1995 = 0.0030 >= 0.0027. OK.
# Strong bearish close: High - Close = 1.2025 - 1.1990 = 0.0035 > 0.0027. OK.
# EMA50 filter: price must be > EMA50. EMA50 around 1.1900. OK.
OPENS.append(1.1995)
HIGHS.append(1.2025)
LOWS.append(1.1980)
CLOSES.append(1.1990)

# Add some padding to finish.
for i in range(5):
    CLOSES.append(1.1990 - i * 0.0050)
    HIGHS.append(1.1990 - i * 0.0050 + 0.0020)
    LOWS.append(1.1990 - i * 0.0050 - 0.0020)
    OPENS.append(1.1990 - i * 0.0050 + 0.0010)


class _FixtureScale(InsideBarPinbarCombo):
    EMA_PERIOD = 5
    ATR_PERIOD = 5
    SWING_PERIOD = 2
    RECENCY_WINDOW = 30

    @property
    def warmup_bars(self) -> int:
        return 10


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
    # Bar 19 is 2020-01-20
    # Bar 28 is 2020-01-29
    assert [str(o.decision_bar) for o in orders] == [
        "2020-01-20 00:00:00+00:00",
        "2020-01-29 00:00:00+00:00",
    ]


def test_first_order_matches_hand_computed_arithmetic(frames, orders) -> None:
    """The full trade plan, derived from the spec.
    At bar 19 (Long):
      Pin bar High = 1.1780, Low = 1.1730.
      Entry = (1.1780 + 1.1730) / 2 = 1.1755.
      ATR14(5) at bar 19 is approx 0.0040. (We will use pytest.approx on the actual calculated ATR).
      Stop = Low - 0.10 * ATR.
      TP1 = Nearest confirmed swing high above entry (which is 1.2020 from bar 11).
    """
    o = orders[0]

    d1 = frames["D1"]
    # We need to calculate the exact ATR for bar 19.
    # ATR period 5 using standard Wilder's smoothing or simple?
    # Actually, we can just extract it from the ATR function or assert relative bounds.
    # We can fetch the frame data.
    from src.layer0.data_access.indicators import atr

    atr_series = atr(d1["High"], d1["Low"], d1["Close"], 5)
    atr_val = atr_series.iloc[19]

    expected_entry = 1.1755
    expected_stop = 1.1730 - 0.10 * atr_val
    expected_tp = 1.2020

    assert o.direction == 1
    assert o.entry == "buy_limit"
    assert o.entry_price == pytest.approx(expected_entry, abs=1e-9)
    assert o.stop.price == pytest.approx(expected_stop, abs=1e-9)

    assert [leg.label for leg in o.exits] == ["TP1"]
    assert [leg.price for leg in o.exits] == pytest.approx([expected_tp], abs=1e-9)
    assert [leg.fraction for leg in o.exits] == pytest.approx([1.0], abs=1e-9)
    assert o.expires_after_bars == 2


def test_second_order_matches_hand_computed_arithmetic(frames, orders) -> None:
    """The full trade plan, derived from the spec.
    At bar 28 (Short):
      Pin bar High = 1.2025, Low = 1.1980.
      Entry = (1.2025 + 1.1980) / 2 = 1.20025.
      TP1 = Nearest confirmed swing low below entry (which is 1.1730 from bar 5, or a newer one?).
      Let's check if there is a newer swing low.
      Bars 12-16 moved down, bar 17 (1.1740), bar 18 (1.1750), bar 19 (1.1730).
      Bar 19 Low is 1.1730. This is the new confirmed swing low.
    """
    o = orders[1]

    d1 = frames["D1"]
    from src.layer0.data_access.indicators import atr

    atr_series = atr(d1["High"], d1["Low"], d1["Close"], 5)
    atr_val = atr_series.iloc[28]

    expected_entry = 1.20025
    expected_stop = 1.2025 + 0.10 * atr_val
    expected_tp = 1.1730

    assert o.direction == -1
    assert o.entry == "sell_limit"
    assert o.entry_price == pytest.approx(expected_entry, abs=1e-9)
    assert o.stop.price == pytest.approx(expected_stop, abs=1e-9)

    assert [leg.label for leg in o.exits] == ["TP1"]
    assert [leg.price for leg in o.exits] == pytest.approx([expected_tp], abs=1e-9)
    assert [leg.fraction for leg in o.exits] == pytest.approx([1.0], abs=1e-9)
    assert o.expires_after_bars == 2


def test_strategy_is_free_of_lookahead(frames) -> None:
    """Every Wave-2 strategy must pass this on real data too."""
    assert_no_lookahead_v2(_FixtureScale(), frames)
