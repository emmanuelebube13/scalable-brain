"""Golden fixture for VshapeSwingBreakout."""

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.vshape_swing_breakout import VshapeSwingBreakout

OPENS = [
    # 0..14 flat
    1.1000,
    1.1000,
    1.1000,
    1.1000,
    1.1000,
    1.1000,
    1.1000,
    1.1000,
    1.1000,
    1.1000,
    1.1000,
    1.1000,
    1.1000,
    1.1000,
    1.1000,
    # 15..19 drop
    1.1000,
    1.0990,
    1.0980,
    1.0970,
    1.0960,
    # 20 low
    1.0950,
    # 21..25 rally
    1.0910,
    1.0950,
    1.0970,
    1.0980,
    1.0990,
    # 26 trigger
    1.1000,
    # 27..31 flat
    1.1050,
    1.1050,
    1.1050,
    1.1050,
    1.1050,
    # 32..36 rally
    1.1050,
    1.1060,
    1.1070,
    1.1080,
    1.1090,
    # 37 high
    1.1100,
    # 38..42 drop
    1.1190,
    1.1150,
    1.1120,
    1.1090,
    1.1070,
    # 43 trigger
    1.1050,
]

HIGHS = [
    1.1010,
    1.1010,
    1.1010,
    1.1010,
    1.1010,
    1.1010,
    1.1010,
    1.1010,
    1.1010,
    1.1010,
    1.1010,
    1.1010,
    1.1010,
    1.1010,
    1.1010,  # 14
    1.1010,
    1.1000,
    1.0990,
    1.0980,
    1.0970,  # 15..19
    1.0960,  # 20 (k_long)
    1.0960,
    1.0980,
    1.0990,
    1.1000,
    1.1005,  # 21..25
    1.1060,  # 26 (trigger)
    1.1060,
    1.1060,
    1.1060,
    1.1060,
    1.1060,  # 27..31
    1.1060,
    1.1070,
    1.1080,
    1.1090,
    1.1100,  # 32..36
    1.1200,  # 37 (k_short)
    1.1195,
    1.1160,
    1.1130,
    1.1100,
    1.1080,  # 38..42
    1.1060,  # 43 (trigger)
]

LOWS = [
    1.0990,
    1.0990,
    1.0990,
    1.0990,
    1.0990,
    1.0990,
    1.0990,
    1.0990,
    1.0990,
    1.0990,
    1.0990,
    1.0990,
    1.0990,
    1.0990,
    1.0990,
    1.0990,
    1.0980,
    1.0970,
    1.0960,
    1.0950,
    1.0900,
    1.0910,
    1.0940,
    1.0960,
    1.0970,
    1.0980,
    1.0990,
    1.1040,
    1.1040,
    1.1040,
    1.1040,
    1.1040,
    1.1040,
    1.1050,
    1.1060,
    1.1070,
    1.1080,
    1.1090,
    1.1150,
    1.1120,
    1.1090,
    1.1070,
    1.1050,
    1.0950,
]

CLOSES = [
    1.1000,
    1.1000,
    1.1000,
    1.1000,
    1.1000,
    1.1000,
    1.1000,
    1.1000,
    1.1000,
    1.1000,
    1.1000,
    1.1000,
    1.1000,
    1.1000,
    1.1000,
    1.0990,
    1.0980,
    1.0970,
    1.0960,
    1.0950,
    1.0910,
    1.0950,
    1.0970,
    1.0980,
    1.0990,
    1.1000,
    1.1050,
    1.1050,
    1.1050,
    1.1050,
    1.1050,
    1.1050,
    1.1060,
    1.1070,
    1.1080,
    1.1090,
    1.1100,
    1.1190,
    1.1150,
    1.1120,
    1.1090,
    1.1070,
    1.1050,
    1.0950,
]

VOLUMES = [1.0] * 44
VOLUMES[26] = 5.0
VOLUMES[43] = 5.0


class _FixtureScale(VshapeSwingBreakout):
    """Production logic, fixture-sized lookbacks."""

    ATR_PERIOD = 14
    SMA_PERIOD = 14

    @property
    def warmup_bars(self) -> int:
        return 14


@pytest.fixture(scope="module")
def frames() -> dict:
    idx = pd.date_range("2026-08-01", periods=len(CLOSES), freq="4h", tz="UTC")
    h4 = pd.DataFrame(
        {
            "Open": OPENS,
            "High": HIGHS,
            "Low": LOWS,
            "Close": CLOSES,
            "Volume": VOLUMES,
        },
        index=idx,
    )
    return {"H4": h4}


@pytest.fixture(scope="module")
def orders(frames) -> list:
    return list(_FixtureScale().generate_orders(frames))


def test_orders_generated(orders) -> None:
    # §4 Setup: expect 2 orders: one long, one short.
    assert len(orders) == 2
    assert orders[0].direction == 1
    assert orders[1].direction == -1


def test_long_order_values(orders, frames) -> None:
    # §4 Setup math:
    # k = 20, c = 25
    # S1: max High in [15..20] = 1.1010. Low[20] = 1.0900.
    # down_leg = 1.1010 - 1.0900 = 110 pips.
    # S2: max High in [21..25] = 1.1005.
    # up_leg = 1.1005 - 1.0900 = 105 pips.
    # L = 1.1010
    # §4 Trigger at bar 26:
    # Close = 1.1050 > 1.1010.

    o = orders[0]

    assert o.direction == 1
    # §4.1 entry market
    assert o.entry == "market"

    # §6 stop = Low[k] - 1.0 pip = 1.0900 - 0.0001 = 1.08990
    assert o.stop.price == pytest.approx(1.08990, abs=1e-9)

    # §6 trail = 3.0 * ATR
    assert o.stop.trail_atr_multiple == 3.0

    # §7 exit legs fractions sum to 1.0
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)
    assert len(o.exits) == 1

    # §7 exit leg 0 is trailing
    assert o.exits[0].kind == "trailing"
    assert o.exits[0].label == "TRAIL"


def test_short_order_values(orders, frames) -> None:
    # §5 Setup math:
    # k = 37, c = 42
    # S1': min Low in [32..37] = 1.1040. High[37] = 1.1200.
    # up_leg = 1.1200 - 1.1040 = 160 pips.
    # S2': min Low in [38..42] = 1.1050.
    # down_leg = 1.1200 - 1.1050 = 150 pips.
    # L = 1.1040
    # §5 Trigger at bar 43:
    # Close = 1.0950 < 1.1040.

    o = orders[1]

    assert o.direction == -1
    # §5.1 entry market
    assert o.entry == "market"

    # §6 stop = High[k] + 1.0 pip = 1.1200 + 0.0001 = 1.12010
    assert o.stop.price == pytest.approx(1.12010, abs=1e-9)

    # §6 trail = 3.0 * ATR
    assert o.stop.trail_atr_multiple == 3.0

    # §7 exit legs fractions sum to 1.0
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)


def test_lookahead(frames) -> None:
    # §9 Causality audit: no lookahead
    assert_no_lookahead_v2(_FixtureScale(), frames)
