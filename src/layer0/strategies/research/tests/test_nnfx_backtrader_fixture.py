"""GOLDEN FIXTURE — NNFX Backtrader."""

from __future__ import annotations

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.nnfx_backtrader import NnfxBacktrader


class _FixtureScale(NnfxBacktrader):
    """Production logic, fixture-sized lookbacks."""

    BUTTER_PERIOD = 3
    STC_FAST = 2
    STC_SLOW = 4
    STC_CYCLE = 2
    ITREND_PERIOD = 3
    DAMIANI_ATR_FAST = 2
    DAMIANI_ATR_SLOW = 4
    DAMIANI_STD_FAST = 3
    DAMIANI_STD_SLOW = 5
    ATR_PERIOD = 3

    @property
    def warmup_bars(self) -> int:
        return 10


CLOSES = [
    10.00,
    10.00,
    10.00,
    10.00,
    10.00,
    10.00,
    10.00,
    10.00,
    10.00,
    10.00,
    10.00,
    10.00,
    10.00,
    10.00,
    10.00,
    10.00,
    10.00,
    10.00,
    10.00,
    10.00,
    10.50,
    11.00,
    11.10,
    11.20,
    11.30,
    11.40,
    11.50,
    11.00,
    10.50,
    10.00,
    9.50,
    9.40,
    9.30,
    9.20,
]


@pytest.fixture(scope="module")
def frames() -> dict:
    idx = pd.date_range("2020-01-01", periods=len(CLOSES), freq="D", tz="UTC")
    d1 = pd.DataFrame(
        {
            "Open": CLOSES,
            "High": [c + 0.10 for c in CLOSES],
            "Low": [c - 0.10 for c in CLOSES],
            "Close": CLOSES,
            "Volume": 1.0,
        },
        index=idx,
    )
    return {"D1": d1, "H4": d1}


@pytest.fixture(scope="module")
def orders(frames) -> list:
    return list(_FixtureScale().generate_orders(frames))


def test_emits_expected_long_order(orders) -> None:
    # We expect one long at index 20 (2020-01-21) and one short at index 27 (2020-01-28).
    assert len(orders) == 2

    o = orders[0]
    assert o.direction == 1
    assert str(o.decision_bar) == "2020-01-21 00:00:00+00:00"

    # §6 ATR(3) hand calculation at bar 20:
    # bars 0-19: close is constant 10.00, TR=0.20. ATR=0.20.
    # bar 20: close 10.50, h=10.60, prev_c=10.00. TR = max(0.20, 10.60-10.00) = 0.60.
    # ATR[20] = 0.20 + (2/4)*(0.60 - 0.20) = 0.40.
    # §6 stop = A - 1.5 * ATR = 10.50 - 1.5 * 0.40 = 9.90.

    # §7 TP1 = A + 3.0 * ATR = 10.50 + 3.0 * 0.40 = 11.70.
    assert o.stop.price == pytest.approx(9.90, abs=1e-9)
    assert o.exits[0].price == pytest.approx(11.70, abs=1e-9)


def test_emits_expected_short_order(orders) -> None:
    o = orders[1]
    assert o.direction == -1
    assert str(o.decision_bar) == "2020-01-28 00:00:00+00:00"

    # §6 ATR(3) continuation to bar 27:
    # bar 21: C=11.00, TR=0.60 -> ATR=0.40 + 0.5*(0.60 - 0.40) = 0.50
    # bar 22: C=11.10, TR=0.20 -> ATR=0.50 + 0.5*(0.20 - 0.50) = 0.35
    # bar 23: C=11.20, TR=0.20 -> ATR=0.35 + 0.5*(0.20 - 0.35) = 0.275
    # bar 24: C=11.30, TR=0.20 -> ATR=0.275 + 0.5*(0.20 - 0.275) = 0.2375
    # bar 25: C=11.40, TR=0.20 -> ATR=0.2375 + 0.5*(0.20 - 0.2375) = 0.21875
    # bar 26: C=11.50, TR=0.20 -> ATR=0.21875 + 0.5*(0.20 - 0.21875) = 0.209375
    # bar 27: C=11.00, TR=0.60 -> ATR=0.209375 + 0.5*(0.60 - 0.209375) = 0.4046875
    # §6 stop = A + 1.5 * ATR = 11.00 + 1.5 * 0.4046875 = 11.60703125
    # §7 TP1 = A - 3.0 * ATR = 11.00 - 3.0 * 0.4046875 = 9.7859375

    assert o.stop.price == pytest.approx(11.60703125, abs=1e-9)
    assert o.exits[0].price == pytest.approx(9.7859375, abs=1e-9)


def test_exit_fractions_and_legs(orders) -> None:
    # §7 Exit legs sum to 1.0.
    for o in orders:
        assert len(o.exits) == 1
        assert o.exits[0].label == "TP1"
        assert o.exits[0].fraction == 1.0
        assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)


def test_strategy_is_free_of_lookahead(frames) -> None:
    assert_no_lookahead_v2(_FixtureScale(), frames)
