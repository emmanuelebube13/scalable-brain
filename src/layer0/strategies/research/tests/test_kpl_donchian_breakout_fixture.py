import numpy as np
import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.kpl_donchian_breakout import KplDonchianBreakout


class _FixtureScale(KplDonchianBreakout):
    DONCHIAN_PERIOD = 2
    ATR_PERIOD = 2

    @property
    def warmup_bars(self) -> int:
        return 5


@pytest.fixture
def frames() -> dict[str, pd.DataFrame]:
    dates = pd.date_range("2020-01-01", periods=25, freq="D")

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
        1.2000,
    ]
    H = [
        1.2020,
        1.2020,
        1.2020,
        1.2020,
        1.2020,
        1.2020,
        1.2040,
        1.2020,
        1.2020,
        1.2020,
        1.2020,
        1.2020,
        1.2020,
        1.2020,
        1.2020,
        1.2020,
        1.2020,
        1.2020,
        1.2020,
        1.2020,
        1.2020,
        1.2020,
        1.2020,
        1.2020,
        1.2020,
    ]
    L = [
        1.1980,
        1.1980,
        1.1980,
        1.1980,
        1.1980,
        1.1980,
        1.1980,
        1.1980,
        1.1980,
        1.1980,
        1.1980,
        1.1980,
        1.1980,
        1.1980,
        1.1980,
        1.1980,
        1.1960,
        1.1980,
        1.1980,
        1.1980,
        1.1980,
        1.1980,
        1.1980,
        1.1980,
        1.1980,
    ]
    C = [
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2030,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.2000,
        1.1970,
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
    return {"D1": df}


@pytest.fixture
def orders(frames):
    return list(_FixtureScale().generate_orders(frames))


def test_strategy_is_free_of_lookahead(frames) -> None:
    assert_no_lookahead_v2(_FixtureScale(), frames)


def test_smoke(orders) -> None:
    assert len(orders) == 2

    # LONG (decision_bar='2020-01-07')
    o1 = orders[0]
    assert o1.direction == 1
    assert o1.entry == "market"
    assert o1.entry_price is None
    assert o1.stop.price == pytest.approx(1.1923333333333335)
    assert o1.stop.trail_atr_multiple == 2.0
    assert o1.exits[0].atr_multiple == 2.0

    # SHORT (decision_bar='2020-01-17')
    o2 = orders[1]
    assert o2.direction == -1
    assert o2.entry == "market"
    assert o2.entry_price is None
    assert o2.stop.price == pytest.approx(1.2076667795672522)
    assert o2.stop.trail_atr_multiple == 2.0
    assert o2.exits[0].atr_multiple == 2.0
