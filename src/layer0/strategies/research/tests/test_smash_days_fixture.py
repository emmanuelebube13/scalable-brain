"""GOLDEN FIXTURE for Smash Days."""

from __future__ import annotations

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.smash_days import SmashDays

# 1. The bars, and why these bars
# We construct a 31-bar daily series to test the Smash Days short-only logic.
# The strategy requires `Close[t] > Close[t-1]` and `Close[t] > max(High[t-5..t-1])`.
# Bars 0-7 are a slow downtrend.
# Bar 8 is a Smash-up day: a spike where the close beats the prior close and the last 5 highs.
# Bars 9-14 are flat/downtrending again.
# Bar 15 is another Smash-up day.
# Bars 16-30 are filler.

DATA = [
    # Open, High, Low, Close
    # t=0 to 4: downward
    (1.1000, 1.1020, 1.0980, 1.0990),  # 0
    (1.0990, 1.1010, 1.0970, 1.0980),  # 1
    (1.0980, 1.1000, 1.0960, 1.0970),  # 2
    (1.0970, 1.0990, 1.0950, 1.0960),  # 3
    (1.0960, 1.0980, 1.0940, 1.0950),  # 4
    (1.0950, 1.0970, 1.0930, 1.0940),  # 5
    (1.0940, 1.0960, 1.0920, 1.0930),  # 6
    (1.0930, 1.0950, 1.0910, 1.0920),  # 7
    # t=8: Smash-up day!
    # PRIOR5 = max(High[3..7]) = max(1.0990, 1.0980, 1.0970, 1.0960, 1.0950) = 1.0990
    # Close(1.1020) > PRIOR5(1.0990) AND Close(1.1020) > Close[7](1.0920)
    (1.0920, 1.1050, 1.0900, 1.1020),  # 8
    # t=9: Normal
    (1.1020, 1.1040, 1.0900, 1.0950),  # 9
    # t=10..14: Flat
    (1.0950, 1.0970, 1.0930, 1.0940),  # 10
    (1.0940, 1.0960, 1.0920, 1.0930),  # 11
    (1.0930, 1.0950, 1.0910, 1.0920),  # 12
    (1.0920, 1.0940, 1.0900, 1.0910),  # 13
    (1.0910, 1.0930, 1.0890, 1.0900),  # 14
    # t=15: Smash-up day!
    # PRIOR5 = max(High[10..14]) = 1.0970
    # Close(1.0980) > PRIOR5(1.0970) AND Close(1.0980) > Close[14](1.0900)
    (1.0900, 1.1000, 1.0850, 1.0980),  # 15
    # Fill out to 30 bars
    (1.0980, 1.0990, 1.0950, 1.0960),  # 16
    (1.0960, 1.0980, 1.0940, 1.0950),  # 17
    (1.0950, 1.0970, 1.0930, 1.0940),  # 18
    (1.0940, 1.0960, 1.0920, 1.0930),  # 19
    (1.0930, 1.0950, 1.0910, 1.0920),  # 20
    (1.0920, 1.0940, 1.0900, 1.0910),  # 21
    (1.0910, 1.0930, 1.0890, 1.0900),  # 22
    (1.0900, 1.0920, 1.0880, 1.0890),  # 23
    (1.0890, 1.0910, 1.0870, 1.0880),  # 24
    (1.0880, 1.0900, 1.0860, 1.0870),  # 25
    (1.0870, 1.0890, 1.0850, 1.0860),  # 26
    (1.0860, 1.0880, 1.0840, 1.0850),  # 27
    (1.0850, 1.0870, 1.0830, 1.0840),  # 28
    (1.0840, 1.0860, 1.0820, 1.0830),  # 29
    (1.0830, 1.0850, 1.0810, 1.0820),  # 30
]


@pytest.fixture(scope="module")
def frames() -> dict:
    # Use D1 freq instead of 1D as older pandas uses D, newer might use D
    # "1D" or "D" usually both work. Let's just use "D".
    idx = pd.date_range("2020-01-01", periods=len(DATA), freq="D", tz="UTC")
    d1 = pd.DataFrame(
        {
            "Open": [d[0] for d in DATA],
            "High": [d[1] for d in DATA],
            "Low": [d[2] for d in DATA],
            "Close": [d[3] for d in DATA],
            "Volume": 1.0,
        },
        index=idx,
    )
    return {"D1": d1}


@pytest.fixture(scope="module")
def orders(frames) -> list:
    return list(SmashDays().generate_orders(frames))


def test_emits_exactly_the_expected_setups(orders) -> None:
    """Rule §5: fire when Close[t] > Close[t-1] AND Close[t] > max(High[t-5..t-1]).

    Bar 8 (2020-01-09):
        Close[8] = 1.1020
        Close[7] = 1.0920 (1.1020 > 1.0920)
        Prior 5 highs (bars 3..7) = [1.0990, 1.0980, 1.0970, 1.0960, 1.0950]
        Max = 1.0990 (1.1020 > 1.0990) -> Fires.

    Bar 15 (2020-01-16):
        Close[15] = 1.0980
        Close[14] = 1.0900 (1.0980 > 1.0900)
        Prior 5 highs (bars 10..14) = [1.0970, 1.0960, 1.0950, 1.0940, 1.0930]
        Max = 1.0970 (1.0980 > 1.0970) -> Fires.
    """
    assert [str(o.decision_bar) for o in orders] == [
        "2020-01-09 00:00:00+00:00",
        "2020-01-16 00:00:00+00:00",
    ]


def test_first_order_matches_hand_computed_arithmetic(orders) -> None:
    """The full trade plan, derived from the spec.

    At 2020-01-09 (bar 8):
        Entry (§5): Low[8] = 1.0900 (sell_stop)
        Stop (§6): High[8] = 1.1050
        Exit (§7): 1.0 fraction, 5 bars time leg
    """
    o = orders[0]

    assert o.direction == -1
    assert o.entry == "sell_stop"
    assert o.entry_price == pytest.approx(1.0900, abs=1e-9)
    assert o.stop.price == pytest.approx(1.1050, abs=1e-9)

    assert len(o.exits) == 1
    leg = o.exits[0]
    assert leg.kind == "time"
    assert leg.bars == 5
    assert leg.fraction == pytest.approx(1.0, abs=1e-9)

    assert o.expires_after_bars == 1


def test_pending_entry_sits_below_the_market(frames, orders) -> None:
    """Rule §5 / NOTE 3: a sell stop must be below the decision close.
    If it is not, the order must be skipped."""
    close = frames["D1"]["Close"]
    for o in orders:
        assert o.entry_price < float(close.loc[o.decision_bar])


def test_strategy_is_free_of_lookahead(frames) -> None:
    """Every Wave-2 strategy must pass this on real data too."""
    assert_no_lookahead_v2(SmashDays(), frames)
