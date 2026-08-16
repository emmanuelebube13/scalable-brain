"""Golden fixture for ma_crossover_swing."""

from __future__ import annotations

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.ma_crossover_swing import MaCrossoverSwing

# ---------------------------------------------------------------------------
# 1. The bars, and why these bars
# ---------------------------------------------------------------------------
# We need to test EMA and MACD crosses. To make the math hand-calculable, we
# pad the start with 28 identical bars (Close = 10.0, High = 10.1, Low = 9.9)
# so that all moving averages converge exactly to 10.0, and MACD converges to 0.
# Then we introduce a bullish spike on bar 28, and a bearish drop on bar 29,
# triggering exactly one long and one short setup.
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
    10.00,
    10.00,
    10.60,
    9.40,
]


class _FixtureScale(MaCrossoverSwing):
    """Production logic, fixture-sized lookbacks."""

    FAST_EMA = 2
    SLOW_EMA = 4
    REGIME_SMA = 5
    MACD_FAST = 2
    MACD_SLOW = 4
    MACD_SIGNAL = 2
    ATR_PERIOD = 2

    @property
    def warmup_bars(self) -> int:
        return 10


@pytest.fixture(scope="module")
def frames() -> dict:
    idx = pd.date_range("2020-01-01", periods=len(CLOSES), freq="1D", tz="UTC")
    d1 = pd.DataFrame(
        {
            "Open": CLOSES,
            "High": [c + 0.1 for c in CLOSES],
            "Low": [c - 0.1 for c in CLOSES],
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


def test_emits_expected_orders(orders) -> None:
    """Rule: exactly one long on the spike, one short on the drop."""
    assert len(orders) == 2
    assert [str(o.decision_bar) for o in orders] == [
        "2020-01-29 00:00:00+00:00",
        "2020-01-30 00:00:00+00:00",
    ]


def test_long_order_matches_hand_computed_arithmetic(orders) -> None:
    """The long order logic from spec §4, §6, and §7.

    At 2020-01-29 (bar index 28):
    Close_t = 10.6
    # §4.1: EMA2 crosses above EMA4. EMA2 = 2/3 * 10.6 + 1/3 * 10.0 = 10.4. EMA4 = 2/5 * 10.6 + 3/5 * 10.0 = 10.24.
    # §4.2: Regime confirmation. Close_t (10.6) > SMA5 (10.12).
    # §4.3: MACD momentum. MACD_line (0.16) > MACD_signal (0.106666666).

    ATR calculation: TR = max(0.2, 10.7-10.0, 10.5-10.0) = 0.7. ATR2 = 2/3 * 0.7 + 1/3 * 0.2 = 1.6 / 3.
    # §6: Stop = Close_t - 1.4 * ATR2 = 10.6 - 1.4 * (1.6 / 3) = 29.56 / 3 = 9.853333333
    # §7: TP leg (fraction 0.5) = Close_t + 3.2 * ATR2 = 10.6 + 3.2 * (1.6 / 3) = 36.92 / 3 = 12.306666666
    """
    o = orders[0]

    assert o.direction == 1
    assert o.entry == "market"
    assert o.entry_price is None
    assert o.decision_close == 10.6

    assert o.stop.price == pytest.approx(9.853333333333333, abs=1e-9)

    assert len(o.exits) == 2
    tp_leg = next(leg for leg in o.exits if leg.label == "TP")
    time_leg = next(leg for leg in o.exits if leg.label == "TIME")

    assert tp_leg.kind == "take_profit"
    assert tp_leg.price == pytest.approx(12.306666666666667, abs=1e-9)
    assert tp_leg.fraction == pytest.approx(0.5)

    assert time_leg.kind == "time"
    assert time_leg.bars == 8
    assert time_leg.fraction == pytest.approx(0.5)


def test_short_order_matches_hand_computed_arithmetic(orders) -> None:
    """The short order logic from spec §5, §6, and §7.

    At 2020-01-30 (bar index 29):
    Close_t = 9.4
    # §5.1: EMA2 crosses below EMA4. EMA2 = 2/3 * 9.4 + 1/3 * 10.4 = 9.73333. EMA4 = 2/5 * 9.4 + 3/5 * 10.24 = 9.904.
    # §5.2: Regime confirmation. Close_t (9.4) < SMA5 (10.0).
    # §5.3: MACD momentum. MACD_line (-0.170666) < MACD_signal (-0.078222).

    ATR calculation: TR = max(0.2, 10.6-9.5, 10.6-9.3) = 1.3. ATR2 = 2/3 * 1.3 + 1/3 * (1.6 / 3) = 9.4 / 9.
    # §6: Stop = Close_t + 1.4 * ATR2 = 9.4 + 1.4 * (9.4 / 9) = 97.76 / 9 = 10.862222222
    # §7: TP leg (fraction 0.5) = Close_t - 3.2 * ATR2 = 9.4 - 3.2 * (9.4 / 9) = 54.52 / 9 = 6.057777777
    """
    o = orders[1]

    assert o.direction == -1
    assert o.entry == "market"
    assert o.entry_price is None
    assert o.decision_close == 9.4

    assert o.stop.price == pytest.approx(10.862222222222222, abs=1e-9)

    assert len(o.exits) == 2
    tp_leg = next(leg for leg in o.exits if leg.label == "TP")
    time_leg = next(leg for leg in o.exits if leg.label == "TIME")

    assert tp_leg.kind == "take_profit"
    assert tp_leg.price == pytest.approx(6.057777777777778, abs=1e-9)
    assert tp_leg.fraction == pytest.approx(0.5)

    assert time_leg.kind == "time"
    assert time_leg.bars == 8
    assert time_leg.fraction == pytest.approx(0.5)


def test_exit_leg_fractions_sum_to_one(orders) -> None:
    """Rule: All strategies must assert that exit fractions sum to exactly 1.0."""
    for o in orders:
        assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# 4. The non-negotiable check
# ---------------------------------------------------------------------------


def test_strategy_is_free_of_lookahead(frames) -> None:
    """Every Wave-2 strategy must pass this on real data too."""
    assert_no_lookahead_v2(_FixtureScale(), frames)
