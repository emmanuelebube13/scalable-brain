"""GOLDEN FIXTURE — daily_fib_retracement (SPEC-daily_fib_retracement, CSV row 16).

40 hand-built D1 bars. Every expected number below is derived from the spec's own
formulas with the arithmetic written out; nothing here was copied from program output.

Why these bars
--------------
The strategy needs three things to align on one fully-closed D1 bar: a non-degenerate
range (§4.1), the close on the correct side of the EMA trend filter (§4.2/§5.2), and
the close inside the 50-61.8% retracement band of that same bar's range (§4.3/§5.3 as
repaired in NOTE A of the strategy module — the band test reads Close[k]).

So the series is built in four blocks:

* bars 0-19  a clean up-ramp (+15 pips/day). Every bar closes **at its own High**, so
             Close = High > High - 0.50*rng: the band precondition fails on all of
             them and no order may exist. They exist to establish the uptrend.
* bar 20     THE LONG SETUP. High 1.11000 / Low 1.10500 / Close 1.10720 — an inside
             pullback day whose close lands in the 50-61.8% band while still holding
             above the (fixture-scaled) EMA.
* bars 21-34 a down-ramp (-15 pips/day). Every bar closes **at its own Low**, so
             Close = Low < Low + 0.50*rng: the short band precondition fails on all
             of them. They exist to roll the EMA over to the short side.
* bar 35     THE SHORT SETUP, the exact mirror. High 1.09000 / Low 1.08500 /
             Close 1.08780.
* bars 36-39 more down-ramp closing at the low: no further orders, and they give the
             look-ahead probe bars to truncate after the short setup.

That "filler bars close at their own extreme" construction is deliberate: it makes the
"exactly two orders" assertion provable from the spec by hand rather than by trust
(see `test_only_the_two_setup_bars_can_satisfy_the_band`).

Assertion -> rule map
---------------------
* `test_emits_exactly_the_two_hand_built_setups`  §4.1-4.3, §5.1-5.3 (all gates)
* `test_only_the_two_setup_bars_can_satisfy_the_band`  §4.3 / §5.3 (zone precondition)
* `test_long_order_matches_hand_computed_arithmetic`  §4 (entry type + 61.8% level),
  §6 (75% stop, breakeven on TP_382, stop does not trail), §7 (TP_382 at 38.2% and
  the ATR(1.5) TRAIL leg, fractions 0.5/0.5 = 1.0), §10 #7 (expires_after_bars = 24)
* `test_short_order_matches_hand_computed_arithmetic`  §5, §6, §7, §10 #7 (mirror)
* `test_risk_and_target_are_the_spec_fractions_of_the_range`  §6 (risk = 0.132*rng)
  and §7 note (TP_382 is 0.236*rng beyond entry)
* `test_limit_sits_on_the_far_side_of_the_decision_close`  NOTE B / contract §2.2
* `test_no_order_before_warmup`  the strategy's own warmup contract
* `test_strategy_is_free_of_lookahead`  hard rule 1 / §9

The fixture subclasses the strategy to shrink TREND_PERIOD 50 -> 5 and warmup 100 ->
10: 40 bars cannot warm a 50-period EMA. Only *periods* change — no level formula, no
fraction, no fib ratio, no logic.
"""

from __future__ import annotations

from typing import Dict, List

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.daily_fib_retracement import DailyFibRetracement

# ---------------------------------------------------------------------------
# 1. The bars, as a literal: (Open, High, Low, Close)
# ---------------------------------------------------------------------------
BARS: List[tuple] = [
    # -- bars 0-19: up-ramp, every bar closes AT ITS HIGH -> band test fails ---
    (1.07750, 1.08000, 1.07700, 1.08000),  # 0
    (1.07900, 1.08150, 1.07850, 1.08150),  # 1
    (1.08050, 1.08300, 1.08000, 1.08300),  # 2
    (1.08200, 1.08450, 1.08150, 1.08450),  # 3
    (1.08350, 1.08600, 1.08300, 1.08600),  # 4
    (1.08500, 1.08750, 1.08450, 1.08750),  # 5
    (1.08650, 1.08900, 1.08600, 1.08900),  # 6
    (1.08800, 1.09050, 1.08750, 1.09050),  # 7
    (1.08950, 1.09200, 1.08900, 1.09200),  # 8
    (1.09100, 1.09350, 1.09050, 1.09350),  # 9
    (1.09250, 1.09500, 1.09200, 1.09500),  # 10
    (1.09400, 1.09650, 1.09350, 1.09650),  # 11
    (1.09550, 1.09800, 1.09500, 1.09800),  # 12
    (1.09700, 1.09950, 1.09650, 1.09950),  # 13
    (1.09850, 1.10100, 1.09800, 1.10100),  # 14
    (1.10000, 1.10250, 1.09950, 1.10250),  # 15
    (1.10150, 1.10400, 1.10100, 1.10400),  # 16
    (1.10300, 1.10550, 1.10250, 1.10550),  # 17
    (1.10450, 1.10700, 1.10400, 1.10700),  # 18
    (1.10600, 1.10850, 1.10550, 1.10850),  # 19
    # -- bar 20: THE LONG SETUP (2020-01-21) ---------------------------------
    (1.10950, 1.11000, 1.10500, 1.10720),  # 20
    # -- bars 21-34: down-ramp, every bar closes AT ITS LOW -> band fails ----
    (1.10950, 1.11000, 1.10700, 1.10700),  # 21
    (1.10800, 1.10850, 1.10550, 1.10550),  # 22
    (1.10650, 1.10700, 1.10400, 1.10400),  # 23
    (1.10500, 1.10550, 1.10250, 1.10250),  # 24
    (1.10350, 1.10400, 1.10100, 1.10100),  # 25
    (1.10200, 1.10250, 1.09950, 1.09950),  # 26
    (1.10050, 1.10100, 1.09800, 1.09800),  # 27
    (1.09900, 1.09950, 1.09650, 1.09650),  # 28
    (1.09750, 1.09800, 1.09500, 1.09500),  # 29
    (1.09600, 1.09650, 1.09350, 1.09350),  # 30
    (1.09450, 1.09500, 1.09200, 1.09200),  # 31
    (1.09300, 1.09350, 1.09050, 1.09050),  # 32
    (1.09150, 1.09200, 1.08900, 1.08900),  # 33
    (1.09000, 1.09050, 1.08750, 1.08750),  # 34
    # -- bar 35: THE SHORT SETUP (2020-02-05) --------------------------------
    (1.08550, 1.09000, 1.08500, 1.08780),  # 35
    # -- bars 36-39: down-ramp continues, closes at the low ------------------
    (1.08850, 1.08900, 1.08600, 1.08600),  # 36
    (1.08700, 1.08750, 1.08450, 1.08450),  # 37
    (1.08550, 1.08600, 1.08300, 1.08300),  # 38
    (1.08400, 1.08450, 1.08150, 1.08150),  # 39
]

LONG_BAR = "2020-01-21 00:00:00+00:00"  # bar 20
SHORT_BAR = "2020-02-05 00:00:00+00:00"  # bar 35


class _FixtureScale(DailyFibRetracement):
    """Production logic, fixture-sized lookbacks."""

    TREND_PERIOD = 5

    @property
    def warmup_bars(self) -> int:
        return 10


@pytest.fixture(scope="module")
def frames() -> Dict[str, pd.DataFrame]:
    idx = pd.date_range("2020-01-01", periods=len(BARS), freq="1D", tz="UTC")
    d1 = pd.DataFrame(
        {
            "Open": [b[0] for b in BARS],
            "High": [b[1] for b in BARS],
            "Low": [b[2] for b in BARS],
            "Close": [b[3] for b in BARS],
            "Volume": 1.0,
        },
        index=idx,
    )
    # Spec §2: context_granularities = none. The D1 frame is the only frame.
    return {"D1": d1}


@pytest.fixture(scope="module")
def orders(frames: Dict[str, pd.DataFrame]) -> List:
    return list(_FixtureScale().generate_orders(frames))


# ---------------------------------------------------------------------------
# 2 + 3. Expected values, computed by hand, then asserted
# ---------------------------------------------------------------------------


def test_emits_exactly_the_two_hand_built_setups(orders: List) -> None:
    """§4 + §5: one long where the up-trend day closes in the band, one short
    where the down-trend day closes in the mirrored band, and nothing else."""
    assert [str(o.decision_bar) for o in orders] == [LONG_BAR, SHORT_BAR]
    assert [o.direction for o in orders] == [1, -1]


def test_only_the_two_setup_bars_can_satisfy_the_band(
    frames: Dict[str, pd.DataFrame],
) -> None:
    """§4.3 / §5.3: the zone precondition is what rejects the other 38 bars.

    Every non-setup bar closes at its own High or its own Low. For such a bar:
      Close = High  ->  Close > High - 0.50*rng, above the shallow band edge
      Close = Low   ->  Close < Low  + 0.50*rng, below the shallow band edge
    so band membership is impossible regardless of the trend filter. This makes
    the "exactly two orders" assertion above a spec consequence, not a hope.
    """
    d1 = frames["D1"]
    for ts, row in d1.iterrows():
        if str(ts) in {LONG_BAR, SHORT_BAR}:
            assert row["Low"] < row["Close"] < row["High"]
            continue
        assert row["Close"] in (row["High"], row["Low"])


def test_long_order_matches_hand_computed_arithmetic(orders: List) -> None:
    """Bar 20 (2020-01-21): High 1.11000, Low 1.10500, Close 1.10720.

    rng            = 1.11000 - 1.10500                     = 0.00500
    50.0% level    = 1.11000 - 0.500 * 0.00500 = 1.11000 - 0.00250 = 1.10750
    61.8% level    = 1.11000 - 0.618 * 0.00500 = 1.11000 - 0.00309 = 1.10691
    75.0% level    = 1.11000 - 0.750 * 0.00500 = 1.11000 - 0.00375 = 1.10625
    38.2% level    = 1.11000 - 0.382 * 0.00500 = 1.11000 - 0.00191 = 1.10809

    §4.3 band test : 1.10691 <= 1.10720 <= 1.10750                      OK
    §4   entry     = 61.8% level                                 = 1.10691
    §6   stop      = 75.0% level                                 = 1.10625
    §7   TP_382    = 38.2% level                                 = 1.10809
    §7   TRAIL     = trailing leg, atr_multiple 1.5, no price
    NOTE B         : buy_limit 1.10691 < decision close 1.10720         OK
    """
    o = orders[0]

    assert o.direction == 1
    assert o.entry == "buy_limit"
    assert o.entry_price == pytest.approx(1.10691, abs=1e-9)
    assert o.stop.price == pytest.approx(1.10625, abs=1e-9)
    assert o.decision_close == pytest.approx(1.10720, abs=1e-9)

    # §7 — two legs, in order, fractions summing to exactly 1.0.
    assert [leg.label for leg in o.exits] == ["TP_382", "TRAIL"]
    assert [leg.fraction for leg in o.exits] == pytest.approx([0.5, 0.5])
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)

    tp, trail = o.exits
    assert tp.kind == "take_profit"
    assert tp.price == pytest.approx(1.10809, abs=1e-9)
    assert trail.kind == "trailing"
    assert trail.atr_multiple == pytest.approx(1.5)
    assert trail.price is None  # a trailing leg carries a distance, never a level

    # §6 — breakeven is armed by a leg that exists; the StopRule never trails.
    assert o.stop.move_to_breakeven_on == "TP_382"
    assert o.stop.move_to_breakeven_on in {leg.label for leg in o.exits}
    assert o.stop.breakeven_offset_pips == 0.0
    assert o.stop.trail_atr_multiple is None

    # §4 / §10 #7 — one trading day of H1 resolution bars, then cancel.
    assert o.expires_after_bars == 24
    assert o.size_fraction == 1.0


def test_short_order_matches_hand_computed_arithmetic(orders: List) -> None:
    """Bar 35 (2020-02-05): High 1.09000, Low 1.08500, Close 1.08780.

    rng            = 1.09000 - 1.08500                     = 0.00500
    50.0% level    = 1.08500 + 0.500 * 0.00500 = 1.08500 + 0.00250 = 1.08750
    61.8% level    = 1.08500 + 0.618 * 0.00500 = 1.08500 + 0.00309 = 1.08809
    75.0% level    = 1.08500 + 0.750 * 0.00500 = 1.08500 + 0.00375 = 1.08875
    38.2% level    = 1.08500 + 0.382 * 0.00500 = 1.08500 + 0.00191 = 1.08691

    §5.3 band test : 1.08750 <= 1.08780 <= 1.08809                      OK
    §5   entry     = 61.8% level                                 = 1.08809
    §6   stop      = 75.0% level                                 = 1.08875
    §7   TP_382    = 38.2% level                                 = 1.08691
    NOTE B         : sell_limit 1.08809 > decision close 1.08780        OK
    """
    o = orders[1]

    assert o.direction == -1
    assert o.entry == "sell_limit"
    assert o.entry_price == pytest.approx(1.08809, abs=1e-9)
    assert o.stop.price == pytest.approx(1.08875, abs=1e-9)
    assert o.decision_close == pytest.approx(1.08780, abs=1e-9)

    assert [leg.label for leg in o.exits] == ["TP_382", "TRAIL"]
    assert [leg.fraction for leg in o.exits] == pytest.approx([0.5, 0.5])
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)

    tp, trail = o.exits
    assert tp.price == pytest.approx(1.08691, abs=1e-9)
    assert trail.kind == "trailing"
    assert trail.atr_multiple == pytest.approx(1.5)

    assert o.stop.move_to_breakeven_on == "TP_382"
    assert o.stop.trail_atr_multiple is None
    assert o.expires_after_bars == 24


def test_risk_and_target_are_the_spec_fractions_of_the_range(orders: List) -> None:
    """§6: initial risk = (0.750 - 0.618) * rng = 0.132 * rng.
    §7 note: TP_382 sits (0.618 - 0.382) * rng = 0.236 * rng beyond entry.

    Both setups use rng = 0.00500, so risk = 0.00066 and target = 0.00118.
    Written as ratios so a changed fib constant is caught, not absorbed.
    """
    for o in orders:
        rng = 0.00500
        risk = o.direction * (o.entry_price - o.stop.price)
        assert risk == pytest.approx(0.132 * rng, abs=1e-9)
        target = o.direction * (o.exits[0].price - o.entry_price)
        assert target == pytest.approx(0.236 * rng, abs=1e-9)


def test_limit_sits_on_the_far_side_of_the_decision_close(
    frames: Dict[str, pd.DataFrame], orders: List
) -> None:
    """NOTE B / contract §2.2: a buy_limit at or above the decision close (or a
    sell_limit at or below it) is an instant fill in disguise and is rejected at
    construction. The strategy must skip such a bar, never clamp the level."""
    close = frames["D1"]["Close"]
    for o in orders:
        c = float(close.loc[o.decision_bar])
        assert o.direction * (c - o.entry_price) > 0.0


def test_no_order_before_warmup(orders: List) -> None:
    """Warmup contract: the fixture scale declares 10 bars, so nothing may be
    emitted before 2020-01-11 (bar 10)."""
    assert min(o.decision_bar for o in orders) >= pd.Timestamp("2020-01-11", tz="UTC")


# ---------------------------------------------------------------------------
# 4. The non-negotiable check
# ---------------------------------------------------------------------------


def test_strategy_is_free_of_lookahead(frames: Dict[str, pd.DataFrame]) -> None:
    """Hard rule 1 / §9. The probe's windows cover the long setup at bar 20, so
    it compares real orders rather than emptiness to emptiness."""
    assert_no_lookahead_v2(_FixtureScale(), frames)
