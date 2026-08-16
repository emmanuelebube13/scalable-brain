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
    O = [1.2000] * 30
    H = [1.2000] * 30
    L = [1.2000] * 30
    C = [1.2000] * 30

    L[2] = 1.1900
    C[2] = 1.1910

    C[8] = 1.1990
    C[9] = 1.1980
    C[10] = 1.1970
    C[11] = 1.1960

    O[12] = 1.1935
    H[12] = 1.1955
    L[12] = 1.1905
    C[12] = 1.1945

    H[16] = 1.2100
    C[16] = 1.2090

    C[20] = 1.2010
    C[21] = 1.2020
    C[22] = 1.2030
    C[23] = 1.2040

    O[24] = 1.2065
    H[24] = 1.2095
    L[24] = 1.2045
    C[24] = 1.2055

    df = pd.DataFrame({"Open": O, "High": H, "Low": L, "Close": C}, index=dates)
    return {"D1": df}


@pytest.fixture
def orders(frames):
    return list(_FixtureScale().generate_orders(frames))


def test_strategy_is_free_of_lookahead(frames) -> None:
    assert_no_lookahead_v2(_FixtureScale(), frames)


def test_long_entry_conditions(orders) -> None:
    # We should have exactly 2 orders (1 long, 1 short)
    assert len(orders) == 2
    o = orders[0]

    # SPEC §4.1: Bullish straight bar
    # mid_t = (1.1955 + 1.1905) / 2 = 1.1930
    # O(t) > mid(t) -> 1.1935 > 1.1930
    # C(t) > O(t) -> 1.1945 > 1.1935
    assert o.direction == 1
    assert o.entry == "buy_limit"
    # Entry price = mid(t) = 1.1930
    assert o.entry_price == pytest.approx(1.1930)


def test_long_stop_and_exit(orders) -> None:
    o = orders[0]
    # SPEC §6: Initial stop = L(t) - 5 pips
    # 1.1905 - 0.0005 = 1.1900
    assert o.stop.price == pytest.approx(1.1900)

    # SPEC §7: TRAIL leg pips = R = mid(t) - stop.price
    # 1.1930 - 1.1900 = 0.0030 = 30.0 pips
    assert len(o.exits) == 1
    assert o.exits[0].fraction == pytest.approx(1.0)
    assert o.exits[0].pips == pytest.approx(30.0)
    assert o.exits[0].kind == "trailing"


def test_short_entry_conditions(orders) -> None:
    o = orders[1]

    # SPEC §5.1: Bearish straight bar
    # mid_t = (1.2095 + 1.2045) / 2 = 1.2070
    # O(t) < mid(t) -> 1.2065 < 1.2070
    # C(t) < O(t) -> 1.2055 < 1.2065
    assert o.direction == -1
    assert o.entry == "sell_limit"
    # Entry price = mid(t) = 1.2070
    assert o.entry_price == pytest.approx(1.2070)


def test_short_stop_and_exit(orders) -> None:
    o = orders[1]
    # SPEC §6: Initial stop = H(t) + 5 pips
    # 1.2095 + 0.0005 = 1.2100
    assert o.stop.price == pytest.approx(1.2100)

    # SPEC §7: TRAIL leg pips = R = stop.price - mid(t)
    # 1.2100 - 1.2070 = 0.0030 = 30.0 pips
    assert len(o.exits) == 1
    assert o.exits[0].fraction == pytest.approx(1.0)
    assert o.exits[0].pips == pytest.approx(30.0)
    assert o.exits[0].kind == "trailing"
