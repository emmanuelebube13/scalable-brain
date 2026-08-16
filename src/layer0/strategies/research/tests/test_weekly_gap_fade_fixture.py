"""GOLDEN FIXTURE — weekly_gap_fade (SPEC-weekly_gap_fade.md).

Every expected number is derived from the spec's formulas before the code was run.

The frame holds the hours either side of three weekends and omits the weeks in
between, because the strategy reads exactly two prices per week — the Friday close
and the week's opening print — and one context value, the D1 ATR. Omitting the
mid-week hours keeps the bars hand-writable without changing a single input: the
week-boundary test (§4 step 1) is a Friday/Sunday pattern check, and the time-exit
count (§7) is calendar arithmetic that never looks at the frame.

The D1 context bars each carry ``High = Close + 50 pip`` and ``Low = Close - 50 pip``
with 10-pip daily steps, so every daily true range is exactly 100 pip and the EWM of
that constant is itself: **ATR(14) = 0.01000**, making §6's catastrophic stop exactly
5 x 0.01000 = 0.05000 from the decision close.

The fixture shrinks only ``warmup_bars`` (336 -> 1). No threshold, multiple or level
is touched — in particular the 5.0-pip gap filter is the production one, which is
what lets the third weekend (a 3-pip gap) act as the negative control.
"""

from __future__ import annotations

from typing import Dict, List

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.weekly_gap_fade import WeeklyGapFade

PIP = 0.0001

# ---------------------------------------------------------------------------
# 1. The bars, and why these bars
# ---------------------------------------------------------------------------
# Three weekends, one per outcome:
#   bar 5   Sunday 2021-02-07 21:00 opens 20 pip BELOW the Friday close -> LONG
#   bar 20  Sunday 2021-02-14 21:00 opens 30 pip ABOVE the Friday close -> SHORT
#   bar 35  Sunday 2021-02-21 21:00 opens  3 pip above it -> below the 5.0-pip
#           threshold, so nothing may be emitted (the negative control)
CLOSES = [
    # Friday 2021-02-05, 16:00-20:00 — the last of these is the prior week close
    1.1960,
    1.1970,
    1.1980,
    1.1990,
    1.2000,
    1.1990,  # bar 5 — Sunday 2021-02-07 21:00, THE LONG
    1.1995,
    1.2000,
    1.2005,
    1.2010,
    1.2015,
    1.2020,
    1.2025,
    1.2030,
    1.2035,
    # Friday 2021-02-12, 16:00-20:00
    1.2080,
    1.2085,
    1.2090,
    1.2095,
    1.2100,
    1.2120,  # bar 20 — Sunday 2021-02-14 21:00, THE SHORT
    1.2125,
    1.2130,
    1.2135,
    1.2140,
    1.2145,
    1.2150,
    1.2155,
    1.2160,
    1.2165,
    # Friday 2021-02-19, 16:00-20:00
    1.2180,
    1.2185,
    1.2190,
    1.2195,
    1.2200,
    1.2205,  # bar 35 — Sunday 2021-02-21 21:00, the 3-pip control
    1.2210,
    1.2215,
    1.2220,
    1.2225,
]
# Opens: continuous within a session (open = previous close); the three weekly
# opening prints are the gaps under test.
WEEK_OPENS = {5: 1.1980, 20: 1.2130, 35: 1.2203}

D1_CLOSES = [1.1900 + i * 10 * PIP for i in range(20)]
D1_HALF_RANGE = 50 * PIP


class _FixtureScale(WeeklyGapFade):
    """Production logic; only the warm-up is shortened."""

    @property
    def warmup_bars(self) -> int:
        return 1


def _h1_index(friday_of_week_b: str = "2021-02-12") -> pd.DatetimeIndex:
    """The hours around three weekends; ``friday_of_week_b`` is varied by one test."""
    stamps: List[pd.Timestamp] = []

    def session(day: str, hours: range) -> None:
        stamps.extend(pd.Timestamp(f"{day} {h:02d}:00", tz="UTC") for h in hours)

    session("2021-02-05", range(16, 21))  # Friday
    session("2021-02-07", range(21, 24))  # Sunday reopen
    session("2021-02-08", range(0, 7))  # Monday
    session(friday_of_week_b, range(16, 21))
    session("2021-02-14", range(21, 24))
    session("2021-02-15", range(0, 7))
    session("2021-02-19", range(16, 21))  # Friday
    session("2021-02-21", range(21, 24))
    session("2021-02-22", range(0, 2))
    return pd.DatetimeIndex(stamps)


def _frames(index: pd.DatetimeIndex) -> Dict[str, pd.DataFrame]:
    opens = [
        WEEK_OPENS.get(i, CLOSES[i - 1] if i else CLOSES[0]) for i in range(len(CLOSES))
    ]
    h1 = pd.DataFrame(
        {
            "Open": opens,
            "High": [max(o, c) + 5 * PIP for o, c in zip(opens, CLOSES)],
            "Low": [min(o, c) - 5 * PIP for o, c in zip(opens, CLOSES)],
            "Close": CLOSES,
            "Volume": 1.0,
        },
        index=index,
    )
    d1_index = pd.date_range(
        "2021-01-25 21:00", periods=len(D1_CLOSES), freq="D", tz="UTC"
    )
    d1 = pd.DataFrame(
        {
            "Open": D1_CLOSES,
            "High": [c + D1_HALF_RANGE for c in D1_CLOSES],
            "Low": [c - D1_HALF_RANGE for c in D1_CLOSES],
            "Close": D1_CLOSES,
            "Volume": 1.0,
        },
        index=d1_index,
    )
    return {"H1": h1, "D1": d1}


@pytest.fixture(scope="module")
def frames() -> Dict[str, pd.DataFrame]:
    return _frames(_h1_index())


@pytest.fixture(scope="module")
def orders(frames: Dict[str, pd.DataFrame]) -> List:
    return list(_FixtureScale().generate_orders(frames))


# ---------------------------------------------------------------------------
# 2 + 3. Expected values, computed by hand, then asserted
# ---------------------------------------------------------------------------


def test_only_gaps_beyond_the_threshold_trade(orders) -> None:
    """§4.5/§5.4 with the §8 proxy: |gap| must reach 5.0 pip.

    weekend 1: 1.19800 - 1.20000 = -0.00200 = -20.0 pip -> long
    weekend 2: 1.21300 - 1.21000 = +0.00300 = +30.0 pip -> short
    weekend 3: 1.22030 - 1.22000 = +0.00030 =  +3.0 pip -> no order
    """
    idx = _h1_index()
    assert [(o.decision_bar, o.direction) for o in orders] == [
        (idx[5], 1),
        (idx[20], -1),
    ]
    assert idx[35] == pd.Timestamp("2021-02-21 21:00", tz="UTC")  # the control bar


def test_long_matches_hand_computed_arithmetic(orders) -> None:
    """The weekend-1 trade plan, from §4, §6 and §7.

    §4.2 prior_week_close = Close of the Friday 20:00 bar = 1.20000
    §4.3 week_open        = Open of the Sunday 21:00 bar  = 1.19800
    §4.4 gap              = -0.00200 = -20.0 pip, so <= -5.0 -> fade it long
    §6   ATR_D1 = 0.01000 (constant by construction), stop = W0_close - 5 x ATR
                        = 1.19900 - 0.05000 = 1.14900
    §7   hold  = hours from the fill bar (Sunday 22:00) to Friday 19:00 UTC
                        = 5 days - 3h = 117 bars
    """
    o = orders[0]

    assert o.direction == 1
    assert o.entry == "market"
    assert o.entry_price is None
    assert o.decision_close == pytest.approx(1.19900, abs=1e-9)
    assert o.stop.price == pytest.approx(1.14900, abs=1e-9)
    assert o.stop.price < o.decision_close
    assert o.stop.move_to_breakeven_on is None  # §6: none
    assert o.stop.trail_atr_multiple is None  # §6: static

    assert [leg.kind for leg in o.exits] == ["time"]
    assert [leg.label for leg in o.exits] == ["W-END"]
    assert [leg.bars for leg in o.exits] == [117]
    assert [leg.fraction for leg in o.exits] == pytest.approx([1.0])
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)
    assert o.expires_after_bars == 1  # §4: defensive only
    assert o.tag == "weekly_gap_fade"


def test_short_matches_hand_computed_arithmetic(orders) -> None:
    """The weekend-2 trade plan — the mirror.

    §5.2 prior_week_close = 1.21000 · week_open = 1.21300 · gap = +30.0 pip
    §6   stop = W0_close + 5 x ATR = 1.21200 + 0.05000 = 1.26200
    §7   same 117-bar hold: the exit is a calendar deadline, not a distance
    """
    o = orders[1]

    assert o.direction == -1
    assert o.decision_close == pytest.approx(1.21200, abs=1e-9)
    assert o.stop.price == pytest.approx(1.26200, abs=1e-9)
    assert o.stop.price > o.decision_close
    assert [leg.bars for leg in o.exits] == [117]
    assert [leg.fraction for leg in o.exits] == pytest.approx([1.0])
    assert o.exits[0].price is None  # a time leg carries no price
    assert o.exits[0].atr_multiple is None


def test_a_week_that_does_not_open_after_a_friday_is_vetoed(orders) -> None:
    """§4 step 1 / §10 #7: the standard weekly pattern, or no trade.

    Re-stamp weekend 2's pre-weekend hours onto Thursday 2021-02-11. The prices, the
    gap and the ATR are all unchanged — only the weekday of the bar preceding the
    Sunday open moves — and the short must disappear, leaving weekend 1's long alone.
    """
    shifted = list(_FixtureScale().generate_orders(_frames(_h1_index("2021-02-11"))))
    assert [(o.decision_bar, o.direction) for o in shifted] == [
        (_h1_index("2021-02-11")[5], 1)
    ]
    assert len(orders) == 2  # the unmodified frame still trades both weekends


def test_the_stop_is_the_catastrophic_five_atr_one(orders) -> None:
    """§6 / §10 #1: 5 x D1 ATR(14), decision-close anchored, both directions.

    Stated as an invariant because the whole r-multiple scale of this strategy rests
    on it: a 1x or 2x ATR stop would silently make every result look different.
    """
    for o in orders:
        assert abs(o.decision_close - o.stop.price) == pytest.approx(
            5.0 * 0.01000, abs=1e-9
        )


# ---------------------------------------------------------------------------
# 4. The non-negotiable check
# ---------------------------------------------------------------------------


def test_strategy_is_free_of_lookahead(frames) -> None:
    """Every Wave-2 strategy must pass this on real data too."""
    assert_no_lookahead_v2(_FixtureScale(), frames)
