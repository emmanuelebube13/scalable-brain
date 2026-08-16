"""GOLDEN FIXTURE — weekly_range_reversal (SPEC-weekly_range_reversal.md).

Every expected number is derived from the spec's formulas before the code was run.
Prices are written as pips above 1.09000 in the comments (1 pip = 0.00010) because
every level in this strategy is a fraction of a range, and pips keep the arithmetic
checkable by eye.

Bar construction: ``High = Close + 10 pip``, ``Low = Close - 10 pip`` on every bar,
so the typical price ``(H + L + C)/3`` equals the close and the CCI reduces to
``(Close - SMA) / (0.015 * sample std)`` over the window — computable by hand. The
inventory ``cci`` uses the sample standard deviation, not the mean absolute
deviation; the arithmetic below uses std, as the code does.

The fixture subclasses the strategy to shrink CCI_PERIOD 2000 -> 5, RANGE_BARS
336 -> 20, TOUCH_LOOKBACK 24 -> 3 and warmup 2000 -> 19. Periods only: the 10/90
crosses, the 5/95 touches, the 12.5%/50% fractions, the 1-pip buffer and the 2:1
floor are all untouched.

Why the price moves are violent: on a 5-bar window the largest attainable CCI is
``(n-1)/sqrt(n)/0.015`` = 119, so the §5.4 arming threshold of 95 can only be
reached by a single large bar. That is an artefact of shrinking the period for a
fixture, not of the strategy — CCI(2000) reaches 95 easily.
"""

from __future__ import annotations

from typing import Dict, List

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.weekly_range_reversal import WeeklyRangeReversal

PIP = 0.0001
BASE = 1.0900
BAND = 10 * PIP

# ---------------------------------------------------------------------------
# 1. The bars, and why these bars
# ---------------------------------------------------------------------------
# 50 H1 bars in two blocks, one FX week apart, so the §4.5 weekly throttle can be
# observed rather than assumed:
#   bars 0-9    a high plateau that fixes the top of the two-week range
#   bars 10-14  a slide to the bottom of it
#   bars 15-19  a low oscillation: CCI dips well below 5, then closes back above
#               10 at bar 19 while price is still inside the bottom eighth
#               -> THE LONG
#   bars 20-24  the same shape again — every gate passes, and the throttle is the
#               only thing that stops it
#   bars 25-44  a slow monotone drift down: the close is the minimum of its own
#               CCI window on every bar, so CCI is pinned at -84 and neither a
#               long cross (>10) nor a short arming (>=90) can occur
#   bar 45      one large up bar: CCI = +119, the arming touch for §5.4
#   bar 46      a smaller up bar: CCI falls back through 90 while price sits in
#               the top eighth of the (now very wide) range -> THE SHORT
CLOSES_PIPS = [
    150,
    148,
    150,
    148,
    150,
    148,
    150,
    148,
    150,
    148,
    120,
    90,
    60,
    30,
    0,
    10,
    0,
    10,
    5,
    8,  # bar 19 — THE LONG
    10,
    0,
    10,
    5,
    8,  # bars 20-24 — qualifying, but the week is already used
    -300,
    -305,
    -310,
    -315,
    -320,
    -325,
    -330,
    -335,
    -340,
    -345,
    -350,
    -355,
    -360,
    -365,
    -370,
    -375,
    -380,
    -385,
    -390,
    -395,  # bars 25-44 — monotone: CCI is -84.3 on every one of them
    0,  # bar 45 — the arming spike, CCI = +119.2
    5,  # bar 46 — THE SHORT, CCI = +73.8
    0,
    -5,
    0,
]
CLOSES = [round(BASE + p * PIP, 5) for p in CLOSES_PIPS]


class _FixtureScale(WeeklyRangeReversal):
    """Production logic, fixture-sized lookbacks (periods only)."""

    CCI_PERIOD = 5
    RANGE_BARS = 20
    TOUCH_LOOKBACK = 3

    @property
    def warmup_bars(self) -> int:
        return 19


def _frame(index: pd.DatetimeIndex) -> Dict[str, pd.DataFrame]:
    h1 = pd.DataFrame(
        {
            "Open": CLOSES,
            "High": [c + BAND for c in CLOSES],
            "Low": [c - BAND for c in CLOSES],
            "Close": CLOSES,
            "Volume": 1.0,
        },
        index=index,
    )
    return {"H1": h1}


def _index_two_weeks() -> pd.DatetimeIndex:
    """Bars 0-24 on Wednesday of FX week 1; bars 25-49 on Wednesday of week 2."""
    first = pd.date_range("2021-03-03 00:00", periods=25, freq="h", tz="UTC")
    second = pd.date_range("2021-03-10 00:00", periods=25, freq="h", tz="UTC")
    return first.append(second)


def _index_three_weeks() -> pd.DatetimeIndex:
    """Same prices, but bars 20-24 land in a NEW FX week (see the throttle test)."""
    first = pd.date_range("2021-03-03 00:00", periods=20, freq="h", tz="UTC")
    second = pd.date_range("2021-03-10 00:00", periods=5, freq="h", tz="UTC")
    third = pd.date_range("2021-03-17 00:00", periods=25, freq="h", tz="UTC")
    return first.append(second).append(third)


@pytest.fixture(scope="module")
def frames() -> Dict[str, pd.DataFrame]:
    return _frame(_index_two_weeks())


@pytest.fixture(scope="module")
def orders(frames: Dict[str, pd.DataFrame]) -> List:
    return list(_FixtureScale().generate_orders(frames))


# ---------------------------------------------------------------------------
# 2 + 3. Expected values, computed by hand, then asserted
# ---------------------------------------------------------------------------


def test_emits_exactly_the_expected_setups(orders) -> None:
    """§4/§5: one long, one short, in 50 bars.

    Bar 45 is the control on the short side: its CCI is 119.2, which arms §5.4 but
    fails §5.3's cross (the cross needs CCI BELOW 90 on the decision bar). Bar 46
    is the first bar where CCI has fallen back through 90.
    """
    index = _index_two_weeks()
    assert [(o.decision_bar, o.direction) for o in orders] == [
        (index[19], 1),
        (index[46], -1),
    ]


def test_long_matches_hand_computed_arithmetic(orders) -> None:
    """The bar-19 trade plan, from §3, §4, §6 and §7.

    Range window = bars 0-19 (20 bars):
      hi2w = max High = 150 + 10 = 160 pip -> 1.10600
      lo2w = min Low  =   0 - 10 = -10 pip -> 1.08900
      rng  = 170 pip = 0.01700
    §4.2 zone_lo = lo2w + 0.125 x rng = 1.08900 + 0.0021250 = 1.0911250;
         Close[19] = 8 pip = 1.09080, which is inside it
    §4.3 CCI[19] over closes (10, 0, 10, 5, 8): mean 6.6, sample std 4.2190,
         CCI = (8 - 6.6) / (0.015 x 4.2190) = +22.1 > 10;
         CCI[18] over (0, 10, 0, 10, 5): mean 5.0, std 5.0, CCI = 0.0 <= 10 -> cross
    §4.4 CCI[16] over (60, 30, 0, 10, 0) = (0 - 20)/(0.015 x 25.4951) = -52.3 <= 5
    §6   stop = lo2w - 1 pip = 1.08900 - 0.00010 = 1.08890
    §7   TP   = lo2w + 0.50 x rng = 1.08900 + 0.00850 = 1.09750
    §4.6 floor: TP - A = 0.00670 >= 2 x (A - SL) = 2 x 0.00190 = 0.00380
    """
    o = orders[0]

    assert o.direction == 1
    assert o.entry == "market"
    assert o.entry_price is None
    assert o.decision_close == pytest.approx(1.09080, abs=1e-9)
    assert o.stop.price == pytest.approx(1.08890, abs=1e-9)
    assert o.stop.move_to_breakeven_on is None  # §6: no breakeven
    assert o.stop.trail_atr_multiple is None  # §6: static stop, no trail

    assert [leg.kind for leg in o.exits] == ["take_profit"]
    assert [leg.label for leg in o.exits] == ["TP1"]
    assert [leg.price for leg in o.exits] == pytest.approx([1.09750], abs=1e-9)
    assert [leg.fraction for leg in o.exits] == pytest.approx([1.0])
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)
    assert o.expires_after_bars is None  # §4: a market intent is never pending


def test_short_matches_hand_computed_arithmetic(orders) -> None:
    """The bar-46 trade plan, from §3, §5, §6 and §7 — the mirror.

    Range window = bars 27-46:
      hi2w = max High = 5 + 10 = 15 pip -> 1.09150
      lo2w = min Low  = -395 - 10 = -405 pip -> 1.04950
      rng  = 420 pip = 0.04200
    §5.2 zone_hi = lo2w + 0.875 x rng = 1.04950 + 0.03675 = 1.08625;
         Close[46] = 5 pip = 1.09050, which is above it
    §5.3 CCI[46] over (-385, -390, -395, 0, 5): mean -233, std 215.017,
         CCI = (5 + 233)/(0.015 x 215.017) = +73.8 < 90;
         CCI[45] over (-380, -385, -390, -395, 0): mean -310, std 173.386,
         CCI = 310/(0.015 x 173.386) = +119.2 >= 90 -> cross down
    §5.4 the same +119.2 is inside the 3-bar arming window and clears 95
    §6   stop = hi2w + 1 pip = 1.09150 + 0.00010 = 1.09160
    §7   TP   = lo2w + 0.50 x rng = 1.04950 + 0.02100 = 1.07050
    §5.6 floor: A - TP = 0.02000 >= 2 x (SL - A) = 2 x 0.00110 = 0.00220
    """
    o = orders[1]

    assert o.direction == -1
    assert o.entry == "market"
    assert o.decision_close == pytest.approx(1.09050, abs=1e-9)
    assert o.stop.price == pytest.approx(1.09160, abs=1e-9)
    assert o.exits[0].price == pytest.approx(1.07050, abs=1e-9)
    assert [leg.fraction for leg in o.exits] == pytest.approx([1.0])
    assert o.exits[0].kind == "take_profit"
    assert o.tag == "range_fade"


def test_reward_risk_floor_holds_for_every_emission(orders) -> None:
    """§4.6/§5.6 restated as an invariant, so a broken gate cannot pass silently."""
    for o in orders:
        target = o.exits[0].price
        assert target is not None
        risk = abs(o.decision_close - o.stop.price)
        reward = abs(target - o.decision_close)
        assert risk > 0
        assert reward >= 2.0 * risk
        # §6: the stop is on the far side of the entry, by exactly 1 pip beyond
        # the range extreme — 19 pip below the close for the long, 11 above for
        # the short.
        if o.direction == 1:
            assert o.stop.price < o.decision_close < target
        else:
            assert target < o.decision_close < o.stop.price


def test_weekly_throttle_is_what_blocks_the_second_setup() -> None:
    """§4.5 / §10 #7: one emitted intent per FX week per pair, both directions.

    Bars 20-24 repeat the bar 15-19 shape exactly, so bar 22 satisfies every gate.
    Re-stamp those same prices so that bars 20-24 fall in the FOLLOWING FX week and
    the order appears — same bars, same arithmetic, different calendar. Bar 22's
    range window (bars 3-22) has the same extremes as bar 19's, so its plan is the
    same stop and target with the close at 10 pip = 1.09100.
    """
    split = _index_three_weeks()
    orders = list(_FixtureScale().generate_orders(_frame(split)))

    assert [(o.decision_bar, o.direction) for o in orders] == [
        (split[19], 1),
        (split[22], 1),
        (split[46], -1),
    ]
    second = orders[1]
    assert second.decision_close == pytest.approx(1.09100, abs=1e-9)
    assert second.stop.price == pytest.approx(1.08890, abs=1e-9)
    assert second.exits[0].price == pytest.approx(1.09750, abs=1e-9)
    assert [leg.fraction for leg in second.exits] == pytest.approx([1.0])


# ---------------------------------------------------------------------------
# 4. The non-negotiable check
# ---------------------------------------------------------------------------


def test_strategy_is_free_of_lookahead(frames) -> None:
    """Every Wave-2 strategy must pass this on real data too."""
    assert_no_lookahead_v2(_FixtureScale(), frames)
