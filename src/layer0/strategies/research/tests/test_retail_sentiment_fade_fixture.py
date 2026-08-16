"""GOLDEN FIXTURE — retail_sentiment_fade (SPEC-retail_sentiment_fade.md).

Every expected number is derived from the spec's formulas before the code was run.

This is the one strategy in the fleet whose input feed does not exist. The fixture
is therefore doing double duty: it pins the trade plan the way every other fixture
does, AND it is the only place the sentiment half of the rule is ever exercised. It
supplies a hand-written four-row sentiment series with explicit `published_at`
stamps, so §9's rule S1 (an observation is usable only 24h after publication) is
tested against real timestamps rather than asserted in prose.

Bar construction: ``High = Close + 20 pip``, ``Low = Close - 20 pip``, and no close
moves more than 20 pip, so every bar's true range is exactly ``High - Low`` =
40 pip and the EWM of that constant series is itself: **ATR(14) = 0.00400 on every
bar**. §6's stop is then exactly 60 pip from the close and §7's target exactly
120 pip.

The fixture subclasses the strategy to shrink FAST_PERIOD 20 -> 3 and SLOW_PERIOD
50 -> 5 (which also sets warmup to 5). Periods only: the 60% threshold, the 24h
publication lag and the 1.5/3.0 ATR multiples are untouched.
"""

from __future__ import annotations

from typing import Dict, List

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.retail_sentiment_fade import (
    RetailSentimentFade,
    eligible_sentiment,
)

PIP = 0.0001
BAND = 20 * PIP
ATR = 40 * PIP

# ---------------------------------------------------------------------------
# 1. The bars, and why these bars
# ---------------------------------------------------------------------------
# 40 D1 closes, stamped 21:00Z on business days from Tuesday 2021-06-01.
# Bars 0-11 fall in 10-pip steps, so SMA(3) sits below SMA(5) — the §4.2 alignment
# for a LONG. Bars 12-39 rise in 10-pip steps, so SMA(3) climbs above SMA(5) — the
# §5.2 alignment for a SHORT. Which of those windows actually trades is decided
# entirely by the sentiment series below.
CLOSES = [
    1.2200,
    1.2190,
    1.2180,
    1.2170,
    1.2160,
    1.2150,  # bar 5 — first LONG (warmup ends here)
    1.2140,
    1.2130,
    1.2120,
    1.2110,
    1.2100,
    1.2090,
    1.2100,
    1.2110,
    1.2120,
    1.2130,
    1.2140,
    1.2150,
    1.2160,
    1.2170,
    1.2180,
    1.2190,
    1.2200,  # bar 22 — first SHORT
    1.2210,
    1.2220,
    1.2230,
    1.2240,
    1.2250,
    1.2260,
    1.2270,
    1.2280,
    1.2290,
    1.2300,
    1.2310,
    1.2320,
    1.2330,
    1.2340,
    1.2350,
    1.2360,
    1.2370,
]

# The sentiment series (§3 schema, §9 timing). Four observations, each published at
# 12:00Z so the 24h lag lands them squarely inside a later D1 session:
#   1. 2021-06-01 — 65% short: an extreme AGAINST a falling market -> longs
#   2. 2021-06-11 — 50/50: neutral, the extreme is over -> the long window closes
#   3. 2021-07-01 — 70% long: an extreme against a rising market -> shorts
#   4. 2021-07-06 — 50/50: neutral again -> the short window closes
SENTIMENT = pd.DataFrame(
    {
        "published_at": pd.to_datetime(
            [
                "2021-06-01 12:00",
                "2021-06-11 12:00",
                "2021-07-01 12:00",
                "2021-07-06 12:00",
            ]
        ).tz_localize("UTC"),
        "long_ratio_pct": [35.0, 50.0, 70.0, 50.0],
        "short_ratio_pct": [65.0, 50.0, 30.0, 50.0],
    }
)


class _FixtureScale(RetailSentimentFade):
    """Production logic, fixture-sized moving averages (periods only)."""

    FAST_PERIOD = 3
    SLOW_PERIOD = 5


def _index() -> pd.DatetimeIndex:
    return pd.date_range("2021-06-01 21:00", periods=len(CLOSES), freq="B", tz="UTC")


@pytest.fixture(scope="module")
def frames() -> Dict[str, pd.DataFrame]:
    d1 = pd.DataFrame(
        {
            "Open": CLOSES,
            "High": [c + BAND for c in CLOSES],
            "Low": [c - BAND for c in CLOSES],
            "Close": CLOSES,
            "Volume": 1.0,
        },
        index=_index(),
    )
    return {"D1": d1}


@pytest.fixture(scope="module")
def orders(frames: Dict[str, pd.DataFrame]) -> List:
    return list(_FixtureScale(sentiment=SENTIMENT).generate_orders(frames))


# ---------------------------------------------------------------------------
# 2 + 3. Expected values, computed by hand, then asserted
# ---------------------------------------------------------------------------


def test_emits_exactly_the_expected_setups(orders) -> None:
    """§4/§5 with §9's lag: which bars can see which observation.

    Observation 1 is published 2021-06-01 12:00 and bar 0 closes 2021-06-02 21:00,
    which is more than 24h later, so the 65%-short reading is eligible from bar 0 —
    but the SMA(5) warm-up means the first tradeable bar is bar 5.
    Observation 2 (neutral) is published 2021-06-11 12:00; bar 8 closes
    2021-06-12 21:00, so from bar 8 the eligible reading is 50/50 and the long
    window shuts. Longs are therefore bars 5, 6 and 7 only.
    The short window opens the same way at bar 22 (observation 3) and shuts at
    bar 25 (observation 4).
    """
    idx = _index()
    assert [(o.decision_bar, o.direction) for o in orders] == [
        (idx[5], 1),
        (idx[6], 1),
        (idx[7], 1),
        (idx[22], -1),
        (idx[23], -1),
        (idx[24], -1),
    ]


def test_long_matches_hand_computed_arithmetic(orders) -> None:
    """The bar-5 trade plan, from §4, §6 and §7.

    §4.1 eligible reading at bar 5 = observation 1: short_ratio 65.0 >= 60.0
    §4.2 SMA(3) = (1.21700 + 1.21600 + 1.21500)/3 = 1.21600
         SMA(5) = (1.21900 + 1.21800 + 1.21700 + 1.21600 + 1.21500)/5 = 1.21700
         1.21600 < 1.21700, so the crowd is short into a falling market
    §6   stop = Close - 1.5 x ATR = 1.21500 - 0.00600 = 1.20900
    §7   TP   = Close + 3.0 x ATR = 1.21500 + 0.01200 = 1.22700
    """
    o = orders[0]

    assert o.direction == 1
    assert o.entry == "market"
    assert o.entry_price is None
    assert o.decision_close == pytest.approx(1.21500, abs=1e-9)
    assert o.stop.price == pytest.approx(1.20900, abs=1e-9)
    assert o.stop.move_to_breakeven_on is None  # §6: no breakeven
    assert o.stop.trail_atr_multiple is None  # §6: static stop

    assert [leg.kind for leg in o.exits] == ["take_profit"]
    assert [leg.label for leg in o.exits] == ["TP1"]
    assert [leg.price for leg in o.exits] == pytest.approx([1.22700], abs=1e-9)
    assert [leg.fraction for leg in o.exits] == pytest.approx([1.0])
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)
    assert o.expires_after_bars is None  # §4: a market intent is never pending
    # §7: the target is exactly twice the stop distance (1:2 reward:risk).
    assert (o.exits[0].price - o.decision_close) == pytest.approx(
        2.0 * (o.decision_close - o.stop.price), abs=1e-9
    )


def test_short_matches_hand_computed_arithmetic(orders) -> None:
    """The bar-22 trade plan, from §5, §6 and §7 — the mirror.

    §5.1 eligible reading at bar 22 = observation 3: long_ratio 70.0 >= 60.0
    §5.2 SMA(3) = (1.21800 + 1.21900 + 1.22000)/3 = 1.21900
         SMA(5) = (1.21600 + ... + 1.22000)/5 = 1.21800; 1.21900 > 1.21800
    §6   stop = Close + 1.5 x ATR = 1.22000 + 0.00600 = 1.22600
    §7   TP   = Close - 3.0 x ATR = 1.22000 - 0.01200 = 1.20800
    """
    o = orders[3]

    assert o.direction == -1
    assert o.decision_close == pytest.approx(1.22000, abs=1e-9)
    assert o.stop.price == pytest.approx(1.22600, abs=1e-9)
    assert o.exits[0].price == pytest.approx(1.20800, abs=1e-9)
    assert [leg.fraction for leg in o.exits] == pytest.approx([1.0])
    assert o.stop.price > o.decision_close > o.exits[0].price
    assert o.tag == "sentiment_fade"


def test_re_emission_while_the_extreme_persists(orders) -> None:
    """§10 #7: the strategy re-emits every qualifying bar; F12 caps admission.

    Each re-emission is anchored to its OWN decision close, so the three longs must
    step down 10 pip at a time: 1.21500 / 1.21400 / 1.21300, with stops and targets
    tracking them. A fire-once reading would produce one order; a stale-anchor bug
    would repeat the first order's levels.
    """
    longs = [o for o in orders if o.direction == 1]
    assert [o.decision_close for o in longs] == pytest.approx(
        [1.21500, 1.21400, 1.21300], abs=1e-9
    )
    assert [o.stop.price for o in longs] == pytest.approx(
        [1.20900, 1.20800, 1.20700], abs=1e-9
    )
    assert [o.exits[0].price for o in longs] == pytest.approx(
        [1.22700, 1.22600, 1.22500], abs=1e-9
    )
    for o in longs:
        assert [leg.fraction for leg in o.exits] == pytest.approx([1.0])


def test_without_the_feed_the_strategy_emits_nothing(frames) -> None:
    """The measurement fact for this id: no sentiment, no orders — and no proxy.

    The strategy must not fall back to trading the SMA alignment alone; that would
    be a different strategy. This is why the harness verdict is UNMEASURABLE.
    """
    assert list(RetailSentimentFade().generate_orders(frames)) == []
    assert list(_FixtureScale().generate_orders(frames)) == []


def test_publication_lag_is_enforced_to_the_second() -> None:
    """§9 rule S1 / §10 #5: usable only 24h after publication, never earlier.

    A D1 bar stamped 2021-06-01 21:00 closes 2021-06-02 21:00, so it may use an
    observation published at or before 2021-06-01 21:00 — exactly the 24h buffer.
    One second later and the observation is invisible to that bar.
    """
    closes = pd.DatetimeIndex(["2021-06-02 21:00"]).tz_localize("UTC")
    lag = pd.Timedelta(hours=24)

    on_time = pd.DataFrame(
        {
            "published_at": pd.DatetimeIndex(["2021-06-01 21:00"]).tz_localize("UTC"),
            "long_ratio_pct": [30.0],
            "short_ratio_pct": [70.0],
        }
    )
    late = pd.DataFrame(
        {
            "published_at": pd.DatetimeIndex(["2021-06-01 21:00:01"]).tz_localize(
                "UTC"
            ),
            "long_ratio_pct": [30.0],
            "short_ratio_pct": [70.0],
        }
    )

    assert eligible_sentiment(on_time, closes, lag)["short_ratio_pct"].iloc[
        0
    ] == pytest.approx(70.0)
    assert pd.isna(eligible_sentiment(late, closes, lag)["short_ratio_pct"].iloc[0])


# ---------------------------------------------------------------------------
# 4. The non-negotiable check
# ---------------------------------------------------------------------------


def test_strategy_is_free_of_lookahead(frames) -> None:
    """Every Wave-2 strategy must pass this — here, with the feed injected."""
    assert_no_lookahead_v2(_FixtureScale(sentiment=SENTIMENT), frames)
