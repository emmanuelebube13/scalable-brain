"""GOLDEN FIXTURE FOR h4_crossover_21_89_macd"""

from __future__ import annotations

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.h4_crossover_21_89_macd import H4Crossover2189Macd

PIP = 0.0001
CLOSES = [
    # Day 0 - Warmup (Indices 0-5)
    1.1000,
    1.1000,
    1.1000,
    1.1000,
    1.1000,
    1.1000,
    # Day 1 - Uptrend initiates (Indices 6-11)
    1.1000,
    1.1000,
    1.1000,
    1.1000,
    1.1100,
    1.1200,
    # Day 2 - Uptrend to Pullback (Indices 12-17) -> Long Setup on Bar 17
    1.1300,
    1.1200,
    1.1100,
    1.1000,
    1.0900,
    1.1200,
    # Day 3 - Resumption up to Downtrend initiation (Indices 18-23)
    1.1300,
    1.1400,
    1.1500,
    1.1300,
    1.1100,
    1.0900,
    # Day 4 - Downtrend to Pullback (Indices 24-29) -> Short Setup on Bar 29
    1.0700,
    1.0800,
    1.0900,
    1.1000,
    1.1100,
    1.0800,
    # Day 5 - Resume downtrend (Indices 30-35)
    1.0600,
    1.0400,
    1.0200,
    1.0200,
    1.0200,
    1.0200,
]


class _FixtureScale(H4Crossover2189Macd):
    EMA_PERIOD = 2
    SMA_PERIOD = 5
    MACD_FAST = 2
    MACD_SLOW = 4
    MACD_SIGNAL = 2
    D1_PERIOD = 2

    @property
    def warmup_bars(self) -> int:
        return 12


@pytest.fixture(scope="module")
def frames() -> dict:
    idx = pd.date_range("2020-01-01", periods=len(CLOSES), freq="4h", tz="UTC")
    h4 = pd.DataFrame(
        {
            "Open": CLOSES,
            "High": [c + 0.0020 for c in CLOSES],
            "Low": [c - 0.0020 for c in CLOSES],
            "Close": CLOSES,
            "Volume": 1.0,
        },
        index=idx,
    )
    d1 = (
        h4.resample("1D")
        .agg(
            {
                "Open": "first",
                "High": "max",
                "Low": "min",
                "Close": "last",
                "Volume": "sum",
            }
        )
        .dropna()
    )
    return {"H4": h4, "D1": d1}


@pytest.fixture(scope="module")
def orders(frames) -> list:
    return list(_FixtureScale().generate_orders(frames))


def test_emits_expected_orders(orders) -> None:
    """Check that we only have the exact expected orders emitted."""
    assert [str(o.decision_bar) for o in orders] == [
        "2020-01-03 20:00:00+00:00",  # Day 2, index 17
        "2020-01-05 20:00:00+00:00",  # Day 4, index 29
    ]


def test_long_arithmetic(orders) -> None:
    """§6 and §7 check for the long setup.

    # §6 stop = D1_min_low (last 2 closed D1 bars) - 4 pips
    # At index 17 (Day 2), closed D1 bars are Day 0 and Day 1.
    # Day 0 closes: all 1.1000 -> Lows = 1.0980. Min D1 Low = 1.0980
    # Day 1 closes: max 1.1200, min 1.1000 -> Lows = 1.0980. Min D1 Low = 1.0980
    # So stop = 1.0980 - 0.0004 = 1.0976

    # §7 TP1 = A + Risk
    # A = Close[17] = 1.1200
    # Risk = A - stop = 1.1200 - 1.0976 = 0.0224
    # TP1 = 1.1200 + 0.0224 = 1.1424
    """
    o = orders[0]
    assert o.direction == 1
    assert o.stop.price == pytest.approx(1.0976, abs=1e-9)
    assert o.exits[0].price == pytest.approx(1.1424, abs=1e-9)
    assert o.exits[0].fraction == pytest.approx(1.0, abs=1e-9)


def test_short_arithmetic(orders) -> None:
    """§6 and §7 check for the short setup.

    # §6 stop = D1_max_high (last 2 closed D1 bars) + 4 pips
    # At index 29 (Day 4), closed D1 bars are Day 2 and Day 3.
    # Day 2 closes: max 1.1300, min 1.0900 -> Highs = 1.1320.
    # Day 3 closes: max 1.1500, min 1.0900 -> Highs = 1.1520.
    # Max D1 High = 1.1520
    # So stop = 1.1520 + 0.0004 = 1.1524

    # §7 TP1 = A - Risk
    # A = Close[29] = 1.0800
    # Risk = stop - A = 1.1524 - 1.0800 = 0.0724
    # TP1 = 1.0800 - 0.0724 = 1.0076
    """
    o = orders[1]
    assert o.direction == -1
    assert o.stop.price == pytest.approx(1.1524, abs=1e-9)
    assert o.exits[0].price == pytest.approx(1.0076, abs=1e-9)
    assert o.exits[0].fraction == pytest.approx(1.0, abs=1e-9)


def test_fractions_sum_to_one(orders) -> None:
    """Hard minimum: assert all exit leg fractions sum to 1.0."""
    for o in orders:
        assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)


def test_every_exit_leg_asserted(orders) -> None:
    """Hard minimum: assert every exit leg."""
    for o in orders:
        assert len(o.exits) == 1
        assert o.exits[0].label == "TP1"


def test_strategy_is_free_of_lookahead(frames) -> None:
    """Audit requirement: no future leaks."""
    assert_no_lookahead_v2(_FixtureScale(), frames)
