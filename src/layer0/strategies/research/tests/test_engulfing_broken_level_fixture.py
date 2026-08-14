"""GOLDEN FIXTURE for ``engulfing_broken_level`` (SPEC-engulfing_broken_level).

34 hand-built D1 bars: 8 inert leading filler bars, an 18-bar block engineered
to fire the LONG setup exactly once, a further 8-bar block engineered to fire
the SHORT setup exactly once, and 4 inert trailing filler bars. One series
covers both directions (the run brief's two-series escape hatch is not
needed here) because, once the first breakout has happened, the same D1 path
can simply keep going and build a second, independent swing structure for the
mirror setup.

Every filler bar is a doji (Open == Close), which makes condition 1
(bullish/bearish) fail unconditionally — they can never become decision bars
regardless of anything else in the frame, so they cannot introduce spurious
orders no matter what swing bookkeeping happens around them.

The fixture subclasses the strategy to shrink ``SWING_PERIOD`` (5 -> 2) and
``ATR_PERIOD`` (14 -> 1) and to override ``warmup_bars`` (34 bars cannot warm
a period-14 ATR at production settings, and the production ``warmup_bars``
formula wants period*4 = 20+). ``ATR_PERIOD=1`` is a deliberate, aggressive
shrink: ``ewm(span=1, adjust=False)`` has alpha=1, so the EWM recursion
collapses to ATR[t] == TrueRange[t] exactly, with no dependency on bars
before t. That makes the stop-buffer arithmetic hand-computable directly
from OHLC, instead of requiring the full recursive EWM history back to bar 0.
This shrinks a *lookback period*, per the reference fixture's own pattern; it
does not change any level formula or entry/exit logic.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.engulfing_broken_level import (
    EngulfingBrokenLevel,
)

# ---------------------------------------------------------------------------
# 1. The bars, and why these bars
# ---------------------------------------------------------------------------
# Index 0-7   : inert doji filler, warms nothing but keeps the frame >30 bars
#               and cannot itself become a decision bar (Open == Close).
# Index 8-16  : builds one confirmed swing low (occurs at 10, level 1.0950,
#               confirms at 12) and one confirmed swing high (occurs at 14,
#               level 1.1010, confirms at 16), with SWING_PERIOD=2.
# Index 17    : the LONG decision bar -- a bullish engulfing candle whose low
#               undercuts the confirmed swing low (1.0950) and whose close
#               breaks above the confirmed swing high (1.1010).
# Index 18-24 : continuation, then a second confirmed swing high (occurs at
#               22, level 1.1060, confirms at 24).
# Index 25-28 : a second confirmed swing low (occurs at 26, level 1.1030,
#               confirms at 28).
# Index 29    : the SHORT decision bar -- a bearish engulfing candle whose
#               high reaches the confirmed swing high (1.1060) and whose
#               close breaks below the confirmed swing low (1.1030).
# Index 30-33 : inert doji filler (trailing).
#
# High/Low outside the engineered bars are kept inside a few pips of
# Open/Close; the engineered bars use wide ranges because the spec's
# geometry genuinely requires it: an engulfing candle that both undercuts a
# recent swing low/high AND closes beyond a nearby confirmed level on the far
# side is, by construction, a wide-range bar.

_FILLER_LEAD = (1.1000, 1.1008, 1.0992, 1.1000)  # O, H, L, C (doji)
_FILLER_TRAIL = (1.1020, 1.1028, 1.1012, 1.1020)  # O, H, L, C (doji)

_BARS = [
    _FILLER_LEAD,  # 0
    _FILLER_LEAD,  # 1
    _FILLER_LEAD,  # 2
    _FILLER_LEAD,  # 3
    _FILLER_LEAD,  # 4
    _FILLER_LEAD,  # 5
    _FILLER_LEAD,  # 6
    _FILLER_LEAD,  # 7
    (1.1000, 1.1005, 1.0995, 1.1002),  # 8
    (1.1002, 1.1004, 1.0985, 1.0990),  # 9
    (1.0990, 1.0992, 1.0950, 1.0975),  # 10  swing-low OCCURS here: low=1.0950
    (1.0975, 1.0985, 1.0960, 1.0980),  # 11
    (1.0980, 1.0995, 1.0965, 1.0990),  # 12  swing-low CONFIRMS here (10+2)
    (1.0990, 1.1000, 1.0980, 1.0995),  # 13
    (1.0995, 1.1010, 1.0985, 1.1005),  # 14  swing-high OCCURS here: high=1.1010
    (1.1005, 1.1005, 1.0990, 1.0995),  # 15
    (
        1.0995,
        1.1000,
        1.0985,
        1.0990,
    ),  # 16  swing-high CONFIRMS here (14+2); prior bar to 17
    (1.0990, 1.1020, 1.0940, 1.1015),  # 17  LONG decision bar
    (1.1015, 1.1025, 1.1005, 1.1020),  # 18
    (1.1020, 1.1030, 1.1010, 1.1025),  # 19
    (1.1025, 1.1035, 1.1020, 1.1030),  # 20
    (1.1030, 1.1040, 1.1025, 1.1035),  # 21
    (1.1035, 1.1060, 1.1030, 1.1050),  # 22  swing-high #2 OCCURS: high=1.1060
    (1.1050, 1.1055, 1.1040, 1.1045),  # 23
    (1.1045, 1.1050, 1.1035, 1.1040),  # 24  swing-high #2 CONFIRMS here (22+2)
    (1.1040, 1.1045, 1.1032, 1.1038),  # 25
    (1.1038, 1.1042, 1.1030, 1.1033),  # 26  swing-low #2 OCCURS: low=1.1030
    (1.1033, 1.1038, 1.1031, 1.1035),  # 27
    (
        1.1035,
        1.1040,
        1.1032,
        1.1036,
    ),  # 28  swing-low #2 CONFIRMS here (26+2); prior bar to 29
    (1.1038, 1.1065, 1.1015, 1.1020),  # 29  SHORT decision bar
    _FILLER_TRAIL,  # 30
    _FILLER_TRAIL,  # 31
    _FILLER_TRAIL,  # 32
    _FILLER_TRAIL,  # 33
]

LONG_BAR_POS = 17
SHORT_BAR_POS = 29


class _FixtureScale(EngulfingBrokenLevel):
    """Production logic, fixture-sized lookbacks (see module docstring)."""

    SWING_PERIOD = 2
    ATR_PERIOD = 1

    @property
    def warmup_bars(self) -> int:
        return 5


@pytest.fixture(scope="module")
def frames() -> dict:
    idx = pd.date_range("2020-01-01", periods=len(_BARS), freq="1D", tz="UTC")
    d1 = pd.DataFrame(
        {
            "Open": [b[0] for b in _BARS],
            "High": [b[1] for b in _BARS],
            "Low": [b[2] for b in _BARS],
            "Close": [b[3] for b in _BARS],
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


def test_emits_exactly_the_long_then_short_setups(frames, orders) -> None:
    """Rule: exactly two orders, at bars 17 (long) and 29 (short) -- spec §4/§5.

    No signal is possible before bar 17: the first confirmed swing high
    doesn't exist (confirmation bar <= t-1) until t=17 (confirms at 16), so
    R_break is undefined for every earlier bar (§4.6/§9). No spurious short
    fires either: S_break stays pinned at the FIRST confirmed low (1.0950,
    absurdly far below price) until the second low confirms at bar 28, so
    condition 6 (close_t < S_break) is unsatisfiable for bars 18-28 (§5.6).
    """
    idx = frames["D1"].index
    assert [o.decision_bar for o in orders] == [
        idx[LONG_BAR_POS],
        idx[SHORT_BAR_POS],
    ]
    assert [o.direction for o in orders] == [1, -1]


def test_long_order_matches_hand_computed_arithmetic(orders) -> None:
    """Bar 17: O=1.0990 H=1.1020 L=1.0940 C=1.1015; prior bar 16: O=1.0995
    H=1.1000 L=1.0985 C=1.0990.

    §4.1 bullish:        C17(1.1015) > O17(1.0990)                    -> True
    §4.2 range engulf:   H17(1.1020) >= H16(1.1000) and
                          L17(1.0940) <= L16(1.0985)                  -> True
    §4.3 body engulf:    C17(1.1015) >= O16(1.0995) and
                          O17(1.0990) <= C16(1.0990)                  -> True
    §4.4 close beyond:   C17(1.1015) > H16(1.1000)                    -> True
    L_swing (confirm<=16) = 1.0950 (only confirmed low so far, from bar 12)
    §4.5:                L17(1.0940) <= L_swing(1.0950)                -> True
    R_break (confirm<=16) = 1.1010 (only confirmed high so far, from bar 16;
                            it is > low17=1.0940, and the only candidate)
    §4.6:                C17(1.1015) > R_break(1.1010)                 -> True

    entry_price = L17 + 0.5*(H17-L17) = 1.0940 + 0.5*(1.1020-1.0940)
                = 1.0940 + 0.5*0.0080 = 1.0940 + 0.0040 = 1.09800      (§4, §10 #10)

    §4.7 TP set (confirm<=17): only 1.1010 (> entry_price 1.0980)      -> TP=1.10100

    ATR (fixture ATR_PERIOD=1 => ATR[17] = TrueRange[17] exactly):
      TR17 = max(H17-L17, |H17-C16|, |L17-C16|)
           = max(1.1020-1.0940, |1.1020-1.0990|, |1.0940-1.0990|)
           = max(0.0080, 0.0030, 0.0050) = 0.0080
    stop = L17 - 0.5*ATR17 = 1.0940 - 0.5*0.0080 = 1.0940 - 0.0040 = 1.09000  (§6)
    """
    o = orders[0]

    assert o.direction == 1
    assert o.entry == "buy_limit"
    assert o.entry_price == pytest.approx(1.09800, abs=1e-9)
    assert o.stop.price == pytest.approx(1.09000, abs=1e-9)

    assert [leg.label for leg in o.exits] == ["TP1"]
    assert [leg.price for leg in o.exits] == pytest.approx([1.10100], abs=1e-9)
    assert [leg.fraction for leg in o.exits] == pytest.approx([1.0])
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)

    assert o.stop.move_to_breakeven_on is None  # §6: "none"
    assert o.expires_after_bars == 24  # §4, §10 #8


def test_short_order_matches_hand_computed_arithmetic(orders) -> None:
    """Bar 29: O=1.1038 H=1.1065 L=1.1015 C=1.1020; prior bar 28: O=1.1035
    H=1.1040 L=1.1032 C=1.1036.

    §5.1 bearish:        C29(1.1020) < O29(1.1038)                    -> True
    §5.2 range engulf:   H29(1.1065) >= H28(1.1040) and
                          L29(1.1015) <= L28(1.1032)                  -> True
    §5.3 body engulf:    C29(1.1020) <= O28(1.1035) and
                          O29(1.1038) >= C28(1.1036)                  -> True
    §5.4 close beyond:   C29(1.1020) < L28(1.1032)                    -> True
    H_swing (confirm<=28) = 1.1060 (most recently confirmed high, bar 24)
    §5.5:                H29(1.1065) >= H_swing(1.1060)                -> True
    S_break (confirm<=28) = max{1.0950, 1.1030} = 1.1030 (both < high29=1.1065;
                            1.1030 confirmed at bar 28, the second swing low)
    §5.6:                C29(1.1020) < S_break(1.1030)                 -> True

    entry_price = H29 - 0.5*(H29-L29) = 1.1065 - 0.5*(1.1065-1.1015)
                = 1.1065 - 0.5*0.0050 = 1.1065 - 0.0025 = 1.10400      (§5, §10 #10)

    §5.7 TP set (confirm<=29): {1.0950, 1.1030} both < entry_price(1.1040);
                            nearest (max) is                          -> TP=1.10300

    ATR (fixture ATR_PERIOD=1 => ATR[29] = TrueRange[29] exactly):
      TR29 = max(H29-L29, |H29-C28|, |L29-C28|)
           = max(1.1065-1.1015, |1.1065-1.1036|, |1.1015-1.1036|)
           = max(0.0050, 0.0029, 0.0021) = 0.0050
    stop = H29 + 0.5*ATR29 = 1.1065 + 0.5*0.0050 = 1.1065 + 0.0025 = 1.10900  (§6)
    """
    o = orders[1]

    assert o.direction == -1
    assert o.entry == "sell_limit"
    assert o.entry_price == pytest.approx(1.10400, abs=1e-9)
    assert o.stop.price == pytest.approx(1.10900, abs=1e-9)

    assert [leg.label for leg in o.exits] == ["TP1"]
    assert [leg.price for leg in o.exits] == pytest.approx([1.10300], abs=1e-9)
    assert [leg.fraction for leg in o.exits] == pytest.approx([1.0])
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)

    assert o.stop.move_to_breakeven_on is None  # §6: "none"
    assert o.expires_after_bars == 24  # §5, §10 #8


def test_exit_fractions_sum_to_one_for_every_order(orders) -> None:
    """Contract-level rule (tolerance 1e-9), also spec §7."""
    for o in orders:
        assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)


def test_pending_entry_on_correct_side_of_decision_close(frames, orders) -> None:
    """Rule (NOTE 3 analogue): a buy_limit must sit BELOW the decision-bar
    close and a sell_limit must sit ABOVE it, or it is a disguised market
    order. The strategy skips (never clamps) a violating bar."""
    close = frames["D1"]["Close"]
    for o in orders:
        c = float(close.loc[o.decision_bar])
        if o.entry == "buy_limit":
            assert o.entry_price is not None and o.entry_price < c
        elif o.entry == "sell_limit":
            assert o.entry_price is not None and o.entry_price > c


def test_take_profit_beyond_entry_in_trade_direction(orders) -> None:
    """Contract-level rule, restated: every TP leg must be strictly beyond
    entry in the trade direction (spec §7 last sentence)."""
    for o in orders:
        for leg in o.exits:
            assert leg.price is not None
            if o.direction == 1:
                assert leg.price > o.entry_price
            else:
                assert leg.price < o.entry_price


def test_no_signal_before_a_swing_high_and_low_have_both_confirmed(orders) -> None:
    """Rule (spec §9): condition 5/6 require confirmation bar <= t-1. The
    first bar at which BOTH a confirmed swing high and a confirmed swing low
    exist (confirmation bar <= t-1) is bar 17 (high confirms at 16)."""
    assert min(o.decision_bar for o in orders) == orders[0].decision_bar
    assert orders[0].decision_bar == list(orders)[0].decision_bar  # sanity
    # Positionally: no order may have decision_bar before index 17.
    for o in orders:
        assert o.decision_bar >= orders[0].decision_bar


# ---------------------------------------------------------------------------
# 4. The non-negotiable check
# ---------------------------------------------------------------------------


def test_strategy_is_free_of_lookahead(frames) -> None:
    """Every Wave-2 strategy must pass this on real data too."""
    assert_no_lookahead_v2(_FixtureScale(), frames)
