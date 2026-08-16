"""GOLDEN FIXTURE for KPL Donchian Breakout."""

from __future__ import annotations

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.kpl_donchian_breakout import KplDonchianBreakout


class _FixtureScale(KplDonchianBreakout):
    """Production logic, fixture-sized lookbacks."""

    DONCHIAN_PERIOD = 2
    ATR_PERIOD = 1

    @property
    def warmup_bars(self) -> int:
        return 3


# ---------------------------------------------------------------------------
# 1. The bars, and why these bars
# ---------------------------------------------------------------------------
# We need a long setup, then a short setup.
# DONCHIAN_PERIOD = 2, ATR_PERIOD = 1
# Warmup takes the first 3 bars (indices 0, 1, 2).
# Bar 3: Long breakout. C[3] > max(H[1], H[2])
# Bar 4: Intermediate no-signal bar.
# Bar 5: Short breakout. C[5] < min(L[3], L[4])
CLOSES = [
    1.1010,  # 0: warmup
    1.1010,  # 1: warmup
    1.1010,  # 2: warmup
    1.1030,  # 3: C=1.1030 > max(H[1],H[2])=1.1020 -> LONG
    1.1030,  # 4: C=1.1030 inside channel
    1.0990,  # 5: C=1.0990 < min(L[3],L[4])=1.1010 -> SHORT
]

HIGHS = [
    1.1020,  # 0
    1.1020,  # 1
    1.1020,  # 2
    1.1040,  # 3
    1.1040,  # 4
    1.1030,  # 5
]

LOWS = [
    1.1000,  # 0
    1.1000,  # 1
    1.1000,  # 2
    1.1010,  # 3
    1.1010,  # 4
    1.0980,  # 5
]


@pytest.fixture(scope="module")
def frames() -> dict[str, pd.DataFrame]:
    idx = pd.date_range("2020-01-01", periods=len(CLOSES), freq="D", tz="UTC")
    d1 = pd.DataFrame(
        {
            "Open": [1.1010] * len(CLOSES),
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


# ---------------------------------------------------------------------------
# 2 + 3. Expected values, computed by hand, then asserted
# ---------------------------------------------------------------------------


def test_strategy_is_free_of_lookahead(frames) -> None:
    """Every Wave-2 strategy must pass this on real data too."""
    assert_no_lookahead_v2(_FixtureScale(), frames)


def test_emits_exactly_the_expected_setups(orders) -> None:
    """Rule: emit orders when daily close breaks 20-day extreme."""
    assert [str(o.decision_bar) for o in orders] == [
        "2020-01-04 00:00:00+00:00",
        "2020-01-06 00:00:00+00:00",
    ]


def test_long_order_matches_hand_computed_arithmetic(orders) -> None:
    """Rule: Long event: Close(t) > DCU(t) AND Close(t-1) <= DCU(t-1).
    Initial stop: Close(t) - 2 * ATR(t).
    Trailing stop: 2 * ATR(t).

    At 2020-01-04 00:00 (index 3):
      dcu_s[3] = max(H[1], H[2]) = max(1.1020, 1.1020) = 1.1020
      Close[3] = 1.1030 > 1.1020  -> LONG FIRES
      Close[2] = 1.1010 <= 1.1020 (dcu_s[2])
      TR[3] = max(H[3]-L[3], H[3]-C[2], C[2]-L[3]) = max(0.0030, 0.0030, 0.0000) = 0.0030
      ATR[3] = TR[3] = 0.0030  (since ATR_PERIOD=1)
      Stop = Close[3] - 2 * ATR[3] = 1.1030 - 2 * 0.0030 = 1.0970
    """
    o = orders[0]

    assert o.direction == 1
    assert o.entry == "market"
    assert o.stop.price == pytest.approx(1.0970, abs=1e-9)
    assert o.stop.trail_atr_multiple == 2.0

    assert len(o.exits) == 1
    assert o.exits[0].fraction == pytest.approx(1.0, abs=1e-9)
    assert o.exits[0].kind == "trailing"
    assert o.exits[0].atr_multiple == 2.0


def test_short_order_matches_hand_computed_arithmetic(orders) -> None:
    """Rule: Short event: Close(t) < DCL(t) AND Close(t-1) >= DCL(t-1).
    Initial stop: Close(t) + 2 * ATR(t).

    At 2020-01-06 00:00 (index 5):
      dcl_s[5] = min(L[3], L[4]) = min(1.1010, 1.1010) = 1.1010
      Close[5] = 1.0990 < 1.1010  -> SHORT FIRES
      Close[4] = 1.1030 >= 1.1000 (dcl_s[4])
      TR[5] = max(H[5]-L[5], H[5]-C[4], C[4]-L[5]) = max(0.0050, 0.0000, 0.0050) = 0.0050
      ATR[5] = TR[5] = 0.0050  (since ATR_PERIOD=1)
      Stop = Close[5] + 2 * ATR[5] = 1.0990 + 2 * 0.0050 = 1.1090
    """
    o = orders[1]

    assert o.direction == -1
    assert o.entry == "market"
    assert o.stop.price == pytest.approx(1.1090, abs=1e-9)
    assert o.stop.trail_atr_multiple == 2.0

    assert len(o.exits) == 1
    assert o.exits[0].fraction == pytest.approx(1.0, abs=1e-9)
    assert o.exits[0].kind == "trailing"
    assert o.exits[0].atr_multiple == 2.0
