"""GOLDEN FIXTURE — the deliverable shape every Wave-2 strategy must copy.

A reviewer reading 51 strategy files has no ground truth. Reading logic and
asking "does this look right?" is precisely where errors survive review. A
golden fixture converts that into "does this fixture encode the spec correctly?",
which is a question a human can actually answer.

The pattern, and all four parts are required:

1. **Hand-built bars** written as a literal, chosen for a stated reason — not
   random data, not loaded from the database.
2. **Expected values computed by hand**, with the arithmetic shown in comments,
   so the numbers are derived from the spec rather than copied from whatever
   the code happened to print.
3. **An assertion** that the strategy produces exactly that.
4. **A mapping** from each assertion back to the rule it enforces.

Note the fixture subclasses the strategy to shrink `TREND_PERIOD`,
`SWING_PERIOD` and `warmup_bars`. That is deliberate and allowed: 36 bars cannot
warm a 50-period daily SMA. The fixture pins the *logic*; production parameters
live in the strategy and are exercised by the harness on real data.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.reference_pullback_continuation import (
    ReferencePullbackContinuation,
)

PIP = 0.0001

# ---------------------------------------------------------------------------
# 1. The bars, and why these bars
# ---------------------------------------------------------------------------
# 36 H4 bars = 6 clean days. The series rises steadily (so the D1 trend filter
# opens), and each day prints a higher swing high followed by a shallow
# pullback — which is exactly the setup the strategy is built to trade. Days 0-1
# exist only to warm the D1 SMA and to let the first swings confirm.
#
# High/Low are Close +/- 8 pips on every bar, so swing levels are trivially
# predictable: swing high level = Close + 0.0008.
CLOSES = [
    # day 0 — warmup
    1.1000,
    1.1010,
    1.1020,
    1.1030,
    1.1040,
    1.1050,
    # day 1 — up, shallow pullback
    1.1060,
    1.1075,
    1.1090,
    1.1080,
    1.1070,
    1.1085,
    # day 2 — higher high (1.1140) then pullback
    1.1100,
    1.1120,
    1.1140,
    1.1130,
    1.1115,
    1.1125,
    # day 3 — SECOND consecutive higher high (1.1170) -> the setup fires
    1.1150,
    1.1170,
    1.1160,
    1.1145,
    1.1155,
    1.1180,
    # day 4 — third higher high (1.1200) -> fires again
    1.1200,
    1.1190,
    1.1175,
    1.1185,
    1.1210,
    1.1230,
    # day 5 — continues; no new confirmation in range
    1.1220,
    1.1240,
    1.1260,
    1.1250,
    1.1270,
    1.1290,
]


class _FixtureScale(ReferencePullbackContinuation):
    """Production logic, fixture-sized lookbacks."""

    TREND_PERIOD = 3
    SWING_PERIOD = 2

    @property
    def warmup_bars(self) -> int:
        return 12


@pytest.fixture(scope="module")
def frames() -> dict:
    idx = pd.date_range("2020-01-01", periods=len(CLOSES), freq="4h", tz="UTC")
    h4 = pd.DataFrame(
        {
            "Open": CLOSES,
            "High": [c + 0.0008 for c in CLOSES],
            "Low": [c - 0.0008 for c in CLOSES],
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


# ---------------------------------------------------------------------------
# 2 + 3. Expected values, computed by hand, then asserted
# ---------------------------------------------------------------------------


def test_emits_exactly_the_expected_setups(orders) -> None:
    """Rule: fire only when BOTH the D1 trend is up AND level_1 > level_2.

    Bars 12-15 have only one confirmed swing high (level_2 is NaN), so no order
    may exist there — that is the confirmation lag doing its job.
    """
    assert [str(o.decision_bar) for o in orders] == [
        "2020-01-04 12:00:00+00:00",
        "2020-01-04 16:00:00+00:00",
        "2020-01-05 08:00:00+00:00",
        "2020-01-05 12:00:00+00:00",
    ]


def test_first_order_matches_hand_computed_arithmetic(orders) -> None:
    """The full trade plan, derived from the spec — not copied from output.

    At 2020-01-04 12:00 (bar 21):
      last confirmed swing high  level_1 = 1.1170 + 0.0008 = 1.11780
      previous confirmed high    level_2 = 1.1140 + 0.0008 = 1.11480  -> higher high
      last confirmed swing low   level_1 = 1.1115 - 0.0008 = 1.11070

      entry = level_1 + ENTRY_BUFFER_PIPS(2) = 1.11780 + 0.0002 = 1.11800
      stop  = swing_low - STOP_BUFFER_PIPS(5) = 1.11070 - 0.0005 = 1.11020
      risk  = 1.11800 - 1.11020                                  = 0.00780
      TP1   = entry + 1 x risk = 1.11800 + 0.00780 = 1.12580
      TP2   = entry + 2 x risk = 1.11800 + 0.01560 = 1.13360
      TP3   = entry + 3 x risk = 1.11800 + 0.02340 = 1.14140
    """
    o = orders[0]

    assert o.direction == 1
    assert o.entry == "buy_stop"
    assert o.entry_price == pytest.approx(1.11800, abs=1e-9)
    assert o.stop.price == pytest.approx(1.11020, abs=1e-9)

    assert [leg.label for leg in o.exits] == ["TP1", "TP2", "TP3"]
    assert [leg.price for leg in o.exits] == pytest.approx(
        [1.12580, 1.13360, 1.14140], abs=1e-9
    )
    assert [leg.fraction for leg in o.exits] == pytest.approx([0.333, 0.333, 0.334])
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)

    # Breakeven is triggered by a leg that exists (contract rejects it otherwise).
    assert o.stop.move_to_breakeven_on == "TP2"
    assert o.stop.move_to_breakeven_on in {leg.label for leg in o.exits}
    assert o.expires_after_bars == 6


def test_risk_reward_ratios_hold_for_every_order(orders) -> None:
    """Rule: legs sit at 1R / 2R / 3R. Derived, so a changed buffer is caught."""
    for o in orders:
        risk = o.entry_price - o.stop.price
        assert risk > 0
        for multiple, leg in zip((1.0, 2.0, 3.0), o.exits):
            assert leg.price == pytest.approx(o.entry_price + multiple * risk, abs=1e-9)


def test_pending_entry_sits_above_the_market(frames, orders) -> None:
    """Rule (NOTE 3): a buy stop below the decision close is a disguised market
    order. The contract rejects those, so the strategy must skip them."""
    close = frames["H4"]["Close"]
    for o in orders:
        assert o.entry_price > float(close.loc[o.decision_bar])


def test_no_orders_before_the_second_higher_high_confirms(orders) -> None:
    """Rule (NOTE 2): a swing high at bar k is knowable only at k+SWING_PERIOD.
    The first setup cannot precede 2020-01-04."""
    assert min(o.decision_bar for o in orders) >= pd.Timestamp("2020-01-04", tz="UTC")


# ---------------------------------------------------------------------------
# 4. The non-negotiable check
# ---------------------------------------------------------------------------


def test_strategy_is_free_of_lookahead(frames) -> None:
    """Every Wave-2 strategy must pass this on real data too."""
    assert_no_lookahead_v2(_FixtureScale(), frames)
