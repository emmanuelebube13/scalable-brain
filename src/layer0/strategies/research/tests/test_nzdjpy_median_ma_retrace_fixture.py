import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.nzdjpy_median_ma_retrace import (
    NzdjpyMedianMaRetrace,
)

CLOSES = [
    80.00,
    81.00,
    82.00,
    83.00,
    84.00,
    85.00,
    86.00,
    75.00,
    100.00,
    100.00,
]


class _FixtureScale(NzdjpyMedianMaRetrace):
    FAST_PERIOD = 2
    SLOW_PERIOD = 5

    @property
    def warmup_bars(self) -> int:
        return 5


@pytest.fixture(scope="module")
def frames() -> dict:
    idx = pd.date_range("2020-01-01", periods=len(CLOSES), freq="1h", tz="UTC")
    h1 = pd.DataFrame(
        {
            "Open": CLOSES,
            "High": [c + 1.00 for c in CLOSES],
            "Low": [c - 1.00 for c in CLOSES],
            "Close": CLOSES,
            "Volume": 1.0,
        },
        index=idx,
    )
    return {"H1": h1}


@pytest.fixture(scope="module")
def orders(frames) -> list:
    return list(_FixtureScale().generate_orders(frames))


def test_emits_exactly_the_expected_setups(orders) -> None:
    assert len(orders) == 2
    assert str(orders[0].decision_bar) == "2020-01-01 07:00:00+00:00"
    assert str(orders[1].decision_bar) == "2020-01-01 08:00:00+00:00"


def test_long_order_math(orders) -> None:
    o = orders[0]
    assert o.direction == 1
    assert o.entry == "market"
    # §4.1: MA5 < MA50 and MA5[t-1] >= MA50[t-1] -> Buy order at 07:00
    # §4.2: Hour is 7 (in 7..13) and minute is 0.
    # §6: Stop = Close * (1 - 0.005) = 75.00 * 0.995 = 74.625
    assert o.stop.price == pytest.approx(74.625, abs=1e-9)
    # §7: TP = Close * (1 + 0.004) = 75.00 * 1.004 = 75.300
    assert o.exits[0].price == pytest.approx(75.300, abs=1e-9)
    assert o.exits[0].label == "TP"


def test_short_order_math(orders) -> None:
    o = orders[1]
    assert o.direction == -1
    assert o.entry == "market"
    # §5.1: MA5 > MA50 and MA5[t-1] <= MA50[t-1] -> Sell order at 08:00
    # §5.2: Hour is 8 (in 7..13) and minute is 0.
    # §6: Stop = Close * (1 + 0.005) = 100.00 * 1.005 = 100.500
    assert o.stop.price == pytest.approx(100.500, abs=1e-9)
    # §7: TP = Close * (1 - 0.004) = 100.00 * 0.996 = 99.600
    assert o.exits[0].price == pytest.approx(99.600, abs=1e-9)
    assert o.exits[0].label == "TP"


def test_fractions_sum_to_one(orders) -> None:
    for o in orders:
        assert len(o.exits) == 1
        assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)
        assert o.exits[0].fraction == pytest.approx(1.0, abs=1e-9)


def test_strategy_is_free_of_lookahead(frames) -> None:
    assert_no_lookahead_v2(_FixtureScale(), frames)
