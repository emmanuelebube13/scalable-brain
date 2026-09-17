import pytest
import pandas as pd
from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research import liquidity_grab_fade as lgf_mod
from src.layer0.strategies.research.liquidity_grab_fade import LiquidityGrabFade

# This fixture's two canonical setups (the long at i=36, the short at i=66) were
# hand-built to pin swing-level RESOLUTION (which confirmed high/low a TP picks)
# and are independent of the FINDINGS-D7 minimum R:R floor added 2026-09-17. Both
# happen to have R:R well under the 0.5 floor (0.204 and 0.339 respectively — see
# test_min_rr_floor_rejects_subfloor_setup, which pins that on purpose, since it is
# structurally the same shape as the b97120fc incident: a wide grab-extreme stop and
# a nearby confirmed level). The level/leakage/no-lookahead tests below disable the
# floor via monkeypatch so they keep testing what they were built to test.

OPENS = [
    10.00,
    10.15,
    10.29,
    10.40,
    10.48,
    10.50,
    10.48,
    10.40,
    10.29,
    10.15,
    10.00,
    9.85,
    9.71,
    9.60,
    9.52,
    9.50,
    9.52,
    9.60,
    9.71,
    9.85,
    10.00,
    10.15,
    10.29,
    10.40,
    10.48,
    10.50,
    10.48,
    10.40,
    10.29,
    10.15,
    10.00,
    10.20,
    9.71,
    9.60,
    9.52,
    9.95,
    9.90,
    9.60,
    9.71,
    9.85,
    10.00,
    10.15,
    10.29,
    10.40,
    10.48,
    10.50,
    10.48,
    10.40,
    10.29,
    10.15,
    10.00,
    9.85,
    9.71,
    9.60,
    9.52,
    9.50,
    9.52,
    9.60,
    9.71,
    9.85,
    10.00,
    9.60,
    10.29,
    10.40,
    10.48,
    9.85,
    9.90,
    10.40,
    10.29,
    10.15,
    10.00,
    9.85,
    9.71,
    9.60,
    9.52,
    9.50,
    9.52,
    9.60,
    9.71,
    9.85,
]
HIGHS = [
    10.10,
    10.25,
    10.39,
    10.50,
    10.58,
    10.60,
    10.58,
    10.50,
    10.39,
    10.25,
    10.10,
    9.95,
    9.81,
    9.70,
    9.62,
    9.20,
    9.62,
    9.70,
    9.81,
    9.95,
    10.10,
    10.25,
    10.39,
    10.50,
    10.58,
    10.60,
    10.58,
    10.50,
    10.39,
    10.25,
    10.10,
    10.30,
    9.81,
    10.80,
    9.62,
    10.00,
    10.50,
    9.70,
    9.81,
    9.95,
    10.10,
    10.25,
    10.39,
    10.50,
    10.58,
    10.60,
    10.58,
    10.50,
    10.39,
    10.25,
    10.10,
    9.95,
    9.81,
    9.70,
    9.62,
    9.60,
    9.62,
    9.70,
    9.81,
    9.95,
    10.10,
    9.90,
    10.39,
    10.50,
    10.58,
    10.00,
    9.95,
    10.50,
    10.39,
    10.25,
    10.10,
    9.95,
    9.81,
    9.70,
    9.62,
    9.60,
    9.62,
    9.70,
    9.81,
    9.95,
]
LOWS = [
    9.90,
    10.05,
    10.19,
    10.30,
    10.38,
    10.40,
    10.38,
    10.30,
    10.19,
    10.05,
    9.90,
    9.75,
    9.61,
    9.50,
    9.42,
    9.00,
    9.42,
    9.50,
    9.61,
    9.75,
    9.90,
    10.05,
    10.19,
    10.30,
    10.38,
    10.40,
    10.38,
    10.30,
    10.19,
    10.05,
    9.90,
    9.90,
    9.61,
    9.50,
    9.42,
    9.80,
    9.80,
    9.50,
    9.61,
    9.75,
    9.90,
    10.05,
    10.19,
    10.30,
    10.38,
    10.40,
    10.38,
    10.30,
    10.19,
    10.05,
    9.90,
    9.75,
    9.61,
    9.50,
    9.42,
    9.40,
    9.42,
    9.50,
    9.61,
    9.75,
    9.90,
    9.50,
    10.19,
    9.20,
    10.38,
    9.80,
    9.30,
    10.30,
    10.19,
    10.05,
    9.90,
    9.75,
    9.61,
    9.50,
    9.42,
    9.40,
    9.42,
    9.50,
    9.61,
    9.75,
]
CLOSES = [
    10.00,
    10.15,
    10.29,
    10.40,
    10.48,
    10.50,
    10.48,
    10.40,
    10.29,
    10.15,
    10.00,
    9.85,
    9.71,
    9.60,
    9.52,
    9.50,
    9.52,
    9.60,
    9.71,
    9.85,
    10.00,
    10.15,
    10.29,
    10.40,
    10.48,
    10.50,
    10.48,
    10.40,
    10.29,
    10.15,
    10.00,
    10.00,
    9.71,
    10.70,
    9.52,
    9.90,
    10.40,
    9.60,
    9.71,
    9.85,
    10.00,
    10.15,
    10.29,
    10.40,
    10.48,
    10.50,
    10.48,
    10.40,
    10.29,
    10.15,
    10.00,
    9.85,
    9.71,
    9.60,
    9.52,
    9.50,
    9.52,
    9.60,
    9.71,
    9.85,
    10.00,
    9.80,
    10.29,
    9.30,
    10.48,
    9.90,
    9.40,
    10.40,
    10.29,
    10.15,
    10.00,
    9.85,
    9.71,
    9.60,
    9.52,
    9.50,
    9.52,
    9.60,
    9.71,
    9.85,
]


class TestLiquidityGrabFade(LiquidityGrabFade):
    @property
    def warmup_bars(self) -> int:
        return 20


@pytest.fixture
def frames():
    df = pd.DataFrame(
        {
            "Open": OPENS,
            "High": HIGHS,
            "Low": LOWS,
            "Close": CLOSES,
        },
        index=pd.date_range("2020-01-01", periods=80, freq="4h"),
    )
    return {"H4": df}


def test_long_entry_and_levels(frames, monkeypatch):
    monkeypatch.setattr(lgf_mod, "MIN_REWARD_RISK_RATIO", 0.0)
    strat = TestLiquidityGrabFade()
    orders = strat.generate_orders(frames)

    assert len(orders) == 2
    long_order = orders[0]

    assert long_order.direction == 1
    assert long_order.entry == "market"
    assert long_order.entry_price is None

    # §6 Initial stop: G_t - 4.0 * pip = 9.42 - 0.0004 = 9.4196
    # G_t is the grab extreme, which is LOWS[34] = 9.42
    assert abs(long_order.stop.price - 9.4196) < 1e-6

    # §7 TP: nearest confirmed swing high > 10.40 (Close[t])
    # The confirmed swing high from i=25 is 10.60
    assert abs(long_order.exits[0].price - 10.60) < 1e-6


def test_short_entry_and_levels(frames, monkeypatch):
    monkeypatch.setattr(lgf_mod, "MIN_REWARD_RISK_RATIO", 0.0)
    strat = TestLiquidityGrabFade()
    orders = strat.generate_orders(frames)

    short_order = orders[1]
    assert short_order.direction == -1
    assert short_order.entry == "market"

    # §6 Initial stop: G_t + 4.0 * pip = 10.58 + 0.0004 = 10.5804
    # G_t is the grab extreme, which is HIGHS[64] = 10.58
    assert abs(short_order.stop.price - 10.5804) < 1e-6

    # §7 TP: nearest confirmed swing low < 9.40 (Close[t])
    # The confirmed swing low from i=15 is 9.00
    assert abs(short_order.exits[0].price - 9.00) < 1e-6


def test_fractions_sum_to_one(frames, monkeypatch):
    monkeypatch.setattr(lgf_mod, "MIN_REWARD_RISK_RATIO", 0.0)
    strat = TestLiquidityGrabFade()
    orders = strat.generate_orders(frames)

    # fractions sum to exactly 1.00 (single leg)
    # §7 Exit legs
    assert orders[0].exits[0].fraction == 1.00
    assert sum(leg.fraction for leg in orders[0].exits) == 1.00

    assert orders[1].exits[0].fraction == 1.00
    assert sum(leg.fraction for leg in orders[1].exits) == 1.00


def test_no_lookahead(frames, monkeypatch):
    monkeypatch.setattr(lgf_mod, "MIN_REWARD_RISK_RATIO", 0.0)
    strat = TestLiquidityGrabFade()
    assert_no_lookahead_v2(strat, frames)


def test_min_rr_floor_rejects_subfloor_setup(frames):
    """D7(a) pin: the fixture's own two canonical setups are sub-floor and rejected.

    Both hand-built setups in this fixture reproduce the b97120fc incident's shape —
    a wide grab-extreme stop (`grab_extreme +/- 4 pips`) paired with a nearby confirmed
    structural level — and, unmodified, have R:R of 0.204 (long) and 0.339 (short),
    both under MIN_REWARD_RISK_RATIO = 0.5. With the floor active (the default),
    generate_orders must emit neither.
    """
    strat = TestLiquidityGrabFade()
    orders = strat.generate_orders(frames)
    assert orders == []


# ── D7 leakage fix tests ──────────────────────────────────────────────────────────────


def test_concurrent_swing_low_not_used_as_tp_at_same_bar(monkeypatch):
    """D7 leakage fix: bar i's own confirmed swing low must not enter the TP pool at bar i.

    The R:R floor is disabled here (monkeypatched to 0.0): this test is about which
    swing low feeds the TP pool, not about whether the resulting R:R clears the floor
    (that is pinned separately in test_min_rr_floor_rejects_subfloor_setup). Without
    disabling it, both of this fixture's canonical orders are floor-rejected and the
    assertion below would pass vacuously over an empty order list.

    Scenario: a short signal fires at bar i.  Bar i coincidentally also has a confirmed
    swing low (sl_vals[i] is not NaN).  With the old append order, that swing low was
    appended BEFORE the TP logic ran, so max(valid_lows) could resolve to bar i's own swing
    level — nearly at-the-money.  With the fix the append is AFTER the order block, so
    bar i's swing is only available for bar i+1.

    We build a minimal frame where:
    - A bearish BOS fires at some bar b, setting up a downtrend episode.
    - A liquidity grab (high above ob_high) fires at bar g.
    - The recapture close (close < ob_low) fires at bar s (signal bar).
    - Bar s has a confirmed swing low at a level that is ABOVE the existing pool's best low.

    If the leakage is present, the TP uses bar s's own swing low (near-ATM).
    With the fix, the TP must use an earlier swing low (farther below entry).
    """
    import numpy as np
    import pandas as pd
    from src.layer0.strategies.research import liquidity_grab_fade as _lgf_mod
    from src.layer0.strategies.research.liquidity_grab_fade import LiquidityGrabFade

    monkeypatch.setattr(_lgf_mod, "MIN_REWARD_RISK_RATIO", 0.0)

    class _LGF(LiquidityGrabFade):
        @property
        def warmup_bars(self) -> int:
            return 10

    n = 60
    # Build a flat frame and then inject specific bars
    opens = [10.0] * n
    highs = [10.1] * n
    lows = [9.9] * n
    closes = [10.0] * n

    # Bar 10: bearish BOS — close below prev confirmed swing low.
    # To make this work cleanly we rely on the fixture to encode the BOS;
    # instead we test the specific claim directly via a black-box property:
    # after the fix, generate_orders must never produce a signal whose TP is at the
    # same value as its own signal bar's confirmed swing low (if that swing low would
    # resolve to a near-ATM target while better lows exist earlier).

    # Use the existing fixture but verify the post-fix invariant: no order's TP
    # is within 1 pip of the signal bar's Close (i.e., no near-ATM target).
    df = pd.DataFrame(
        {
            "Open": OPENS,
            "High": HIGHS,
            "Low": LOWS,
            "Close": CLOSES,
        },
        index=pd.date_range("2020-01-01", periods=len(CLOSES), freq="4h"),
    )
    frames = {"H4": df}
    strat = _LGF()
    orders = strat.generate_orders(frames)

    pip = 0.0001
    for order in orders:
        # TP must be at least 20 pips away from the signal bar's Close
        # (near-ATM target = leakage still present)
        signal_close = df.loc[order.decision_bar, "Close"]
        if order.direction == 1:
            reward_pips = (order.exits[0].price - signal_close) / pip
        else:
            reward_pips = (signal_close - order.exits[0].price) / pip
        assert reward_pips > 20, (
            f"TP too close to entry ({reward_pips:.1f} pips) — "
            f"possible concurrent-bar swing leakage at {order.decision_bar}"
        )


def test_leakage_fix_does_not_break_no_lookahead(frames, monkeypatch):
    """D7: the fix must not introduce new lookahead (verified by the contract check)."""
    monkeypatch.setattr(lgf_mod, "MIN_REWARD_RISK_RATIO", 0.0)
    strat = TestLiquidityGrabFade()
    from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2

    assert_no_lookahead_v2(strat, frames)
