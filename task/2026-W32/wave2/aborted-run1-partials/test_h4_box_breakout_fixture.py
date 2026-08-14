"""GOLDEN FIXTURE — h4_box_breakout.

Spec: ``task/2026-W32/fleet/upload/wave2/specs/SPEC-h4_box_breakout.md``

Every expected number below is derived from the spec's formulas with the arithmetic
shown, not copied from what the code printed.

Unlike the reference fixture there is **no ``_FixtureScale`` subclass**, and that is the
point: the strategy has no lookback period to shrink. The box is one completed H4 bar
(spec §9, zero confirmation lag) and production ``warmup_bars`` is already 1, so the
fixture exercises the production parameters verbatim — 21-pip buffer, 4 x 0.25 ladder,
29-bar expiry, all of it.

----------------------------------------------------------------------------
ASSERTION -> SPEC RULE MAP
----------------------------------------------------------------------------
test_box_bar_is_the_sunday_2100_bar_only
    §3 step 2 — box_bar is the H4 bar stamped Sunday 21:00 UTC. Proves the Monday
    01:00 bars (the alternative rejected in §10 row 1) are NOT box bars, and that
    the Thu/Fri bars of the truncated first week produce nothing.
    §4 / §5 / §10 row 5 — one setup per week = exactly two intents per box bar,
    long and short, emitted together at the same decision bar.
test_week_one_long_matches_hand_computed_arithmetic
    §4.2 buffer B = 20 + 1.0 = 21 pips · §4.3 E_long = box_high + B ·
    §6 stop = box_low with no buffer · §7 TP_k = E_long + k x H at 0.25 each ·
    §4.3 expires_after_bars = 29 · §6 no breakeven, no trail.
test_week_one_short_matches_hand_computed_arithmetic
    §5 — exact mirror, including the symmetric buffer of §10 row 6, and
    §6 stop = box_high.
test_week_two_geometry_is_rederived_from_its_own_box
    §3 step 3 — H is recomputed per week; a smaller box gives a tighter ladder.
    Catches any hard-coded level.
test_ladder_is_equal_weighted_and_sums_to_one
    §7 — fractions 0.25 x 4 = 1.0 (contract tolerance 1e-9); §10 row 3 rejects
    tail-weighting.
test_tp1_is_slightly_less_than_one_r
    §7 closing note — risk = H + 21 pips while TP1 = +1 H, so declared TP1 < 1R.
    This is the honest consequence of the buffer and must NOT be "fixed".
test_pending_entries_sit_on_the_correct_side_of_the_decision_close
    Contract ``OrderIntent.__post_init__`` / reference NOTE 3 — buy_stop above,
    sell_stop below the decision-bar close.
test_stop_is_exactly_the_opposite_box_edge
    §6 / §10 row 7 — literal box edge, no buffer added.
test_degenerate_flat_box_skips_the_week
    §3 step 3 — H <= 0 means the week is skipped entirely.
test_strategy_is_free_of_lookahead
    Fleet hard rule 1 — ``assert_no_lookahead_v2`` must pass, and must pass on bars
    where the strategy actually fires.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.h4_box_breakout import H4BoxBreakout

# GBP_JPY conventions: 1 pip = 0.01 price units, so the spec's 21-pip buffer is 0.21.
PIP = 0.01
BUFFER = 21 * PIP  # 20-pip noise buffer + 1.0-pip spread proxy (§4.2)

# ---------------------------------------------------------------------------
# 1. The bars, and why these bars
# ---------------------------------------------------------------------------
# 40 H4 bars of a plausible GBP_JPY tape around 185.00, laid out as three feed-week
# fragments so that the *calendar* logic is what gets tested:
#
#   bars 0-5   tail of a week whose Sunday-21:00 bar is NOT in the frame
#              (Thu 21:00 -> Fri 17:00). Must produce nothing: §3 step 2 says a week
#              without its week-open bar is skipped, never re-anchored.
#   bars 6-35  one complete feed week: Sun 2024-01-07 21:00 -> Fri 2024-01-12 17:00.
#              That is exactly 30 H4 bars, which is the arithmetic behind
#              expires_after_bars = 29 in §4.3. Bar 6 is BOX #1, a deliberately round
#              1.00-wide box (185.00 / 184.00) so every level below is exact.
#              Price then breaks up through the long trigger at bar 10 and trends for
#              the rest of the week — a realistic path for the setup, though the
#              position engine is not exercised here.
#   bars 36-39 the start of the next feed week: Sun 2024-01-14 21:00 is BOX #2, a
#              much tighter 0.50-wide box (186.50 / 186.00) reached after a weekend
#              gap down. A second box of a different width is what proves the ladder
#              is derived from H rather than hard-coded.
#
# 2024-01-07 and 2024-01-14 are Sundays; 2024-01-08 and 2024-01-15 are Mondays. The
# Monday 01:00 bars are present precisely so the test can prove they are not boxes.
#
# Every bar satisfies Low <= min(Open, Close) <= max(Open, Close) <= High.
# Columns: (timestamp, Open, High, Low, Close)
BARS: List[Tuple[str, float, float, float, float]] = [
    # -- tail of the preceding week: no week-open bar in frame -> no setup --------
    ("2024-01-04 21:00", 184.30, 184.55, 184.20, 184.45),  # Thu
    ("2024-01-05 01:00", 184.45, 184.60, 184.35, 184.50),  # Fri
    ("2024-01-05 05:00", 184.50, 184.65, 184.40, 184.55),
    ("2024-01-05 09:00", 184.55, 184.70, 184.30, 184.40),
    ("2024-01-05 13:00", 184.40, 184.60, 184.25, 184.35),
    ("2024-01-05 17:00", 184.35, 184.50, 184.20, 184.30),
    # -- feed week 2024-01-07 -> 2024-01-12: 30 bars, bar 6 is BOX #1 ------------
    ("2024-01-07 21:00", 184.20, 185.00, 184.00, 184.50),  # Sun  BOX #1, H = 1.00
    ("2024-01-08 01:00", 184.50, 184.80, 184.40, 184.70),  # Mon  (NOT a box bar)
    ("2024-01-08 05:00", 184.70, 184.95, 184.55, 184.60),
    ("2024-01-08 09:00", 184.60, 184.90, 184.45, 184.85),
    ("2024-01-08 13:00", 184.85, 185.30, 184.75, 185.25),  # breaks 185.21 long trigger
    ("2024-01-08 17:00", 185.25, 185.60, 185.10, 185.45),
    ("2024-01-08 21:00", 185.45, 185.70, 185.30, 185.55),
    ("2024-01-09 01:00", 185.55, 185.80, 185.40, 185.65),
    ("2024-01-09 05:00", 185.65, 185.90, 185.50, 185.60),
    ("2024-01-09 09:00", 185.60, 185.95, 185.45, 185.85),
    ("2024-01-09 13:00", 185.85, 186.30, 185.75, 186.20),
    ("2024-01-09 17:00", 186.20, 186.40, 186.00, 186.10),
    ("2024-01-09 21:00", 186.10, 186.35, 185.95, 186.25),
    ("2024-01-10 01:00", 186.25, 186.50, 186.10, 186.40),
    ("2024-01-10 05:00", 186.40, 186.60, 186.20, 186.30),
    ("2024-01-10 09:00", 186.30, 186.55, 186.15, 186.45),
    ("2024-01-10 13:00", 186.45, 186.80, 186.35, 186.70),
    ("2024-01-10 17:00", 186.70, 186.95, 186.55, 186.80),
    ("2024-01-10 21:00", 186.80, 187.00, 186.60, 186.70),
    ("2024-01-11 01:00", 186.70, 186.90, 186.50, 186.60),
    ("2024-01-11 05:00", 186.60, 186.85, 186.40, 186.75),
    ("2024-01-11 09:00", 186.75, 187.05, 186.65, 186.95),
    ("2024-01-11 13:00", 186.95, 187.25, 186.85, 187.15),
    ("2024-01-11 17:00", 187.15, 187.30, 186.95, 187.05),
    ("2024-01-11 21:00", 187.05, 187.20, 186.85, 186.95),
    ("2024-01-12 01:00", 186.95, 187.10, 186.75, 186.85),
    ("2024-01-12 05:00", 186.85, 187.00, 186.60, 186.70),
    ("2024-01-12 09:00", 186.70, 186.85, 186.45, 186.55),
    ("2024-01-12 13:00", 186.55, 186.70, 186.30, 186.45),
    ("2024-01-12 17:00", 186.45, 186.60, 186.25, 186.35),  # Fri 17:00 = bar 29
    # -- next feed week: bar 36 is BOX #2, a tighter box after a weekend gap -----
    ("2024-01-14 21:00", 186.10, 186.50, 186.00, 186.40),  # Sun  BOX #2, H = 0.50
    ("2024-01-15 01:00", 186.40, 186.60, 186.30, 186.55),  # Mon  (NOT a box bar)
    ("2024-01-15 05:00", 186.55, 186.75, 186.45, 186.65),
    ("2024-01-15 09:00", 186.65, 186.90, 186.55, 186.80),
]

# A second, deliberately degenerate series: the week-open bar is FLAT (High == Low),
# so H = 0 and §3 step 3 requires the week to be skipped. The flat bar sits at
# position 1 so that production warmup_bars = 1 is not what makes the test pass.
FLAT_BOX_BARS: List[Tuple[str, float, float, float, float]] = [
    ("2024-01-05 17:00", 184.35, 184.50, 184.20, 184.30),  # Fri
    ("2024-01-07 21:00", 185.00, 185.00, 185.00, 185.00),  # Sun  flat box, H = 0
    ("2024-01-08 01:00", 185.00, 185.40, 184.80, 185.30),  # Mon
    ("2024-01-08 05:00", 185.30, 185.60, 185.10, 185.20),
]


def _frame(rows: List[Tuple[str, float, float, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [r[1] for r in rows],
            "High": [r[2] for r in rows],
            "Low": [r[3] for r in rows],
            "Close": [r[4] for r in rows],
            "Volume": 1.0,
        },
        index=pd.DatetimeIndex([pd.Timestamp(r[0], tz="UTC") for r in rows]),
    )


@pytest.fixture(scope="module")
def frames() -> Dict[str, pd.DataFrame]:
    return {"H4": _frame(BARS)}


@pytest.fixture(scope="module")
def orders(frames: Dict[str, pd.DataFrame]) -> List:
    return list(H4BoxBreakout().generate_orders(frames))


def test_bars_are_well_formed() -> None:
    """Sanity on the literal itself: 40 bars, valid OHLC, strictly increasing stamps."""
    assert len(BARS) == 40
    for stamp, open_, high, low, close in BARS:
        assert low <= min(open_, close) <= max(open_, close) <= high, stamp
    idx = _frame(BARS).index
    assert idx.is_monotonic_increasing
    # The complete feed week is bars 6..35 inclusive = 30 H4 bars, which is the
        # arithmetic behind expires_after_bars = 29 (§4.3).
    assert str(idx[6]) == "2024-01-07 21:00:00+00:00"
    assert str(idx[35]) == "2024-01-12 17:00:00+00:00"
    assert idx[35] - idx[6] == pd.Timedelta(hours=116)  # 29 intervals of 4h


# ---------------------------------------------------------------------------
# 2 + 3. Expected values, computed by hand, then asserted
# ---------------------------------------------------------------------------


def test_box_bar_is_the_sunday_2100_bar_only(orders: List) -> None:
    """§3 step 2 + §4/§5: two intents per Sunday-21:00 bar, and nothing anywhere else.

    Bars 0-5 belong to a week whose Sunday-21:00 bar is not in the frame, so that
    week is skipped (§3 step 2). The Monday 01:00 bars — the "first H4 bar of Monday
    UTC" reading rejected in §10 row 1 — must produce nothing.
    """
    assert [(str(o.decision_bar), o.direction) for o in orders] == [
        ("2024-01-07 21:00:00+00:00", 1),
        ("2024-01-07 21:00:00+00:00", -1),
        ("2024-01-14 21:00:00+00:00", 1),
        ("2024-01-14 21:00:00+00:00", -1),
    ]
    assert [o.entry for o in orders] == [
        "buy_stop",
        "sell_stop",
        "buy_stop",
        "sell_stop",
    ]


def test_week_one_long_matches_hand_computed_arithmetic(orders: List) -> None:
    """BOX #1, long side. All arithmetic from spec §3/§4/§6/§7.

    Box bar = 2024-01-07 21:00 (Sunday), High 185.00 / Low 184.00 / Close 184.50
      box_high = 185.00
      box_low  = 184.00
      H        = 185.00 - 184.00                = 1.00      (§3 step 3)
      B        = (20 + 1.0) pips x 0.01         = 0.21      (§4.2)

      E_long   = box_high + B = 185.00 + 0.21   = 185.21    (§4.3)
      stop     = box_low                        = 184.00    (§6, no buffer)
      risk     = 185.21 - 184.00                = 1.21      ( = H + 21 pips)

      TP1 = E_long + 1 x H = 185.21 + 1.00      = 186.21    (§7)
      TP2 = E_long + 2 x H = 185.21 + 2.00      = 187.21
      TP3 = E_long + 3 x H = 185.21 + 3.00      = 188.21
      TP4 = E_long + 4 x H = 185.21 + 4.00      = 189.21
    """
    o = orders[0]

    assert o.direction == 1
    assert o.entry == "buy_stop"
    assert o.entry_price == pytest.approx(185.21, abs=1e-9)
    assert o.stop.price == pytest.approx(184.00, abs=1e-9)
    assert o.decision_close == pytest.approx(184.50, abs=1e-9)

    assert [leg.label for leg in o.exits] == ["TP1", "TP2", "TP3", "TP4"]
    assert [leg.price for leg in o.exits] == pytest.approx(
        [186.21, 187.21, 188.21, 189.21], abs=1e-9
    )

    # §6: static stop for the life of the trade — no breakeven, no trail.
    assert o.stop.move_to_breakeven_on is None
    assert o.stop.trail_atr_multiple is None
    # §4.3: dies at bar 29 = Friday 17:00 UTC, before the next box bar can exist.
    assert o.expires_after_bars == 29


def test_week_one_short_matches_hand_computed_arithmetic(orders: List) -> None:
    """BOX #1, short side — the exact mirror. Spec §5, §6, §7, §10 row 6.

      E_short = box_low - B = 184.00 - 0.21     = 183.79    (§5.2, symmetric buffer)
      stop    = box_high                        = 185.00    (§6)
      risk    = 185.00 - 183.79                 = 1.21      ( = H + 21 pips)

      TP1 = E_short - 1 x H = 183.79 - 1.00     = 182.79    (§7 mirror)
      TP2 = E_short - 2 x H = 183.79 - 2.00     = 181.79
      TP3 = E_short - 3 x H = 183.79 - 3.00     = 180.79
      TP4 = E_short - 4 x H = 183.79 - 4.00     = 179.79
    """
    o = orders[1]

    assert o.direction == -1
    assert o.entry == "sell_stop"
    assert o.entry_price == pytest.approx(183.79, abs=1e-9)
    assert o.stop.price == pytest.approx(185.00, abs=1e-9)

    assert [leg.label for leg in o.exits] == ["TP1", "TP2", "TP3", "TP4"]
    assert [leg.price for leg in o.exits] == pytest.approx(
        [182.79, 181.79, 180.79, 179.79], abs=1e-9
    )
    assert o.expires_after_bars == 29

    # Both sides of one weekly setup share the decision bar and the risk distance
    # (§10 row 5: emitted together, no OCO exists to cancel either).
    assert o.decision_bar == orders[0].decision_bar
    long_risk = orders[0].entry_price - orders[0].stop.price
    short_risk = o.stop.price - o.entry_price
    assert short_risk == pytest.approx(long_risk, abs=1e-9)


def test_week_two_geometry_is_rederived_from_its_own_box(orders: List) -> None
:
    """BOX #2 proves H is per-week, not hard-coded. Spec §3 step 3, §4, §5, §7.

    Box bar = 2024-01-14 21:00 (Sunday), High 186.50 / Low 186.00 / Close 186.40
      H = 186.50 - 186.00 = 0.50

      long : E = 186.50 + 0.21 = 186.71 · stop = 186.00
             TP = 186.71 + {0.50, 1.00, 1.50, 2.00}
                = 187.21, 187.71, 188.21, 188.71
      short: E = 186.00 - 0.21 = 185.79 · stop = 186.50
             TP = 185.79 - {0.50, 1.00, 1.50, 2.00}
                = 185.29, 184.79, 184.29, 183.79
    """
    long_order, short_order = orders[2], orders[3]

    assert long_order.entry_price == pytest.approx(186.71, abs=1e-9)
    assert long_order.stop.price == pytest.approx(186.00, abs=1e-9)
    assert [leg.price for leg in long_order.exits] == pytest.approx(
        [187.21, 187.71, 188.21, 188.71], abs=1e-9
    )

    assert short_order.entry_price == pytest.approx(185.79, abs=1e-9)
    assert short_order.stop.price == pytest.approx(186.50, abs=1e-9)
    assert [leg.price for leg in short_order.exits] == pytest.approx(
        [185.29, 184.79, 184.29, 183.79], abs=1e-9
    )


def test_ladder_is_equal_weighted_and_sums_to_one(orders: List) -> None:
    """§7 + fleet hard rule 4: 0.25 x 4 = 1.0. §10 row 3 rejects tail-weighting."""
    for o in orders:
        assert len(o.exits) == 4
        assert [leg.fraction for leg in o.exits] == [0.25, 0.25, 0.25, 0.25]
        assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)
        assert all(leg.kind == "take_profit" for leg in o.exits)


def test_tp1_is_slightly_less_than_one_r(orders: List) -> None:
    """§7 closing note: risk = H + 21 pips but TP1 = +1 H, so TP1 < 1R by design.

    This is the honest cost of the buffer. A "fix" that widened TP1 to 1R would be a
    silent improvement of the source and is forbidden by fleet hard rule 5.
    """
    for o in orders:
        risk = abs(o.entry_price - o.stop.price)
        tp1_distance = abs(o.exits[0].price - o.entry_price)
        assert tp1_distance < risk
        # The shortfall is exactly the 21-pip buffer.
        assert risk - tp1_distance == pytest.approx(BUFFER, abs=1e-9)
        # And each rung is one box height further out.
        height = tp1_distance
        for k, leg in enumerate(o.exits, start=1):
            assert abs(leg.price - o.entry_price) == pytest.approx(
                k * height, abs=1e-9
            )


def test_pending_entries_sit_on_the_correct_side_of_the_decision_close(
    frames: Dict[str, pd.DataFrame], orders: List
) -> None:
    """Contract ``OrderIntent`` / reference NOTE 3: no pending order may already be
    through the market at the decision bar."""
    close = frames["H4"]["Close"]
    for o in orders:
        decision_close = float(close.loc[o.decision_bar])
        if o.direction == 1:
            assert o.entry_price > decision_close
        else:
            assert o.entry_price < decision_close


def test_stop_is_exactly_the_opposite_box_edge(
    frames: Dict[str, pd.DataFrame], orders: List
) -> None:
    """§6 / §10 row 7: the stop is the literal box edge — no buffer is added."""
    h4 = frames["H4"]
    for o in orders:
        bar = h4.loc[o.decision_bar]
        if o.direction == 1:
            assert o.stop.price == pytest.approx(float(bar["Low"]), abs=1e-12)
            assert o.entry_price == pytest.approx(
                float(bar["High"]) + BUFFER, abs=1e-9
            )
        else:
            assert o.stop.price == pytest.approx(float(bar["High"]), abs=1e-12)
            assert o.entry_price == pytest.approx(float(bar["Low"]) - BUFFER, abs=1e-9)


def test_degenerate_flat_box_skips_the_week() -> None:
    """§3 step 3: H <= 0 means the week is skipped entirely, both sides."""
    flat = {"H4": _frame(FLAT_BOX_BARS)}
    assert list(H4BoxBreakout().generate_orders(flat)) == []


# ---------------------------------------------------------------------------
# 4. The non-negotiable check
# ---------------------------------------------------------------------------


def test_strategy_is_free_of_lookahead(frames: Dict[str, pd.DataFrame]) -> None:
    """Fleet hard rule 1. The probe is only meaningful because the strategy fires on
    these bars (bar 6 is inside every truncation window the probe builds)."""
    assert_no_lookahead_v2(H4BoxBreakout(), frames)
