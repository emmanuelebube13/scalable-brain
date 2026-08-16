"""GOLDEN FIXTURE — sunday_breakout (SPEC-sunday_breakout.md).

Every expected number is derived from the spec's formulas before the code was run.

Two things make the arithmetic exact:

* **The weekly ATR is a constant.** Each W1 bar carries ``High = Close + 100 pip``
  and ``Low = Close - 100 pip`` and closes move 50 pip a week, so every weekly true
  range is exactly ``High - Low`` = 200 pip and the EWM of that constant is itself:
  **ATR(14) = 0.02000**, and §7's target distance is 0.5 x 0.02000 = 0.01000.
* **The last weekly bar is deliberately five times wider** (1000 pip range). It must
  never reach a decision: §3/§10 #2 shift the W1 index a full week forward and merge
  with ``allow_exact_matches=False``. If that shift were dropped, the ATR at the
  second Sunday candle would be 0.03067 and the target distance 0.01533 instead of
  0.01000 — so the target assertions below are a look-ahead test, not decoration.

The H4 index is the real trading grid: bars stamped 21:00, 01:00, 05:00, 09:00,
13:00 and 17:00 UTC, with nothing between Friday 21:00 and Sunday 21:00. Exactly one
bar per week starts on a Sunday, which is the Sunday candle (§9).

The fixture shrinks only ``warmup_bars`` (420 -> 1); no period, threshold or level in
the strategy is touched.
"""

from __future__ import annotations

from typing import Dict, List

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.sunday_breakout import SundayBreakout

PIP = 0.0001

# ---------------------------------------------------------------------------
# 1. The bars, and why these bars
# ---------------------------------------------------------------------------
# 40 H4 bars spanning the tail of one week and two complete Sunday candles:
#   bars 0-4    Friday 2021-01-08 — the frame starts mid-week, as any real slice
#               does, so the FIRST bar cannot be mistaken for a week opening
#   bar 5       Sunday 2021-01-10 21:00 — SUNDAY CANDLE 1, a 30-pip half-range
#   bars 6-34   the rest of that trading week (29 bars — the §4.6 expiry count)
#   bar 35      Sunday 2021-01-17 21:00 — SUNDAY CANDLE 2, a 25-pip half-range,
#               chosen different so a hardcoded level cannot pass both
#   bars 36-39  the start of the following week
CLOSES = [
    1.2950,
    1.2960,
    1.2970,
    1.2980,
    1.2990,
    1.3000,  # bar 5 — Sunday candle 1
    1.3010,
    1.3020,
    1.3030,
    1.3040,
    1.3050,
    1.3060,
    1.3070,
    1.3080,
    1.3090,
    1.3100,
    1.3110,
    1.3120,
    1.3130,
    1.3120,
    1.3110,
    1.3100,
    1.3090,
    1.3080,
    1.3070,
    1.3060,
    1.3050,
    1.3060,
    1.3070,
    1.3080,
    1.3090,
    1.3100,
    1.3110,
    1.3120,
    1.3130,
    1.3100,  # bar 35 — Sunday candle 2
    1.3110,
    1.3120,
    1.3130,
    1.3140,
]
# Half-range of each bar. Uniform 20 pip except the two Sunday candles, whose
# ranges are what the whole strategy is built on.
HALF_RANGE = [20 * PIP] * len(CLOSES)
HALF_RANGE[5] = 30 * PIP
HALF_RANGE[35] = 25 * PIP

# Weekly bars, stamped at the Sunday open of the week they cover.
W1_CLOSES = [1.2900, 1.2950, 1.3000, 1.2950, 1.3000, 1.3050]
W1_HALF_RANGE = [100 * PIP] * 6
W1_HALF_RANGE[5] = 500 * PIP  # the week that must never reach a decision


class _FixtureScale(SundayBreakout):
    """Production logic; only the warm-up is shortened."""

    @property
    def warmup_bars(self) -> int:
        return 1


def _h4_index() -> pd.DatetimeIndex:
    """The real H4 grid: no bars between Friday 21:00 and Sunday 21:00 UTC."""
    grid = pd.date_range("2021-01-08 01:00", periods=90, freq="4h", tz="UTC")
    trading = [
        ts
        for ts in grid
        if not (
            (ts.weekday() == 4 and ts.hour == 21)  # Friday 21:00 — market closed
            or ts.weekday() == 5  # Saturday
            or (ts.weekday() == 6 and ts.hour < 21)  # Sunday before the reopen
        )
    ]
    return pd.DatetimeIndex(trading[: len(CLOSES)])


def _w1_index() -> pd.DatetimeIndex:
    return pd.date_range("2020-12-06 21:00", periods=6, freq="7D", tz="UTC")


@pytest.fixture(scope="module")
def frames() -> Dict[str, pd.DataFrame]:
    h4 = pd.DataFrame(
        {
            "Open": CLOSES,
            "High": [c + h for c, h in zip(CLOSES, HALF_RANGE)],
            "Low": [c - h for c, h in zip(CLOSES, HALF_RANGE)],
            "Close": CLOSES,
            "Volume": 1.0,
        },
        index=_h4_index(),
    )
    w1 = pd.DataFrame(
        {
            "Open": W1_CLOSES,
            "High": [c + h for c, h in zip(W1_CLOSES, W1_HALF_RANGE)],
            "Low": [c - h for c, h in zip(W1_CLOSES, W1_HALF_RANGE)],
            "Close": W1_CLOSES,
            "Volume": 1.0,
        },
        index=_w1_index(),
    )
    return {"H4": h4, "W1": w1}


@pytest.fixture(scope="module")
def orders(frames: Dict[str, pd.DataFrame]) -> List:
    return list(_FixtureScale().generate_orders(frames))


# ---------------------------------------------------------------------------
# 2 + 3. Expected values, computed by hand, then asserted
# ---------------------------------------------------------------------------


def test_one_decision_per_week_at_the_sunday_candle(orders) -> None:
    """§9: only the first H4 bar of a trading week decides, and it emits both sides.

    Bars 0-4 are a Friday, so the frame's first bar is not a week opening; bars 6-34
    are mid-week and must be silent even though price makes new highs and lows there.
    """
    idx = _h4_index()
    assert [(o.decision_bar, o.direction, o.entry) for o in orders] == [
        (idx[5], 1, "buy_stop"),
        (idx[5], -1, "sell_stop"),
        (idx[35], 1, "buy_stop"),
        (idx[35], -1, "sell_stop"),
    ]
    assert idx[5] == pd.Timestamp("2021-01-10 21:00", tz="UTC")  # a Sunday
    assert idx[35] == pd.Timestamp("2021-01-17 21:00", tz="UTC")


def test_long_matches_hand_computed_arithmetic(orders) -> None:
    """Sunday candle 1, long side — §4, §6, §7.

    sun_high = 1.30000 + 0.00300 = 1.30300 · sun_low = 1.30000 - 0.00300 = 1.29700
    §4.4 entry = sun_high + 10 pip = 1.30300 + 0.00100 = 1.30400
    §6   stop  = sun_low                                = 1.29700
         R     = (sun_high - sun_low) + 10 pip = 0.00600 + 0.00100 = 0.00700
    §7   BE_2R = entry + 2R = 1.30400 + 0.01400 = 1.31800  (fraction 0.01)
         TP    = entry + 0.5 x ATR_w = 1.30400 + 0.01000 = 1.31400  (fraction 0.99)
    §7 note: TP is NEARER than BE_2R here, which is legal and expected — a trade that
    reaches target before +2R never needed the breakeven move.
    """
    o = orders[0]

    assert o.entry_price == pytest.approx(1.30400, abs=1e-9)
    assert o.decision_close == pytest.approx(1.30000, abs=1e-9)
    assert o.entry_price > o.decision_close  # a buy stop is never through the market
    assert o.stop.price == pytest.approx(1.29700, abs=1e-9)
    assert o.stop.move_to_breakeven_on == "BE_2R"
    assert o.stop.breakeven_offset_pips == pytest.approx(0.0)
    assert o.stop.trail_atr_multiple is None  # §6: no trail

    assert [leg.label for leg in o.exits] == ["BE_2R", "TP"]
    assert [leg.price for leg in o.exits] == pytest.approx([1.31800, 1.31400], abs=1e-9)
    assert [leg.fraction for leg in o.exits] == pytest.approx([0.01, 0.99])
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)
    assert o.expires_after_bars == 29  # §4.6: dies at the Friday 21:00 close


def test_short_matches_hand_computed_arithmetic(orders) -> None:
    """Sunday candle 1, short side — §5, §6, §7. R is identical to the long's.

    §5.3 entry = sun_low - 10 pip = 1.29700 - 0.00100 = 1.29600
    §6   stop  = sun_high                              = 1.30300
    §7   BE_2R = entry - 2R = 1.29600 - 0.01400 = 1.28200
         TP    = entry - 0.5 x ATR_w = 1.29600 - 0.01000 = 1.28600
    """
    o = orders[1]

    assert o.entry == "sell_stop"
    assert o.entry_price == pytest.approx(1.29600, abs=1e-9)
    assert o.entry_price < o.decision_close
    assert o.stop.price == pytest.approx(1.30300, abs=1e-9)
    assert [leg.price for leg in o.exits] == pytest.approx([1.28200, 1.28600], abs=1e-9)
    assert [leg.fraction for leg in o.exits] == pytest.approx([0.01, 0.99])
    # §6: the declared risk is the same on both sides of the same Sunday candle.
    assert abs(o.entry_price - o.stop.price) == pytest.approx(0.00700, abs=1e-9)
    assert abs(orders[0].entry_price - orders[0].stop.price) == pytest.approx(
        0.00700, abs=1e-9
    )


def test_second_week_re_anchors_on_its_own_candle(orders) -> None:
    """Sunday candle 2 — every level moves with the new candle, none are cached.

    sun_high = 1.31000 + 0.00250 = 1.31250 · sun_low = 1.30750
    R = 0.00500 + 0.00100 = 0.00600
    long  entry 1.31350, stop 1.30750, BE_2R 1.31350 + 0.01200 = 1.32550,
          TP 1.31350 + 0.01000 = 1.32350
    short entry 1.30650, stop 1.31250, BE_2R 1.29450, TP 1.29650
    """
    long_order, short_order = orders[2], orders[3]

    assert long_order.entry_price == pytest.approx(1.31350, abs=1e-9)
    assert long_order.stop.price == pytest.approx(1.30750, abs=1e-9)
    assert [leg.price for leg in long_order.exits] == pytest.approx(
        [1.32550, 1.32350], abs=1e-9
    )
    assert short_order.entry_price == pytest.approx(1.30650, abs=1e-9)
    assert short_order.stop.price == pytest.approx(1.31250, abs=1e-9)
    assert [leg.price for leg in short_order.exits] == pytest.approx(
        [1.29450, 1.29650], abs=1e-9
    )
    assert [leg.fraction for leg in short_order.exits] == pytest.approx([0.01, 0.99])


def test_weekly_atr_excludes_the_week_that_has_not_completed(orders) -> None:
    """§3 / §10 #2: the target distance proves which weekly bar was used.

    The last W1 bar has a 1000-pip range. Had it been visible at Sunday candle 2 the
    ATR would be 0.02000 + (2/15) x (0.10000 - 0.02000) = 0.03067 and the target
    distance 0.01533. Every emitted order must instead sit 0.01000 from its entry —
    half of the 0.02000 ATR built from completed weeks only.
    """
    for o in orders:
        target = o.exits[1].price
        assert target is not None
        assert abs(target - o.entry_price) == pytest.approx(0.01000, abs=1e-9)


# ---------------------------------------------------------------------------
# 4. The non-negotiable check
# ---------------------------------------------------------------------------


def test_strategy_is_free_of_lookahead(frames) -> None:
    """Every Wave-2 strategy must pass this on real data too."""
    assert_no_lookahead_v2(_FixtureScale(), frames)
