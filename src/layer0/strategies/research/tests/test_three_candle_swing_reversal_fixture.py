"""GOLDEN FIXTURE — Three Candle Swing Reversal"""

from dataclasses import replace
import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.three_candle_swing_reversal import (
    ThreeCandleSwingReversal,
)

OPENS = [
    150.50,
    150.00,
    150.00,
    150.00,
    150.00,
    149.00,
    149.00,
    150.00,
    150.00,
    150.00,
    150.00,
    151.00,
    151.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
]

HIGHS = [
    150.90,
    150.80,
    150.70,
    150.60,
    150.10,
    149.50,
    149.80,
    150.10,
    150.20,
    150.30,
    151.50,
    151.40,
    151.30,
    150.50,
    150.50,
    150.50,
    150.50,
    150.50,
    150.50,
    150.50,
    150.50,
    150.50,
    150.50,
    150.50,
    150.50,
    150.50,
    150.50,
    150.50,
    150.50,
    150.50,
    150.50,
    150.50,
    150.50,
    150.50,
    150.50,
    150.50,
]

LOWS = [
    150.00,
    149.90,
    149.80,
    149.70,
    148.50,
    148.60,
    148.70,
    149.00,
    149.10,
    149.20,
    149.50,
    150.00,
    150.00,
    149.50,
    149.50,
    149.50,
    149.50,
    149.50,
    149.50,
    149.50,
    149.50,
    149.50,
    149.50,
    149.50,
    149.50,
    149.50,
    149.50,
    149.50,
    149.50,
    149.50,
    149.50,
    149.50,
    149.50,
    149.50,
    149.50,
    149.50,
]

CLOSES = [
    150.50,
    150.00,
    150.00,
    150.00,
    149.00,
    149.00,
    149.50,
    150.00,
    150.00,
    150.00,
    151.00,
    151.00,
    150.50,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
    150.00,
]


class _FixtureScale(ThreeCandleSwingReversal):
    @property
    def metadata(self):
        # We need USD_JPY as primary so pip=0.01 for the two-decimal-place fixture
        return replace(super().metadata, pairs=["USD_JPY"])


@pytest.fixture(scope="module")
def frames() -> dict:
    idx = pd.date_range("2020-01-01", periods=len(CLOSES), freq="D", tz="UTC")
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


def test_orders_emitted(orders) -> None:
    # §4.4 trigger event: at bar 6 (2020-01-07), long trigger met
    # §5.4 trigger event: at bar 12 (2020-01-13), short trigger met
    assert len(orders) == 2
    assert [str(o.decision_bar) for o in orders] == [
        "2020-01-07 00:00:00+00:00",
        "2020-01-13 00:00:00+00:00",
    ]


def test_long_order_logic(orders) -> None:
    o = orders[0]

    # §4 Entry type and level
    # E_long = min(open[t-2], close[t-2]) = min(150.00, 149.00) = 149.00
    assert o.direction == 1
    assert o.entry == "buy_limit"
    assert o.entry_price == pytest.approx(149.00)

    # §6 stop = min(E_long - 50 pip, min(low[t-2], low[t-1]) - 15 pip)
    # min(149.00 - 0.50, min(148.50, 148.60) - 0.15) = min(148.50, 148.35) = 148.35
    assert o.stop.price == pytest.approx(148.35)

    # §7 Exit leg TP1 = E_long + 100 pip = 149.00 + 1.00 = 150.00
    assert len(o.exits) == 1
    assert o.exits[0].label == "TP1"
    assert o.exits[0].price == pytest.approx(150.00)

    # §7 Fractions sum to 1.0
    assert o.exits[0].fraction == pytest.approx(1.0)
    assert o.expires_after_bars == 2


def test_short_order_logic(orders) -> None:
    o = orders[1]

    # §5 Entry type and level
    # E_short = max(open[t-2], close[t-2]) = max(150.00, 151.00) = 151.00
    assert o.direction == -1
    assert o.entry == "sell_limit"
    assert o.entry_price == pytest.approx(151.00)

    # §6 stop = max(E_short + 50 pip, max(high[t-2], high[t-1]) + 15 pip)
    # max(151.00 + 0.50, max(151.50, 151.40) + 0.15) = max(151.50, 151.65) = 151.65
    assert o.stop.price == pytest.approx(151.65)

    # §7 Exit leg TP1 = E_short - 100 pip = 151.00 - 1.00 = 150.00
    assert len(o.exits) == 1
    assert o.exits[0].label == "TP1"
    assert o.exits[0].price == pytest.approx(150.00)

    # §7 Fractions sum to 1.0
    assert o.exits[0].fraction == pytest.approx(1.0)
    assert o.expires_after_bars == 2


def test_no_lookahead(frames) -> None:
    # §9 Causality check
    assert_no_lookahead_v2(_FixtureScale(), frames)
