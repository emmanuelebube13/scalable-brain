"""Golden fixture for precision_swing."""

from __future__ import annotations

import pandas as pd
import pytest
from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.precision_swing import PrecisionSwing

CLOSES = [
    10.00,
    10.45,
    10.88,
    11.28,
    11.63,
    11.93,
    12.16,
    12.32,
    12.40,
    12.40,
    12.32,
    12.17,
    11.95,
    11.68,
    11.37,
    11.03,
    10.68,
    10.34,
    10.01,
    9.73,
    9.49,
    9.31,
    9.20,
    9.16,
    9.21,
    9.33,
    9.53,
    9.80,
    10.14,
    10.52,
    10.94,
    11.38,
    11.83,
    12.27,
    12.69,
    13.06,
    13.39,
    13.65,
    13.84,
    13.95,
    13.98,
    13.93,
    13.81,
    13.62,
    13.37,
    13.07,
    12.75,
    12.40,
    12.05,
    11.72,
    11.41,
    11.15,
    10.94,
    10.80,
    10.74,
    10.75,
    10.84,
    11.01,
    11.25,
    11.56,
    11.93,
    12.33,
    12.77,
    13.22,
    13.66,
    14.09,
    14.48,
    14.83,
    15.12,
    15.34,
    15.48,
    15.55,
    15.53,
    15.44,
    15.28,
    15.05,
    14.77,
    14.46,
    14.12,
    13.77,
    14.42,
    14.01,
    13.62,
    13.29,
    13.02,
    12.83,
    12.71,
    12.66,
    12.70,
    12.82,
    13.00,
    13.24,
    13.53,
    13.86,
    14.20,
    14.55,
    14.89,
    15.20,
    15.46,
    15.68,
    15.83,
    15.90,
    15.90,
    15.82,
    15.66,
    15.42,
    15.12,
    14.76,
    14.36,
    13.93,
    13.48,
    13.04,
    12.60,
    12.21,
    11.85,
    11.56,
    11.33,
    11.18,
    11.10,
    11.11,
    11.19,
    11.34,
    11.56,
    11.83,
    12.15,
    12.49,
    12.83,
    13.18,
    13.50,
    13.79,
    14.03,
    14.20,
    14.31,
    14.34,
    14.29,
    14.16,
    13.96,
    13.68,
    13.35,
    12.96,
    12.54,
    12.10,
    11.65,
    11.21,
    10.80,
    10.42,
    10.10,
    9.84,
    9.66,
    9.55,
    9.52,
    9.57,
    9.70,
    9.89,
    10.14,
    10.44,
    10.77,
    11.12,
    11.47,
    11.80,
]

HIGHS = [c + 0.50 for c in CLOSES]
LOWS = [c - 0.50 for c in CLOSES]


class _FixtureScale(PrecisionSwing):
    pass


@pytest.fixture(scope="module")
def frames() -> dict:
    idx = pd.date_range("2020-01-01", periods=len(CLOSES), freq="4h", tz="UTC")
    d1 = pd.DataFrame(
        {
            "Open": CLOSES,
            "High": HIGHS,
            "Low": LOWS,
            "Close": CLOSES,
            "Volume": 1.0,
        },
        index=idx,
    )
    return {"H4": d1}


@pytest.fixture(scope="module")
def orders(frames) -> list:
    return list(_FixtureScale().generate_orders(frames))


def test_emits_expected_orders(orders) -> None:
    assert len(orders) == 4


def test_long_order(orders) -> None:
    # Math: stop level sl = 10.24, close = 14.77
    # §4.5: Stop = SL_level = 10.24
    # §7: TP = Close + 1.25 * (Close - SL_level)
    # Risk = 14.77 - 10.24 = 4.53
    # Target = 1.25 * 4.53 = 5.6625
    # TP = 14.77 + 5.6625 = 20.4325
    o = orders[0]
    assert o.direction == 1
    assert o.stop.price == pytest.approx(10.24, abs=1e-2)
    assert o.exits[0].price == pytest.approx(20.4325, abs=1e-2)


def test_short_order(orders) -> None:
    # Math: stop level sl = 16.05, close = 13.00
    # §5.5: Stop = SL_level = 16.05
    # §7: TP = Close - 1.25 * (SL_level - Close)
    # Risk = 16.05 - 13.00 = 3.05
    # Target = 1.25 * 3.05 = 3.8125
    # TP = 13.00 - 3.8125 = 9.1875
    o = orders[1]
    assert o.direction == -1
    assert o.stop.price == pytest.approx(16.05, abs=1e-2)
    assert o.exits[0].price == pytest.approx(9.1875, abs=1e-2)


def test_exit_fractions(orders) -> None:
    for o in orders:
        assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0)


def test_no_lookahead(frames) -> None:
    assert_no_lookahead_v2(_FixtureScale(), frames)
