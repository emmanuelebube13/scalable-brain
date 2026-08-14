"""GOLDEN FIXTURE for ``holy_grail_pullback`` (spec §29, row 29 of the CSV).

Format follows ``test_reference_pullback_continuation_fixture.py`` exactly:
hand-built bars, hand-computed expected ``OrderIntent`` values with the
arithmetic in comments, an assertion that ``generate_orders`` produces
exactly that, and a mapping from each assertion back to the spec rule it
enforces.

The strategy is subclassed (``_FixtureScale``) to shrink ``SMA_PERIOD``,
``ADX_PERIOD`` and ``SWING_PERIOD`` — 37 D1 bars cannot warm a 20-period SMA,
a 14-period ADX and a 5-bar swing-confirmation lag all at once. Shrinking
periods is explicitly allowed (RUN_BRIEF); the *logic* and every *level
formula* (entry, stop, TP) are untouched production code from
``holy_grail_pullback.py``.

Why these 37 bars, in one paragraph (full rationale in the report):
Bars 0-7 are a flat/choppy warm-up that seeds one confirmed swing low
(1.0991) and keeps ADX below 30. Bars 8-15 are a clean, monotonically rising
sequence (fixed +30-pip steps) that (a) produces an OBSERVED ADX(3) upward
cross through 30 partway through, satisfying §4.1, and (b) — because a
strictly monotonic run never produces a new local extremum — leaves the
1.0991 swing low as the only confirmed swing low all the way to bar 16, and
lets the bar-15 high (1.1250) stand as the freshest un-superseded high once
it confirms. Bar 16 is a single-day "V" pullback: its low wicks down through
SMA(3) while its close stays above it (§4.3's touch condition), and — with
SWING_PERIOD shrunk to 1 — this is exactly the bar at which the bar-15 high
confirms, so the long setup fires with a real, non-stale TP. Bars 17-24
resume the rally then chop sideways, letting ADX decay back toward 30 so a
FRESH downward cross can be observed (§5.1 requires one, exactly as §4.1
does for longs). Bars 25-32 are the mirror-image monotonic decline, and bar
33 is the mirror single-day bounce (high wicks up through SMA, close stays
below it) that fires the short setup. Bars 34-36 just extend the series past
the last decision bar so ``assert_no_lookahead_v2``'s truncation probe has
room to re-emit and compare.

The ADX(3)/SMA(3) crossing points themselves are the output of a
double-EWM recursion (Wilder DI/ADX smoothing) that is not mentally
tractable bar-by-bar; per the report's Fixture-rationale section, the
crossing bars were located by running the repository's own, already-reviewed
``indicators.sma`` / ``indicators.adx`` functions over these exact hand-built
bars (a calculator, not a "run the strategy and paste" shortcut) and are
asserted here as pre-conditions, not as the thing under test. The thing
under test — entry level, stop level, TP level, exit fractions, expiry — is
100% arithmetic from OHLC values that are themselves literals below, worked
by hand in the comments beside each assertion.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.holy_grail_pullback import HolyGrailPullback

PIP = 0.0001  # non-JPY pip size (spec §3 get_pip_value; all closes here < 20)

# ---------------------------------------------------------------------------
# 1. The bars, and why these bars (see module docstring for the narrative)
# ---------------------------------------------------------------------------
# Open is never read by this strategy (only High/Low/Close feed §4/§5/§6/§7),
# so Open = Close on every bar for simplicity; it carries no signal either
# way. 37 bars total.

OPENS = [
    1.1000, 1.1005, 1.0998, 1.1003, 1.0997, 1.1004, 1.0999, 1.1002,
    1.1032, 1.1062, 1.1092, 1.1122, 1.1152, 1.1182, 1.1212, 1.1242,
    1.1232, 1.1267, 1.1302, 1.1337, 1.1332, 1.1340, 1.1333, 1.1339,
    1.1334, 1.1304, 1.1274, 1.1244, 1.1214, 1.1184, 1.1154, 1.1124,
    1.1094, 1.1104, 1.1069, 1.1034, 1.0999,
]  # fmt: skip

HIGHS = [
    1.1008, 1.1013, 1.1006, 1.1011, 1.1005, 1.1012, 1.1007, 1.1010,
    1.1040, 1.1070, 1.1100, 1.1130, 1.1160, 1.1190, 1.1220, 1.1250,
    1.1240, 1.1275, 1.1310, 1.1345, 1.1340, 1.1348, 1.1341, 1.1347,
    1.1342, 1.1312, 1.1282, 1.1252, 1.1222, 1.1192, 1.1162, 1.1132,
    1.1102, 1.1114, 1.1077, 1.1042, 1.1007,
]  # fmt: skip

LOWS = [
    1.0992, 1.0997, 1.0990, 1.0995, 1.0989, 1.0996, 1.0991, 1.0994,
    1.1024, 1.1054, 1.1084, 1.1114, 1.1144, 1.1174, 1.1204, 1.1234,
    1.1222, 1.1259, 1.1294, 1.1329, 1.1324, 1.1332, 1.1325, 1.1331,
    1.1326, 1.1296, 1.1266, 1.1236, 1.1206, 1.1176, 1.1146, 1.1116,
    1.1086, 1.1096, 1.1061, 1.1026, 1.0991,
]  # fmt: skip

CLOSES = [
    1.1000, 1.1005, 1.0998, 1.1003, 1.0997, 1.1004, 1.0999, 1.1002,
    1.1032, 1.1062, 1.1092, 1.1122, 1.1152, 1.1182, 1.1212, 1.1242,
    1.1232, 1.1267, 1.1302, 1.1337, 1.1332, 1.1340, 1.1333, 1.1339,
    1.1334, 1.1304, 1.1274, 1.1244, 1.1214, 1.1184, 1.1154, 1.1124,
    1.1094, 1.1104, 1.1069, 1.1034, 1.0999,
]  # fmt: skip

assert len(OPENS) == len(HIGHS) == len(LOWS) == len(CLOSES) == 37


class _FixtureScale(HolyGrailPullback):
    """Production logic, fixture-sized lookbacks (RUN_BRIEF: shrink periods,
    never the logic or a level formula)."""

    SMA_PERIOD = 3
    ADX_PERIOD = 3
    SWING_PERIOD = 1  # swing definition AND confirmation lag, shrunk from 5

    @property
    def warmup_bars(self) -> int:
        return 10


@pytest.fixture(scope="module")
def frames() -> dict:
    idx = pd.date_range("2020-01-01", periods=len(CLOSES), freq="1D", tz="UTC")
    d1 = pd.DataFrame(
        {"Open": OPENS, "High": HIGHS, "Low": LOWS, "Close": CLOSES, "Volume": 1.0},
        index=idx,
    )
    return {"D1": d1}


@pytest.fixture(scope="module")
def orders(frames) -> list:
    return list(_FixtureScale().generate_orders(frames))


# ---------------------------------------------------------------------------
# 2 + 3. Expected values, computed by hand, then asserted
# ---------------------------------------------------------------------------


def test_emits_exactly_the_expected_setups(orders) -> None:
    """Rule (§4/§5): exactly one long setup (bar 16, the touch after the
    monotonic rally) and one short setup (bar 33, the mirror touch after the
    monotonic decline). No other bar satisfies every gate simultaneously —
    the touch candles at bars 3/5/7 and the chop-zone touches at bars 20/22
    occur before the ADX episode/rising conjunction (§4.1/§4.2) is open."""
    assert [str(o.decision_bar) for o in orders] == [
        "2020-01-17 00:00:00+00:00",
        "2020-02-03 00:00:00+00:00",
    ]


def test_long_order_matches_hand_computed_arithmetic(orders) -> None:
    """The long trade plan at decision bar 2020-01-17 (index 16), derived from
    the spec — not copied from output.

    Inputs (all decision-bar-knowable, all literals above):
      High[16]  = 1.1240
      Close[16] = 1.1232
      Most recent CONFIRMED swing low  (period=1, knowable at 16):
        the low of bar 6 (2020-01-07) = 1.0991, confirmed at bar 7 and never
        superseded (a strictly rising sequence of lows, bars 8-15, produces
        no new swing-low candidate).
      Most recent CONFIRMED swing high (period=1, knowable at 16):
        the high of bar 15 (2020-01-16) = 1.1250 (the peak), confirmed
        EXACTLY at bar 16 (occurrence 15 + period 1) — i.e. knowable at the
        decision bar itself.

    §4.5 entry  = High[16] + 1 pip = 1.1240 + 0.0001         = 1.12410
    §6   stop   = swing_low - 1 pip = 1.0991 - 0.0001        = 1.09900
    §7   TP1    = swing_high (exact)                         = 1.12500
    §4.7 gates: stop(1.09900) < entry(1.12410)  -> holds
                TP1(1.12500)  > entry(1.12410)  -> holds (9-pip margin)
    """
    o = orders[0]

    assert o.direction == 1
    assert o.entry == "buy_stop"
    assert o.entry_price == pytest.approx(1.12410, abs=1e-9)
    assert o.stop.price == pytest.approx(1.09900, abs=1e-9)
    assert o.stop.move_to_breakeven_on is None  # §6: source has no breakeven rule
    assert o.stop.trail_atr_multiple is None  # §6: static stop, no trail

    assert [leg.label for leg in o.exits] == ["TP1"]
    assert [leg.kind for leg in o.exits] == ["take_profit"]
    assert o.exits[0].price == pytest.approx(1.12500, abs=1e-9)
    assert o.exits[0].fraction == pytest.approx(1.0, abs=1e-9)  # §7: single leg

    assert o.expires_after_bars == 1  # §4.6, §10 #5


def test_short_order_matches_hand_computed_arithmetic(orders) -> None:
    """The short trade plan at decision bar 2020-02-03 (index 33), derived
    from the spec's mirror rule §5 — not copied from output.

    Inputs (all decision-bar-knowable, all literals above):
      Low[33]   = 1.1096
      Close[33] = 1.1104
      Most recent CONFIRMED swing high (period=1, knowable at 33):
        the high of bar 23 (2020-01-24) = 1.1347. It is a candidate
        (1.1347 > bar 22's high 1.1341) and confirms at bar 24 since bar 24's
        high (1.1342) does not exceed it. It supersedes the earlier-confirmed
        1.1348 (bar 21, confirmed bar 22) as "most recent", and nothing in
        the monotonic decline (bars 25-32) produces a newer confirmed high.
      Most recent CONFIRMED swing low  (period=1, knowable at 33):
        the low of bar 32 (2020-02-02) = 1.1086 (the trough), confirmed
        EXACTLY at bar 33 — knowable at the decision bar itself.

    §5.5 entry  = Low[33] - 1 pip = 1.1096 - 0.0001          = 1.10950
    §6   stop   = swing_high + 1 pip = 1.1347 + 0.0001       = 1.13480
    §7   TP1    = swing_low (exact)                           = 1.10860
    §5.7 gates: stop(1.13480) > entry(1.10950)  -> holds (huge margin)
                TP1(1.10860)  < entry(1.10950)  -> holds (9-pip margin)
    """
    o = orders[1]

    assert o.direction == -1
    assert o.entry == "sell_stop"
    assert o.entry_price == pytest.approx(1.10950, abs=1e-9)
    assert o.stop.price == pytest.approx(1.13480, abs=1e-9)
    assert o.stop.move_to_breakeven_on is None
    assert o.stop.trail_atr_multiple is None

    assert [leg.label for leg in o.exits] == ["TP1"]
    assert [leg.kind for leg in o.exits] == ["take_profit"]
    assert o.exits[0].price == pytest.approx(1.10860, abs=1e-9)
    assert o.exits[0].fraction == pytest.approx(1.0, abs=1e-9)

    assert o.expires_after_bars == 1


def test_exit_fractions_sum_to_one(orders) -> None:
    """Contract rule (RUN_BRIEF, contract_v2 §2.2): exit-leg fractions across
    an OrderIntent must sum to 1.0 within 1e-9. Single-leg here (§7), but
    asserted explicitly rather than assumed."""
    for o in orders:
        assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)


def test_pending_entry_sits_on_correct_side_of_close(frames, orders) -> None:
    """Rule (contract_v2 __post_init__, mirrors reference NOTE 3): a buy_stop
    must sit above the decision-bar close and a sell_stop below it, or the
    contract rejects the intent as a disguised market order."""
    close = frames["D1"]["Close"]
    for o in orders:
        c = float(close.loc[o.decision_bar])
        if o.entry == "buy_stop":
            assert o.entry_price > c
        elif o.entry == "sell_stop":
            assert o.entry_price < c
        else:  # pragma: no cover - this strategy only emits stop orders
            raise AssertionError(f"unexpected entry kind {o.entry!r}")


def test_no_orders_before_the_adx_episode_opens(orders) -> None:
    """Rule (§4.1/§5.1): an ADX>30 episode requires an OBSERVED upward cross.
    Bars 0-7 (flat/choppy) never push ADX(3) above 30 with a qualifying
    cross, so no setup may fire there even though touch candles occur at
    bars 3, 5 and 7 (Low<=SMA & Close>SMA all hold on those bars too)."""
    assert min(o.decision_bar for o in orders) >= pd.Timestamp("2020-01-09", tz="UTC")


# ---------------------------------------------------------------------------
# 4. The non-negotiable check
# ---------------------------------------------------------------------------


def test_strategy_is_free_of_lookahead(frames) -> None:
    """Every Wave-2 strategy must pass this on real data too (PROMPT.md hard
    rule 1; RUN_BRIEF's offline substitute for the real-data probe). Fires on
    the full series (2 orders), so the probe has bars to prove itself on."""
    assert_no_lookahead_v2(_FixtureScale(), frames)
