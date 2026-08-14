"""GOLDEN FIXTURE for ``bb_midline_break`` (SPEC-bb_midline_break.md, CSV row 28).

Two hand-built 20-bar H4 series (40 literal OHLC bars in total), one engineered to
fire the long setup and one to fire its exact mirror short. The spec's condition 2
requires ``close > mid`` for a long and ``close < mid`` for a short, so a single
series cannot produce both (§5, mutual exclusivity) — hence two literals and two
tests, as the run brief permits.

Assertion -> spec rule map
--------------------------
* ``test_long_series_fires_once_at_the_breakout_bar``      §4.1-§4.5 (all five long gates)
* ``test_long_order_matches_hand_computed_arithmetic``     §4 entry type · §6 stop · §7 TP1
* ``test_short_series_fires_once_at_the_breakout_bar``     §5.1-§5.5 (all five short gates)
* ``test_short_order_matches_hand_computed_arithmetic``    §5 entry type · §6 stop · §7 TP1
* ``test_no_order_when_the_prior_band_touch_is_removed``   §4.1 (the touch is required)
* ``test_touch_on_the_breakout_bar_itself_does_not_count`` §9 / §10 #2 (the ``.shift(1)``)
* ``test_stop_is_static_with_no_breakeven_and_no_trail``   §6 (no buffer, no BE, no trail)
* ``test_market_entry_carries_no_level_and_never_expires`` §4/§5 entry type + expires=null
* ``test_r_geometry_holds_for_every_order``                §6 (R = |C-S| >= 0.75 x range) · §7
* ``test_metadata_matches_the_spec_scope``                 §2 scope · §3 indicators
* ``test_strategy_is_free_of_lookahead``                   hard rule 1 (both series)

Why these bars
--------------
Both series are built so that **exactly one bar in twenty clears the big-body gate**
(§4.3: ``body[t] > 1.5 x avg_body[t]``, window including t per §10 #10). Every bar
except the breakout bar has a body of 8 or 10 pips against an average body of 8-21
pips, so the "exactly one order" assertions are verifiable by hand without computing
a single band value on the quiet bars. The bands only have to be evaluated at the two
bars that matter (the touch bar 11 and the breakout bar 12), and that arithmetic is
worked out in the comments below.

The fixture subclasses the strategy to shrink ``BB_PERIOD`` and ``BODY_PERIOD`` from
20 to 5 — 20 bars cannot warm a 20-period band. ``TOUCH_LOOKBACK``, ``BODY_MULTIPLE``,
``CLOSE_QUARTILE`` and ``TP_R_MULTIPLE`` are the production values, untouched: those
are logic, not lookback. ``warmup_bars`` is derived (``BB_PERIOD + TOUCH_LOOKBACK``),
so it follows the shrink to 10 automatically.
"""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import OrderIntent, assert_no_lookahead_v2
from src.layer0.strategies.research.bb_midline_break import BollingerMidlineBreak

# ---------------------------------------------------------------------------
# 1. The bars, and why these bars
# ---------------------------------------------------------------------------
# LONG series — (Open, High, Low, Close), 20 H4 bars starting 2020-01-01 00:00 UTC.
#
# Bars 0-10: a textbook linear downtrend, 10 pips of close per bar, every candle an
#   8-pip bearish body with a 3-pip lower wick. For a 5-bar linear ramp of step d the
#   mid sits at close + 2d and the sample std (ddof=1, the pandas/inventory
#   convention, §10 #6) is sqrt(250) = 15.81 pips, so
#       lower[j] = close[j] + 20 - 31.62 = close[j] - 11.62 pips,
#   while low[j] = close[j] - 3 pips. No bar here touches the lower band, and with
#   body = avg_body = 8 pips none of them can clear the 1.5x body gate either.
#
# Bar 11 (the TOUCH bar): a small 8-pip bearish body with a long 25-pip lower wick.
#   closes in its window (bars 7-11) = 1.1130 1.1120 1.1110 1.1100 1.1085
#       mid[11]   = 5.5545 / 5                       = 1.11090
#       devs (pips) = +21 +11 +1 -9 -24, sum sq      = 1220
#       std       = sqrt(1220 / 4) = sqrt(305)       = 17.4642 pips
#       lower[11] = 1.11090 - 2 x 0.00174642         = 1.10741
#       low[11]   = 1.10600  <=  1.10741             -> §4.1 TOUCH (14 pip margin)
#   body[11] = 8 pips vs avg_body[11] = 8 pips -> 8 > 12 is false, so bar 11 itself
#   emits nothing: the touch bar is never the breakout bar (§10 #2).
#
# Bar 12 (the BREAKOUT bar): a 65-pip bullish engulfing candle closing near its high.
#       §4.1 touch in {7..11}? bar 11 -> yes
#       closes in window (bars 8-12) = 1.1120 1.1110 1.1100 1.1085 1.1150
#       mid[12]   = 5.5565 / 5                       = 1.11130
#       §4.2 close[12] = 1.11500 > 1.11130 and close[11] = 1.10850 <= mid[11] 1.11090
#       §4.3 body[12] = |1.1150 - 1.1085| = 65 pips
#            avg_body[12] = (8 + 8 + 8 + 8 + 65) / 5 = 19.4 pips; 1.5 x 19.4 = 29.1
#            65 > 29.1 -> pass (the ONLY bar in the series that does)
#       §4.4 range = 1.1152 - 1.1080 = 72 pips; high - 0.25 x range = 1.11340
#            close 1.11500 >= 1.11340 -> top quartile
#       §4.5 close 1.1150 > open 1.1085 -> bullish
#
# Bars 13-19: gentle 10-pip follow-through. Bodies are 10 pips against average bodies
#   of 19.8 / 20.2 / 20.6 / 21.0 / 10 / 10 / 10 pips, so the 1.5x gate rejects every
#   one of them. They exist to prove the strategy does not re-fire while the trend
#   runs (§5 last paragraph: a cross cannot repeat on adjacent bars).
BARS_LONG: List[Tuple[float, float, float, float]] = [
    (1.1208, 1.1209, 1.1197, 1.1200),  # 0
    (1.1198, 1.1199, 1.1187, 1.1190),  # 1
    (1.1188, 1.1189, 1.1177, 1.1180),  # 2
    (1.1178, 1.1179, 1.1167, 1.1170),  # 3
    (1.1168, 1.1169, 1.1157, 1.1160),  # 4  bands first defined here
    (1.1158, 1.1159, 1.1147, 1.1150),  # 5
    (1.1148, 1.1149, 1.1137, 1.1140),  # 6
    (1.1138, 1.1139, 1.1127, 1.1130),  # 7
    (1.1128, 1.1129, 1.1117, 1.1120),  # 8
    (1.1118, 1.1119, 1.1107, 1.1110),  # 9
    (1.1108, 1.1109, 1.1097, 1.1100),  # 10 first bar past warmup (=10)
    (1.1093, 1.1095, 1.1060, 1.1085),  # 11 TOUCH: low 1.1060 <= lower 1.10741
    (1.1085, 1.1152, 1.1080, 1.1150),  # 12 BREAKOUT -> long
    (1.1150, 1.1165, 1.1148, 1.1160),  # 13
    (1.1160, 1.1175, 1.1158, 1.1170),  # 14
    (1.1170, 1.1185, 1.1168, 1.1180),  # 15
    (1.1180, 1.1195, 1.1178, 1.1190),  # 16
    (1.1190, 1.1205, 1.1188, 1.1200),  # 17
    (1.1200, 1.1215, 1.1198, 1.1210),  # 18
    (1.1210, 1.1225, 1.1208, 1.1220),  # 19
]

# SHORT series — the exact reflection of BARS_LONG about 1.1000
# (p -> 2.2000 - p, with High and Low swapped). A reflection leaves every rolling
# mean reflected and every rolling std unchanged, so mid' = 2.2000 - mid,
# upper' = 2.2000 - lower, and each long inequality becomes its short mirror with the
# identical margin. That makes §5.1-§5.5 checkable from the §4 arithmetic above:
#       upper[11] = 2.2000 - 1.10741 = 1.09259 ; high[11] = 1.09400 >= it -> §5.1 TOUCH
#       mid[12]   = 2.2000 - 1.11130 = 1.08870 ; close[12] = 1.08500 < it -> §5.2
#       mid[11]   = 2.2000 - 1.11090 = 1.08910 ; close[11] = 1.09150 >= it -> §5.2
#       §5.3 body[12] = |1.0850 - 1.0915| = 65 pips vs 1.5 x 19.4 = 29.1 -> pass
#       §5.4 range = 1.0920 - 1.0848 = 72 pips; low + 0.25 x range = 1.08660
#            close 1.08500 <= 1.08660 -> bottom quartile
#       §5.5 close 1.0850 < open 1.0915 -> bearish
BARS_SHORT: List[Tuple[float, float, float, float]] = [
    (1.0792, 1.0803, 1.0791, 1.0800),  # 0
    (1.0802, 1.0813, 1.0801, 1.0810),  # 1
    (1.0812, 1.0823, 1.0811, 1.0820),  # 2
    (1.0822, 1.0833, 1.0821, 1.0830),  # 3
    (1.0832, 1.0843, 1.0831, 1.0840),  # 4
    (1.0842, 1.0853, 1.0841, 1.0850),  # 5
    (1.0852, 1.0863, 1.0851, 1.0860),  # 6
    (1.0862, 1.0873, 1.0861, 1.0870),  # 7
    (1.0872, 1.0883, 1.0871, 1.0880),  # 8
    (1.0882, 1.0893, 1.0881, 1.0890),  # 9
    (1.0892, 1.0903, 1.0891, 1.0900),  # 10
    (1.0907, 1.0940, 1.0905, 1.0915),  # 11 TOUCH: high 1.0940 >= upper 1.09259
    (1.0915, 1.0920, 1.0848, 1.0850),  # 12 BREAKOUT -> short
    (1.0850, 1.0852, 1.0835, 1.0840),  # 13
    (1.0840, 1.0842, 1.0825, 1.0830),  # 14
    (1.0830, 1.0832, 1.0815, 1.0820),  # 15
    (1.0820, 1.0822, 1.0805, 1.0810),  # 16
    (1.0810, 1.0812, 1.0795, 1.0800),  # 17
    (1.0800, 1.0802, 1.0785, 1.0790),  # 18
    (1.0790, 1.0792, 1.0775, 1.0780),  # 19
]

BREAKOUT_BAR = "2020-01-03 00:00:00+00:00"  # bar 12 = 2020-01-01 00:00 UTC + 48h


class _FixtureScale(BollingerMidlineBreak):
    """Production logic, fixture-sized lookbacks (periods only — never levels)."""

    BB_PERIOD = 5
    BODY_PERIOD = 5


def _frames(
    bars: Sequence[Tuple[float, float, float, float]],
) -> Dict[str, pd.DataFrame]:
    idx = pd.date_range("2020-01-01", periods=len(bars), freq="4h", tz="UTC")
    h4 = pd.DataFrame(
        {
            "Open": [b[0] for b in bars],
            "High": [b[1] for b in bars],
            "Low": [b[2] for b in bars],
            "Close": [b[3] for b in bars],
            "Volume": 1.0,
        },
        index=idx,
    )
    return {"H4": h4}


@pytest.fixture(scope="module")
def long_frames() -> Dict[str, pd.DataFrame]:
    return _frames(BARS_LONG)


@pytest.fixture(scope="module")
def short_frames() -> Dict[str, pd.DataFrame]:
    return _frames(BARS_SHORT)


@pytest.fixture(scope="module")
def long_orders(long_frames: Dict[str, pd.DataFrame]) -> List[OrderIntent]:
    return list(_FixtureScale().generate_orders(long_frames))


@pytest.fixture(scope="module")
def short_orders(short_frames: Dict[str, pd.DataFrame]) -> List[OrderIntent]:
    return list(_FixtureScale().generate_orders(short_frames))


# ---------------------------------------------------------------------------
# 2 + 3. Expected values, computed by hand from the spec, then asserted
# ---------------------------------------------------------------------------


def test_long_series_fires_once_at_the_breakout_bar(
    long_orders: List[OrderIntent],
) -> None:
    """§4.1-§4.5: only bar 12 satisfies all five long conditions.

    Bar 11 is the touch bar and fails §4.3 (body 8 vs threshold 12). Bars 13-19 all
    fail §4.3 as well (body 10 vs thresholds 29.7 / 30.3 / 30.9 / 31.5 / 15 / 15 / 15
    pips), and bars 0-10 fail it with body = avg_body = 8 pips.
    """
    assert [str(o.decision_bar) for o in long_orders] == [BREAKOUT_BAR]
    assert [o.direction for o in long_orders] == [1]


def test_long_order_matches_hand_computed_arithmetic(
    long_orders: List[OrderIntent],
) -> None:
    """The whole trade plan for bar 12, derived from §4/§6/§7 — not from output.

    Bar 12 OHLC = (1.1085, 1.1152, 1.1080, 1.1150).

      §4  entry = market, entry_price = None (fill at the open of t+1, §10 #8)
          anchor C   = close[12]                        = 1.11500
      §6  stop  S    = low[12], zero buffer (§10 #5)    = 1.10800
          R          = |C - S| = 1.11500 - 1.10800      = 0.00700
      §7  TP1        = C + 1.5 x R = 1.11500 + 0.01050  = 1.12550
          fraction   = 1.0 (single full-size leg)
    """
    o = long_orders[0]

    assert o.direction == 1
    assert o.entry == "market"
    assert o.entry_price is None
    assert o.decision_close == pytest.approx(1.11500, abs=1e-9)
    assert o.stop.price == pytest.approx(1.10800, abs=1e-9)

    assert [leg.label for leg in o.exits] == ["TP1"]
    assert [leg.kind for leg in o.exits] == ["take_profit"]
    assert o.exits[0].price == pytest.approx(1.12550, abs=1e-9)
    assert o.exits[0].fraction == pytest.approx(1.0, abs=1e-9)


def test_short_series_fires_once_at_the_breakout_bar(
    short_orders: List[OrderIntent],
) -> None:
    """§5.1-§5.5: the mirror image — only bar 12 satisfies all five short conditions."""
    assert [str(o.decision_bar) for o in short_orders] == [BREAKOUT_BAR]
    assert [o.direction for o in short_orders] == [-1]


def test_short_order_matches_hand_computed_arithmetic(
    short_orders: List[OrderIntent],
) -> None:
    """The whole trade plan for bar 12 of the mirror series, from §5/§6/§7.

    Bar 12 OHLC = (1.0915, 1.0920, 1.0848, 1.0850).

      §5  entry = market, entry_price = None
          anchor C   = close[12]                        = 1.08500
      §6  stop  S    = high[12], zero buffer (§10 #5)   = 1.09200
          R          = |C - S| = 1.09200 - 1.08500      = 0.00700
      §7  TP1        = C - 1.5 x R = 1.08500 - 0.01050  = 1.07450
    """
    o = short_orders[0]

    assert o.direction == -1
    assert o.entry == "market"
    assert o.entry_price is None
    assert o.decision_close == pytest.approx(1.08500, abs=1e-9)
    assert o.stop.price == pytest.approx(1.09200, abs=1e-9)

    assert [leg.label for leg in o.exits] == ["TP1"]
    assert o.exits[0].price == pytest.approx(1.07450, abs=1e-9)
    assert o.exits[0].fraction == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Negative tests — the conditions that must be able to *stop* a trade
# ---------------------------------------------------------------------------


def test_no_order_when_the_prior_band_touch_is_removed() -> None:
    """§4.1: the band touch is a required gate, not decoration.

    One field changes from BARS_LONG: bar 11's low is lifted from 1.1060 to 1.1097
    (the same 3-pip wick the quiet bars have), so it no longer reaches
    lower[11] = 1.10741. Nothing else moves — the bands, bodies, the cross and the
    quartile test at bar 12 are all identical — so a strategy that ignored §4.1
    would still fire here.
    """
    bars = [list(b) for b in BARS_LONG]
    bars[11][2] = 1.1097
    frames = _frames([(b[0], b[1], b[2], b[3]) for b in bars])
    assert list(_FixtureScale().generate_orders(frames)) == []


def test_touch_on_the_breakout_bar_itself_does_not_count() -> None:
    """§9 / §10 #2: the 5-bar touch window is ``.shift(1)``ed, so bar t is excluded.

    Two fields change from BARS_LONG: bar 11's low is lifted to 1.1097 (no touch),
    and bar 12's low is dropped from 1.1080 to 1.1060 so that bar 12 now touches its
    OWN lower band:
        closes in window (bars 8-12) = 1.1120 1.1110 1.1100 1.1085 1.1150
        mid[12]   = 1.11130
        devs (pips) = +7 -3 -13 -28 +37, sum sq        = 2380
        std       = sqrt(2380 / 4) = sqrt(595)         = 24.3926 pips
        lower[12] = 1.11130 - 2 x 0.00243926           = 1.10642
        low[12]   = 1.10600 <= 1.10642                 -> bar 12 touches, at bar 12
    Bar 12 still clears §4.2-§4.5 (widening the range to 92 pips keeps the close in
    the top quartile: 1.1152 - 0.25 x 0.0092 = 1.11290 <= 1.11500). An
    implementation that allowed a same-bar touch would emit a long here. The correct
    one emits nothing.
    """
    bars = [list(b) for b in BARS_LONG]
    bars[11][2] = 1.1097
    bars[12][2] = 1.1060
    frames = _frames([(b[0], b[1], b[2], b[3]) for b in bars])
    assert list(_FixtureScale().generate_orders(frames)) == []


# ---------------------------------------------------------------------------
# Structural invariants that hold for every order the strategy can emit
# ---------------------------------------------------------------------------


def test_stop_is_static_with_no_breakeven_and_no_trail(
    long_orders: List[OrderIntent], short_orders: List[OrderIntent]
) -> None:
    """§6: ``move_to_breakeven_on: none``, ``trail_atr_multiple: null``, no buffer."""
    for o in long_orders + short_orders:
        assert o.stop.move_to_breakeven_on is None
        assert o.stop.trail_atr_multiple is None
        assert o.stop.breakeven_offset_pips == 0.0


def test_market_entry_carries_no_level_and_never_expires(
    long_orders: List[OrderIntent], short_orders: List[OrderIntent]
) -> None:
    """§4/§5: market entry, ``expires_after_bars`` null, no time exit, no reversal exit."""
    for o in long_orders + short_orders:
        assert o.entry == "market"
        assert o.entry_price is None
        assert o.expires_after_bars is None
        assert o.time_exit_after_bars is None
        assert o.close_on_opposite is False
        assert o.size_fraction == 1.0
        assert o.strategy_id == "bb_midline_break"


def test_r_geometry_holds_for_every_order(
    long_frames: Dict[str, pd.DataFrame],
    short_frames: Dict[str, pd.DataFrame],
    long_orders: List[OrderIntent],
    short_orders: List[OrderIntent],
) -> None:
    """§6 + §7: R = |C - S| measured from the decision close, TP1 at exactly 1.5R,
    fractions summing to 1.0, and the spec's stated floor R >= 0.75 x range[t]."""
    for frames, orders in ((long_frames, long_orders), (short_frames, short_orders)):
        bar = frames["H4"]
        for o in orders:
            row = bar.loc[o.decision_bar]
            close = float(row["Close"])
            bar_range = float(row["High"]) - float(row["Low"])
            expected_stop = (
                float(row["Low"]) if o.direction == 1 else float(row["High"])
            )

            assert o.decision_close == pytest.approx(close, abs=1e-12)
            assert o.stop.price == pytest.approx(expected_stop, abs=1e-12)

            risk = abs(close - o.stop.price)
            assert risk >= 0.75 * bar_range - 1e-12
            assert o.exits[0].price == pytest.approx(
                close + o.direction * 1.5 * risk, abs=1e-12
            )
            assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)


def test_metadata_matches_the_spec_scope() -> None:
    """§2 scope and §3 indicator inventory, plus the provenance the brief mandates."""
    meta = BollingerMidlineBreak().metadata

    assert meta.strategy_id == "bb_midline_break"
    assert meta.author == "wave2-fleet"
    assert meta.version == "0.1.0"
    assert meta.primary_granularity == "H4"
    assert tuple(meta.context_granularities) == ()  # §2: no context frame
    assert meta.simulate_on == "H1"  # §2 / contract Part D
    assert meta.source_row == 28
    assert meta.pairs == ["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"]
    # §3: no swing/pivot detection anywhere, so causal_structure is not required.
    assert BollingerMidlineBreak().required_indicators == ["bollinger_bands", "sma"]
    # warmup is derived from the two lookbacks, not chosen: 20 + 5.
    assert BollingerMidlineBreak().warmup_bars == 25


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
