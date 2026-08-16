"""Golden fixture for xard_ma_cross_daily_open."""

from __future__ import annotations

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.xard_ma_cross_daily_open import (
    XardMaCrossDailyOpen,
)

PIP = 0.0001

TIMESTAMPS = [
    # Day 0
    "2026-08-01 21:00:00+00:00",
    "2026-08-01 22:00:00+00:00",
    "2026-08-01 23:00:00+00:00",
    "2026-08-02 00:00:00+00:00",
    # Day 1
    "2026-08-02 21:00:00+00:00",
    "2026-08-02 22:00:00+00:00",
    "2026-08-02 23:00:00+00:00",
    "2026-08-03 00:00:00+00:00",
    # Day 2
    "2026-08-03 21:00:00+00:00",
    "2026-08-03 22:00:00+00:00",
    "2026-08-03 23:00:00+00:00",
    "2026-08-04 00:00:00+00:00",
    # Day 3
    "2026-08-04 21:00:00+00:00",
    "2026-08-04 22:00:00+00:00",
    "2026-08-04 23:00:00+00:00",
    "2026-08-05 00:00:00+00:00",
    # Day 4
    "2026-08-05 21:00:00+00:00",
    "2026-08-05 22:00:00+00:00",
    "2026-08-05 23:00:00+00:00",
    "2026-08-06 00:00:00+00:00",
    # Day 5
    "2026-08-06 21:00:00+00:00",
    "2026-08-06 22:00:00+00:00",
    "2026-08-06 23:00:00+00:00",
    "2026-08-07 00:00:00+00:00",
    # Day 6
    "2026-08-07 21:00:00+00:00",
    "2026-08-07 22:00:00+00:00",
    "2026-08-07 23:00:00+00:00",
    "2026-08-08 00:00:00+00:00",
    # Day 7
    "2026-08-08 21:00:00+00:00",
    "2026-08-08 22:00:00+00:00",
    "2026-08-08 23:00:00+00:00",
    "2026-08-09 00:00:00+00:00",
]

OPENS = [
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
    10.00,
    10.00,
    10.00,
    10.00,
    10.00,
    10.00,
    10.00,
    10.00,
    12.00,
    12.00,
    12.00,
    12.00,
]

HIGHS = [
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
    12.00,
    10.00,
    10.00,
    10.00,
    12.00,
    10.00,
    10.00,
    10.00,
    12.00,
    10.00,
    11.00,
    11.00,
    14.00,
    12.00,
    12.00,
    12.00,
]

LOWS = [
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
    10.00,
    10.00,
    10.00,
    10.00,
    10.00,
    10.00,
    10.00,
    10.00,
    12.00,
    12.00,
    11.00,
    11.00,
]

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
    10.00,
    10.00,
    10.00,
    10.00,
    10.00,
    10.00,
    11.00,
    11.00,
    12.00,
    12.00,
    11.00,
    13.00,
]


class _FixtureScale(XardMaCrossDailyOpen):
    """Production logic, fixture-sized lookbacks."""

    SMA_FAST = 2
    SMA_SLOW1 = 3
    SMA_SLOW2 = 4
    ADR_PERIOD = 2

    @property
    def warmup_bars(self) -> int:
        return 20


@pytest.fixture(scope="module")
def frames() -> dict:
    h1 = pd.DataFrame(
        {
            "Open": OPENS,
            "High": HIGHS,
            "Low": LOWS,
            "Close": CLOSES,
            "Volume": 1.0,
        },
        index=pd.DatetimeIndex(TIMESTAMPS),
    )
    return {"H1": h1}


@pytest.fixture(scope="module")
def orders(frames) -> list:
    return list(_FixtureScale().generate_orders(frames))


def test_emits_exactly_expected_setups(orders) -> None:
    # Rule: fire only on fresh MA cross and ADR gate
    assert [str(o.decision_bar) for o in orders] == [
        "2026-08-07 23:00:00+00:00",
        "2026-08-08 23:00:00+00:00",
    ]


def test_long_order_matches_hand_computed_arithmetic(orders) -> None:
    # §4.1: Cross up at 2026-08-07 23:00
    # §4.2: Close = 11.00, DO = 10.00 -> Close > DO
    # §4.3: ADR(2) = ( (12.00-10.00) + (12.00-10.00) ) / 2 = 2.00
    # §4.3: Disp = (11.00 - 10.00) / 2.00 = 0.50 >= 0.15
    # §6: Stop = DO(t) - 5 * PIP = 10.00 - 0.0005 = 9.9995
    # §7: Risk = Close - Stop = 11.00 - 9.9995 = 1.0005
    # §7: TP = Close + 2 * Risk = 11.00 + 2 * 1.0005 = 13.0010
    # §7: Exits sum to 1.0
    o = orders[0]

    assert o.direction == 1
    assert o.entry == "market"
    assert o.entry_price is None
    assert o.stop.price == pytest.approx(9.9995, abs=1e-9)

    assert len(o.exits) == 1
    assert o.exits[0].label == "TP1"
    assert o.exits[0].price == pytest.approx(13.0010, abs=1e-9)
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)


def test_short_order_matches_hand_computed_arithmetic(orders) -> None:
    # §5.1: Cross down at 2026-08-08 23:00
    # §5.2: Close = 11.00, DO = 12.00 -> Close < DO
    # §5.3: ADR(2) = ( (12.00-10.00) + (12.00-10.00) ) / 2 = 2.00
    # §5.3: Disp = (11.00 - 12.00) / 2.00 = -0.50 <= -0.15
    # §6: Stop = DO(t) + 5 * PIP = 12.00 + 0.0005 = 12.0005
    # §7: Risk = Stop - Close = 12.0005 - 11.00 = 1.0005
    # §7: TP = Close - 2 * Risk = 11.00 - 2 * 1.0005 = 8.9990
    # §7: Exits sum to 1.0
    o = orders[1]

    assert o.direction == -1
    assert o.entry == "market"
    assert o.entry_price is None
    assert o.stop.price == pytest.approx(12.0005, abs=1e-9)

    assert len(o.exits) == 1
    assert o.exits[0].label == "TP1"
    assert o.exits[0].price == pytest.approx(8.9990, abs=1e-9)
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)


def test_strategy_is_free_of_lookahead(frames) -> None:
    # Rule: Every Wave-2 strategy must pass this on real data too.
    assert_no_lookahead_v2(_FixtureScale(), frames)
