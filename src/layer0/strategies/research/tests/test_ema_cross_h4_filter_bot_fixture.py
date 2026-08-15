"""GOLDEN FIXTURE for ``ema_cross_h4_filter_bot`` (SPEC row 41).

Two hand-built 40-bar H1 series (each with its own 10-bar H4 context frame), one
engineered to fire the long setup and one its exact mirror short. §4.2 demands a
bullish H4 regime for a long and §5.2 a bearish one for a short, so a single pair
of frames cannot produce both — hence two literals and two tests, as the run
brief permits.

Assertion -> spec rule map
--------------------------
* ``test_long_series_fires_once_at_the_cross_bar``        §4.1-§4.3 (all three long gates)
* ``test_long_order_matches_hand_computed_arithmetic``    §4 entry type · §6 stop · §7 TP1
* ``test_short_series_fires_once_at_the_cross_bar``       §5.1-§5.3 (all three short gates)
* ``test_short_order_matches_hand_computed_arithmetic``   §5 entry type · §6 stop · §7 TP1
* ``test_session_gate_blocks_a_cross_outside_the_window`` §4.3 / §8 (the clock filter)
* ``test_h4_regime_veto_blocks_a_counter_trend_cross``    §4.2 / §8 (the regime filter)
* ``test_only_the_closed_h4_bar_informs_the_decision``    §9 / §10 #5 (the MTF join)
* ``test_bracket_geometry_holds_for_every_order``         §6 stop · §7 TP · fractions
* ``test_metadata_matches_the_spec_scope``                §2 scope · §3 indicators
* ``test_strategy_is_free_of_lookahead``                  hard rule 1 (both series)

Why these bars
--------------
Every EMA in this spec is ``ewm(adjust=False)``, so a run of *identical* closes
pins both H1 EMAs to that exact value with no floating-point residue. The quiet
bars therefore make ``ema_fast == ema_slow`` **exactly**, and the single price
step at bar 32 is the only place any arithmetic has to be done — one step of the
recursion, by hand, shown below. Open/High/Low vary freely on the quiet bars
(the EMAs read Close only) so the series is still a legal OHLC frame.

The H4 context frame is a 10-pip-per-bar ramp, which under ``ewm(adjust=False)``
keeps Close strictly above (long) or below (short) the regime EMA at every bar
past the first. Its **last two bars deliberately flip the regime**: they are not
readable at the decision bar and exist so that an implementation reading an
unclosed context bar produces a different answer (§9, §10 #5).

The fixture subclasses the strategy to shrink the three EMA periods (9/21/200 ->
3/7/3) — 40 bars cannot warm a 200-period H4 EMA. ``STOP_PIPS``, ``TP_PIPS``,
the session hours and ``EXPIRY_BARS`` are production values, untouched: those are
logic, not lookback. ``warmup_bars`` is derived, so it follows the shrink to
``max(4 x 3, 3 x 7) = 21`` automatically.
"""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import OrderIntent, assert_no_lookahead_v2
from src.layer0.strategies.research.ema_cross_h4_filter_bot import EmaCrossH4FilterBot

Bar = Tuple[float, float, float, float]

# ---------------------------------------------------------------------------
# 1. The bars, and why these bars
# ---------------------------------------------------------------------------
# H1 LONG series — (Open, High, Low, Close), 40 bars from 2020-01-01 00:00 UTC.
# Bar i opens at 00:00 + i hours; the DECISION INSTANT is its close, i + 1 hours.
#
# Bars 0-31: Close pinned at 1.1000. With ewm(adjust=False) seeded on bar 0 that
#   makes ema3[j] = ema7[j] = 1.1000 for every j <= 31, so `fast > slow` and
#   `fast < slow` are both False and no bar here can be a cross (§4.1 / §5.1).
#   Highs and lows wander; only Close feeds the EMAs.
#
# Bar 32 (the CROSS bar) — opens 2020-01-02 08:00, decision instant 09:00 UTC:
#       Close steps to 1.1100. One step of the recursion, alpha = 2/(n+1):
#       ema3:  alpha = 0.5   -> 0.5   x 1.1100 + 0.5  x 1.1000 = 1.10500
#       ema7:  alpha = 0.25  -> 0.25  x 1.1100 + 0.75 x 1.1000 = 1.10250
#       §4.1  ema3[32] 1.10500 > ema7[32] 1.10250, and at bar 31 they were EQUAL
#             (1.1000 <= 1.1000) -> a fresh bullish cross exactly on bar 32.
#       §4.3  decision instant 09:00 UTC is inside [07:00, 21:00) -> admitted.
#       §4.2  see the H4 table below: the governing H4 bar is index 7, bullish.
#
# Bars 33-39: Close held at 1.1100. ema3 stays above ema7 (both rise toward
#   1.1100 with ema3 leading), so `fast[t-1] <= slow[t-1]` fails at every one of
#   them: the cross cannot re-fire while the move runs (§4.1 "fresh cross").
BARS_H1_LONG: List[Bar] = [
    (1.1000, 1.1004, 1.0996, 1.1000),  # 0
    (1.1000, 1.1005, 1.0995, 1.1000),  # 1
    (1.1000, 1.1003, 1.0997, 1.1000),  # 2
    (1.1000, 1.1006, 1.0994, 1.1000),  # 3
    (1.1000, 1.1004, 1.0996, 1.1000),  # 4
    (1.1000, 1.1002, 1.0998, 1.1000),  # 5
    (1.1000, 1.1005, 1.0995, 1.1000),  # 6
    (1.1000, 1.1004, 1.0996, 1.1000),  # 7
    (1.1000, 1.1003, 1.0997, 1.1000),  # 8
    (1.1000, 1.1006, 1.0994, 1.1000),  # 9
    (1.1000, 1.1004, 1.0996, 1.1000),  # 10
    (1.1000, 1.1002, 1.0998, 1.1000),  # 11
    (1.1000, 1.1005, 1.0995, 1.1000),  # 12
    (1.1000, 1.1004, 1.0996, 1.1000),  # 13
    (1.1000, 1.1003, 1.0997, 1.1000),  # 14
    (1.1000, 1.1006, 1.0994, 1.1000),  # 15
    (1.1000, 1.1004, 1.0996, 1.1000),  # 16
    (1.1000, 1.1002, 1.0998, 1.1000),  # 17
    (1.1000, 1.1005, 1.0995, 1.1000),  # 18
    (1.1000, 1.1004, 1.0996, 1.1000),  # 19
    (1.1000, 1.1003, 1.0997, 1.1000),  # 20
    (1.1000, 1.1006, 1.0994, 1.1000),  # 21  first bar past warmup (=21)
    (1.1000, 1.1004, 1.0996, 1.1000),  # 22
    (1.1000, 1.1002, 1.0998, 1.1000),  # 23
    (1.1000, 1.1005, 1.0995, 1.1000),  # 24
    (1.1000, 1.1004, 1.0996, 1.1000),  # 25
    (1.1000, 1.1003, 1.0997, 1.1000),  # 26
    (1.1000, 1.1006, 1.0994, 1.1000),  # 27
    (1.1000, 1.1004, 1.0996, 1.1000),  # 28
    (1.1000, 1.1002, 1.0998, 1.1000),  # 29
    (1.1000, 1.1005, 1.0995, 1.1000),  # 30
    (1.1000, 1.1004, 1.0996, 1.1000),  # 31
    (1.1000, 1.1105, 1.0998, 1.1100),  # 32 CROSS -> long
    (1.1100, 1.1104, 1.1096, 1.1100),  # 33
    (1.1100, 1.1105, 1.1095, 1.1100),  # 34
    (1.1100, 1.1103, 1.1097, 1.1100),  # 35
    (1.1100, 1.1106, 1.1094, 1.1100),  # 36
    (1.1100, 1.1104, 1.1096, 1.1100),  # 37
    (1.1100, 1.1102, 1.1098, 1.1100),  # 38
    (1.1100, 1.1105, 1.1095, 1.1100),  # 39
]

# H4 BULLISH context — 10 bars from 2020-01-01 00:00 UTC, four hours apart.
# ema3 (alpha = 0.5), by hand:
#       e0 = 1.1000                                 close 1.1000  (seed, flat)
#       e1 = 0.5 x (1.1010 + 1.1000)   = 1.10050    close 1.1010  > e1
#       e2 = 0.5 x (1.1020 + 1.10050)  = 1.101250   close 1.1020  > e2
#       e3 = 0.5 x (1.1030 + 1.101250) = 1.102125   close 1.1030  > e3
#       e4 = 0.5 x (1.1040 + 1.102125) = 1.1030625  close 1.1040  > e4
#       e5 = 0.5 x (1.1050 + 1.1030625)  = 1.10403125    close 1.1050 > e5
#       e6 = 0.5 x (1.1060 + 1.10403125) = 1.105015625   close 1.1060 > e6
#       e7 = 0.5 x (1.1070 + 1.105015625) = 1.1060078125 close 1.1070 > e7 -> BULLISH
#       e8 = 0.5 x (1.0900 + 1.1060078125) = 1.09800390625 close 1.0900 < e8 -> BEARISH
# H1 bar 32 opens 2020-01-02 08:00. §9: the governing H4 bar T needs T + 4h <= t,
# so T <= 2020-01-02 04:00 -> index 7, which is BULLISH. Index 8 opens at exactly
# 2020-01-02 08:00 and does not close until 12:00; it is bearish precisely so that
# an implementation reading `h4.index <= t` would veto the long and fail this file.
H4_CLOSES_BULL: List[float] = [
    1.1000,  # 0
    1.1010,  # 1
    1.1020,  # 2
    1.1030,  # 3
    1.1040,  # 4
    1.1050,  # 5
    1.1060,  # 6
    1.1070,  # 7  <- governs the decision at H1 bar 32
    1.0900,  # 8  <- NOT closed at the decision; bearish on purpose
    1.0910,  # 9
]

# H1 SHORT series — identical construction, stepping DOWN at bar 32.
#       ema3[32] = 0.5  x 1.0900 + 0.5  x 1.1000 = 1.09500
#       ema7[32] = 0.25 x 1.0900 + 0.75 x 1.1000 = 1.09750
#       §5.1  ema3 1.09500 < ema7 1.09750, equal at bar 31 -> fresh bearish cross.
BARS_H1_SHORT: List[Bar] = [
    (b[0], b[1], b[2], b[3]) for b in BARS_H1_LONG[:32]
] + [
    (1.1000, 1.1002, 1.0895, 1.0900),  # 32 CROSS -> short
    (1.0900, 1.0904, 1.0896, 1.0900),  # 33
    (1.0900, 1.0905, 1.0895, 1.0900),  # 34
    (1.0900, 1.0903, 1.0897, 1.0900),  # 35
    (1.0900, 1.0906, 1.0894, 1.0900),  # 36
    (1.0900, 1.0904, 1.0896, 1.0900),  # 37
    (1.0900, 1.0902, 1.0898, 1.0900),  # 38
    (1.0900, 1.0905, 1.0895, 1.0900),  # 39
]

# H4 BEARISH context — the descending mirror. ema3 by hand:
#       e1 = 0.5 x (1.0990 + 1.1000)      = 1.09950        close 1.0990 < e1
#       e2 = 0.5 x (1.0980 + 1.09950)     = 1.098750       close 1.0980 < e2
#       e3 = 0.5 x (1.0970 + 1.098750)    = 1.0978750      close 1.0970 < e3
#       e4 = 0.5 x (1.0960 + 1.0978750)   = 1.0969375      close 1.0960 < e4
#       e5 = 0.5 x (1.0950 + 1.0969375)   = 1.09596875     close 1.0950 < e5
#       e6 = 0.5 x (1.0940 + 1.09596875)  = 1.094984375    close 1.0940 < e6
#       e7 = 0.5 x (1.0930 + 1.094984375) = 1.0939921875   close 1.0930 < e7 -> BEARISH
#       e8 = 0.5 x (1.1100 + 1.0939921875) = 1.10199609375 close 1.1100 > e8 -> BULLISH
H4_CLOSES_BEAR: List[float] = [
    1.1000,  # 0
    1.0990,  # 1
    1.0980,  # 2
    1.0970,  # 3
    1.0960,  # 4
    1.0950,  # 5
    1.0940,  # 6
    1.0930,  # 7  <- governs the decision at H1 bar 32
    1.1100,  # 8  <- NOT closed at the decision; bullish on purpose
    1.1090,  # 9
]

CROSS_BAR = "2020-01-02 08:00:00+00:00"  # H1 bar 32 = 2020-01-01 00:00 + 32h


class _FixtureScale(EmaCrossH4FilterBot):
    """Production logic, fixture-sized lookbacks (periods only — never levels)."""

    EMA_FAST_PERIOD = 3
    EMA_SLOW_PERIOD = 7
    EMA_REGIME_PERIOD = 3


def _h4_frame(closes: Sequence[float]) -> pd.DataFrame:
    """An H4 frame whose Close drives the regime EMA; O/H/L bracket it by 5 pips."""
    idx = pd.date_range("2020-01-01", periods=len(closes), freq="4h", tz="UTC")
    return pd.DataFrame(
        {
            "Open": [c for c in closes],
            "High": [c + 0.0005 for c in closes],
            "Low": [c - 0.0005 for c in closes],
            "Close": list(closes),
            "Volume": 1.0,
        },
        index=idx,
    )


def _frames(bars: Sequence[Bar], h4_closes: Sequence[float]) -> Dict[str, pd.DataFrame]:
    idx = pd.date_range("2020-01-01", periods=len(bars), freq="1h", tz="UTC")
    h1 = pd.DataFrame(
        {
            "Open": [b[0] for b in bars],
            "High": [b[1] for b in bars],
            "Low": [b[2] for b in bars],
            "Close": [b[3] for b in bars],
            "Volume": 1.0,
        },
        index=idx,
    )
    return {"H1": h1, "H4": _h4_frame(h4_closes)}


@pytest.fixture(scope="module")
def long_frames() -> Dict[str, pd.DataFrame]:
    return _frames(BARS_H1_LONG, H4_CLOSES_BULL)


@pytest.fixture(scope="module")
def short_frames() -> Dict[str, pd.DataFrame]:
    return _frames(BARS_H1_SHORT, H4_CLOSES_BEAR)


@pytest.fixture(scope="module")
def long_orders(long_frames: Dict[str, pd.DataFrame]) -> List[OrderIntent]:
    return list(_FixtureScale().generate_orders(long_frames))


@pytest.fixture(scope="module")
def short_orders(short_frames: Dict[str, pd.DataFrame]) -> List[OrderIntent]:
    return list(_FixtureScale().generate_orders(short_frames))


# ---------------------------------------------------------------------------
# 2 + 3. Expected values, computed by hand from the spec, then asserted
# ---------------------------------------------------------------------------


def test_long_series_fires_once_at_the_cross_bar(
    long_orders: List[OrderIntent],
) -> None:
    """§4.1-§4.3: bar 32 is the only bar satisfying all three long gates.

    Bars 0-31 have ema3 == ema7 exactly, so no cross exists there at all; bars
    33-39 fail the freshness half of §4.1 because ema3 was already above ema7 at
    the previous bar.
    """
    assert [str(o.decision_bar) for o in long_orders] == [CROSS_BAR]
    assert [o.direction for o in long_orders] == [1]


def test_long_order_matches_hand_computed_arithmetic(
    long_orders: List[OrderIntent],
) -> None:
    """The whole trade plan for bar 32, derived from §4/§6/§7 — not from output.

    Bar 32 OHLC = (1.1000, 1.1105, 1.0998, 1.1100); pip = 0.0001 (non-JPY quote).

      §4  entry = market, entry_price = None (fill at the open of t+1, F1/F2)
          anchor C = close[32]                              = 1.11000
      §6  stop  = C - 50 pip  = 1.11000 - 0.00500           = 1.10500
      §7  TP1   = C + 100 pip = 1.11000 + 0.01000           = 1.12000
          fraction = 1.0 (single full-size leg, 1:2 RR)
      §4  expires_after_bars = 1
    """
    o = long_orders[0]

    assert o.direction == 1
    assert o.entry == "market"
    assert o.entry_price is None
    assert o.decision_close == pytest.approx(1.11000, abs=1e-12)
    assert o.stop.price == pytest.approx(1.10500, abs=1e-12)

    assert [leg.label for leg in o.exits] == ["TP1"]
    assert [leg.kind for leg in o.exits] == ["take_profit"]
    assert o.exits[0].price == pytest.approx(1.12000, abs=1e-12)
    assert o.exits[0].fraction == pytest.approx(1.0, abs=1e-9)
    assert o.expires_after_bars == 1


def test_short_series_fires_once_at_the_cross_bar(
    short_orders: List[OrderIntent],
) -> None:
    """§5.1-§5.3: the mirror — only bar 32 satisfies all three short gates."""
    assert [str(o.decision_bar) for o in short_orders] == [CROSS_BAR]
    assert [o.direction for o in short_orders] == [-1]


def test_short_order_matches_hand_computed_arithmetic(
    short_orders: List[OrderIntent],
) -> None:
    """The whole trade plan for bar 32 of the mirror series, from §5/§6/§7.

    Bar 32 OHLC = (1.1000, 1.1002, 1.0895, 1.0900); pip = 0.0001.

      §5  entry = market, entry_price = None
          anchor C = close[32]                              = 1.09000
      §6  stop  = C + 50 pip  = 1.09000 + 0.00500           = 1.09500
      §7  TP1   = C - 100 pip = 1.09000 - 0.01000           = 1.08000
    """
    o = short_orders[0]

    assert o.direction == -1
    assert o.entry == "market"
    assert o.entry_price is None
    assert o.decision_close == pytest.approx(1.09000, abs=1e-12)
    assert o.stop.price == pytest.approx(1.09500, abs=1e-12)

    assert [leg.label for leg in o.exits] == ["TP1"]
    assert o.exits[0].price == pytest.approx(1.08000, abs=1e-12)
    assert o.exits[0].fraction == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Negative tests — the gates that must be able to *stop* a trade
# ---------------------------------------------------------------------------


def test_session_gate_blocks_a_cross_outside_the_window() -> None:
    """§4.3 / §8: the decision instant must be in [07:00, 21:00) UTC.

    The identical price step is moved from bar 32 to bar 26, which opens
    2020-01-02 02:00 and therefore decides at 03:00 UTC — outside the window.
    Everything else is unchanged: bar 26 is past warmup (21), ema3/ema7 are still
    equal on bar 25, and the governing H4 bar for a 02:00 decision is index 5
    (2020-01-01 20:00, closing 2020-01-02 00:00), whose close 1.1050 sits above
    e5 = 1.10403125, so the regime filter would have admitted it. Only the clock
    stops this trade, and bars 27-39 cannot re-cross.
    """
    bars = list(BARS_H1_LONG[:26])
    bars.append((1.1000, 1.1105, 1.0998, 1.1100))  # the step, now at bar 26
    bars += [(1.1100, 1.1104, 1.1096, 1.1100)] * 13  # bars 27-39, flat at 1.1100
    frames = _frames(bars, H4_CLOSES_BULL)
    assert list(_FixtureScale().generate_orders(frames)) == []


def test_h4_regime_veto_blocks_a_counter_trend_cross() -> None:
    """§4.2 / §8: a bullish H1 cross in a bearish H4 regime is skipped.

    The long H1 series is paired with the descending H4 frame, whose governing
    bar (index 7, close 1.0930 vs e7 = 1.0939921875) is bearish. Nothing about
    the H1 cross changes, so an implementation ignoring §4.2 would still fire.
    """
    frames = _frames(BARS_H1_LONG, H4_CLOSES_BEAR)
    assert list(_FixtureScale().generate_orders(frames)) == []


def test_only_the_closed_h4_bar_informs_the_decision() -> None:
    """§9 / §10 #5: the governing H4 bar is the last one with ``T + 4h <= t``.

    H4 index 7 is made BEARISH and index 8 BULLISH:
        e6 = 1.105015625 (unchanged)
        e7 = 0.5 x (1.0950 + 1.105015625)  = 1.1000078125 ; close 1.0950 < e7
        e8 = 0.5 x (1.1200 + 1.1000078125) = 1.11000390625; close 1.1200 > e8
    H1 bar 32 opens 2020-01-02 08:00, exactly when H4 index 8 opens — that bar
    does not close until 12:00 and must not be read. The correct join uses index
    7 and vetoes the long; an implementation using ``h4.index <= t`` would read
    index 8, see a bullish regime and emit an order. Zero orders is the pass.
    """
    h4 = list(H4_CLOSES_BULL)
    h4[7] = 1.0950
    h4[8] = 1.1200
    h4[9] = 1.1210
    frames = _frames(BARS_H1_LONG, h4)
    assert list(_FixtureScale().generate_orders(frames)) == []


# ---------------------------------------------------------------------------
# Structural invariants that hold for every order the strategy can emit
# ---------------------------------------------------------------------------


def test_bracket_geometry_holds_for_every_order(
    long_frames: Dict[str, pd.DataFrame],
    short_frames: Dict[str, pd.DataFrame],
    long_orders: List[OrderIntent],
    short_orders: List[OrderIntent],
) -> None:
    """§6 + §7: a static 50-pip stop and a 100-pip target, both measured from the
    decision-bar close, with exit fractions summing to 1.0 and no trail/breakeven."""
    for frames, orders in ((long_frames, long_orders), (short_frames, short_orders)):
        h1 = frames["H1"]
        for o in orders:
            close = float(h1.loc[o.decision_bar, "Close"])
            assert o.decision_close == pytest.approx(close, abs=1e-12)
            # pip = 0.0001 for every quote in this fixture (all well under 20.0).
            assert o.stop.price == pytest.approx(close - o.direction * 0.0050, abs=1e-12)
            assert o.exits[0].price == pytest.approx(
                close + o.direction * 0.0100, abs=1e-12
            )
            assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)
            # §6: static stop — no breakeven move, no trail, no offset.
            assert o.stop.move_to_breakeven_on is None
            assert o.stop.trail_atr_multiple is None
            assert o.stop.breakeven_offset_pips == 0.0
            # §10 #8/#9: no time exit, no reversal exit, no sizing.
            assert o.time_exit_after_bars is None
            assert o.close_on_opposite is False
            assert o.size_fraction == 1.0
            assert o.strategy_id == "ema_cross_h4_filter_bot"


def test_metadata_matches_the_spec_scope() -> None:
    """§2 scope and §3 indicator inventory, plus the provenance the brief mandates."""
    strat = EmaCrossH4FilterBot()
    meta = strat.metadata

    assert meta.strategy_id == "ema_cross_h4_filter_bot"
    assert meta.author == "wave2-fleet"
    assert meta.version == "0.1.0"
    assert meta.primary_granularity == "H1"
    assert tuple(meta.context_granularities) == ("H4",)  # §2 — the regime filter
    assert meta.simulate_on == "H1"
    assert meta.source_row == 41
    # §2 pairs_available, live only — the pending Wave-1 additions are excluded.
    assert meta.pairs == ["EUR_USD", "GBP_USD", "USD_JPY", "USD_CAD", "AUD_USD"]
    # §3: no swing/pivot detection anywhere, so causal_structure is not required.
    assert strat.required_indicators == ["ema"]
    # warmup is derived from the periods, not chosen: max(4 x 200, 3 x 21).
    assert strat.warmup_bars == 800


# ---------------------------------------------------------------------------
# 4. The non-negotiable check
# ---------------------------------------------------------------------------


def test_strategy_is_free_of_lookahead(
    long_frames: Dict[str, pd.DataFrame], short_frames: Dict[str, pd.DataFrame]
) -> None:
    """Hard rule 1. Both series fire, so the probe re-emits at a real firing bar
    rather than comparing emptiness to emptiness (contract FIX-S1-013 path)."""
    assert_no_lookahead_v2(_FixtureScale(), long_frames)
    assert_no_lookahead_v2(_FixtureScale(), short_frames)
