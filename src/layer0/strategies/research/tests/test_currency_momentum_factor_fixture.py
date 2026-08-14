"""GOLDEN FIXTURE — currency_momentum_factor (SPEC-currency_momentum_factor.md).

Every expected number below is derived from the spec by hand, with the
arithmetic shown, so the assertions test the spec rather than testing that the
code equals itself.

Assertion -> spec rule map
--------------------------
* ``test_emits_one_order_per_month_long_then_short``
      §8.1 monthly cadence (as implemented per NOTE 2 of the strategy module:
      the first D1 bar of each calendar month), §8.3 one decision per month,
      §4 long side, §5 short side.
* ``test_decisions_only_on_the_first_bar_of_a_month``
      §8.1 — every other D1 bar emits nothing.
* ``test_long_order_matches_hand_computed_arithmetic``
      §4 (direction, market entry, size_fraction 1/3), §6 (stop =
      close(decision) - 3.0 x ATR(D1,14)), §7 (single MONTH_END time leg,
      bars = 21, fraction 1.0), §4.5/§10 row 6 (weights not renormalised).
* ``test_short_order_matches_hand_computed_arithmetic``
      §5 (mirror direction), §6 (stop above the decision close).
* ``test_every_order_has_one_time_leg_summing_to_one``
      §7 and fleet hard rule 4 (fractions sum to exactly 1.0).
* ``test_stop_sits_on_the_losing_side_of_the_decision_close``
      §6/§10 row 7 — the anchor is the decision close, not the (unknowable) fill.
* ``test_no_breakeven_and_no_trail``
      §6 — "move_to_breakeven_on: none", "trail: none".
* ``test_currency_momentum_inverts_for_usd_base_pairs``
      §3 — mom_c = C(t)/C(t-252)-1 for USD-quote, C(t-252)/C(t)-1 for USD-base.
* ``test_direction_mapping_equals_the_sign_of_the_pair_return``
      §4.4/§5.4 and NOTE 1 — the momentum inversion and the direction inversion
      for USD-base pairs cancel, which is what lets the single-pair path emit
      the spec's direction without knowing which pair it holds.
* ``test_five_currency_universe_nets_the_median_flat``
      §4.2-4.3, §5.3, §2 and §10 row 2 — the documented degeneracy.
* ``test_seven_currency_universe_is_not_degenerate``
      §2 — after the Wave-1 additions ranks 1-3 long, 4 flat, 5-7 short.
* ``test_exact_ties_break_by_universe_declaration_order``
      §3 — "earlier-listed currency receives the better rank".
* ``test_strategy_is_free_of_lookahead``
      Fleet hard rule 1 / §9 — the probe, on bars where the strategy fires.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.currency_momentum_factor import (
    CurrencyMomentumFactor,
    currency_momentum,
    direction_for_currency_weight,
    net_tercile_weights,
)

# ---------------------------------------------------------------------------
# 1. The bars, and why these bars
# ---------------------------------------------------------------------------
# 45 D1 business-day bars from 2020-01-01, i.e. Jan 1 -> Mar 3 2020. Chosen so
# that exactly two calendar-month boundaries fall inside the series *after* the
# lookback is warm:
#
#   bar 0  = 2020-01-01 (Wed)   ... bar 22 = 2020-01-31   (23 January bars)
#   bar 23 = 2020-02-03 (Mon)   ... bar 42 = 2020-02-28   (20 February bars)
#   bar 43 = 2020-03-02 (Mon), bar 44 = 2020-03-03
#
# The series rises 20 pips per bar to bar 23 and then falls 20 pips per bar, so
# the trailing 6-bar return (the fixture's stand-in for the 252-bar one) is
# POSITIVE at the February decision bar and NEGATIVE at the March decision bar:
# one long and one short from a single literal series.
#
# High = Close + 50 pips and Low = Close - 50 pips on every bar, and no close
# moves more than 20 pips, so the true range is 0.0100 on every bar (the 50-pip
# half-range dominates both close-to-close terms). ATR(14) of a constant true
# range is that constant, so ATR(D1,14) = 0.0100 at every bar and the §6 stop
# distance is 3.0 x 0.0100 = 0.0300 exactly — hand-checkable without simulating
# an exponential moving average.
CLOSES = [
    # January: +20 pips/bar (bars 0-23, warming the lookback and rising)
    1.1000,
    1.1020,
    1.1040,
    1.1060,
    1.1080,
    1.1100,
    1.1120,
    1.1140,
    1.1160,
    1.1180,
    1.1200,
    1.1220,
    1.1240,
    1.1260,
    1.1280,
    1.1300,
    1.1320,
    1.1340,  # bar 17 — the lookback anchor for the February decision
    1.1360,
    1.1380,
    1.1400,
    1.1420,
    1.1440,
    1.1460,  # bar 23 = 2020-02-03, first bar of February -> LONG decision
    # February onwards: -20 pips/bar
    1.1440,
    1.1420,
    1.1400,
    1.1380,
    1.1360,
    1.1340,
    1.1320,
    1.1300,
    1.1280,
    1.1260,
    1.1240,
    1.1220,
    1.1200,
    1.1180,  # bar 37 — the lookback anchor for the March decision
    1.1160,
    1.1140,
    1.1120,
    1.1100,
    1.1080,
    1.1060,  # bar 43 = 2020-03-02, first bar of March -> SHORT decision
    1.1040,
]

HALF_RANGE = 0.0050  # High/Low offset, so true range = 0.0100 on every bar
EXPECTED_ATR = 0.0100  # ATR(14) of a constant true range
EXPECTED_STOP_DISTANCE = 0.0300  # §6: 3.0 x ATR(D1,14) = 3.0 x 0.0100
ONE_THIRD = 1.0 / 3.0


class _FixtureScale(CurrencyMomentumFactor):
    """Production logic, fixture-sized lookback.

    Only the 252-bar momentum window is shrunk (45 bars cannot warm it), which
    also shrinks ``warmup_bars`` because the strategy derives it from the same
    constant. ATR_PERIOD, STOP_ATR_MULTIPLE, HOLD_BARS and TERCILE_WEIGHT are
    the production values — no level formula and no logic is changed.
    """

    LOOKBACK_BARS = 6


@pytest.fixture(scope="module")
def frames() -> dict:
    idx = pd.date_range("2020-01-01", periods=len(CLOSES), freq="B", tz="UTC")
    d1 = pd.DataFrame(
        {
            "Open": CLOSES,
            "High": [c + HALF_RANGE for c in CLOSES],
            "Low": [c - HALF_RANGE for c in CLOSES],
            "Close": CLOSES,
            "Volume": 1.0,
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


def test_emits_one_order_per_month_long_then_short(orders) -> None:
    """§8.1/§8.3: exactly one decision per calendar month, on its first bar.

    Bar 0 (2020-01-01) is also a month's first bar but has no lookback history
    (§8.2 needs 7 closed bars at fixture scale), so January emits nothing.
    """
    assert [str(o.decision_bar) for o in orders] == [
        "2020-02-03 00:00:00+00:00",
        "2020-03-02 00:00:00+00:00",
    ]
    assert [o.direction for o in orders] == [1, -1]


def test_decisions_only_on_the_first_bar_of_a_month(frames, orders) -> None:
    """§8.1: no order may carry a decision bar that shares a month with its
    predecessor — every non-cadence D1 bar emits nothing."""
    index = frames["D1"].index
    position = {ts: i for i, ts in enumerate(index)}
    for o in orders:
        i = position[o.decision_bar]
        assert i > 0
        assert index[i].month != index[i - 1].month


def test_long_order_matches_hand_computed_arithmetic(orders) -> None:
    """The February leg, derived from the spec — not copied from output.

    At bar 23 = 2020-02-03 (close 1.1460), lookback anchor bar 17 (close 1.1340):

      pair 6-bar return = 1.1460 / 1.1340 - 1 = +0.010582...  > 0
        -> the currency appreciated against the dollar -> long (§4.4, NOTE 1)
      ATR(D1,14)        = 0.0100                        (constant true range)
      stop  = close(decision) - 3.0 x ATR = 1.1460 - 0.0300 = 1.1160   (§6)
      exits = [MONTH_END, fraction 1.0, kind="time", bars = 21]         (§7)
      size_fraction = 1/3                                              (§4.5)
    """
    o = orders[0]

    assert o.direction == 1
    assert o.entry == "market"  # §4: market entry, fills at t+1 open (F1/F2)
    assert o.entry_price is None  # contract: market entries carry no price
    assert o.expires_after_bars is None  # §4: n/a for a market entry
    assert o.decision_close == pytest.approx(1.1460, abs=1e-9)
    assert o.stop.price == pytest.approx(1.1160, abs=1e-9)
    assert o.decision_close - o.stop.price == pytest.approx(
        EXPECTED_STOP_DISTANCE, abs=1e-9
    )
    assert o.size_fraction == pytest.approx(ONE_THIRD, abs=1e-12)

    assert [leg.label for leg in o.exits] == ["MONTH_END"]
    leg = o.exits[0]
    assert leg.kind == "time"
    assert leg.bars == 21
    assert leg.fraction == pytest.approx(1.0, abs=1e-9)
    assert leg.price is None and leg.atr_multiple is None and leg.pips is None


def test_short_order_matches_hand_computed_arithmetic(orders) -> None:
    """The March leg — the mirror of §4, per §5.

    At bar 43 = 2020-03-02 (close 1.1060), lookback anchor bar 37 (close 1.1180):

      pair 6-bar return = 1.1060 / 1.1180 - 1 = -0.010733...  < 0
        -> the currency depreciated against the dollar -> short (§5.4, NOTE 1)
      stop  = close(decision) + 3.0 x ATR = 1.1060 + 0.0300 = 1.1360   (§6)
    """
    o = orders[1]

    assert o.direction == -1
    assert o.entry == "market"
    assert o.entry_price is None
    assert o.decision_close == pytest.approx(1.1060, abs=1e-9)
    assert o.stop.price == pytest.approx(1.1360, abs=1e-9)
    assert o.stop.price - o.decision_close == pytest.approx(
        EXPECTED_STOP_DISTANCE, abs=1e-9
    )
    assert o.size_fraction == pytest.approx(ONE_THIRD, abs=1e-12)
    assert [leg.label for leg in o.exits] == ["MONTH_END"]
    assert o.exits[0].bars == 21


def test_every_order_has_one_time_leg_summing_to_one(orders) -> None:
    """§7 + fleet hard rule 4: one leg, fraction exactly 1.0."""
    assert orders
    for o in orders:
        assert len(o.exits) == 1
        assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)


def test_stop_sits_on_the_losing_side_of_the_decision_close(orders) -> None:
    """§6/§10 row 7: the 3xATR anchor is the decision close (knowable at
    emission), so the stop must be below it for longs and above it for shorts."""
    for o in orders:
        assert o.decision_close is not None
        if o.direction == 1:
            assert o.stop.price < o.decision_close
        else:
            assert o.stop.price > o.decision_close


def test_no_breakeven_and_no_trail(orders) -> None:
    """§6: "move_to_breakeven_on: none", "trail: none"."""
    for o in orders:
        assert o.stop.move_to_breakeven_on is None
        assert o.stop.trail_atr_multiple is None
        assert o.stop.breakeven_offset_pips == 0.0


# ---------------------------------------------------------------------------
# The cross-sectional core (§3, §4.2-4.3, §5.3). Not reachable from
# generate_orders under the single-pair interface — see the strategy module's
# docstring — so it is pinned directly here.
# ---------------------------------------------------------------------------


def test_currency_momentum_inverts_for_usd_base_pairs() -> None:
    """§3: USD-quote uses C(t)/C(t-252)-1; USD-base uses C(t-252)/C(t)-1.

    EUR_USD 1.1000 -> 1.2100:  1.2100/1.1000 - 1 = +0.10  (EUR appreciated)
    USD_JPY 100.00 -> 110.00:  100.00/110.00 - 1 = -0.0909090909...
                               (the yen DEPRECIATED while the pair rose)
    """
    assert currency_momentum(1.1000, 1.2100, usd_base=False) == pytest.approx(
        0.10, abs=1e-12
    )
    assert currency_momentum(100.0, 110.0, usd_base=True) == pytest.approx(
        100.0 / 110.0 - 1.0, abs=1e-12
    )
    assert currency_momentum(100.0, 110.0, usd_base=True) < 0.0


def test_direction_mapping_equals_the_sign_of_the_pair_return() -> None:
    """§4.4/§5.4 + NOTE 1: the two inversions for USD-base pairs cancel.

    For a currency whose momentum puts it in the long tercile (weight +1/3) or
    the short tercile (weight -1/3), the emitted pair direction always equals
    the sign of the PAIR's own 12-month return:

      EUR_USD up   -> mom_EUR > 0 -> long EUR  -> +1 == sign(+)
      EUR_USD down -> mom_EUR < 0 -> short EUR -> -1 == sign(-)
      USD_JPY up   -> mom_JPY < 0 -> short JPY -> +1 == sign(+)
      USD_JPY down -> mom_JPY > 0 -> long JPY  -> -1 == sign(-)
    """
    cases = [
        # (close_then, close_now, usd_base)
        (1.1000, 1.2100, False),
        (1.2100, 1.1000, False),
        (100.0, 110.0, True),
        (110.0, 100.0, True),
    ]
    for close_then, close_now, usd_base in cases:
        mom = currency_momentum(close_then, close_now, usd_base=usd_base)
        weight = ONE_THIRD if mom > 0 else -ONE_THIRD
        direction = direction_for_currency_weight(weight, usd_base=usd_base)
        pair_return = close_now / close_then - 1.0
        assert direction == (1 if pair_return > 0 else -1)


def test_five_currency_universe_nets_the_median_flat() -> None:
    """§4.2-4.3 / §5.3 / §10 row 2 — the documented degeneracy.

    mom: EUR +0.10, GBP +0.05, JPY 0.00, AUD -0.05, CAD -0.10
    ranks (descending): EUR 1, GBP 2, JPY 3, AUD 4, CAD 5;  |U| = 5
    top3    = {rank <= 3}       = {EUR, GBP, JPY}
    bottom3 = {rank >= |U| - 2} = {rank >= 3} = {JPY, AUD, CAD}
    w_c = 1/3 * [top3] - 1/3 * [bottom3]:
      EUR +1/3, GBP +1/3, JPY 1/3 - 1/3 = 0, AUD -1/3, CAD -1/3
    -> long-2 / short-2 with the median currency flat and NO order on its pair.
    """
    weights = net_tercile_weights(
        {"EUR": 0.10, "GBP": 0.05, "JPY": 0.00, "AUD": -0.05, "CAD": -0.10}
    )
    assert weights["EUR"] == pytest.approx(ONE_THIRD, abs=1e-12)
    assert weights["GBP"] == pytest.approx(ONE_THIRD, abs=1e-12)
    assert weights["JPY"] == 0.0  # exact: the legs cancel, so no order is emitted
    assert weights["AUD"] == pytest.approx(-ONE_THIRD, abs=1e-12)
    assert weights["CAD"] == pytest.approx(-ONE_THIRD, abs=1e-12)
    assert sum(weights.values()) == pytest.approx(0.0, abs=1e-12)


def test_seven_currency_universe_is_not_degenerate() -> None:
    """§2: with the Wave-1 additions (|U| = 7) ranks 1-3 long, 4 flat, 5-7 short.

    mom: EUR +0.12 (1), GBP +0.09 (2), JPY +0.06 (3), AUD +0.03 (4),
         CAD -0.03 (5), NZD -0.06 (6), CHF -0.09 (7);  bottom3 = {rank >= 5}
    """
    weights = net_tercile_weights(
        {
            "EUR": 0.12,
            "GBP": 0.09,
            "JPY": 0.06,
            "AUD": 0.03,
            "CAD": -0.03,
            "NZD": -0.06,
            "CHF": -0.09,
        }
    )
    assert [weights[c] for c in ("EUR", "GBP", "JPY")] == pytest.approx(
        [ONE_THIRD] * 3, abs=1e-12
    )
    assert weights["AUD"] == 0.0
    assert [weights[c] for c in ("CAD", "NZD", "CHF")] == pytest.approx(
        [-ONE_THIRD] * 3, abs=1e-12
    )


def test_exact_ties_break_by_universe_declaration_order() -> None:
    """§3: on an exact tie the earlier-listed currency takes the better rank.

    Universe order is (EUR, GBP, JPY, AUD, CAD, NZD, CHF). With JPY and AUD tied
    at 0.00 on a 5-currency universe, JPY takes rank 3 (net 0) and AUD rank 4
    (short); reversing the tie-break would flip which pair trades.
    """
    weights = net_tercile_weights(
        {"EUR": 0.10, "GBP": 0.05, "JPY": 0.00, "AUD": 0.00, "CAD": -0.10}
    )
    assert weights["JPY"] == 0.0
    assert weights["AUD"] == pytest.approx(-ONE_THIRD, abs=1e-12)


# ---------------------------------------------------------------------------
# 4. The non-negotiable check
# ---------------------------------------------------------------------------


def test_strategy_is_free_of_lookahead(frames) -> None:
    """Fleet hard rule 1 / §9. The probe's windows cover the February order, so
    it is re-emitted from truncated frames and compared — it is not comparing
    emptiness to emptiness."""
    assert_no_lookahead_v2(_FixtureScale(), frames)
