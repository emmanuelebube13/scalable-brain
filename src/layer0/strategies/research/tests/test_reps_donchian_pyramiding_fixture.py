"""GOLDEN FIXTURE — reps_donchian_pyramiding (SPEC-reps_donchian_pyramiding).

Every expected number below is derived from the spec's formulas before the code was
run, and the arithmetic is shown so a reviewer can check it against the spec without
executing anything.

Two construction rules make the whole trade plan hand-computable:

* **D1 bars**: 40 hand-chosen closes, one per business day at 21:00Z, with
  ``High = Close + 10 pip`` and ``Low = Close - 10 pip`` on every bar. So the shifted
  D1 Donchian(3) at bar *t* is ``max(Close[t-3..t-1]) + 10 pip`` (upper) and
  ``min(Close[t-3..t-1]) - 10 pip`` (lower), and a weekly bar's High/Low/Close are
  the week's max/min close ±10 pip and its Friday close.
* **H4 bars**: each D1 session is expanded into 6 H4 bars carrying that session's
  OHLC. Two consequences, both used below:
  1. the last H4 bar closed at the *open* of D1 bar *t* is the last H4 bar of session
     *t-1*, and the shifted H4 Donchian(3) there is that session's own Low/High —
     so **§6 stop = Low[t-1] for a long, High[t-1] for a short**;
  2. only the FIRST H4 bar of a session can break the shifted H4 channel, and it does
     so exactly when the session moved more than 10 pip against the previous close —
     so the §4.3 "counter-move then reversal" pattern reduces to
     ``Close[t-2] < Close[t-3] - 10 pip`` followed by ``Close[t-1] > Close[t-2] + 10 pip``.

The fixture subclasses the strategy to shrink CHANNEL_PERIOD 20 -> 3 and warmup
150 -> 15. Periods only: no formula, threshold or level is changed. 40 business days
cannot warm a 20-week channel.
"""

from __future__ import annotations

from typing import Dict, List

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.reps_donchian_pyramiding import (
    RepsDonchianPyramiding,
)

PIP = 0.0001

# ---------------------------------------------------------------------------
# 1. The bars, and why these bars
# ---------------------------------------------------------------------------
# 40 business days = 8 clean broker weeks (Mon-Fri, stamped 21:00Z), starting
# Monday 2020-01-06. Weeks 0-2 are a quiet base that defines the weekly channel;
# week 3 closes above it (the INITIAL_LONG event); week 4 carries both pyramid
# add-ons; week 5 breaks the long series and closes below the weekly lower channel
# (the INITIAL_SHORT event); weeks 6-7 mirror the long side and then drift in
# 5-pip steps, which can never break a channel sitting 10 pip away.
CLOSES = [
    # week 0 (2020-01-06) — base
    1.1000,
    1.1010,
    1.1005,
    1.1015,
    1.1010,
    # week 1 (2020-01-13) — base
    1.1020,
    1.1015,
    1.1025,
    1.1020,
    1.1030,
    # week 2 (2020-01-20) — base; weekly highs so far: 1.1025 / 1.1040 / 1.1050
    1.1025,
    1.1035,
    1.1030,
    1.1040,
    1.1035,
    # week 3 (2020-01-27) — closes 1.1080 > 1.1050 = weekly channel -> INITIAL_LONG
    1.1045,
    1.1060,
    1.1055,
    1.1070,
    1.1080,
    # week 4 (2020-02-03) — bar 20 initial, bar 21 D1 add-on, bar 24 H4 add-on
    1.1075,
    1.1095,
    1.1070,
    1.1090,
    1.1100,
    # week 5 (2020-02-10) — bar 25 breaks the long series; week closes 1.0980
    1.1040,
    1.1020,
    1.1000,
    1.0990,
    1.0980,
    # week 6 (2020-02-17) — bar 30 initial short, bar 31 D1 add-on, bar 34 H4 add-on
    1.0975,
    1.0960,
    1.0980,
    1.0955,
    1.0950,
    # week 7 (2020-02-24) — 5-pip drift: nothing may fire
    1.0945,
    1.0940,
    1.0935,
    1.0930,
    1.0925,
]

BAND = 10 * PIP  # High/Low offset on every hand-written bar


class _FixtureScale(RepsDonchianPyramiding):
    """Production logic, fixture-sized lookbacks (periods only)."""

    CHANNEL_PERIOD = 3

    @property
    def warmup_bars(self) -> int:
        return 15


@pytest.fixture(scope="module")
def frames() -> Dict[str, pd.DataFrame]:
    idx = pd.date_range("2020-01-06 21:00", periods=len(CLOSES), freq="B", tz="UTC")
    d1 = pd.DataFrame(
        {
            "Open": CLOSES,
            "High": [c + BAND for c in CLOSES],
            "Low": [c - BAND for c in CLOSES],
            "Close": CLOSES,
            "Volume": 1.0,
        },
        index=idx,
    )
    # Each D1 session -> 6 H4 bars carrying that session's OHLC (see module docstring).
    h4_index: List[pd.Timestamp] = []
    h4_rows: List[Dict[str, float]] = []
    for ts, row in d1.iterrows():
        for k in range(6):
            h4_index.append(ts + pd.Timedelta(hours=4 * k))
            h4_rows.append(
                {
                    "Open": row["Open"],
                    "High": row["High"],
                    "Low": row["Low"],
                    "Close": row["Close"],
                    "Volume": 1.0,
                }
            )
    h4 = pd.DataFrame(h4_rows, index=pd.DatetimeIndex(h4_index))
    return {"D1": d1, "H4": h4}


@pytest.fixture(scope="module")
def orders(frames: Dict[str, pd.DataFrame]) -> List:
    return list(_FixtureScale().generate_orders(frames))


def _bar(n: int) -> str:
    """The timestamp of D1 bar n, as printed."""
    return str(
        pd.date_range("2020-01-06 21:00", periods=len(CLOSES), freq="B", tz="UTC")[n]
    )


# ---------------------------------------------------------------------------
# 2 + 3. Expected values, computed by hand from the spec, then asserted
# ---------------------------------------------------------------------------


def test_emits_exactly_the_expected_series(orders) -> None:
    """§4/§5: which events fire, and only those.

    bar 20 INITIAL_LONG   — week 3 closed 1.1080 > weekly channel 1.1050 (= max of
                            the weeks-0..2 highs), first D1 bar of week 4.
    bar 21 ADDON_LONG_D1  — 1.1095 > D1 channel 1.1090 (= max(1.1055,1.1070,1.1080)
                            + 10 pip) and bar 20 was not above its own channel.
    bar 24 ADDON_LONG_H4  — session 22 fell 25 pip (1.1070 < 1.1095 - 10 pip) and
                            session 23 rose 20 pip (1.1090 > 1.1070 + 10 pip).
    bar 30 INITIAL_SHORT  — week 5 closed 1.0980 < weekly lower channel 1.1015.
    bar 31 ADDON_SHORT_D1 — 1.0960 < D1 lower channel 1.0965.
    bar 34 ADDON_SHORT_H4 — mirror of bar 24 across sessions 32 and 33.
    """
    assert [(str(o.decision_bar), o.tag, o.direction) for o in orders] == [
        (_bar(20), "INITIAL_LONG", 1),
        (_bar(21), "ADDON_LONG_D1", 1),
        (_bar(24), "ADDON_LONG_H4", 1),
        (_bar(30), "INITIAL_SHORT", -1),
        (_bar(31), "ADDON_SHORT_D1", -1),
        (_bar(34), "ADDON_SHORT_H4", -1),
    ]


def test_initial_long_matches_hand_computed_arithmetic(orders) -> None:
    """The whole trade plan for bar 20, from §4, §6 and §7.

    §4  entry  = market (no entry_price); decision close = 1.10750
    §6  stop   = shifted H4 lower channel at the last H4 bar closed by the decision
                 bar's open = Low[19] = 1.10800 - 0.00100 = 1.10700
    §4  guard  = stop 1.10700 < close 1.10750  -> emission allowed
    §7  exits  = one leg, fraction 1.0, trailing, atr_multiple 6.0
    §4  expiry = 1 bar (a market intent fills next open or not at all)
    """
    o = orders[0]

    assert o.direction == 1
    assert o.entry == "market"
    assert o.entry_price is None
    assert o.decision_close == pytest.approx(1.10750, abs=1e-9)
    assert o.stop.price == pytest.approx(1.10700, abs=1e-9)
    assert o.stop.price < o.decision_close
    assert o.stop.move_to_breakeven_on is None  # §10 #6: no breakeven move
    assert o.stop.trail_atr_multiple is None  # §10 #5: static stop, no double trail

    assert [leg.kind for leg in o.exits] == ["trailing"]
    assert [leg.label for leg in o.exits] == ["SERIES_EXIT"]
    assert [leg.fraction for leg in o.exits] == pytest.approx([1.0])
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)
    assert o.exits[0].atr_multiple == pytest.approx(6.0)
    assert o.expires_after_bars == 1


def test_long_addons_price_off_the_previous_session_low(orders) -> None:
    """§6 + §4 condition 2, for both add-on kinds.

    bar 21 stop = Low[20] = 1.10750 - 0.00100 = 1.10650
    bar 24 stop = Low[23] = 1.10900 - 0.00100 = 1.10800
    Pyramid-into-strength (§10 #8): each emission's close must exceed the previous
    long emission's close — 1.10750 -> 1.10950 -> 1.11000.
    """
    d1_addon, h4_addon = orders[1], orders[2]

    assert d1_addon.stop.price == pytest.approx(1.10650, abs=1e-9)
    assert d1_addon.decision_close == pytest.approx(1.10950, abs=1e-9)
    assert h4_addon.stop.price == pytest.approx(1.10800, abs=1e-9)
    assert h4_addon.decision_close == pytest.approx(1.11000, abs=1e-9)

    longs = [o for o in orders if o.direction == 1]
    closes = [o.decision_close for o in longs]
    assert closes == sorted(closes) and len(set(closes)) == len(closes)
    for o in longs:
        assert o.stop.price < o.decision_close
        assert [leg.fraction for leg in o.exits] == pytest.approx([1.0])


def test_short_side_is_the_exact_mirror(orders) -> None:
    """§5 + §6, shorts.

    bar 30 stop = High[29] = 1.09800 + 0.00100 = 1.09900, close 1.09750
    bar 31 stop = High[30] = 1.09750 + 0.00100 = 1.09850, close 1.09600
    bar 34 stop = High[33] = 1.09550 + 0.00100 = 1.09650, close 1.09500
    Pyramid proxy mirrored: 1.09750 -> 1.09600 -> 1.09500, strictly falling.
    """
    shorts = [o for o in orders if o.direction == -1]

    assert [o.stop.price for o in shorts] == pytest.approx(
        [1.09900, 1.09850, 1.09650], abs=1e-9
    )
    assert [o.decision_close for o in shorts] == pytest.approx(
        [1.09750, 1.09600, 1.09500], abs=1e-9
    )
    for o in shorts:
        assert o.entry == "market"
        assert o.stop.price > o.decision_close  # §5 guard: stop above the market
        assert [leg.fraction for leg in o.exits] == pytest.approx([1.0])
        assert o.exits[0].kind == "trailing"


def test_no_second_initial_while_a_series_is_active(orders) -> None:
    """§4/§5 state machine and §10 #11.

    Two further weekly breakouts occur and neither may open a new series:
      * week 4 closes 1.1100 > its weekly channel 1.1090, but bar 25 has already
        reset the long series and the stop guard (Low[24] = 1.10900 is above the
        1.10400 close) blocks the emission — the weekly event is spent either way;
      * week 6 closes 1.0950 < its weekly lower channel 1.0970 while the short
        series is still ACTIVE, so no second INITIAL_SHORT is emitted.
    """
    initials = [o for o in orders if o.tag.startswith("INITIAL")]
    assert [o.tag for o in initials] == ["INITIAL_LONG", "INITIAL_SHORT"]
    assert str(initials[0].decision_bar) == _bar(20)
    assert str(initials[1].decision_bar) == _bar(30)
    # Week 7 (bars 35-39) drifts 5 pip per session: nothing can break a channel
    # that sits 10 pip away, so no order may exist after bar 34.
    assert max(o.decision_bar for o in orders) == pd.Timestamp(_bar(34))


def test_every_intent_is_a_single_leg_market_order(orders) -> None:
    """§7: exactly one leg, fraction 1.0, trailing at 6.0 x ATR; §4: expiry 1 bar.

    A fractional trailing leg is rejected by the position engine, and fractions
    must sum to exactly 1.0 — assert both properties on every intent, not just the
    first, so a regression in one branch cannot hide behind another.
    """
    assert len(orders) == 6
    for o in orders:
        assert o.entry == "market" and o.entry_price is None
        assert len(o.exits) == 1
        leg = o.exits[0]
        assert leg.kind == "trailing"
        assert leg.fraction == pytest.approx(1.0, abs=1e-9)
        assert leg.atr_multiple == pytest.approx(6.0)
        assert leg.price is None
        assert o.expires_after_bars == 1
        assert o.size_fraction == pytest.approx(1.0)  # §10 #7: System 1 never sizes


# ---------------------------------------------------------------------------
# 4. The non-negotiable check
# ---------------------------------------------------------------------------


def test_strategy_is_free_of_lookahead(frames) -> None:
    """Every Wave-2 strategy must pass this on real data too."""
    assert_no_lookahead_v2(_FixtureScale(), frames)
