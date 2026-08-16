"""GOLDEN FIXTURE — the deliverable shape every Wave-2 strategy must copy."""

from __future__ import annotations

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.mtf_swing_weekly_pivots import (
    MtfSwingWeeklyPivots,
)

# ---------------------------------------------------------------------------
# 1. The bars, and why these bars
# ---------------------------------------------------------------------------
# 36 H4 bars = 6 clean days. The series rises steadily (so the D1 trend filter
# opens for long), and prints a bullish rejection candle to trigger the setup.
# The second half of the series falls steadily (D1 trend down) and prints a
# bearish rejection candle.
CLOSES = [
    10.00,
    10.02,
    10.04,
    10.06,
    10.08,
    10.10,
    10.12,
    10.14,
    10.16,
    10.18,
    10.20,
    10.22,
    10.24,
    10.26,
    10.28,
    10.30,
    10.32,
    10.34,
    10.20,
    10.50,
    10.50,
    10.50,
    10.50,
    10.50,
    10.48,
    10.46,
    10.44,
    10.42,
    10.40,
    10.38,
    10.36,
    10.34,
    10.32,
    10.30,
    10.28,
    10.26,
    10.40,
    10.10,
    10.10,
    10.10,
    10.10,
    10.10,
]


class _FixtureScale(MtfSwingWeeklyPivots):
    """Production logic, fixture-sized lookbacks."""

    D1_EMA_FAST = 2
    D1_EMA_SLOW = 3
    H4_EMA = 1
    H4_RSI = 2
    STOP_WINDOW = 3

    @property
    def warmup_bars(self) -> int:
        return 12


@pytest.fixture(scope="module")
def frames() -> dict:
    idx = pd.date_range("2026-01-01", periods=len(CLOSES), freq="4h", tz="UTC")
    h4 = pd.DataFrame({"Close": CLOSES}, index=idx)
    h4["Open"] = h4["Close"].shift(1).fillna(h4["Close"])
    h4["High"] = h4[["Open", "Close"]].max(axis=1) + 0.05
    h4["Low"] = h4[["Open", "Close"]].min(axis=1) - 0.05
    h4["Volume"] = 1.0

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


# ---------------------------------------------------------------------------
# 2 + 3. Expected values, computed by hand, then asserted
# ---------------------------------------------------------------------------


def test_emits_exactly_the_expected_setups(orders) -> None:
    """Rule: fire only when BOTH the D1 trend is correct AND pullback validates."""
    assert [str(o.decision_bar) for o in orders] == [
        "2026-01-04 04:00:00+00:00",
        "2026-01-07 04:00:00+00:00",
    ]


def test_first_order_matches_hand_computed_arithmetic_long(orders) -> None:
    """The full trade plan, derived from the spec — not copied from output.

    At 2026-01-04 04:00 (bar 19):
    # §4.1 D1 regime is uptrend (closes rising linearly from 10.00 to 10.34)
    # §4.4 Bullish reversal: Close(19)=10.50 > Open(19)=10.20, Close(19)=10.50 > High(18)=10.39
    # §6 Stop Rule: S_long(19) = min(Low[17...19])
    # Low(17) = min(10.32, 10.34) - 0.05 = 10.27
    # Low(18) = min(10.34, 10.20) - 0.05 = 10.15
    # Low(19) = min(10.20, 10.50) - 0.05 = 10.15
    # §6 Stop = min(10.27, 10.15, 10.15) = 10.15
    # §7 TP1 = Close + 2.0 * (Close - S_long) = 10.50 + 2.0 * (10.50 - 10.15) = 11.20
    """
    o = orders[0]

    assert o.direction == 1
    assert o.entry == "market"
    assert o.entry_price is None
    assert o.stop.price == pytest.approx(10.15, abs=1e-9)

    assert [leg.label for leg in o.exits] == ["TP1"]
    assert [leg.price for leg in o.exits] == pytest.approx([11.20], abs=1e-9)

    # Asserting exit legs sum to exactly 1.0 (Hard Minimums rule)
    assert [leg.fraction for leg in o.exits] == pytest.approx([1.0])
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)


def test_second_order_matches_hand_computed_arithmetic_short(orders) -> None:
    """The full trade plan, derived from the spec — not copied from output.

    At 2026-01-07 04:00 (bar 31):
    # §5.1 D1 regime is downtrend (closes falling linearly from 10.48 to 10.26)
    # §5.4 Bearish reversal: Close(31)=10.10 < Open(31)=10.40, Close(31)=10.10 < Low(30)=10.21
    # §6 Stop Rule: S_short(31) = max(High[29...31])
    # High(29) = max(10.28, 10.26) + 0.05 = 10.33
    # High(30) = max(10.26, 10.40) + 0.05 = 10.45
    # High(31) = max(10.40, 10.10) + 0.05 = 10.45
    # §6 Stop = max(10.33, 10.45, 10.45) = 10.45
    # §7 TP1 = Close - 2.0 * (S_short - Close) = 10.10 - 2.0 * (10.45 - 10.10) = 9.40
    """
    o = orders[1]

    assert o.direction == -1
    assert o.entry == "market"
    assert o.entry_price is None
    assert o.stop.price == pytest.approx(10.45, abs=1e-9)

    assert [leg.label for leg in o.exits] == ["TP1"]
    assert [leg.price for leg in o.exits] == pytest.approx([9.40], abs=1e-9)
    assert [leg.fraction for leg in o.exits] == pytest.approx([1.0])
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# 4. The non-negotiable check
# ---------------------------------------------------------------------------


def test_strategy_is_free_of_lookahead(frames) -> None:
    """Every Wave-2 strategy must pass this on real data too."""
    assert_no_lookahead_v2(_FixtureScale(), frames)
