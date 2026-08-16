import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.weekly_day_reversal_ea import WeeklyDayReversalEa

# ---------------------------------------------------------------------------
# 1. The bars, and why these bars
# ---------------------------------------------------------------------------
# 36 D1 bars covering roughly 5 weeks.
# Days 0 to 20 have a static daily range of 0.02 (1.11 - 1.09).
# Day 21 (a Monday) and Day 28 (a Monday) have a larger range of 0.05
# to trigger the volatility filter.
# Day 21 is bearish (Close < Open). Day 28 is bullish (Close > Open).
# This tests both long and short entry conditions.

OPENS = [
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.15,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
]

CLOSES = [
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.15,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
    1.10,
]

HIGHS = [
    1.11,
    1.11,
    1.11,
    1.11,
    1.11,
    1.11,
    1.11,
    1.11,
    1.11,
    1.11,
    1.11,
    1.11,
    1.11,
    1.11,
    1.11,
    1.11,
    1.11,
    1.11,
    1.11,
    1.11,
    1.11,
    1.15,
    1.11,
    1.11,
    1.11,
    1.11,
    1.11,
    1.11,
    1.15,
    1.11,
    1.11,
    1.11,
    1.11,
    1.11,
    1.11,
    1.11,
]

LOWS = [
    1.09,
    1.09,
    1.09,
    1.09,
    1.09,
    1.09,
    1.09,
    1.09,
    1.09,
    1.09,
    1.09,
    1.09,
    1.09,
    1.09,
    1.09,
    1.09,
    1.09,
    1.09,
    1.09,
    1.09,
    1.09,
    1.10,
    1.09,
    1.09,
    1.09,
    1.09,
    1.09,
    1.09,
    1.10,
    1.09,
    1.09,
    1.09,
    1.09,
    1.09,
    1.09,
    1.09,
]


class _FixtureScale(WeeklyDayReversalEa):
    @property
    def warmup_bars(self) -> int:
        return 14


@pytest.fixture(scope="module")
def frames() -> dict:
    idx = pd.date_range("2020-01-06", periods=len(CLOSES), freq="1D", tz="UTC")
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
    """Rule: fire only when next bar is Tuesday and volatility filter passes."""
    # Day 21 (Monday, 2020-01-27): Large bearish day
    # Day 28 (Monday, 2020-02-03): Large bullish day
    assert [str(o.decision_bar) for o in orders] == [
        "2020-01-27 00:00:00+00:00",
        "2020-02-03 00:00:00+00:00",
    ]


def test_first_order_long_matches_arithmetic(orders) -> None:
    """The full trade plan, derived from the spec — not copied from output.

    At 2020-01-27 00:00:00+00:00 (bar 21, Monday):
    §4.2 Previous day bearish: Close[D] < Open[D] -> 1.10 < 1.15. Direction is +1.
    §8 Range filter: High[D] - Low[D] = 1.15 - 1.10 = 0.05
    §3 ADR14[D] = (13 * 0.02 + 0.05) / 14 = 0.31 / 14 = 0.022142857
    §8 Filter check: 0.05 >= 1.5 * 0.022142857 = 0.033214285 (Passes)
    §6 Stop distance = 0.5 * ADR14[D] = 0.011071428
    §6 Stop price = Close[D] - 0.5 * ADR14[D] = 1.10 - 0.011071428 = 1.08892857
    §7 TIME_CLOSE leg = 23 bars
    §7 fraction = 1.0
    """
    o = orders[0]
    assert o.direction == 1
    assert o.entry == "market"
    assert o.entry_price is None

    expected_stop = 1.10 - 0.01107142857142857
    assert o.stop.price == pytest.approx(expected_stop, abs=1e-8)

    assert len(o.exits) == 1
    leg = o.exits[0]
    assert leg.kind == "time"
    assert leg.bars == 23
    assert leg.label == "TIME_CLOSE"
    assert leg.fraction == 1.0
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)


def test_second_order_short_matches_arithmetic(orders) -> None:
    """Short scenario derived from spec.

    At 2020-02-03 00:00:00+00:00 (bar 28, Monday):
    §5.2 Previous day bullish: Close[D] > Open[D] -> 1.15 > 1.10. Direction is -1.
    §8 Range filter: High[D] - Low[D] = 1.15 - 1.10 = 0.05
    §3 ADR14[D] = (12 * 0.02 + 0.05 + 0.05) / 14 = 0.34 / 14 = 0.024285714
    §8 Filter check: 0.05 >= 1.5 * 0.024285714 = 0.036428571 (Passes)
    §6 Stop distance = 0.5 * ADR14[D] = 0.012142857
    §6 Stop price = Close[D] + 0.5 * ADR14[D] = 1.15 + 0.012142857 = 1.16214285
    """
    o = orders[1]
    assert o.direction == -1
    assert o.entry == "market"
    assert o.entry_price is None

    expected_stop = 1.15 + 0.012142857142857143
    assert o.stop.price == pytest.approx(expected_stop, abs=1e-8)

    assert len(o.exits) == 1
    leg = o.exits[0]
    assert leg.kind == "time"
    assert leg.bars == 23
    assert leg.fraction == 1.0


# ---------------------------------------------------------------------------
# 4. The non-negotiable check
# ---------------------------------------------------------------------------


def test_strategy_is_free_of_lookahead(frames) -> None:
    """Every Wave-2 strategy must pass this on real data too."""
    assert_no_lookahead_v2(_FixtureScale(), frames)
