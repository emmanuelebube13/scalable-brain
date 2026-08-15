"""GOLDEN FIXTURE — double_bottom_measured_move.

Spec: task/2026-August-week1/fleet/upload/wave2/specs/SPEC-double_bottom_measured_move.md
Strategy: src/layer0/strategies/research/double_bottom_measured_move.py

All five required parts (task/2026-August-week1/wave2/RUN_BRIEF.md, "The golden fixture"):

1. Hand-built D1 bars, written as a literal, chosen for a stated reason.
2. Expected OrderIntent values computed by hand from the spec's formulas
   (§4/§5 pattern geometry, §6 stop, §7 exit legs), with the arithmetic
   shown in comments -- NOT copied from whatever the strategy printed.
3. Assertions that ``generate_orders`` produces exactly those values.
4. A mapping (in the comments next to each assertion) back to the spec
   rule that requires it.
5. The mandatory ``assert_no_lookahead_v2`` probe.

-----------------------------------------------------------------------
1. The bars, and why these bars
-----------------------------------------------------------------------

One continuous 34-bar D1 series builds a classic W (double bottom) in its
first half and a classic M (double top) in its second half, sharing the
swing structure so both sides of the strategy (§4 long, §5 short) are
exercised by a single hand-traceable price path -- exactly the shape the
strategy scans for, nothing more.

Every bar uses the SAME true range: ``High = mid + 0.0050``,
``Low = mid - 0.0050`` (0.0100 total), and every consecutive ``mid`` step
is <= 0.0050 in absolute value. Under ``indicators.atr`` (Wilder EWM on
True Range), that keeps ``True Range[i] == 0.0100`` for EVERY bar
(``TR[0] = High[0]-Low[0] = 0.0100`` since ``prev_close`` is undefined
there, and if ``ATR[i-1] == 0.0100`` and ``TR[i] == 0.0100`` then
``ATR[i] = alpha*TR[i] + (1-alpha)*ATR[i-1] == 0.0100`` by induction,
independent of ``ATR_PERIOD``/``span``). So **ATR14 == 0.0100 at every
bar** -- this is verified by construction, not assumed, and it is why
``ATR_PERIOD`` needs no shrinking in the fixture subclass below: only the
swing-confirmation lag (``SWING_PERIOD``) and the pre-decline lookback
(``DECLINE_LOOKBACK_BARS``) are periods long enough to need shrinking for
a 34-bar fixture (RUN_BRIEF: "shrink periods; never change the logic").

Bar-by-bar reasoning (occurrence positions; ``confirmed_swing_points``
stamps the CONFIRMATION bar at ``occurrence + SWING_PERIOD`` but carries
the level set at the occurrence bar -- spec §3/§9):

* idx 0-4: a lead-in decline (1.0980 -> 1.0920) so idx 2-4
  (``kA - DECLINE_LOOKBACK_BARS .. kA - 1``) gives the §4 #2 decline gate
  something to measure.
* idx 5 = **A** (``kA``), a confirmed swing low: ``Low[5]=1.0850``. Every
  candidate low at idx 2/3/4 fails CONFIRMATION because the very next bar
  undercuts it (the decline keeps going) -- only idx 5, where idx 6/7
  hold flat-or-higher, survives. §4 #1.
* idx 6-7: rally into **C** (``kC``) at idx 7, a confirmed swing high:
  ``High[7]=1.1050``. idx 6 is a high CANDIDATE too but fails
  confirmation because idx 7 exceeds it -- only the actual peak confirms.
  §4 #3.
* idx 8-9: pullback into **B** (``kB``) at idx 9, a confirmed swing low:
  ``Low[9]=1.0870``. §4 #5.
* idx 10-11: idx 11 = ``s = kB + SWING_PERIOD = 9+2 = 11`` is the
  activation bar. Close[11]=1.1005 does not yet clear ``LC=1.1050``.
* idx 12: Close=1.1055 > LC=1.1050 -- the LONG breakout fires here (first
  bar of the trigger window that qualifies). §4 #10/#11.
* idx 13-15: rally into **A'** (``kA'``) at idx 15, a confirmed swing
  high: ``High[15]=1.1190``. §5 #1.
* idx 16-17: decline into **C'** (``kC'``) at idx 17, a confirmed swing
  low: ``Low[17]=1.1010``. §5 #3.
* idx 18-19: rally into **B'** (``kB'``) at idx 19, a confirmed swing
  high: ``High[19]=1.1172``. §5 #5.
* idx 20-21: ``s' = 19+2 = 21``. Close[21]=1.1040 does not yet clear
  ``LC'=1.1010``.
* idx 22: Close=1.0990 < LC'=1.1010 -- the SHORT breakdown fires here.
  §5 #9-11.
* idx 23-33: a plain monotonic decline, added only to reach a
  hand-constructed-but-comfortable 34 bars and to feed
  ``assert_no_lookahead_v2``'s truncation windows. A strictly monotonic
  run produces no new swing CANDIDATE that ever confirms (every
  candidate is immediately undercut by the next bar, and the last
  ``SWING_PERIOD`` bars can never confirm at all), so it manufactures no
  further patterns -- verified by hand below, not by running the code.

Every OTHER combination the strategy's scan loop tries against this data
was walked by hand and rejected, so the fixture's assertion of "exactly
two orders" is a genuine claim, not an oversight:

* ``kA=9`` (B of the first pattern, re-tried as a fresh A): C=idx15,
  B=idx17, offset = (1.1010-1.0870)/(1.1190-1.0870) = 0.0140/0.0320 =
  0.4375 -- outside [0.05, 0.20] (§4 #6) -- rejected.
* ``kA=17``: C=idx19, then no confirmed swing low ever occurs after idx19
  in this data -- no B -- rejected (§4 #5, "if this first post-C swing
  low fails ... the pattern is dead"; here there simply is no candidate).
* ``kA'=7`` (C of the first pattern, re-tried as a fresh A'): C'=idx9,
  B'=idx15, and ``LB'=High[15]=1.1190`` is NOT less than
  ``LA'=High[7]=1.1050`` -- fails §5 #6 (`LB' < LA'`) -- rejected.
* ``kA'=19`` (B' of the second pattern): no confirmed swing low occurs
  after idx19 -- no C' -- rejected.

-----------------------------------------------------------------------
2/3/4. Expected values (hand arithmetic) and assertions -- see each test.
-----------------------------------------------------------------------
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.double_bottom_measured_move import (
    DoubleBottomMeasuredMove,
)

# ---------------------------------------------------------------------------
# 1. The bars
# ---------------------------------------------------------------------------
# "mid" doubles as Open and Close; High = mid+0.0050, Low = mid-0.0050 on
# every bar, and no consecutive mid step exceeds 0.0050 in magnitude -- see
# the module docstring for why that pins True Range (hence ATR14) at exactly
# 0.0100 on every single bar, by construction.
MIDS = [
    1.0980,  # 0  lead-in
    1.0970,  # 1
    1.0960,  # 2  decline-lookback window for A starts here
    1.0940,  # 3
    1.0920,  # 4
    1.0900,  # 5  A  (kA)   LA = Low[5]  = 1.0850
    1.0950,  # 6
    1.1000,  # 7  C  (kC)   LC = High[7] = 1.1050
    1.0960,  # 8
    1.0920,  # 9  B  (kB)   LB = Low[9]  = 1.0870
    1.0960,  # 10
    1.1005,  # 11 s = kB+2 = 11 (activation; Close 1.1005 < LC, no fire yet)
    1.1055,  # 12 Close 1.1055 > LC=1.1050 -> LONG fires (t=12)
    1.1080,  # 13
    1.1110,  # 14
    1.1140,  # 15 A' (kA')  LA' = High[15] = 1.1190
    1.1100,  # 16
    1.1060,  # 17 C' (kC')  LC' = Low[17]  = 1.1010
    1.1090,  # 18
    1.1122,  # 19 B' (kB')  LB' = High[19] = 1.1172
    1.1080,  # 20
    1.1040,  # 21 s' = kB'+2 = 21 (activation; Close 1.1040 > LC', no fire)
    1.0990,  # 22 Close 1.0990 < LC'=1.1010 -> SHORT fires (t=22)
    1.0960,  # 23 plain decline tail (no new confirmed swings -- see docstring)
    1.0930,  # 24
    1.0900,  # 25
    1.0870,  # 26
    1.0840,  # 27
    1.0810,  # 28
    1.0780,  # 29
    1.0750,  # 30
    1.0720,  # 31
    1.0690,  # 32
    1.0660,  # 33
]

HALF_RANGE = 0.0050  # High-mid = mid-Low; keeps TR (hence ATR14) == 0.0100


class _FixtureScale(DoubleBottomMeasuredMove):
    """Production logic, fixture-sized lookbacks (RUN_BRIEF: shrink periods
    only). ``ATR_PERIOD`` is deliberately left at its production value of
    14 -- the fixture's constant True Range (see module docstring) makes
    ATR14 == 0.0100 regardless of period, so no shrink is needed there.
    ``FORMATION_MAX_BARS`` (40) and ``TRIGGER_WINDOW_BARS`` (20) are also
    left at production values: both patterns below complete in 4 bars and
    trigger within 1 bar of activation, comfortably inside the defaults.
    """

    SWING_PERIOD = 2  # §3/§9: confirmed_swing_points period + confirmation lag
    DECLINE_LOOKBACK_BARS = 3  # §4 #2 / §5 #2: bars examined before A/A'

    # warmup_bars is inherited unchanged: the base class computes it as
    # DECLINE_LOOKBACK_BARS + 2 + SWING_PERIOD from `self.*`, so it already
    # picks up the shrunk values above (3 + 2 + 2 = 7) with no override.


@pytest.fixture(scope="module")
def frames() -> dict:
    idx = pd.date_range("2020-01-01", periods=len(MIDS), freq="1D", tz="UTC")
    d1 = pd.DataFrame(
        {
            "Open": MIDS,
            "High": [m + HALF_RANGE for m in MIDS],
            "Low": [m - HALF_RANGE for m in MIDS],
            "Close": MIDS,
            "Volume": 1.0,
        },
        index=idx,
    )
    return {"D1": d1}


@pytest.fixture(scope="module")
def orders(frames) -> list:
    return list(_FixtureScale().generate_orders(frames))


# ---------------------------------------------------------------------------
# 2 + 3 + 4. Expected values, computed by hand, asserted, mapped to spec
# ---------------------------------------------------------------------------


def test_emits_exactly_the_expected_setups(orders) -> None:
    """Exactly one long (idx 12) and one short (idx 22) -- every other scan
    candidate was walked by hand in the module docstring and rejected by
    §4 #6 (offset), §4 #5 (no B), §5 #6 (offset direction) or §5 #5 (no C').
    """
    assert [str(o.decision_bar) for o in orders] == [
        "2020-01-13 00:00:00+00:00",  # idx 12
        "2020-01-23 00:00:00+00:00",  # idx 22
    ]
    assert [o.direction for o in orders] == [1, -1]


def test_long_order_matches_hand_computed_arithmetic(orders) -> None:
    """The long trade plan, derived from §4/§6/§7 -- not copied from output.

    Pattern: A=idx5, C=idx7, B=idx9, s=11, trigger t=12.
      LA = Low[5]  = 1.0900 - 0.0050 = 1.08500   (§4 #1)
      LC = High[7] = 1.1000 + 0.0050 = 1.10500   (§4 #3)
      H  = LC - LA = 1.10500 - 1.08500 = 0.02000  (§4 #4, height)
      LB = Low[9]  = 1.0920 - 0.0050 = 1.08700
      offset = (LB-LA)/H = (1.08700-1.08500)/0.02000 = 0.0020/0.0200
             = 0.10 -> within [0.05, 0.20]           (§4 #6)

      decision_close = Close[12] = 1.10550
      pip = 0.0001 (price 1.1055 < the JPY threshold -> EUR_USD convention)
      stop  = LA - 1.0 pip = 1.08500 - 0.0001 = 1.08490          (§6)
      TP1   = 2*LC - LA = 2*1.10500 - 1.08500
            = 2.21000 - 1.08500 = 1.12500                        (§7)
    """
    o = orders[0]

    assert o.direction == 1  # §4: long side
    assert o.entry == "market"  # §4 entry type: close-above-C market entry
    assert o.entry_price is None  # §4: "n/a for market"
    assert o.decision_close == pytest.approx(1.10550, abs=1e-9)

    assert o.stop.price == pytest.approx(1.08490, abs=1e-9)  # §6 initial stop
    assert o.stop.move_to_breakeven_on is None  # §6: none
    assert o.stop.trail_atr_multiple is None  # §6: no trail

    assert [leg.label for leg in o.exits] == ["TP1"]  # §7: single leg
    assert [leg.kind for leg in o.exits] == ["take_profit"]
    assert [leg.fraction for leg in o.exits] == pytest.approx([1.0])  # §7
    assert o.exits[0].price == pytest.approx(1.12500, abs=1e-9)  # §7

    assert o.expires_after_bars is None  # §4: market order, no pending lifetime
    assert o.tag == "double_bottom_measured_move"
    assert o.strategy_id == "double_bottom_measured_move"

    # §6 validation note: "entry ~= Close[t] > LC > LA > stop" -- stop
    # strictly below the decision-bar close that triggered the entry.
    assert o.stop.price < o.decision_close


def test_short_order_matches_hand_computed_arithmetic(orders) -> None:
    """The short trade plan, derived from §5/§6/§7 -- the mirror adaptation.

    Pattern: A'=idx15, C'=idx17, B'=idx19, s'=21, trigger t=22.
      LA' = High[15] = 1.1140 + 0.0050 = 1.11900   (§5 #1)
      LC' = Low[17]  = 1.1060 - 0.0050 = 1.10100   (§5 #3)
      H'  = LA' - LC' = 1.11900 - 1.10100 = 0.01800 (§5 #4, height)
      LB' = High[19]  = 1.1122 + 0.0050 = 1.11720
      offset = (LA'-LB')/H' = (1.11900-1.11720)/0.01800 = 0.0018/0.0180
             = 0.10 -> within [0.05, 0.20]            (§5 #6)

      decision_close = Close[22] = 1.09900
      pip = 0.0001 (price 1.0990 < the JPY threshold -> EUR_USD convention)
      stop  = LA' + 1.0 pip = 1.11900 + 0.0001 = 1.11910          (§6)
      TP1   = 2*LC' - LA' = 2*1.10100 - 1.11900
            = 2.20200 - 1.11900 = 1.08300                         (§7)
    """
    o = orders[1]

    assert o.direction == -1  # §5: short side
    assert o.entry == "market"
    assert o.entry_price is None
    assert o.decision_close == pytest.approx(1.09900, abs=1e-9)

    assert o.stop.price == pytest.approx(1.11910, abs=1e-9)  # §6 initial stop
    assert o.stop.move_to_breakeven_on is None
    assert o.stop.trail_atr_multiple is None

    assert [leg.label for leg in o.exits] == ["TP1"]
    assert [leg.kind for leg in o.exits] == ["take_profit"]
    assert [leg.fraction for leg in o.exits] == pytest.approx([1.0])
    assert o.exits[0].price == pytest.approx(1.08300, abs=1e-9)  # §7

    assert o.expires_after_bars is None
    assert o.tag == "double_bottom_measured_move"
    assert o.strategy_id == "double_bottom_measured_move"

    # Mirror of the §6 validation note for shorts: stop strictly above the
    # decision-bar close that triggered the entry.
    assert o.stop.price > o.decision_close


def test_exit_fractions_sum_to_one_for_every_order(orders) -> None:
    """Contract invariant (§7: "Fractions sum to 1.0"); tolerance 1e-9 per
    ``OrderIntent.__post_init__``."""
    for o in orders:
        assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# 5. The non-negotiable check
# ---------------------------------------------------------------------------


def test_strategy_is_free_of_lookahead(frames) -> None:
    """Every Wave-2 strategy must pass this on real data too."""
    assert_no_lookahead_v2(_FixtureScale(), frames)
