"""GOLDEN FIXTURE — h4_forex_system.

Format follows ``test_reference_pullback_continuation_fixture.py``:

1. Hand-built bars, literal, chosen for stated reasons (below).
2. Expected ``OrderIntent`` values computed by hand from the spec, arithmetic
   shown in comments.
3. Assertions that ``generate_orders`` produces exactly that.
4. A mapping from each assertion back to the spec rule it enforces.

The fixture subclasses ``H4ForexSystem`` to shrink the EMA/SMA/MACD periods
(``EMA_FAST_PERIOD``, ``SMA_SLOW_PERIOD``, ``MACD_FAST/SLOW/SIGNAL``) and
``warmup_bars`` — 36 bars cannot warm a 26/9 MACD. This is the same allowed
pattern as the reference fixture's ``_FixtureScale``. The Parabolic SAR
``PSAR_STEP``/``PSAR_MAX_AF`` are **not** shrunk: they are not lookback
periods, they are the level formula itself (spec §3), and changing them would
change the arithmetic under test.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.h4_forex_system import H4ForexSystem

PIP = 0.0001  # GBP_USD, spec §3 / §6

# ---------------------------------------------------------------------------
# 1. The bars, and why these bars
# ---------------------------------------------------------------------------
# 36 H4 bars, High/Low = Close +/- 0.0010 on every bar (a constant spread, so
# every indicator value below is reproducible from Close alone):
#
#   idx  0-5   (6 bars) flat at 1.1000 — seeds the Parabolic SAR in long mode
#               with no cushion (SAR == Low, EP == High: dot sits ON the bar,
#               never "below" it — see §3's strict "<") and warms SMA(3)/EMA.
#   idx  6-9   (4 bars) a clean rise 1.1030 -> 1.1120 — by bar 6 the 6-EMA/
#               13-SMA analogue crosses UP, the MACD analogue crosses UP, and
#               the SAR (still lagging from the flat seed) sits strictly below
#               the bar: all three §4 conditions land on the SAME bar, engineered
#               by construction, not by search.
#   idx  10    a sharp drop to 1.0950 — the plunge is engineered to (a) push
#               Low(10) under the still-rising long-mode SAR, forcing the §3
#               reversal to short mode (SAR jumps to the prior leg's extreme,
#               well above price -> dot above), and (b) simultaneously flip the
#               EMA/SMA analogue and the MACD analogue down. All three §5
#               conditions land on bar 10.
#   idx  11-12  two more down bars, easing into a floor at 1.0920.
#   idx  13-35  (24 bars) flat at 1.0920 — pads the fixture to 36 bars and lets
#               every indicator settle into a quiescent state (EMA==SMA exactly
#               once 3 flat bars have accumulated) so no further §4/§5
#               conjunction can ever be satisfied again: this proves bar 6 and
#               bar 10 are the ONLY two orders, not just the first two.
#
# Every intermediate EMA(1)/SMA(3)/MACD(1,2,2)/PSAR(0.02,0.20) value on this
# series was hand-derived from the recursions in spec §3 (Wilder PSAR) and the
# inventory formulas (`ema`, `sma`, `macd`) before this file was written; the
# derivation is reproduced next to each assertion below. EMA_FAST_PERIOD=1
# makes the fast average degenerate to Close itself (alpha = 2/(1+1) = 1),
# which is what makes the cross arithmetic tractable by hand while remaining
# the same EMA formula the production strategy uses (only the *period* differs
# from the spec's 6, exactly as the run brief permits).
CLOSES = [
    # idx 0-5: flat seed for PSAR / SMA(3) warmup
    1.1000,
    1.1000,
    1.1000,
    1.1000,
    1.1000,
    1.1000,
    # idx 6-9: clean rise -> long setup fires at idx 6
    1.1030,
    1.1060,
    1.1090,
    1.1120,
    # idx 10: sharp drop -> short setup fires at idx 10
    1.0950,
    # idx 11-12: ease into the floor
    1.0930,
    1.0920,
] + [
    1.0920
] * 23  # idx 13-35: flat floor, pads to 36 bars, no further crosses

assert len(CLOSES) == 36


class _FixtureScale(H4ForexSystem):
    """Production logic, fixture-sized lookbacks (never a changed formula)."""

    EMA_FAST_PERIOD = 1  # spec's 6-EMA, shrunk so the cross is hand-tractable
    SMA_SLOW_PERIOD = 3  # spec's 13-SMA, shrunk to warm in 3 bars
    MACD_FAST = 1  # spec's 12, shrunk
    MACD_SLOW = 2  # spec's 26, shrunk
    MACD_SIGNAL = 2  # spec's 9, shrunk
    # PSAR_STEP / PSAR_MAX_AF intentionally NOT overridden (see module docstring).

    @property
    def warmup_bars(self) -> int:
        return 3  # enough for SMA(3) to be defined; production uses 27 (§3)


@pytest.fixture(scope="module")
def frames() -> dict:
    idx = pd.date_range("2020-01-01", periods=len(CLOSES), freq="4h", tz="UTC")
    h4 = pd.DataFrame(
        {
            "Open": CLOSES,
            "High": [c + 0.0010 for c in CLOSES],
            "Low": [c - 0.0010 for c in CLOSES],
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


def test_emits_exactly_two_orders_long_then_short(orders) -> None:
    """Rule (§4/§5): fires only on the bar where EMA/SMA cross, MACD cross,
    and PSAR position all hold simultaneously.

    idx 6  -> long  (2020-01-01 00:00 + 6*4h = 2020-01-02 00:00)
    idx 10 -> short (2020-01-01 00:00 + 10*4h = 2020-01-02 16:00)

    No other bar satisfies the full conjunction (see the flat head/tail
    reasoning in the bars comment above), so exactly two orders exist.
    """
    assert [str(o.decision_bar) for o in orders] == [
        "2020-01-02 00:00:00+00:00",
        "2020-01-02 16:00:00+00:00",
    ]
    assert [o.direction for o in orders] == [1, -1]


def test_long_order_matches_hand_computed_arithmetic(orders) -> None:
    """The long trade plan at idx 6, derived from spec §4/§6/§7.

    EMA(1)[6] = Close[6] = 1.1030 (period-1 EMA degenerates to Close).
    SMA(3)[6] = mean(Close[4], Close[5], Close[6])
              = mean(1.1000, 1.1000, 1.1030) = 3.3030 / 3 = 1.1010.
    EMA(1)[5] = Close[5] = 1.1000; SMA(3)[5] = mean(1.1000,1.1000,1.1000) = 1.1000.
      -> EMA[6](1.1030) > SMA[6](1.1010) AND EMA[5](1.1000) <= SMA[5](1.1000):
         the 6-EMA/13-SMA analogue crosses UP on bar 6 (§4.1).

    MACD(1,2,2): fast EMA(1) = Close; slow EMA(2), alpha = 2/3:
      S2[5] = 1.1000 (flat run); S2[6] = S2[5] + (2/3)(Close[6]-S2[5])
             = 1.1000 + (2/3)(0.0030) = 1.1020.
      macd_line[6] = Close[6] - S2[6] = 1.1030 - 1.1020 = 0.0010.
      macd_line[5] = Close[5] - S2[5] = 1.1000 - 1.1000 = 0.
      signal = EMA(macd_line, 2), alpha = 2/3; signal[5] = 0 (macd_line has
        been exactly 0 for the whole flat run, and EMA of a constant is that
        constant).
      signal[6] = 0 + (2/3)(0.0010 - 0) = 0.00066667.
      -> macd_line[6](0.0010) > signal[6](0.00066667) AND
         macd_line[5](0) <= signal[5](0): MACD analogue crosses UP on bar 6
         (§4.2).

    Parabolic SAR (§3): seeded at idx 1 in long mode (Close[1] >= Close[0]):
      SAR[1] = Low[0] = 1.0990, EP[1] = High[1] = 1.1010, AF = 0.02.
      Bars 2-5 are flat (High/Low constant at 1.1010/1.0990): SAR stays
        clamped to Low[t-1]=Low[t-2]=1.0990 every bar (EP never rises, since
        High never exceeds 1.1010); SAR[5] = 1.0990, EP = 1.1010, AF = 0.02.
      Bar 6: SAR_raw = 1.0990 + 0.02*(1.1010-1.0990) = 1.09904;
        clamp = min(1.09904, Low[5]=1.0990, Low[4]=1.0990) = 1.0990;
        Low[6]=1.1020 < 1.0990? No -> no reversal;
        High[6]=1.1040 > EP(1.1010)? Yes -> EP=1.1040, AF=0.04;
        SAR[6] = 1.0990 (the clamped value).
      -> psar[6](1.0990) < Low[6](1.1020): PSAR dot below the bar (§4.3).

    All three §4 conditions hold on bar 6 -> long order.

    §6: stop = C - SL_pips*P, C = Close[6] = 1.1030, SL_pips(H4 GBP_USD) = 70,
        P = 0.0001 -> stop = 1.1030 - 70*0.0001 = 1.1030 - 0.0070 = 1.0960.
    §7: TP1 = C + TP_pips*P, TP_pips(H4 GBP_USD) = 60
        -> TP1 = 1.1030 + 60*0.0001 = 1.1030 + 0.0060 = 1.1090.
    """
    o = orders[0]
    close_t = 1.1030

    assert o.direction == 1
    assert o.entry == "market"
    assert o.entry_price is None  # §4: entry_price = None for a market entry
    assert o.decision_close == pytest.approx(close_t, abs=1e-9)

    assert o.stop.price == pytest.approx(1.0960, abs=1e-9)
    assert o.stop.move_to_breakeven_on is None  # §6: none
    assert o.stop.trail_atr_multiple is None  # §6: static stop, never moves

    assert [leg.label for leg in o.exits] == ["TP1"]
    assert [leg.fraction for leg in o.exits] == pytest.approx([1.0])
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)
    assert o.exits[0].price == pytest.approx(1.1090, abs=1e-9)

    assert o.expires_after_bars is None  # §4: market entry, no pending order


def test_short_order_matches_hand_computed_arithmetic(orders) -> None:
    """The short trade plan at idx 10, derived from spec §5/§6/§7.

    EMA(1)[10] = Close[10] = 1.0950.
    SMA(3)[10] = mean(Close[8], Close[9], Close[10])
               = mean(1.1090, 1.1120, 1.0950) = 3.3160 / 3 = 1.10533333.
    EMA(1)[9] = 1.1120; SMA(3)[9] = mean(1.1060,1.1090,1.1120) = 1.1090.
      -> EMA[10](1.0950) < SMA[10](1.10533) AND EMA[9](1.1120) >= SMA[9](1.1090):
         the EMA/SMA analogue crosses DOWN on bar 10 (§5.1).

    MACD(1,2,2), continuing the slow EMA(2) recursion (alpha = 2/3):
      S2[7]=1.1046667, S2[8]=1.1075556, S2[9]=1.1105185,
      S2[10] = S2[9] + (2/3)(Close[10]-S2[9])
              = 1.1105185 + (2/3)(1.0950-1.1105185) = 1.1105185-0.0103457
              = 1.1001728.
      macd_line[9] = Close[9]-S2[9] = 1.1120-1.1105185 = 0.0014815.
      macd_line[10] = Close[10]-S2[10] = 1.0950-1.1001728 = -0.0051728.
      signal[9] = 0.0014321, signal[10] = signal[9] + (2/3)(macd_line[10]-signal[9])
                = 0.0014321 + (2/3)(-0.0066049) = -0.0029712.
      -> macd_line[10](-0.0051728) < signal[10](-0.0029712) AND
         macd_line[9](0.0014815) >= signal[9](0.0014321): MACD analogue
         crosses DOWN on bar 10 (§5.2).

    Parabolic SAR, continuing the long-mode recursion from bar 6
      (SAR=1.0990, EP=1.1040, AF=0.04) through bars 7-9:
      bar 7: raw=1.0990+0.04*(1.1040-1.0990)=1.0992; clamp=min(1.0992,
             Low[6]=1.1020, Low[5]=1.0990)=1.0990; no reversal (Low[7]=1.1050);
             High[7]=1.1070>EP(1.1040) -> EP=1.1070, AF=0.06; SAR[7]=1.0990.
      bar 8: raw=1.0990+0.06*(1.1070-1.0990)=1.09948; clamp=min(1.09948,
             Low[7]=1.1050, Low[6]=1.1020)=1.09948; no reversal (Low[8]=1.1080);
             High[8]=1.1100>EP(1.1070) -> EP=1.1100, AF=0.08; SAR[8]=1.09948.
      bar 9: raw=1.09948+0.08*(1.1100-1.09948)=1.1003216; clamp=min(1.1003216,
             Low[8]=1.1080, Low[7]=1.1050)=1.1003216; no reversal (Low[9]=1.1110);
             High[9]=1.1130>EP(1.1100) -> EP=1.1130, AF=0.10; SAR[9]=1.1003216.
      bar 10: raw=1.1003216+0.10*(1.1130-1.1003216)=1.10158944; clamp=
             min(1.10158944, Low[9]=1.1110, Low[8]=1.1080)=1.10158944;
             Low[10]=1.0940 < 1.10158944 -> REVERSAL to short:
             SAR[10] = EP(1.1130) (the prior long leg's highest high),
             EP resets to Low[10]=1.0940, AF resets to 0.02.
      -> psar[10](1.1130) > High[10](1.0960): PSAR dot above the bar (§5.3).

    All three §5 conditions hold on bar 10 -> short order.

    §6: stop = C + SL_pips*P, C = Close[10] = 1.0950, SL_pips = 70
        -> stop = 1.0950 + 0.0070 = 1.1020.
    §7: TP1 = C - TP_pips*P, TP_pips = 60 -> TP1 = 1.0950 - 0.0060 = 1.0890.
    """
    o = orders[1]
    close_t = 1.0950

    assert o.direction == -1
    assert o.entry == "market"
    assert o.entry_price is None
    assert o.decision_close == pytest.approx(close_t, abs=1e-9)

    assert o.stop.price == pytest.approx(1.1020, abs=1e-9)
    assert o.stop.move_to_breakeven_on is None
    assert o.stop.trail_atr_multiple is None

    assert [leg.label for leg in o.exits] == ["TP1"]
    assert [leg.fraction for leg in o.exits] == pytest.approx([1.0])
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)
    assert o.exits[0].price == pytest.approx(1.0890, abs=1e-9)

    assert o.expires_after_bars is None


def test_stop_and_target_pip_distances_match_the_h4_gbp_usd_table(orders) -> None:
    """Rule (§6/§7 table): H4 GBP_USD risks 70 pips to make 60, for both
    directions — derived from entry-anchor arithmetic, not hardcoded levels."""
    for o in orders:
        risk_pips = abs(o.decision_close - o.stop.price) / PIP
        reward_pips = abs(o.exits[0].price - o.decision_close) / PIP
        assert risk_pips == pytest.approx(70.0, abs=1e-6)
        assert reward_pips == pytest.approx(60.0, abs=1e-6)


def test_no_orders_outside_the_two_engineered_setups(orders) -> None:
    """Rule (§4/§5 conjunction): the flat head (idx 0-5) and flat floor
    (idx 13-35) each hold EMA==SMA or a non-crossing state, so the three-way
    conjunction can never be satisfied there. Exactly two orders exist."""
    assert len(orders) == 2


# ---------------------------------------------------------------------------
# 4. The non-negotiable check
# ---------------------------------------------------------------------------


def test_strategy_is_free_of_lookahead(frames) -> None:
    """Every Wave-2 strategy must pass this on real data too."""
    assert_no_lookahead_v2(_FixtureScale(), frames)
