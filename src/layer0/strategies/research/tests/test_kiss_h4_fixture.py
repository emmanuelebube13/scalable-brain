import numpy as np
import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.kiss_h4 import KissH4


class _FixtureScale(KissH4):
    LWMA_PERIOD = 2
    ATR_PERIOD = 2
    MACD_FAST = 2
    MACD_SLOW = 4
    MACD_SIGNAL = 2
    SWING_PERIOD = 1
    SWING_COUNT = 2

    @property
    def warmup_bars(self) -> int:
        return 10


@pytest.fixture
def frames() -> dict[str, pd.DataFrame]:
    dates = pd.date_range("2020-01-01", periods=35, freq="4h")

    O = [
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2030,
        1.2015,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2015,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
    ]
    H = [
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2020,
        1.2000,
        1.2000,
        1.2000,
        1.2040,
        1.2000,
        1.2000,
        1.2035,
        1.2050,
        1.2000,
        1.2060,
        1.2000,
        1.2000,
        1.2000,
        1.2040,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2015,
        1.2020,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
    ]
    L = [
        1.2000,
        1.2000,
        1.1980,
        1.2000,
        1.2000,
        1.2000,
        1.1990,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2015,
        1.2010,
        1.2000,
        1.2000,
        1.2000,
        1.2020,
        1.2000,
        1.2000,
        1.2000,
        1.1990,
        1.2000,
        1.2000,
        1.1995,
        1.1980,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
    ]
    C = [
        1.2000,
        1.2000,
        1.1985,
        1.2000,
        1.2015,
        1.2000,
        1.1995,
        1.2000,
        1.2030,
        1.2000,
        1.2000,
        1.2020,
        1.2040,
        1.2000,
        1.2050,
        1.2000,
        1.2025,
        1.2000,
        1.2030,
        1.2000,
        1.1995,
        1.2000,
        1.2000,
        1.2010,
        1.1985,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
    ]

    df = pd.DataFrame({"Open": O, "High": H, "Low": L, "Close": C}, index=dates)
    return {"H4": df}


@pytest.fixture
def orders(frames):
    return list(_FixtureScale().generate_orders(frames))


def test_long_entry_matches_hand_arithmetic(orders) -> None:
    # Rule §6: "Initial stop ... Close_t - 100 * pip"
    # Rule §7: "TP1 ... 75 pips for high-ADR (proxied by price > 1.15)"
    #
    # For Long at 2020-01-03 00:00:00:
    #   Close_t = 1.2040
    #   pip     = 0.0001
    #   Stop    = 1.2040 - 100 * 0.0001 = 1.1940
    #   TP1     = 1.2040 + 75 * 0.0001 = 1.2115
    o = orders[0]
    assert o.direction == 1
    assert o.entry == "market"
    assert o.stop.price == pytest.approx(1.1940)

    assert len(o.exits) == 2

    # Assert every exit leg and fraction
    assert o.exits[0].label == "TP1"
    assert o.exits[0].price == pytest.approx(1.2115)
    assert o.exits[0].fraction == pytest.approx(0.5)

    assert o.exits[1].label == "TIME1"
    assert o.exits[1].bars == 12
    assert o.exits[1].fraction == pytest.approx(0.5)


def test_short_entry_matches_hand_arithmetic(orders) -> None:
    # Rule §6: "Initial stop ... Close_t + 100 * pip"
    # Rule §7: "TP1 ... 75 pips for high-ADR"
    #
    # For Short at 2020-01-05 00:00:00:
    #   Close_t = 1.1985
    #   pip     = 0.0001
    #   Stop    = 1.1985 + 100 * 0.0001 = 1.2085
    #   TP1     = 1.1985 - 75 * 0.0001 = 1.1910
    o = orders[1]
    assert o.direction == -1
    assert o.entry == "market"
    assert o.stop.price == pytest.approx(1.2085)

    assert len(o.exits) == 2

    # Assert every exit leg and fraction
    assert o.exits[0].label == "TP1"
    assert o.exits[0].price == pytest.approx(1.1910)
    assert o.exits[0].fraction == pytest.approx(0.5)

    assert o.exits[1].label == "TIME1"
    assert o.exits[1].bars == 12
    assert o.exits[1].fraction == pytest.approx(0.5)


def test_exit_fractions_sum_to_one(orders) -> None:
    # Rule §7: "Fractions sum to 1.0 ... splitting 50/50"
    for o in orders:
        assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0)


def test_strategy_is_free_of_lookahead(frames) -> None:
    assert_no_lookahead_v2(_FixtureScale(), frames)
