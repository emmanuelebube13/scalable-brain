"""GOLDEN FIXTURE — src/layer0/strategies/research/demark_fractal_breakout.py.

Format follows REFERENCE_FIXTURE.py
(``test_reference_pullback_continuation_fixture.py``): hand-built bars, hand
-computed expected ``OrderIntent`` values with the arithmetic shown, an
assertion that ``generate_orders`` matches exactly, and a mapping of each
assertion back to the spec rule it enforces.

---------------------------------------------------------------------------
1. The bars, and why these bars
---------------------------------------------------------------------------
30 H4 bars, index 0..29. ``confirmed_swing_points`` detects highs and lows
INDEPENDENTLY (a swing high depends only on the High column, a swing low only
on the Low column — see causal_structure.py), so the High and Low series
below are engineered separately, each flat except for one deliberate spike:

  High: 1.1000 everywhere except bar 8, which spikes to 1.1050.
  Low:  1.0950 everywhere except bar 2 (dips to 1.0900) and bar 14 (dips to
        1.0850).
  Close/Open: flat 1.0975 everywhere (between the Low and High baselines;
        never read by the strategy except as ``decision_close``).

Because every non-spike value is IDENTICAL, no other bar can satisfy
``confirmed_swing_points``'s strict occurrence test (`>` / `<`, never `>=`
/ `<=`) — a tie never registers a swing. So there are exactly three raw
swing events, each isolated:

  * bar 2  -> confirmed swing LOW  (occurrence j1=2,  level Low[2]=1.0900)
  * bar 8  -> confirmed swing HIGH (occurrence k1=8,  level High[8]=1.1050)
  * bar 14 -> confirmed swing LOW  (occurrence j2=14, level Low[14]=1.0850)

``confirmed_swing_points(period=2)`` confirms each at ``occurrence + 2``
(bars 4, 10, 16); the strategy's mandatory extra lag (spec §10 #2, NOTE 1)
shifts that one more bar, to ``occurrence + 3`` (bars 5, 11, 17) — this is
where the strategy treats each level as a FRESH confirmation event:

  * bar 5  -- fresh BLUE event, level 1.0900. No RED circle has confirmed yet
             (the first one confirms at bar 11), so §5.3's stop-anchor
             requirement fails and NO short is emitted here. This bar exists
             specifically to prove the anchor-missing skip (spec §10 #9).
  * bar 11 -- fresh RED event, level 1.1050. The blue circle from bar 5 is
             available as the long's stop anchor (§4.3) -> LONG fires.
  * bar 17 -- fresh BLUE event, level 1.0850. The red circle from bar 11 is
             now available as the short's stop anchor (§5.3) -> SHORT fires.

So this single 30-bar series is engineered to fire exactly once long and
once short, from the minimum three fractals needed to prove both the
"anchor exists" and "anchor missing" paths (§4.3/§5.3, §10 #9).

---------------------------------------------------------------------------
2 + 3. Expected values, computed by hand from the spec, then asserted
---------------------------------------------------------------------------
Pip = 0.0001 (EUR_USD, ``metadata.pairs[0]``).

LONG (decision_bar = bar 11, red circle occurring at k=8, level High[8]=1.1050):
  entry = High[k] + 4.0 pips + 1.0 pip = 1.1050 + 0.0005          = 1.10550   (§4)
  blue anchor (bar-5 event) = Low[j1] = 1.0900                     (§4.3)
  stop  = Low[j] - 3.0 pips = 1.0900 - 0.0003                     = 1.08970   (§6)

SHORT (decision_bar = bar 17, blue circle occurring at j=14, level Low[14]=1.0850):
  entry = Low[j] - 4.0 pips - 1.0 pip = 1.0850 - 0.0005           = 1.08450   (§5)
  red anchor (bar-11 event) = High[k1] = 1.1050                    (§5.3)
  stop  = High[k] + 3.0 pips = 1.1050 + 0.0003                    = 1.10530   (§6)

Both orders carry a single TRAIL exit leg (fraction 1.0, kind="trailing",
atr_multiple=1.5 -- spec §6/§7), no breakeven (§6), and
``expires_after_bars = 12`` (3 H4 decision bars x 4 H1 bars/H4 bar -- spec
§10 #11, see NOTE in the strategy module for why 12 and not 3).

---------------------------------------------------------------------------
4. Assertion -> spec rule map
---------------------------------------------------------------------------
  test_emits_exactly_the_expected_setups      -> §4.1/§5.1 (fresh-event gate,
                                                  one order per confirmation),
                                                  §10 #9 (anchor-missing skip)
  test_long_order_matches_hand_computed_arithmetic -> §4 entry/stop formulas,
                                                  §6 stop, §7 TRAIL leg
  test_short_order_matches_hand_computed_arithmetic -> §5 entry/stop formulas
                                                  (mirror), §6, §7
  test_exit_fractions_sum_to_one              -> contract fraction-sum rule
                                                  (hard rule 4) / §7
  test_pending_entries_sit_on_the_correct_side_of_market -> NOTE 4 / §4,§5
                                                  ("Condition 2 guarantees ...")
  test_no_short_when_no_confirmed_red_anchor_exists -> §5.3, §10 #9
  test_strategy_is_free_of_lookahead          -> contract §2.1 / hard rule 1
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.demark_fractal_breakout import (
    DemarkFractalBreakout,
)

PIP = 0.0001

N_BARS = 30
HIGH_BASE = 1.1000
LOW_BASE = 1.0950
FLAT = 1.0975  # Open/Close baseline; strictly between LOW_BASE and HIGH_BASE

HIGHS = [HIGH_BASE] * N_BARS
LOWS = [LOW_BASE] * N_BARS

# Bar 2: isolated swing LOW (dip below the flat Low baseline on both sides).
LOWS[2] = 1.0900
# Bar 8: isolated swing HIGH (spike above the flat High baseline on both sides).
HIGHS[8] = 1.1050
# Bar 14: second isolated swing LOW.
LOWS[14] = 1.0850


class _FixtureScale(DemarkFractalBreakout):
    """Production logic; only ``warmup_bars`` is shrunk (NOTE: LevDP=2 and the
    3-bar staleness/lag windows already need almost no history — the
    production value is sized for the engine's ATR(14) trail, not for this
    strategy's own signal, so it is safe and expected to override it here)."""

    @property
    def warmup_bars(self) -> int:
        return 0


@pytest.fixture(scope="module")
def frames() -> dict:
    idx = pd.date_range("2020-03-02", periods=N_BARS, freq="4h", tz="UTC")
    h4 = pd.DataFrame(
        {
            "Open": [FLAT] * N_BARS,
            "High": HIGHS,
            "Low": LOWS,
            "Close": [FLAT] * N_BARS,
            "Volume": 1.0,
        },
        index=idx,
    )
    return {"H4": h4}


@pytest.fixture(scope="module")
def orders(frames) -> list:
    return list(_FixtureScale().generate_orders(frames))


# ---------------------------------------------------------------------------
# 2 + 3. Expected values, then asserted
# ---------------------------------------------------------------------------


def test_emits_exactly_the_expected_setups(frames, orders) -> None:
    """Rule (§4.1/§5.1 fresh-confirmation gate; §10 #9 anchor-missing skip):

    Three fractals confirm (lag-adjusted) at bars 5, 11, 17. Bar 5 (a fresh
    blue/short candidate) has no confirmed red circle yet -> skipped. Bars 11
    (long) and 17 (short) both have a valid opposite anchor -> exactly 2
    orders, in bar order.
    """
    idx = frames["H4"].index
    assert [o.decision_bar for o in orders] == [idx[11], idx[17]]
    assert [o.direction for o in orders] == [1, -1]


def test_long_order_matches_hand_computed_arithmetic(orders) -> None:
    """§4 entry, §6 stop/trail, §7 exit leg — arithmetic in the module docstring.

    entry = High[8] + 4pip + 1pip = 1.1050 + 0.0005 = 1.10550
    stop  = Low[2]  - 3pip        = 1.0900 - 0.0003 = 1.08970
    """
    o = orders[0]
    assert o.direction == 1
    assert o.entry == "buy_stop"
    assert o.entry_price == pytest.approx(1.10550, abs=1e-9)
    assert o.stop.price == pytest.approx(1.08970, abs=1e-9)
    assert o.stop.move_to_breakeven_on is None  # §6: no breakeven mechanism
    assert o.stop.trail_atr_multiple == pytest.approx(1.5)  # §6

    assert [leg.label for leg in o.exits] == ["TRAIL"]
    assert o.exits[0].kind == "trailing"
    assert o.exits[0].fraction == pytest.approx(1.0)
    assert o.exits[0].atr_multiple == pytest.approx(1.5)  # §7
    assert o.exits[0].price is None  # trailing legs carry no absolute price

    assert o.expires_after_bars == 12  # §10 #11 translation (3 H4 x 4 H1/H4)


def test_short_order_matches_hand_computed_arithmetic(orders) -> None:
    """§5 entry, §6 stop/trail, §7 exit leg (mirror of the long case).

    entry = Low[14] - 4pip - 1pip = 1.0850 - 0.0005 = 1.08450
    stop  = High[8] + 3pip        = 1.1050 + 0.0003 = 1.10530
    """
    o = orders[1]
    assert o.direction == -1
    assert o.entry == "sell_stop"
    assert o.entry_price == pytest.approx(1.08450, abs=1e-9)
    assert o.stop.price == pytest.approx(1.10530, abs=1e-9)
    assert o.stop.move_to_breakeven_on is None
    assert o.stop.trail_atr_multiple == pytest.approx(1.5)

    assert [leg.label for leg in o.exits] == ["TRAIL"]
    assert o.exits[0].kind == "trailing"
    assert o.exits[0].fraction == pytest.approx(1.0)
    assert o.exits[0].atr_multiple == pytest.approx(1.5)

    assert o.expires_after_bars == 12


def test_exit_fractions_sum_to_one(orders) -> None:
    """Contract rule (hard rule 4 / spec §7: 'fractions sum to exactly 1.0')."""
    for o in orders:
        total = sum(leg.fraction for leg in o.exits)
        assert total == pytest.approx(1.0, abs=1e-9)


def test_pending_entries_sit_on_the_correct_side_of_market(frames, orders) -> None:
    """NOTE 4 / spec §4,§5: 'Condition 2 guarantees Close(t) <= High(t) <
    High[k] < entry_price' (and the mirror for shorts) -- a buy_stop must be
    above the decision close, a sell_stop below it."""
    close = frames["H4"]["Close"]
    for o in orders:
        c = float(close.loc[o.decision_bar])
        if o.entry == "buy_stop":
            assert o.entry_price > c
        elif o.entry == "sell_stop":
            assert o.entry_price < c


def test_no_short_when_no_confirmed_red_anchor_exists(frames) -> None:
    """§5.3 / §10 #9: the bar-5 fresh blue event has no confirmed red circle
    yet (the first red confirms at bar 11) -- must be skipped, not fall back
    to any invented anchor. Verified directly against the full order list
    (not just the final assertion in test_emits_exactly_the_expected_setups)
    so a future change to the anchor logic cannot silently reintroduce it."""
    orders = list(_FixtureScale().generate_orders(frames))
    idx = frames["H4"].index
    assert idx[5] not in {o.decision_bar for o in orders}


# ---------------------------------------------------------------------------
# 4. The non-negotiable check
# ---------------------------------------------------------------------------


def test_strategy_is_free_of_lookahead(frames) -> None:
    """Every Wave-2 strategy must pass this on real data too (contract §2.1)."""
    assert_no_lookahead_v2(_FixtureScale(), frames)
