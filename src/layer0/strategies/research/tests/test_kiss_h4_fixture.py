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


def test_strategy_is_free_of_lookahead(frames) -> None:
    assert_no_lookahead_v2(_FixtureScale(), frames)


def test_smoke(orders) -> None:
    assert len(orders) == 2

    o1 = orders[0]
    assert o1.direction == 1
    assert o1.entry == "market"
    assert o1.stop.price == pytest.approx(1.194)
    assert o1.exits[0].price == pytest.approx(1.2115)

    o2 = orders[1]
    assert o2.direction == -1
    assert o2.entry == "market"
    assert o2.stop.price == pytest.approx(1.2085)
    assert o2.exits[0].price == pytest.approx(1.191)
