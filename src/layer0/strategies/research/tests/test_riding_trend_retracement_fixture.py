"""GOLDEN FIXTURE for riding_trend_retracement"""

from __future__ import annotations

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.riding_trend_retracement import (
    RidingTrendRetracement,
)

PIP = 0.0001

CLOSES = [
    # day 0
    10.00,
    10.01,
    10.02,
    10.03,
    10.04,
    10.05,
    # day 1
    10.10,
    10.11,
    10.12,
    10.13,
    10.14,
    10.15,
    # day 2
    10.20,
    10.21,
    10.22,
    10.23,
    10.24,
    10.25,
    # day 3
    10.30,
    10.31,
    10.32,
    10.33,
    10.34,
    10.35,
    # day 4
    10.40,
    10.41,
    10.42,
    10.43,
    10.44,
    10.45,
    # day 5 (H1 at index 30)
    10.50,  # 30
    10.48,  # 31
    10.46,  # 32 (L1)
    10.48,  # 33
    10.55,  # 34 (H2)
    10.53,  # 35
    # day 6
    10.51,  # 36 (L2)
    10.53,  # 37
    10.60,  # 38 (H3)
    10.58,  # 39
    10.56,  # 40 (Confirms H3)
    10.54,  # 41
    # day 7 transition
    10.50,
    10.40,
    10.30,
    10.20,
    10.10,
    10.00,
    # day 8
    9.90,
    9.80,
    9.70,
    9.60,
    9.50,
    9.40,
    # day 9
    9.30,
    9.20,
    9.10,
    9.00,
    8.90,
    8.80,
    # day 10
    8.70,
    8.60,
    8.50,
    8.40,
    8.30,
    8.20,
    # day 11 (L1 at 66)
    8.10,  # 66
    8.12,  # 67
    8.14,  # 68 (H1)
    8.12,  # 69
    8.00,  # 70 (L2)
    8.02,  # 71
    # day 12
    8.04,  # 72 (H2)
    8.02,  # 73
    7.90,  # 74 (L3)
    7.92,  # 75
    7.94,  # 76 (Confirms L3)
    7.96,  # 77
]


class _FixtureScale(RidingTrendRetracement):
    TREND_PERIOD = 3
    TREND_SLOPE_PERIOD = 1
    ZIGZAG_DEPTH = 2
    ZIGZAG_BACKSTEP = 2

    @property
    def warmup_bars(self) -> int:
        return 18


@pytest.fixture(scope="module")
def frames() -> dict:
    idx = pd.date_range("2020-01-01", periods=len(CLOSES), freq="4h", tz="UTC")
    h4 = pd.DataFrame(
        {
            "Open": CLOSES,
            "High": [c + 0.01 for c in CLOSES],
            "Low": [c - 0.01 for c in CLOSES],
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


def test_emits_expected_long_order(orders) -> None:
    # Rule §4.2: entry = H3 + 3 pips
    long_orders = [o for o in orders if o.direction == 1]
    assert len(long_orders) >= 1
    o = long_orders[0]

    # Bar 40 is 2020-01-07 16:00:00+00:00
    assert str(o.decision_bar) == "2020-01-07 16:00:00+00:00"
    assert o.entry == "buy_stop"

    # §4.2 H3 + 3 pips = 10.61 + 0.0003 = 10.6103
    assert o.entry_price == pytest.approx(10.6103, abs=1e-9)
    # §6 SL = max(10.6103 - 0.0100, 10.50 - 0.0020) = 10.6003
    assert o.stop.price == pytest.approx(10.6003, abs=1e-9)


def test_long_exit_legs(orders) -> None:
    # Rule §7: 3 scale-out legs summing to 1.0
    o = [o for o in orders if o.direction == 1][0]

    # §7 TP1 = 10.6103 + 0.0200 = 10.6303
    # §7 TP2 = 10.6103 + 0.0400 = 10.6503
    # §7 TP3 = 10.6103 + 0.0600 = 10.6703
    assert [leg.label for leg in o.exits] == ["TP1", "TP2", "TP3"]
    assert [leg.price for leg in o.exits] == pytest.approx(
        [10.6303, 10.6503, 10.6703], abs=1e-9
    )
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)
    assert o.stop.move_to_breakeven_on == "TP2"


def test_emits_expected_short_order(orders) -> None:
    # Rule §5.2: entry = L3 - 3 pips
    short_orders = [o for o in orders if o.direction == -1]
    assert len(short_orders) >= 1
    o = short_orders[0]

    # Bar 76 is 2020-01-13 16:00:00+00:00
    assert str(o.decision_bar) == "2020-01-13 16:00:00+00:00"
    assert o.entry == "sell_stop"

    # §5.2 L3 - 3 pips = 7.89 - 0.0003 = 7.8897
    assert o.entry_price == pytest.approx(7.8897, abs=1e-9)
    # §6 SL = min(7.8897 + 0.0100, 8.05 + 0.0020) = 7.8997
    assert o.stop.price == pytest.approx(7.8997, abs=1e-9)


def test_short_exit_legs(orders) -> None:
    o = [o for o in orders if o.direction == -1][0]

    # §7 TP1 = 7.8897 - 0.0200 = 7.8697
    # §7 TP2 = 7.8897 - 0.0400 = 7.8497
    # §7 TP3 = 7.8897 - 0.0600 = 7.8297
    assert [leg.label for leg in o.exits] == ["TP1", "TP2", "TP3"]
    assert [leg.price for leg in o.exits] == pytest.approx(
        [7.8697, 7.8497, 7.8297], abs=1e-9
    )
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)


def test_strategy_is_free_of_lookahead(frames) -> None:
    # §9 Causality Audit
    assert_no_lookahead_v2(_FixtureScale(), frames)
