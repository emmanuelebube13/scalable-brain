import numpy as np
import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.janus_swing_system import JanusSwingSystem


class _FixtureScale(JanusSwingSystem):
    SWING_PERIOD = 1

    @property
    def warmup_bars(self) -> int:
        return 5


@pytest.fixture
def frames() -> dict[str, pd.DataFrame]:
    dates = pd.date_range("2020-01-01", periods=30, freq="D")

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
        1.2000,
        1.1935,
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
        1.2065,
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
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.1955,
        1.2000,
        1.2000,
        1.2000,
        1.2100,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2095,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
    ]
    L = [
        1.2000,
        1.2000,
        1.1900,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.1905,
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
        1.2045,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
    ]
    C = [
        1.2000,
        1.2000,
        1.1910,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.1990,
        1.1980,
        1.1970,
        1.1960,
        1.1945,
        1.2000,
        1.2000,
        1.2000,
        1.2090,
        1.2000,
        1.2000,
        1.2000,
        1.2010,
        1.2020,
        1.2030,
        1.2040,
        1.2055,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
    ]

    df = pd.DataFrame({"Open": O, "High": H, "Low": L, "Close": C}, index=dates)
    return {"D1": df}


@pytest.fixture
def orders(frames):
    return list(_FixtureScale().generate_orders(frames))


def test_strategy_is_free_of_lookahead(frames) -> None:
    assert_no_lookahead_v2(_FixtureScale(), frames)


def test_smoke(orders) -> None:
    assert len(orders) == 2

    # LONG
    o1 = orders[0]
    assert o1.direction == 1
    assert o1.entry == "buy_limit"
    assert o1.entry_price == pytest.approx(1.193)
    assert o1.stop.price == pytest.approx(1.190)
    assert o1.exits[0].pips == pytest.approx(30.0)

    # SHORT
    o2 = orders[1]
    assert o2.direction == -1
    assert o2.entry == "sell_limit"
    assert o2.entry_price == pytest.approx(1.207)
    assert o2.stop.price == pytest.approx(1.210)
    assert o2.exits[0].pips == pytest.approx(30.0)
