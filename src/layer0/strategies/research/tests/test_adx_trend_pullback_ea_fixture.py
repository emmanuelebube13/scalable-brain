"""GOLDEN FIXTURE — ``adx_trend_pullback_ea`` (spec row 38).

Two hand-built 46-bar H1 series, written out as literals below. The second is
the exact price reflection of the first about 1.10000 (``P' = 2.20000 - P``,
High and Low swapped), which flips ``+DI``/``-DI`` and leaves ADX, ATR and
``dist`` untouched — so the same setup fires short at the same bar with mirrored
levels. That is what makes one hand-computed arithmetic block cover both sides.

Every bar in both series is engineered so that
``High - Low == 0.00100`` **and** the previous bar's Close lies inside
``[Low, High]``. Then ``TR(j) = max(H-L, |H-C(j-1)|, |L-C(j-1)|) = 0.00100``
for every bar, and an EMA of a constant series is that constant, so

    **ATR14(k) = 0.00100 exactly, on every bar.**

That is the whole reason the bars look like this: it makes the spec's §6/§7
geometry (``2 × ATR`` and ``4 × ATR`` from the decision close) exact decimal
arithmetic instead of a floating-point reconstruction of a 14-bar ewm.

Shape of the long series (bar indices are 0-based positions):

* bars 0-15  — a ±2-pip sawtooth. Alternating higher-high / lower-low bars keep
  BOTH smoothed +DM and -DM positive, which drags ADX down out of the 100 it
  starts at. This is the only way to make "ADX rising" a real test later: with a
  one-sided series ``DX == 100`` on every bar and ADX pins at 100, where
  ``ADX(k) > ADX(k-1)`` can never hold. Price stays within ~2 pips of EMA20,
  so ``dist`` never approaches 1.
* bars 16-30 — a clean +0.5-pip/bar ramp: every bar makes a higher high AND a
  higher low, so ``-DM = 0``, ``DX -> 100`` and ADX climbs monotonically
  (mid-30s at bar 16, ~62 at bar 32) — clearing 25 and rising at the decision
  bar. A 0.5-pip slope holds ``dist`` at ~0.40, well clear of the arm.
* bar 31    — the impulse: Close jumps +9 pips to 1.10185, stretching price to
  ``dist = 1.1717 >= 1.0``. **This arms the pullback.** The bar still makes a
  higher high and a higher low, so the trend filter stays open.
* bar 32    — the release: the bar shifts further up (higher high, higher low →
  ``+DM > 0``, ``-DM = 0``, ADX still rising) while Close slips back 2 pips to
  1.10165, and EMA20 catches up 1 pip. ``dist`` falls to 0.8791 < 1.0.
  **All five conditions hold → the one and only order fires here.**
* bars 33-45 — the ramp resumes; ``dist`` decays from 0.84 and never re-arms, so
  no second setup exists.

``dist`` is >= 1.0 at exactly one bar (31) in the whole series, which is what
makes the expected order list provably a single element: §4.3 can only be
satisfied at bar 32.

Assertion → spec-rule map is at the bottom of the file.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.adx_trend_pullback_ea import AdxTrendPullbackEa

# ---------------------------------------------------------------------------
# 1. The bars, and why these bars (see the module docstring)
#    (Open, High, Low, Close). Open = previous Close, so the series is gapless.
# ---------------------------------------------------------------------------

BARS_LONG: List[Tuple[float, float, float, float]] = [
    (1.10000, 1.10050, 1.09950, 1.10000),  # 0  sawtooth: ADX must fall off 100
    (1.10000, 1.10070, 1.09970, 1.10020),  # 1
    (1.10020, 1.10050, 1.09950, 1.10000),  # 2
    (1.10000, 1.10070, 1.09970, 1.10020),  # 3
    (1.10020, 1.10050, 1.09950, 1.10000),  # 4
    (1.10000, 1.10070, 1.09970, 1.10020),  # 5
    (1.10020, 1.10050, 1.09950, 1.10000),  # 6
    (1.10000, 1.10070, 1.09970, 1.10020),  # 7
    (1.10020, 1.10050, 1.09950, 1.10000),  # 8
    (1.10000, 1.10070, 1.09970, 1.10020),  # 9
    (1.10020, 1.10050, 1.09950, 1.10000),  # 10
    (1.10000, 1.10070, 1.09970, 1.10020),  # 11
    (1.10020, 1.10050, 1.09950, 1.10000),  # 12
    (1.10000, 1.10070, 1.09970, 1.10020),  # 13
    (1.10020, 1.10050, 1.09950, 1.10000),  # 14
    (1.10000, 1.10070, 1.09970, 1.10020),  # 15
    (1.10020, 1.10075, 1.09975, 1.10025),  # 16 clean ramp starts: ADX rises
    (1.10025, 1.10080, 1.09980, 1.10030),  # 17
    (1.10030, 1.10085, 1.09985, 1.10035),  # 18
    (1.10035, 1.10090, 1.09990, 1.10040),  # 19
    (1.10040, 1.10095, 1.09995, 1.10045),  # 20
    (1.10045, 1.10100, 1.10000, 1.10050),  # 21
    (1.10050, 1.10105, 1.10005, 1.10055),  # 22
    (1.10055, 1.10110, 1.10010, 1.10060),  # 23
    (1.10060, 1.10115, 1.10015, 1.10065),  # 24
    (1.10065, 1.10120, 1.10020, 1.10070),  # 25
    (1.10070, 1.10125, 1.10025, 1.10075),  # 26
    (1.10075, 1.10130, 1.10030, 1.10080),  # 27
    (1.10080, 1.10135, 1.10035, 1.10085),  # 28
    (1.10085, 1.10140, 1.10040, 1.10090),  # 29
    (1.10090, 1.10145, 1.10045, 1.10095),  # 30
    (1.10095, 1.10190, 1.10090, 1.10185),  # 31 impulse -> dist 1.1717 (ARM)
    (1.10185, 1.10215, 1.10115, 1.10165),  # 32 release -> dist 0.8791 (FIRE)
    (1.10165, 1.10220, 1.10120, 1.10170),  # 33 ramp resumes; dist decays
    (1.10170, 1.10225, 1.10125, 1.10175),  # 34
    (1.10175, 1.10230, 1.10130, 1.10180),  # 35
    (1.10180, 1.10235, 1.10135, 1.10185),  # 36
    (1.10185, 1.10240, 1.10140, 1.10190),  # 37
    (1.10190, 1.10245, 1.10145, 1.10195),  # 38
    (1.10195, 1.10250, 1.10150, 1.10200),  # 39
    (1.10200, 1.10255, 1.10155, 1.10205),  # 40
    (1.10205, 1.10260, 1.10160, 1.10210),  # 41
    (1.10210, 1.10265, 1.10165, 1.10215),  # 42
    (1.10215, 1.10270, 1.10170, 1.10220),  # 43
    (1.10220, 1.10275, 1.10175, 1.10225),  # 44
    (1.10225, 1.10280, 1.10180, 1.10230),  # 45
]

# The exact reflection: Open' = 2.20000 - Open, High' = 2.20000 - Low,
# Low' = 2.20000 - High, Close' = 2.20000 - Close. Written out rather than
# computed so the bars remain a literal a reviewer can read.
BARS_SHORT: List[Tuple[float, float, float, float]] = [
    (1.10000, 1.10050, 1.09950, 1.10000),  # 0
    (1.10000, 1.10030, 1.09930, 1.09980),  # 1
    (1.09980, 1.10050, 1.09950, 1.10000),  # 2
    (1.10000, 1.10030, 1.09930, 1.09980),  # 3
    (1.09980, 1.10050, 1.09950, 1.10000),  # 4
    (1.10000, 1.10030, 1.09930, 1.09980),  # 5
    (1.09980, 1.10050, 1.09950, 1.10000),  # 6
    (1.10000, 1.10030, 1.09930, 1.09980),  # 7
    (1.09980, 1.10050, 1.09950, 1.10000),  # 8
    (1.10000, 1.10030, 1.09930, 1.09980),  # 9
    (1.09980, 1.10050, 1.09950, 1.10000),  # 10
    (1.10000, 1.10030, 1.09930, 1.09980),  # 11
    (1.09980, 1.10050, 1.09950, 1.10000),  # 12
    (1.10000, 1.10030, 1.09930, 1.09980),  # 13
    (1.09980, 1.10050, 1.09950, 1.10000),  # 14
    (1.10000, 1.10030, 1.09930, 1.09980),  # 15
    (1.09980, 1.10025, 1.09925, 1.09975),  # 16
    (1.09975, 1.10020, 1.09920, 1.09970),  # 17
    (1.09970, 1.10015, 1.09915, 1.09965),  # 18
    (1.09965, 1.10010, 1.09910, 1.09960),  # 19
    (1.09960, 1.10005, 1.09905, 1.09955),  # 20
    (1.09955, 1.10000, 1.09900, 1.09950),  # 21
    (1.09950, 1.09995, 1.09895, 1.09945),  # 22
    (1.09945, 1.09990, 1.09890, 1.09940),  # 23
    (1.09940, 1.09985, 1.09885, 1.09935),  # 24
    (1.09935, 1.09980, 1.09880, 1.09930),  # 25
    (1.09930, 1.09975, 1.09875, 1.09925),  # 26
    (1.09925, 1.09970, 1.09870, 1.09920),  # 27
    (1.09920, 1.09965, 1.09865, 1.09915),  # 28
    (1.09915, 1.09960, 1.09860, 1.09910),  # 29
    (1.09910, 1.09955, 1.09855, 1.09905),  # 30
    (1.09905, 1.09910, 1.09810, 1.09815),  # 31 impulse down (ARM)
    (1.09815, 1.09885, 1.09785, 1.09835),  # 32 release (FIRE, short)
    (1.09835, 1.09880, 1.09780, 1.09830),  # 33
    (1.09830, 1.09875, 1.09775, 1.09825),  # 34
    (1.09825, 1.09870, 1.09770, 1.09820),  # 35
    (1.09820, 1.09865, 1.09765, 1.09815),  # 36
    (1.09815, 1.09860, 1.09760, 1.09810),  # 37
    (1.09810, 1.09855, 1.09755, 1.09805),  # 38
    (1.09805, 1.09850, 1.09750, 1.09800),  # 39
    (1.09800, 1.09845, 1.09745, 1.09795),  # 40
    (1.09795, 1.09840, 1.09740, 1.09790),  # 41
    (1.09790, 1.09835, 1.09735, 1.09785),  # 42
    (1.09785, 1.09830, 1.09730, 1.09780),  # 43
    (1.09780, 1.09825, 1.09725, 1.09775),  # 44
    (1.09775, 1.09820, 1.09720, 1.09770),  # 45
]

START = "2024-03-04"  # a Monday; bar 32 is therefore 2024-03-05 08:00 UTC
DECISION_BAR = pd.Timestamp("2024-03-05 08:00:00", tz="UTC")

# ---------------------------------------------------------------------------
# 2. Expected values, computed by hand from the SPEC
# ---------------------------------------------------------------------------
# ATR14(32) = 0.00100 (constant-TR construction, see module docstring).
#
# EMA20 (inventory `ema` = span-20, adjust=False):
#   EMA(j) = EMA(j-1) + (2/21) * (Close(j) - EMA(j-1)),  EMA(0) = 1.10000
#   Rolling that recursion over bars 0-30 gives EMA(30) = 1.1005550.
#   EMA(31) = 1.1005550 + 0.0952381 * (1.10185 - 1.1005550)
#           = 1.1005550 + 0.0952381 * 0.0012950 = 1.1006783
#   EMA(32) = 1.1006783 + 0.0952381 * (1.10165 - 1.1006783)
#           = 1.1006783 + 0.0952381 * 0.0009717 = 1.1007709
#
# §4.3 arm    dist(31) = |1.10185 - 1.1006783| / 0.00100 = 1.171698 >= 1.0  OK
#   (the EMA chain above is shown rounded to 7 dp at each step; carried at full
#   precision the quotient is 1.1716979..., which is the value asserted below.
#   Corrected from 1.17167 by the orchestrator — a rounding slip in the final
#   division, not a disagreement about the rule. The 1e-5 tolerance is unchanged.)
# §4.4 release dist(32) = |1.10165 - 1.1007709| / 0.00100 = 0.879155 < 1.0  OK
#   (same rounding note as above; full precision gives 0.8791552...)
#   (and dist < 1.0 at every other bar, so bar 32 is the only possible fire)
#
# §6 stop  (long)  = Close(32) - 2.0 * ATR14(32) = 1.10165 - 0.00200 = 1.09965
# §7 TP1   (long)  = Close(32) + 4.0 * ATR14(32) = 1.10165 + 0.00400 = 1.10565
#   R_declared = 2.0 * 0.00100 = 0.00200; TP distance = rr * R = 2.0 * 0.00200
#   = 0.00400, i.e. 4.0 * ATR from the decision-bar close anchor.
#
# Mirror (short series, Close(32)' = 2.20000 - 1.10165 = 1.09835):
# §6 stop  (short) = 1.09835 + 0.00200 = 1.10035
# §7 TP1   (short) = 1.09835 - 0.00400 = 1.09435
EXPECTED_LONG_CLOSE = 1.10165
EXPECTED_LONG_STOP = 1.09965
EXPECTED_LONG_TP = 1.10565
EXPECTED_SHORT_CLOSE = 1.09835
EXPECTED_SHORT_STOP = 1.10035
EXPECTED_SHORT_TP = 1.09435

EXPECTED_ATR = 0.00100
EXPECTED_DIST_ARM = 1.171698  # bar 31, spec §4.3
EXPECTED_DIST_RELEASE = 0.879155  # bar 32, spec §4.4


def _frame(bars: List[Tuple[float, float, float, float]]) -> pd.DataFrame:
    idx = pd.date_range(START, periods=len(bars), freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "Open": [b[0] for b in bars],
            "High": [b[1] for b in bars],
            "Low": [b[2] for b in bars],
            "Close": [b[3] for b in bars],
            "Volume": 1.0,
        },
        index=idx,
    )


@pytest.fixture(scope="module")
def long_frames() -> Dict[str, pd.DataFrame]:
    return {"H1": _frame(BARS_LONG)}


@pytest.fixture(scope="module")
def short_frames() -> Dict[str, pd.DataFrame]:
    return {"H1": _frame(BARS_SHORT)}


@pytest.fixture(scope="module")
def long_orders(long_frames: Dict[str, pd.DataFrame]) -> list:
    return list(AdxTrendPullbackEa().generate_orders(long_frames))


@pytest.fixture(scope="module")
def short_orders(short_frames: Dict[str, pd.DataFrame]) -> list:
    return list(AdxTrendPullbackEa().generate_orders(short_frames))


# ---------------------------------------------------------------------------
# The premises the hand arithmetic rests on, checked independently of the
# strategy: constant true range, and the spec's own EMA recursion.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bars", [BARS_LONG, BARS_SHORT])
def test_fixture_bars_have_constant_true_range(
    bars: List[Tuple[float, float, float, float]],
) -> None:
    """Premise of every level below: TR = 0.00100 on every bar, so ATR14 = 0.00100."""
    for i, (open_, high, low, close) in enumerate(bars):
        assert high - low == pytest.approx(EXPECTED_ATR, abs=1e-9), i
        assert low <= open_ <= high, i
        assert low <= close <= high, i
        if i:
            prev_close = bars[i - 1][3]
            # prev close inside the bar => |H - C(j-1)| and |L - C(j-1)| <= H - L
            assert low <= prev_close <= high, i


def test_arm_and_release_distances_match_the_spec_recursion() -> None:
    """§4.3 / §4.4 recomputed from the spec's EMA recursion, not from the strategy.

    This is the fixture's own ground truth: dist crosses 1.0 downward exactly
    once in the series, between bar 31 and bar 32.
    """
    closes = [b[3] for b in BARS_LONG]
    alpha = 2.0 / (AdxTrendPullbackEa.EMA_PERIOD + 1.0)
    ema_val = closes[0]
    dists: List[float] = [0.0]
    for close in closes[1:]:
        ema_val += alpha * (close - ema_val)
        dists.append(abs(close - ema_val) / EXPECTED_ATR)

    assert dists[31] == pytest.approx(EXPECTED_DIST_ARM, abs=1e-5)
    assert dists[32] == pytest.approx(EXPECTED_DIST_RELEASE, abs=1e-5)
    # dist >= PULL_RATIO at bar 31 and nowhere else -> only bar 32 can fire.
    armed = [i for i, d in enumerate(dists) if d >= AdxTrendPullbackEa.PULL_RATIO]
    assert armed == [31]


# ---------------------------------------------------------------------------
# 3. The assertions
# ---------------------------------------------------------------------------


def test_long_series_emits_exactly_one_order(long_orders: list) -> None:
    """§4: all five conditions coincide only at bar 32 (2024-03-05 08:00 UTC)."""
    assert [str(o.decision_bar) for o in long_orders] == [str(DECISION_BAR)]


def test_long_order_matches_hand_computed_arithmetic(long_orders: list) -> None:
    """The complete trade plan, derived from spec §4/§6/§7 (arithmetic above)."""
    order = long_orders[0]

    assert order.direction == 1  # §4.5  +DI(32) > -DI(32)
    assert order.entry == "market"  # §4    market at the open of k+1
    assert order.entry_price is None  # §4    market => entry_price None
    assert order.expires_after_bars is None  # §4    not a pending order
    assert order.decision_close == pytest.approx(EXPECTED_LONG_CLOSE, abs=1e-9)

    # §6 initial stop = Close(k) - 2.0 * ATR14(k) = 1.10165 - 0.00200
    assert order.stop.price == pytest.approx(EXPECTED_LONG_STOP, abs=1e-9)
    assert order.stop.move_to_breakeven_on is None  # §6 no breakeven rule
    assert order.stop.trail_atr_multiple is None  # §6 static stop
    assert order.stop.breakeven_offset_pips == 0.0

    # §7 single take-profit leg at Close(k) + 4.0 * ATR14(k) = 1.10165 + 0.00400
    assert [leg.label for leg in order.exits] == ["TP1"]
    assert [leg.kind for leg in order.exits] == ["take_profit"]
    assert order.exits[0].price == pytest.approx(EXPECTED_LONG_TP, abs=1e-9)
    assert order.exits[0].fraction == pytest.approx(1.0, abs=1e-9)
    assert sum(leg.fraction for leg in order.exits) == pytest.approx(1.0, abs=1e-9)


def test_short_series_emits_exactly_one_mirrored_order(short_orders: list) -> None:
    """§5 / §6 / §7 on the reflected series: same bar, mirrored levels.

    The reflection swaps +DM and -DM (High' = 2.20000 - Low), so ADX, ATR and
    dist are bit-for-bit the same story and only the DMI consensus flips.
    """
    assert [str(o.decision_bar) for o in short_orders] == [str(DECISION_BAR)]
    order = short_orders[0]

    assert order.direction == -1  # §5.5'  -DI(32) > +DI(32)
    assert order.entry == "market"
    assert order.entry_price is None
    assert order.expires_after_bars is None
    assert order.decision_close == pytest.approx(EXPECTED_SHORT_CLOSE, abs=1e-9)

    # §6 short stop = Close(k) + 2.0 * ATR14(k) = 1.09835 + 0.00200
    assert order.stop.price == pytest.approx(EXPECTED_SHORT_STOP, abs=1e-9)
    # §7 short TP  = Close(k) - 4.0 * ATR14(k) = 1.09835 - 0.00400
    assert [leg.label for leg in order.exits] == ["TP1"]
    assert order.exits[0].price == pytest.approx(EXPECTED_SHORT_TP, abs=1e-9)
    assert order.exits[0].fraction == pytest.approx(1.0, abs=1e-9)


def test_risk_reward_geometry_holds_on_both_sides(
    long_orders: list, short_orders: list
) -> None:
    """§6/§7 derived: R = 2.0 x ATR from the close, TP = rr x R with rr = 2.0."""
    for order in (*long_orders, *short_orders):
        risk = (order.decision_close - order.stop.price) * order.direction
        assert risk == pytest.approx(
            AdxTrendPullbackEa.SL_MULT * EXPECTED_ATR, abs=1e-9
        )
        reward = (order.exits[0].price - order.decision_close) * order.direction
        assert reward == pytest.approx(AdxTrendPullbackEa.RR * risk, abs=1e-9)


def test_no_order_on_the_arm_bar(long_frames: Dict[str, pd.DataFrame]) -> None:
    """§4.4: the release is required, not just the arm.

    Truncating the frame at bar 31 — the bar that stretched to dist 1.17 — must
    produce nothing at all. The setup only exists once bar 32 has closed.
    """
    truncated = {"H1": long_frames["H1"].iloc[:32]}
    assert list(AdxTrendPullbackEa().generate_orders(truncated)) == []


def test_nothing_fires_before_warmup(long_orders: list) -> None:
    """§9 warm-up: no decision bar earlier than ``warmup_bars`` (30)."""
    strategy = AdxTrendPullbackEa()
    first_allowed = pd.date_range(START, periods=len(BARS_LONG), freq="1h", tz="UTC")[
        strategy.warmup_bars
    ]
    assert all(o.decision_bar >= first_allowed for o in long_orders)


# ---------------------------------------------------------------------------
# 4. The non-negotiable check
# ---------------------------------------------------------------------------


def test_strategy_is_free_of_lookahead_long(
    long_frames: Dict[str, pd.DataFrame],
) -> None:
    assert_no_lookahead_v2(AdxTrendPullbackEa(), long_frames)


def test_strategy_is_free_of_lookahead_short(
    short_frames: Dict[str, pd.DataFrame],
) -> None:
    assert_no_lookahead_v2(AdxTrendPullbackEa(), short_frames)


# ---------------------------------------------------------------------------
# 5. Assertion -> spec rule map
# ---------------------------------------------------------------------------
# test_fixture_bars_have_constant_true_range
#     not a spec rule — it pins the fixture premise (ATR14 = 0.00100) that every
#     hand-computed level below depends on. §3 (ATR14, Wilder/ewm of TR).
# test_arm_and_release_distances_match_the_spec_recursion
#     §3 dist(j) = |Close(j) - EMA20(j)| / ATR14(j); §10 #9 (inventory span-20
#     EMA, not the CSV's ewm(com=20)); §4.3 arm >= 1.0; §4.4 release < 1.0.
# test_long_series_emits_exactly_one_order
#     §4.1 ADX > 25 · §4.2 ADX rising · §4.3 arm at k-1 · §4.4 release at k ·
#     §4.5 +DI > -DI. Conjunction holds at exactly one bar.
# test_long_order_matches_hand_computed_arithmetic
#     §4 entry = market / entry_price None / expires_after_bars null ·
#     §6 stop = Close(k) - 2.0 x ATR14(k), no breakeven, no trail ·
#     §7 one take_profit leg, fraction 1.0, Close(k) + 4.0 x ATR14(k).
# test_short_series_emits_exactly_one_mirrored_order
#     §5 (conditions 1-4 direction-agnostic, 5' flipped) · §6/§7 short mirror.
# test_risk_reward_geometry_holds_on_both_sides
#     §3 sl_mult = 2.0, rr = 2.0 · §6 R_declared = 2.0 x ATR14(k) ·
#     §7 TP distance = rr x R_declared = 4.0 x ATR14(k).
# test_no_order_on_the_arm_bar
#     §4.4 (release is a separate, later condition) · §9 the decision bar is k,
#     never k-1.
# test_nothing_fires_before_warmup
#     §9 warm-up: emit nothing until all five indicator series are non-NaN.
# test_strategy_is_free_of_lookahead_long / _short
#     §9 causality audit in full; PROMPT.md hard rule 1. Both probes cover the
#     firing bar (position 32 of 46, warmup 30), so they compare real orders and
#     not emptiness-to-emptiness.
