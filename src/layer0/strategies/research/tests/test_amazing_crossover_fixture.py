"""GOLDEN FIXTURE — amazing_crossover (spec row 34).

Spec: ``task/2026-August-week1/fleet/upload/wave2/specs/SPEC-amazing_crossover.md``.

Two hand-built 40-bar H1 series (one long, one short) plus a third frame that
reuses the long series' Closes with different wicks. Every expected number below
is derived from the spec's formulas, not from running the strategy:

* the *levels* come straight from §6/§7 arithmetic on ``C_t`` and ``pip``;
* the *firing bar* is derived from the indicator recursions themselves —
  ``ema(x, p)``: ``a = 2/(p+1)``, ``e[i] = a·x[i] + (1-a)·e[i-1]``, and
  ``rsi``: the same ``a = 2/(p+1)`` smoothing of gains/losses of the median
  series, ``rsi = 100 − 100/(1 + G/L)`` — worked out in the comments where each
  series is defined.

Assertion → spec rule map
-------------------------
=========================================== ==========================================
 test                                        rule it pins
=========================================== ==========================================
 test_long_fires_exactly_once                §4 (both conditions, same bar t), §11
 test_long_order_matches_spec_arithmetic     §4 entry, §6 stop + breakeven, §7 legs
 test_short_fires_exactly_once               §5 (mirror), §11
 test_short_order_matches_spec_arithmetic    §5 entry, §6 stop + breakeven, §7 legs
 test_conditions_merely_holding_is_not_enou  §4/§5 "same bar t", §10 #1
 test_rsi_is_read_from_the_median_price      §3 (RSI input = (High+Low)/2, not Close)
 test_every_order_is_a_market_order          §4/§5 market entry, expires_after_bars null
 test_exit_fractions_sum_to_one              §7 (0.10 + 0.90), contract tolerance 1e-9
 test_stop_geometry_is_one_r_of_100_pips     §6 (100-pip stop), §11 RR ≈ 1 : 0.47
 test_breakeven_trigger_names_an_exit_leg    §6 move_to_breakeven_on = "BE_TRIGGER"
 test_no_trailing_stop_is_declared           §6/§10 #4 (ladder inexpressible)
 test_strategy_is_free_of_lookahead          §9 / fleet hard rule 1
=========================================== ==========================================

The fixture subclasses the strategy only to shrink ``warmup_bars`` (50 → 20):
40 bars cannot contain a 50-bar warmup. **No period and no level formula is
changed** — EMA 5/10, RSI 10, the 50 midline and the 100/20/50-pip geometry are
all the production values.
"""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import OrderIntent, assert_no_lookahead_v2
from src.layer0.strategies.research.amazing_crossover import AmazingCrossover

PIP = 0.0001  # EUR_USD-scale quotes, so spec §6 gives pip = 0.0001
SPIKE = 25  # index of the ignition bar in both series

# ---------------------------------------------------------------------------
# 1. The bars, and why these bars
# ---------------------------------------------------------------------------
# LONG series: 25 bars of a perfectly regular 2-pip-per-bar downtrend, then one
# 50-pip ignition bar, then 14 bars drifting up 2 pips a bar.
#
# The downtrend is regular on purpose, because it makes the state at bar 24
# exact rather than approximate:
#
#   * EMA lag on a linear ramp of slope -d settles at (1-a)/a bars, i.e. 2 bars
#     for EMA5 (a = 1/3) and 4.5 bars for EMA10 (a = 2/11). So at bar 24
#     ema5 = C + 2d and ema10 = C + 4.5d, hence ema5 - ema10 = -2.5d = -5 pips:
#     the fast EMA is *below* the slow one, so an up-cross is available.
#   * every median-price change is a loss, so RSI's average gain is 0 and
#     rsi = 100 - 100/(1+0) = 0 — far below the 50 midline, so an up-cross of
#     50 is available too.
#
# Bar 25 then has to flip BOTH on the same bar (§4). Writing d = 2 pips and the
# ignition bar's Close jump as U:
#
#   EMA cross-up needs  ema5-ema10 to go positive:
#     diff[25] = -2.5d + (1/3)(U - 2d) - (2/11)(U - 4.5d) = (5/33)U - 2.349d > 0
#            ->  U > 15.5 d.  Chosen U = 50 pips = 25 d, giving diff = +2.94 pips.
#   RSI cross-up needs  G/L > 1 at bar 25, where L[24] = d (converged) and the
#     median price rose by U_med:
#     G = (2/11)U_med, L = (9/11)d  ->  U_med > 4.5 d.
#     The ignition bar is O=1.19520 H=1.20040 L=1.19500 C=1.20020, so its median
#     is (1.20040+1.19500)/2 = 1.19770 against 1.19530 at bar 24: U_med = 24 pips
#     = 12 d, giving G/L = 2.688 and rsi = 100 - 100/3.688 = 72.89.
#
# Both flip at bar 25 and nowhere else: from bar 26 on the fast EMA stays above
# the slow one and rsi stays above 50, so neither can *cross* again inside the
# window. Bars 1..24 are all "already below" on both, so nothing crosses there
# either (and they sit inside warmup regardless).
#
# Non-ignition bars use Open = Close, High = Close + 3 pips, Low = Close - 1 pip.
# The wicks are deliberately asymmetric so the median price is NOT the close —
# a strategy that fed Close to RSI would be reading a different series.
CLOSES_LONG = [
    # bars 0-24 — regular 2-pip downtrend (warmup + a clean pre-cross state)
    1.20000,
    1.19980,
    1.19960,
    1.19940,
    1.19920,
    1.19900,
    1.19880,
    1.19860,
    1.19840,
    1.19820,
    1.19800,
    1.19780,
    1.19760,
    1.19740,
    1.19720,
    1.19700,
    1.19680,
    1.19660,
    1.19640,
    1.19620,
    1.19600,
    1.19580,
    1.19560,
    1.19540,
    1.19520,
    # bar 25 — the ignition bar: Close +50 pips (see SPIKE_LONG for its wicks)
    1.20020,
    # bars 26-39 — steady 2-pip drift up; no further cross is possible
    1.20040,
    1.20060,
    1.20080,
    1.20100,
    1.20120,
    1.20140,
    1.20160,
    1.20180,
    1.20200,
    1.20220,
    1.20240,
    1.20260,
    1.20280,
    1.20300,
]

# SHORT series: the exact reflection of the long one — a regular 2-pip uptrend
# (ema5 - ema10 = +5 pips, rsi = 100 because every median change is a gain),
# then a 50-pip down-close ignition bar, then a 2-pip drift down. RSI is exactly
# antisymmetric (gains and losses swap, so rsi -> 100 - rsi) and the EMAs are
# affine, so the same two inequalities give diff[25] = -2.94 pips and
# rsi[25] = 100 - 72.89 = 27.11 — both cross down at bar 25 (§5).
CLOSES_SHORT = [
    # bars 0-24 — regular 2-pip uptrend
    1.20000,
    1.20020,
    1.20040,
    1.20060,
    1.20080,
    1.20100,
    1.20120,
    1.20140,
    1.20160,
    1.20180,
    1.20200,
    1.20220,
    1.20240,
    1.20260,
    1.20280,
    1.20300,
    1.20320,
    1.20340,
    1.20360,
    1.20380,
    1.20400,
    1.20420,
    1.20440,
    1.20460,
    1.20480,
    # bar 25 — the ignition bar: Close -50 pips
    1.19980,
    # bars 26-39 — steady 2-pip drift down
    1.19960,
    1.19940,
    1.19920,
    1.19900,
    1.19880,
    1.19860,
    1.19840,
    1.19820,
    1.19800,
    1.19780,
    1.19760,
    1.19740,
    1.19720,
    1.19700,
]

# The ignition bars, written out as explicit (Open, High, Low, Close).
#
# SPIKE_LONG      median = (1.20040 + 1.19500) / 2 = 1.19770  -> +24 pips, crosses 50
# SPIKE_SHORT     median = (1.20500 + 1.19960) / 2 = 1.20230  -> -24 pips, crosses 50
# SPIKE_LONG_LOW  median = (1.20040 + 1.19140) / 2 = 1.19590  -> +6 pips only:
#                 G/L = ((2/11)·6) / ((9/11)·2) = 0.667, rsi = 40.20 < 50, so the
#                 RSI leg of §4 fails even though the EMA leg still fires. Same
#                 Closes as SPIKE_LONG — only the Low differs.
SPIKE_LONG: Tuple[float, float, float, float] = (1.19520, 1.20040, 1.19500, 1.20020)
SPIKE_SHORT: Tuple[float, float, float, float] = (1.20480, 1.20500, 1.19960, 1.19980)
SPIKE_LONG_LOW: Tuple[float, float, float, float] = (1.19520, 1.20040, 1.19140, 1.20020)


class _FixtureWarmup(AmazingCrossover):
    """Production logic and production periods; fixture-sized warmup only."""

    @property
    def warmup_bars(self) -> int:
        return 20


def _frame(
    closes: Sequence[float],
    wick_up: float,
    wick_down: float,
    spike: Tuple[float, float, float, float],
) -> pd.DataFrame:
    """Build the H1 frame: uniform wicks everywhere except the ignition bar."""
    rows: List[Tuple[float, float, float, float]] = []
    for i, close in enumerate(closes):
        if i == SPIKE:
            rows.append(spike)
        else:
            rows.append((close, close + wick_up, close - wick_down, close))
    index = pd.date_range("2020-01-01", periods=len(closes), freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "Open": [r[0] for r in rows],
            "High": [r[1] for r in rows],
            "Low": [r[2] for r in rows],
            "Close": [r[3] for r in rows],
            "Volume": 1.0,
        },
        index=index,
    )


@pytest.fixture(scope="module")
def frames_long() -> Dict[str, pd.DataFrame]:
    return {"H1": _frame(CLOSES_LONG, 0.0003, 0.0001, SPIKE_LONG)}


@pytest.fixture(scope="module")
def frames_short() -> Dict[str, pd.DataFrame]:
    return {"H1": _frame(CLOSES_SHORT, 0.0001, 0.0003, SPIKE_SHORT)}


@pytest.fixture(scope="module")
def frames_median_probe() -> Dict[str, pd.DataFrame]:
    """Long Closes, deeper ignition-bar Low: the median barely rises."""
    return {"H1": _frame(CLOSES_LONG, 0.0003, 0.0001, SPIKE_LONG_LOW)}


@pytest.fixture(scope="module")
def orders_long(frames_long: Dict[str, pd.DataFrame]) -> List[OrderIntent]:
    return list(_FixtureWarmup().generate_orders(frames_long))


@pytest.fixture(scope="module")
def orders_short(frames_short: Dict[str, pd.DataFrame]) -> List[OrderIntent]:
    return list(_FixtureWarmup().generate_orders(frames_short))


# ---------------------------------------------------------------------------
# 2 + 3. Expected values, computed by hand from the spec, then asserted
# ---------------------------------------------------------------------------

# Bar 25 of the long series, C_t = 1.20020, pip = 0.0001 (§6):
#   stop        = C_t - 100 x pip = 1.20020 - 0.01000 = 1.19020
#   BE_TRIGGER  = C_t +  20 x pip = 1.20020 + 0.00200 = 1.20220   fraction 0.10
#   TP1         = C_t +  50 x pip = 1.20020 + 0.00500 = 1.20520   fraction 0.90
LONG_CLOSE = 1.20020
LONG_STOP = 1.19020
LONG_BE = 1.20220
LONG_TP1 = 1.20520

# Bar 25 of the short series, C_t = 1.19980 — the exact mirror (§5, §7):
#   stop        = C_t + 100 x pip = 1.19980 + 0.01000 = 1.20980
#   BE_TRIGGER  = C_t -  20 x pip = 1.19980 - 0.00200 = 1.19780   fraction 0.10
#   TP1         = C_t -  50 x pip = 1.19980 - 0.00500 = 1.19480   fraction 0.90
SHORT_CLOSE = 1.19980
SHORT_STOP = 1.20980
SHORT_BE = 1.19780
SHORT_TP1 = 1.19480

FIRING_BAR = "2020-01-02 01:00:00+00:00"  # bar 25 of an hourly index from 00:00


def test_long_fires_exactly_once(orders_long: List[OrderIntent]) -> None:
    """§4: one order, at the single bar where BOTH crosses happen."""
    assert [str(o.decision_bar) for o in orders_long] == [FIRING_BAR]
    assert orders_long[0].direction == 1


def test_long_order_matches_spec_arithmetic(orders_long: List[OrderIntent]) -> None:
    """§4 entry mechanics, §6 stop, §7 exit legs — all anchored to C_t."""
    o = orders_long[0]

    assert o.entry == "market"  # §4
    assert o.entry_price is None  # §4 — the t+1 open is unknowable here
    assert o.decision_close == pytest.approx(LONG_CLOSE, abs=1e-9)
    assert o.stop.price == pytest.approx(LONG_STOP, abs=1e-9)  # §6

    assert [leg.label for leg in o.exits] == ["BE_TRIGGER", "TP1"]  # §7
    assert [leg.price for leg in o.exits] == pytest.approx(
        [LONG_BE, LONG_TP1], abs=1e-9
    )
    assert [leg.fraction for leg in o.exits] == pytest.approx([0.10, 0.90])
    assert all(leg.kind == "take_profit" for leg in o.exits)
    assert o.stop.move_to_breakeven_on == "BE_TRIGGER"  # §6
    assert o.stop.breakeven_offset_pips == 0.0  # §6


def test_short_fires_exactly_once(orders_short: List[OrderIntent]) -> None:
    """§5: the mirror image fires once, short, at the same bar of its series."""
    assert [str(o.decision_bar) for o in orders_short] == [FIRING_BAR]
    assert orders_short[0].direction == -1


def test_short_order_matches_spec_arithmetic(orders_short: List[OrderIntent]) -> None:
    """§5/§6/§7: every level mirrors, so the sign of `direction` is pinned."""
    o = orders_short[0]

    assert o.entry == "market"
    assert o.entry_price is None
    assert o.decision_close == pytest.approx(SHORT_CLOSE, abs=1e-9)
    assert o.stop.price == pytest.approx(SHORT_STOP, abs=1e-9)

    assert [leg.label for leg in o.exits] == ["BE_TRIGGER", "TP1"]
    assert [leg.price for leg in o.exits] == pytest.approx(
        [SHORT_BE, SHORT_TP1], abs=1e-9
    )
    assert [leg.fraction for leg in o.exits] == pytest.approx([0.10, 0.90])
    assert o.stop.move_to_breakeven_on == "BE_TRIGGER"


def test_conditions_merely_holding_is_not_enough(
    orders_long: List[OrderIntent], orders_short: List[OrderIntent]
) -> None:
    """§4/§5 and §10 #1: the crosses must HAPPEN at bar t, not merely hold.

    At bar 26 of the long series ema5 = 1.198222 > ema10 = 1.197487 and
    rsi(median) = 86.71 > 50 — both conditions hold — yet nothing may be emitted,
    because neither flipped between bar 25 and bar 26. The looser "both hold" or
    "within a few bars" reading rejected in §10 #1 would fire on bars 26-39 of
    both series; this asserts it does not.
    """
    later_bars = {
        str(ts)
        for ts in pd.date_range("2020-01-02 02:00", periods=14, freq="1h", tz="UTC")
    }
    for orders in (orders_long, orders_short):
        assert not later_bars & {str(o.decision_bar) for o in orders}


def test_rsi_is_read_from_the_median_price(
    frames_median_probe: Dict[str, pd.DataFrame],
) -> None:
    """§3: the RSI input is (High + Low) / 2, not Close.

    frames_median_probe has byte-identical Closes to frames_long, so the EMA leg
    of §4 still crosses up at bar 25. Only the ignition bar's Low is deeper, which
    drags its median from 1.19770 down to 1.19590 (+6 pips instead of +24). That
    puts RSI at 40.20, below the 50 midline, so the conjunction fails and NO order
    may exist. A strategy that fed Close to RSI would be unaffected by the wick
    and would still emit one — this test is what distinguishes the two.
    """
    orders = list(_FixtureWarmup().generate_orders(frames_median_probe))
    assert orders == []


def test_every_order_is_a_market_order(
    orders_long: List[OrderIntent], orders_short: List[OrderIntent]
) -> None:
    """§4/§5: market entry, filled at the t+1 open, so no pending expiry."""
    for o in orders_long + orders_short:
        assert o.entry == "market"
        assert o.entry_price is None
        assert o.expires_after_bars is None  # spec: expires_after_bars = null
        assert o.time_exit_after_bars is None  # §7 declares no time exit
        assert o.close_on_opposite is False  # §8 declares no reversal exit


def test_exit_fractions_sum_to_one(
    orders_long: List[OrderIntent], orders_short: List[OrderIntent]
) -> None:
    """§7: 0.10 + 0.90 = 1.0, inside the contract's 1e-9 tolerance."""
    for o in orders_long + orders_short:
        assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)


def test_stop_geometry_is_one_r_of_100_pips(
    orders_long: List[OrderIntent], orders_short: List[OrderIntent]
) -> None:
    """§6/§7/§11: risk is 100 pips from C_t; the legs sit at 20 and 50 pips.

    Derived from the declared distances rather than restated as levels, so a
    changed constant is caught in both directions. The weighted target
    0.10 x 20 + 0.90 x 50 = 47 pips against 100 pips of risk is the ~1 : 0.47
    declared RR §11 calls the central economic fact.
    """
    for o in orders_long + orders_short:
        assert o.decision_close is not None
        c_t = o.decision_close
        risk = o.direction * (c_t - o.stop.price)
        assert risk == pytest.approx(100 * PIP, abs=1e-9)
        for pips, leg in zip((20.0, 50.0), o.exits):
            assert leg.price is not None
            assert o.direction * (leg.price - c_t) == pytest.approx(
                pips * PIP, abs=1e-9
            )
        weighted = sum(
            leg.fraction * o.direction * ((leg.price or 0.0) - c_t) for leg in o.exits
        )
        assert weighted == pytest.approx(47 * PIP, abs=1e-9)


def test_breakeven_trigger_names_an_exit_leg(
    orders_long: List[OrderIntent], orders_short: List[OrderIntent]
) -> None:
    """§6: the breakeven trigger must name a leg that exists (contract check)."""
    for o in orders_long + orders_short:
        assert o.stop.move_to_breakeven_on in {leg.label for leg in o.exits}


def test_no_trailing_stop_is_declared(
    orders_long: List[OrderIntent], orders_short: List[OrderIntent]
) -> None:
    """§6/§10 #4: the author's open-ended P&L ladder is inexpressible, so only
    the first rung exists and no ATR trail is invented to stand in for it."""
    for o in orders_long + orders_short:
        assert o.stop.trail_atr_multiple is None
        assert all(leg.kind != "trailing" for leg in o.exits)


# ---------------------------------------------------------------------------
# 4. The non-negotiable check
# ---------------------------------------------------------------------------


def test_strategy_is_free_of_lookahead(
    frames_long: Dict[str, pd.DataFrame], frames_short: Dict[str, pd.DataFrame]
) -> None:
    """§9 / hard rule 1. Both series fire inside the probe's comparison windows
    (bar 25 of 40, warmup 20), so the probe is comparing real orders rather than
    emptiness to emptiness."""
    assert_no_lookahead_v2(_FixtureWarmup(), frames_long)
    assert_no_lookahead_v2(_FixtureWarmup(), frames_short)
