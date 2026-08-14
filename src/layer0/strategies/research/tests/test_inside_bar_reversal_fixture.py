"""GOLDEN FIXTURE for ``inside_bar_reversal`` (SPEC-inside_bar_reversal.md).

Follows the shape of ``test_reference_pullback_continuation_fixture.py``: hand-built bars,
expected ``OrderIntent`` values computed by hand from the spec (arithmetic in comments),
an assertion that ``generate_orders`` produces exactly that, and a mapping from each
assertion back to the spec rule it enforces.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.inside_bar_reversal import InsideBarReversal

# ---------------------------------------------------------------------------
# 1. The bars, and why these bars
# ---------------------------------------------------------------------------
# 41 D1 bars, three phases, engineered so the strategy fires exactly once long and
# once short, plus a handful of trailing bars so the look-ahead probe's truncation
# windows actually cover the short order too (see the last test).
#
# Phase 1 (bars 0-9): a clean uptrend. Every High/Low is strictly higher than the
# previous bar, so no inside bar can occur here, and the peak at bar 9 becomes a
# confirmed swing high (period=5) at bar 14 -- the TP target for the long trade.
#
# Phase 2 (bars 10-19): a clean downtrend (mirrors phase 1). Bar 19 is the container
# bar for the long signal AND becomes a confirmed swing low at bar 24 -- the TP
# target for the later short trade.
#
# Bar 20: the LONG decision bar. Bar 19 (bearish, part of the downtrend) is the
# container; bar 20 is strictly inside bar 19's range (High/Low margins of exactly
# 0.0001) and bullish -- the reversal pattern (spec §4).
#
# Phase 3 (bars 21-34): a clean uptrend (mirrors phase 1/2), so no new swing low ever
# forms after bar 19 (Lows only increase from here on) and tr[t] has time to turn
# positive again for the short precondition.
#
# Bar 35: the SHORT decision bar, exact mirror of bar 20 -- bar 34 (bullish) is the
# container, bar 35 is strictly inside it and bearish.
#
# Bars 36-40: a short trailing downtrend. Not part of any signal; they exist only so
# assert_no_lookahead_v2's truncation windows (which start at n//2) extend far enough
# to include bar 35's decision in a non-trivial comparison.
OPENS = [
    1.0985,
    1.1000,
    1.1015,
    1.1030,
    1.1045,
    1.1060,
    1.1075,
    1.1090,
    1.1105,
    1.1120,
    1.1135,
    1.1115,
    1.1095,
    1.1075,
    1.1055,
    1.1035,
    1.1015,
    1.0995,
    1.0975,
    1.0955,
    1.0935,
    1.0945,
    1.0960,
    1.0975,
    1.0990,
    1.1005,
    1.1020,
    1.1035,
    1.1050,
    1.1065,
    1.1080,
    1.1095,
    1.1110,
    1.1125,
    1.1140,
    1.1155,
    1.1145,
    1.1130,
    1.1115,
    1.1100,
    1.1085,
]
HIGHS = [
    1.1002,
    1.1017,
    1.1032,
    1.1047,
    1.1062,
    1.1077,
    1.1092,
    1.1107,
    1.1122,
    1.1137,
    1.1136,
    1.1116,
    1.1096,
    1.1076,
    1.1056,
    1.1036,
    1.1016,
    1.0996,
    1.0976,
    1.0956,
    1.0946,
    1.0962,
    1.0977,
    1.0992,
    1.1007,
    1.1022,
    1.1037,
    1.1052,
    1.1067,
    1.1082,
    1.1097,
    1.1112,
    1.1127,
    1.1142,
    1.1157,
    1.1156,
    1.1146,
    1.1131,
    1.1116,
    1.1101,
    1.1086,
]
LOWS = [
    1.0983,
    1.0998,
    1.1013,
    1.1028,
    1.1043,
    1.1058,
    1.1073,
    1.1088,
    1.1103,
    1.1118,
    1.1113,
    1.1093,
    1.1073,
    1.1053,
    1.1033,
    1.1013,
    1.0993,
    1.0973,
    1.0953,
    1.0933,
    1.0934,
    1.0943,
    1.0958,
    1.0973,
    1.0988,
    1.1003,
    1.1018,
    1.1033,
    1.1048,
    1.1063,
    1.1078,
    1.1093,
    1.1108,
    1.1123,
    1.1138,
    1.1144,
    1.1128,
    1.1113,
    1.1098,
    1.1083,
    1.1068,
]
CLOSES = [
    1.1000,
    1.1015,
    1.1030,
    1.1045,
    1.1060,
    1.1075,
    1.1090,
    1.1105,
    1.1120,
    1.1135,
    1.1115,
    1.1095,
    1.1075,
    1.1055,
    1.1035,
    1.1015,
    1.0995,
    1.0975,
    1.0955,
    1.0935,
    1.0945,
    1.0960,
    1.0975,
    1.0990,
    1.1005,
    1.1020,
    1.1035,
    1.1050,
    1.1065,
    1.1080,
    1.1095,
    1.1110,
    1.1125,
    1.1140,
    1.1155,
    1.1145,
    1.1130,
    1.1115,
    1.1100,
    1.1085,
    1.1070,
]

assert len(OPENS) == len(HIGHS) == len(LOWS) == len(CLOSES) == 41


@pytest.fixture(scope="module")
def frames() -> dict:
    idx = pd.date_range("2020-01-01", periods=len(CLOSES), freq="D", tz="UTC")
    d1 = pd.DataFrame(
        {"Open": OPENS, "High": HIGHS, "Low": LOWS, "Close": CLOSES, "Volume": 1.0},
        index=idx,
    )
    # context_granularities: none (spec §2) -- the strategy only ever reads "D1".
    return {"D1": d1}


@pytest.fixture(scope="module")
def orders(frames) -> list:
    return list(InsideBarReversal().generate_orders(frames))


# ---------------------------------------------------------------------------
# 2 + 3. Expected values, computed by hand, then asserted
# ---------------------------------------------------------------------------


def test_emits_exactly_the_long_then_the_short(orders) -> None:
    """Rule: exactly one long (bar 20) then one short (bar 35); nothing else.

    Every other bar fails condition 3 (spec §4/§5): phases 1-3 are built so High is
    monotonic within each trend leg (uptrend) or Low is monotonic (downtrend), which
    makes the strict inside-bar test fail everywhere except the two constructed bars.
    """
    assert [str(o.decision_bar) for o in orders] == [
        "2020-01-21 00:00:00+00:00",  # bar 20
        "2020-02-05 00:00:00+00:00",  # bar 35
    ]
    assert [o.direction for o in orders] == [1, -1]


def test_long_order_matches_hand_computed_arithmetic(orders) -> None:
    """Long trade plan at bar 20, derived from the spec (§3, §4, §6, §7).

    tr[20] = mean(close[i] - close[i-10] for i in 16..20)   (spec §3)
      close16-close6 = 1.0995 - 1.1090 = -0.0095
      close17-close7 = 1.0975 - 1.1105 = -0.0130
      close18-close8 = 1.0955 - 1.1120 = -0.0165
      close19-close9 = 1.0935 - 1.1135 = -0.0200
      close20-close10 = 1.0945 - 1.1115 = -0.0170
      tr[20] = (-0.0095-0.0130-0.0165-0.0200-0.0170) / 5 = -0.0760 / 5 = -0.0152 < 0
      -> downtrend precondition holds (spec §4 cond. 1).

    Container bar 19: Close=1.0935 < Open=1.0955 -> bearish (spec §4 cond. 2).
    Inside bar 20 (strict, spec §4 cond. 3):
      High[20]=1.0946 < High[19]=1.0956 ; Low[20]=1.0934 > Low[19]=1.0933.
    Inside bar 20 colour (spec §4 cond. 4): Close=1.0945 > Open=1.0935 -> bullish.

    TP existence (spec §4 cond. 5): the only confirmed swing high by bar 20 is the
    phase-1 peak at bar 9 (High[9]=1.1137, left cond. High[9]=1.1137 > max(High[4..8])
    = 1.1122; confirms at bar 9+5=14 once High[10..14] <= 1.1137, which holds since
    the downtrend's highest subsequent High is High[10]=1.1136). 1.1137 > Close[20]
    = 1.0945, so the gate passes and it is the (only, hence nearest) TP candidate.

    Stop  (spec §6 long)  = Low[19]  = 1.0933
    TP1   (spec §7 long)  = High[9]  = 1.1137
    """
    o = orders[0]

    assert o.direction == 1
    assert o.entry == "market"
    assert o.entry_price is None
    assert o.stop.price == pytest.approx(1.0933, abs=1e-9)
    assert o.stop.move_to_breakeven_on is None  # spec §6: move_to_breakeven_on: none
    assert o.stop.trail_atr_multiple is None  # spec §6: trail: none

    assert [leg.label for leg in o.exits] == ["TP1"]
    assert [leg.fraction for leg in o.exits] == pytest.approx([1.0])
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)
    assert o.exits[0].price == pytest.approx(1.1137, abs=1e-9)

    assert o.expires_after_bars is None  # spec §4: expires_after_bars: null
    assert o.size_fraction == pytest.approx(1.0)


def test_short_order_matches_hand_computed_arithmetic(orders) -> None:
    """Short trade plan at bar 35, exact mirror (spec §3, §5, §6, §7).

    tr[35] = mean(close[i] - close[i-10] for i in 31..35)   (spec §3)
      close31-close21 = 1.1110 - 1.0960 = 0.0150
      close32-close22 = 1.1125 - 1.0975 = 0.0150
      close33-close23 = 1.1140 - 1.0990 = 0.0150
      close34-close24 = 1.1155 - 1.1005 = 0.0150
      close35-close25 = 1.1145 - 1.1020 = 0.0125
      tr[35] = (0.0150*4 + 0.0125) / 5 = 0.0725 / 5 = 0.0145 > 0
      -> uptrend precondition holds (spec §5 cond. 1).

    Container bar 34: Close=1.1155 > Open=1.1140 -> bullish (spec §5 cond. 2).
    Inside bar 35 (strict, spec §5 cond. 3):
      High[35]=1.1156 < High[34]=1.1157 ; Low[35]=1.1144 > Low[34]=1.1138.
    Inside bar 35 colour (spec §5 cond. 4): Close=1.1145 < Open=1.1155 -> bearish.

    TP existence (spec §5 cond. 5): the only confirmed swing low by bar 35 is the
    phase-2 trough at bar 19 (Low[19]=1.0933, left cond. Low[19]=1.0933 <
    min(Low[14..18])=1.0953; confirms at bar 19+5=24 once Low[20..24] >= 1.0933,
    which holds since phase 3 is monotonically rising from bar 20 onward). No lower
    low ever forms afterwards (Low is monotonic non-decreasing from bar 19 through
    bar 35), so 1.0933 stays the nearest confirmed level below Close[35]=1.1145.

    Stop  (spec §6 short) = High[34] = 1.1157
    TP1   (spec §7 short) = Low[19]  = 1.0933
    """
    o = orders[1]

    assert o.direction == -1
    assert o.entry == "market"
    assert o.entry_price is None
    assert o.stop.price == pytest.approx(1.1157, abs=1e-9)
    assert o.stop.move_to_breakeven_on is None
    assert o.stop.trail_atr_multiple is None

    assert [leg.label for leg in o.exits] == ["TP1"]
    assert [leg.fraction for leg in o.exits] == pytest.approx([1.0])
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)
    assert o.exits[0].price == pytest.approx(1.0933, abs=1e-9)

    assert o.expires_after_bars is None
    assert o.size_fraction == pytest.approx(1.0)


def test_tp_beyond_close_in_the_trade_direction(frames, orders) -> None:
    """Rule (spec §4/§5 cond. 5): the TP level must sit strictly beyond the decision
    close, in the trade direction -- the declarability/existence gate itself."""
    close = frames["D1"]["Close"]
    for o in orders:
        decision_close = float(close.loc[o.decision_bar])
        tp = o.exits[0].price
        if o.direction == 1:
            assert tp > decision_close
        else:
            assert tp < decision_close


# ---------------------------------------------------------------------------
# 4. The non-negotiable check
# ---------------------------------------------------------------------------


def test_strategy_is_free_of_lookahead(frames) -> None:
    """Every Wave-2 strategy must pass this on real data too."""
    assert_no_lookahead_v2(InsideBarReversal(), frames)
