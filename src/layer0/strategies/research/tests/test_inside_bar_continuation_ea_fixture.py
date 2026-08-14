"""GOLDEN FIXTURE — inside_bar_continuation_ea.

Format follows ``test_reference_pullback_continuation_fixture.py`` (the
Wave-2 REFERENCE_FIXTURE): hand-built bars, hand-computed expected
``OrderIntent`` values with the arithmetic shown in comments, an assertion
that ``generate_orders`` reproduces them exactly, and a mapping from each
assertion to the spec rule it enforces.

The fixture subclasses the strategy to shrink ``ATR_PERIOD`` from 14 to 1 and
``warmup_bars`` from 42 to 1 — that is allowed and expected (30 bars cannot
warm a 14-period ATR to a "settled" state the way 10 years of H4 data does).
Shrinking the ATR period to 1 makes ``ewm(span=1, adjust=False)`` degenerate
to alpha=1.0, i.e. ``atr[t] == true_range[t]`` exactly with no dependence on
any bar before ``t-1`` — which is what makes the ATR filter's arithmetic
checkable by hand below. Nothing about the *logic* changes: the same five
gates, the same 0.62 stop fraction, the same 1.0 RR, the same
``expires_after_bars = 1``.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.inside_bar_continuation_ea import (
    InsideBarContinuationEA,
)

# ---------------------------------------------------------------------------
# 1. The bars, and why these bars
# ---------------------------------------------------------------------------
# 30 H4 bars (5 trading days at 6 bars/day). Three blocks of flat "filler"
# bars (Open == Close, so they can never satisfy the Main Bar directional
# gate §4.1/§5.1) bracket two hand-built setups:
#
#   bars 0-5   filler @ 1.0980  (warmup; also proves filler never fires)
#   bar  6     Main Bar, BULLISH  -> the long setup's Main Bar
#   bar  7     Signal Bar, inside bar 6                -> LONG fires here
#   bars 8-19  filler @ 1.1100  (12 bars of padding / no-signal proof)
#   bar  20    Main Bar, BEARISH -> the short setup's Main Bar
#   bar  21    Signal Bar, inside bar 20                -> SHORT fires here
#   bars 22-29 filler @ 1.1100  (trailing padding)
#
# Filler bars within a block are IDENTICAL to each other, so the strict
# containment inequalities (§4.4/§5.4: High[t] < High[t-1] AND
# Low[t] > Low[t-1]) never hold between two filler bars — equal is not
# strictly less/greater. Filler bars adjacent to a real bar also fail
# containment (checked in test_no_spurious_orders_from_filler_bars). Every
# non-filler bar (6, 7, 20, 21) used as a would-be Main Bar for its
# neighbour also fails body dominance (§4.2/§5.2) or containment — verified
# by the same test, and by construction of the exact-order-list assertion
# below (exactly two orders, no more).

OPENS = (
    [1.0980] * 6 + [1.1000, 1.1050] + [1.1100] * 12 + [1.1200, 1.1145] + [1.1100] * 8
)
HIGHS = (
    [1.0985] * 6 + [1.1065, 1.1062] + [1.1105] * 12 + [1.1205, 1.1160] + [1.1105] * 8
)
LOWS = [1.0975] * 6 + [1.0995, 1.1040] + [1.1095] * 12 + [1.1135, 1.1138] + [1.1095] * 8
CLOSES = (
    [1.0980] * 6 + [1.1060, 1.1055] + [1.1100] * 12 + [1.1140, 1.1142] + [1.1100] * 8
)

assert len(OPENS) == len(HIGHS) == len(LOWS) == len(CLOSES) == 30


class _FixtureScale(InsideBarContinuationEA):
    """Production logic, fixture-sized ATR lookback."""

    ATR_PERIOD = 1  # ewm(span=1) => atr[t] == true_range[t], hand-checkable

    @property
    def warmup_bars(self) -> int:
        return 1


@pytest.fixture(scope="module")
def frames() -> dict:
    idx = pd.date_range("2020-01-01", periods=len(CLOSES), freq="4h", tz="UTC")
    h4 = pd.DataFrame(
        {
            "Open": OPENS,
            "High": HIGHS,
            "Low": LOWS,
            "Close": CLOSES,
            "Volume": 1.0,
        },
        index=idx,
    )
    return {"H4": h4}


@pytest.fixture(scope="module")
def orders(frames) -> list:
    return list(_FixtureScale().generate_orders(frames))


# ---------------------------------------------------------------------------
# 2 + 3. Expected values, computed by hand, then asserted
# ---------------------------------------------------------------------------


def test_emits_exactly_the_expected_setups(orders) -> None:
    """Rule (§4, §5): exactly one long at bar 7, one short at bar 21.

    Every filler bar and every non-filler bar used as the OTHER role fails
    at least one of the five gates (see the bar-by-bar note above), so no
    third order can exist.
    """
    assert [str(o.decision_bar) for o in orders] == [
        "2020-01-02 04:00:00+00:00",  # bar 7 (Signal Bar of the long setup)
        "2020-01-04 12:00:00+00:00",  # bar 21 (Signal Bar of the short setup)
    ]
    assert [o.direction for o in orders] == [1, -1]
    assert [o.entry for o in orders] == ["buy_stop", "sell_stop"]


def test_long_setup_matches_hand_computed_arithmetic(orders) -> None:
    """Long setup: Main Bar = bar 6, Signal Bar = bar 7.

    Main Bar (bar 6):  Open=1.1000 Close=1.1060 High=1.1065 Low=1.0995
      rng[5]  = 1.1065 - 1.0995                          = 0.0070   (§3)
      body[5] = |1.1060 - 1.1000|                        = 0.0060  (§3)
      §4.1 bullish: Close(1.1060) > Open(1.1000)                    -> True
      §4.2 body dominance: 0.0060 >= 0.5 x 0.0070 = 0.0035          -> True

    Signal Bar (bar 7): Open=1.1050 Close=1.1055 High=1.1062 Low=1.1040
      §4.4 containment: High(1.1062) < 1.1065 AND Low(1.1040) > 1.0995
                                                                     -> True
      rng[6] = 1.1062 - 1.1040                            = 0.0022
      §4.5 size: 0.0022 <= 0.5 x 0.0070 = 0.0035                    -> True

      ATR14[7] with ATR_PERIOD=1 (ewm span=1 => atr[t] = true_range[t]):
        true_range[7] = max(High[7]-Low[7],
                             |High[7]-Close[6]|,
                             |Low[7]-Close[6]|)
                       = max(1.1062-1.1040, |1.1062-1.1060|, |1.1040-1.1060|)
                       = max(0.0022, 0.0002, 0.0020)
                       = 0.0022
      §4.3 ATR filter: rng[5](0.0070) >= 1.5 x 0.0022 = 0.0033      -> True

    Trade plan (§4, §6, §7):
      entry_price = High[bar6]                             = 1.1065
        (exact Main Bar high, no buffer, §4/§10 row 5)
      risk R = 0.62 x rng[5] = 0.62 x 0.0070                = 0.00434  (§6)
      stop  = entry - R      = 1.1065 - 0.00434             = 1.10216  (§6)
      TP1   = entry + 1.0 x R = 1.1065 + 0.00434            = 1.11084  (§7)
    """
    o = orders[0]

    assert o.direction == 1
    assert o.entry == "buy_stop"
    assert o.entry_price == pytest.approx(1.1065, abs=1e-9)
    assert o.stop.price == pytest.approx(1.10216, abs=1e-9)

    assert [leg.label for leg in o.exits] == ["TP1"]
    assert [leg.fraction for leg in o.exits] == pytest.approx([1.0])
    assert o.exits[0].price == pytest.approx(1.11084, abs=1e-9)
    assert o.exits[0].kind == "take_profit"

    # §6: stop.move_to_breakeven_on = "none"; §6: trail = "none".
    assert o.stop.move_to_breakeven_on is None
    assert o.stop.trail_atr_multiple is None
    # §4: expires_after_bars = 1.
    assert o.expires_after_bars == 1


def test_short_setup_matches_hand_computed_arithmetic(orders) -> None:
    """Short setup: Main Bar = bar 20, Signal Bar = bar 21 (mirror of §5).

    Main Bar (bar 20): Open=1.1200 Close=1.1140 High=1.1205 Low=1.1135
      rng[19]  = 1.1205 - 1.1135                          = 0.0070   (§3)
      body[19] = |1.1140 - 1.1200|                        = 0.0060  (§3)
      §5.1 bearish: Close(1.1140) < Open(1.1200)                    -> True
      §5.2 body dominance: 0.0060 >= 0.5 x 0.0070 = 0.0035          -> True

    Signal Bar (bar 21): Open=1.1145 Close=1.1142 High=1.1160 Low=1.1138
      §5.4 containment: High(1.1160) < 1.1205 AND Low(1.1138) > 1.1135
                                                                     -> True
      rng[20] = 1.1160 - 1.1138                           = 0.0022
      §5.5 size: 0.0022 <= 0.5 x 0.0070 = 0.0035                    -> True

      true_range[21] = max(High[21]-Low[21],
                            |High[21]-Close[20]|,
                            |Low[21]-Close[20]|)
                      = max(1.1160-1.1138, |1.1160-1.1140|, |1.1138-1.1140|)
                      = max(0.0022, 0.0020, 0.0002)
                      = 0.0022
      §5.3 ATR filter: rng[19](0.0070) >= 1.5 x 0.0022 = 0.0033     -> True

    Trade plan (§5, §6, §7):
      entry_price = Low[bar20]                             = 1.1135   (§5)
      risk R = 0.62 x rng[19] = 0.62 x 0.0070               = 0.00434  (§6)
      stop  = entry + R      = 1.1135 + 0.00434             = 1.11784  (§6)
      TP1   = entry - 1.0 x R = 1.1135 - 0.00434            = 1.10916  (§7)
    """
    o = orders[1]

    assert o.direction == -1
    assert o.entry == "sell_stop"
    assert o.entry_price == pytest.approx(1.1135, abs=1e-9)
    assert o.stop.price == pytest.approx(1.11784, abs=1e-9)

    assert [leg.label for leg in o.exits] == ["TP1"]
    assert [leg.fraction for leg in o.exits] == pytest.approx([1.0])
    assert o.exits[0].price == pytest.approx(1.10916, abs=1e-9)
    assert o.exits[0].kind == "take_profit"

    assert o.stop.move_to_breakeven_on is None
    assert o.stop.trail_atr_multiple is None
    assert o.expires_after_bars == 1


def test_exit_fractions_sum_to_one(orders) -> None:
    """Rule (§7 / contract hard rule 4): exit-leg fractions sum to 1.0."""
    for o in orders:
        assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)


def test_pending_entry_sits_on_correct_side_of_close(frames, orders) -> None:
    """Rule (§4 validity note / §5 mirror): a pending entry must be on the
    correct side of the decision-bar close — buy_stop above, sell_stop
    below. The spec proves this always holds given strict containment
    (§4.4/§5.4); this test demonstrates it empirically on the fixture."""
    close = frames["H4"]["Close"]
    for o in orders:
        c = float(close.loc[o.decision_bar])
        if o.entry == "buy_stop":
            assert o.entry_price > c
        else:
            assert o.entry_price < c


def test_expires_after_one_bar(orders) -> None:
    """Rule (§4 / §5 / §10 row 2): expires_after_bars = 1, EA-style
    next-bar-only fill window."""
    for o in orders:
        assert o.expires_after_bars == 1


def test_no_spurious_orders_from_filler_bars(frames) -> None:
    """Rule (§4.4/§5.4 + §4.2/§5.2): filler bars can never be a Main Bar
    (Open == Close, so neither §4.1 nor §5.1 can hold) and identical
    adjacent filler bars can never satisfy the strict containment
    inequality either. Re-run on filler-only slices to make that explicit,
    independent of the two-order assertion above."""
    h4 = frames["H4"]
    strat = _FixtureScale()
    filler_only = h4.iloc[0:6]
    assert list(strat.generate_orders({"H4": filler_only})) == []
    filler_only_2 = h4.iloc[8:20]
    assert list(strat.generate_orders({"H4": filler_only_2})) == []


# ---------------------------------------------------------------------------
# 4. The non-negotiable check
# ---------------------------------------------------------------------------


def test_strategy_is_free_of_lookahead(frames) -> None:
    """Every Wave-2 strategy must pass this on real data too. Proven here on
    hand-built fixture frames per RUN_BRIEF.md ("What you cannot run")."""
    assert_no_lookahead_v2(_FixtureScale(), frames)
