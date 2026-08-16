"""GOLDEN FIXTURE for smashing_forex_2."""

from __future__ import annotations

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.smashing_forex_2 import SmashingForex2

PIP = 0.0001

# ---------------------------------------------------------------------------
# 1. The bars, and why these bars
# ---------------------------------------------------------------------------
# We need to trigger the strategy's long and short entries based on EMA and CCI.
# We use a 40-bar sequence.
# Bars 0-19: Alternating 1.1000 and 1.0990. EMA(3) and CCI(14) stabilize. CCI fluctuates < 100.
# Bar 20: Price jumps 100 pips to 1.1100. EMA(3) moves to 1.10466. CCI(14) > +100. Long triggers.
# Bars 21-34: Alternating 1.1100 and 1.1110. EMA(3) and CCI(14) stabilize.
# Bar 35: Price drops 100 pips to 1.1000. EMA(3) moves to 1.10533. CCI(14) < -100. Short triggers.

CLOSES = (
    [1.1000, 1.0990] * 10 +   # Bars 0-19 (Ends on 1.0990 at Bar 19)
    [1.1100] +                # Bar 20
    [1.1100, 1.1110] * 7 +    # Bars 21-34 (Ends on 1.1110 at Bar 34)
    [1.1000] +                # Bar 35
    [1.1000, 1.1010] * 2      # Bars 36-39
)


class _FixtureScale(SmashingForex2):
    """Production logic, fixture-sized lookbacks."""

    EMA_PERIOD = 3
    CCI_PERIOD = 14

    @property
    def warmup_bars(self) -> int:
        return 15


@pytest.fixture(scope="module")
def frames() -> dict:
    idx = pd.date_range("2026-08-01", periods=len(CLOSES), freq="4h", tz="UTC")
    # To keep typical price equal to close, we make high/low symmetrically distant
    h4 = pd.DataFrame(
        {
            "Open": CLOSES,
            "High": [c + 0.0010 for c in CLOSES],
            "Low": [c - 0.0010 for c in CLOSES],
            "Close": CLOSES,
            "Volume": 1.0,
        },
        index=idx,
    )
    return {"H4": h4}


@pytest.fixture(scope="module")
def orders(frames) -> list:
    return list(_FixtureScale().generate_orders(frames))


# ---------------------------------------------------------------------------
# 2 + 3. Expected values, computed by hand, then asserted
# ---------------------------------------------------------------------------

def test_emits_exactly_the_expected_setups(orders) -> None:
    """Rule: fire only when EMA and CCI joint condition turns true (fresh signal)."""
    assert [str(o.decision_bar) for o in orders] == [
        "2026-08-04 08:00:00+00:00",  # Bar 20
        "2026-08-06 20:00:00+00:00",  # Bar 35
    ]


def test_long_entry_matches_hand_computed_arithmetic(orders) -> None:
    """The long trade plan derived from the spec.

    At Bar 20 (index 20):
    # §3 EMA(3) converges to 1/3 * 1.1000 + 2/3 * 1.0990 at Bar 19, so EMA[19] = 1.099333
    # §3 EMA(3)[20] = Close[20]*0.5 + EMA[19]*0.5 = 1.11000 * 0.5 + 1.099333 * 0.5 = 1.104666
    # §4 CCI(14) > +100 because price jumped 100 pips
    # §6 dist_ema = (C[t] - EMA[t]) + 5 pips = (1.110000 - 1.104666) + 0.00050 = 0.005833
    # §6 dist_cap = 200 pips = 0.02000
    # §6 dist = min(0.005833, 0.02000) = 0.005833
    # §6 stop = Close_t - dist = 1.110000 - 0.005833 = 1.104166
    # §7 TP1 = Close_t + 200 pips = 1.11000 + 0.02000 = 1.13000
    """
    o = orders[0]

    assert o.direction == 1
    assert o.entry == "market"
    assert o.decision_close == pytest.approx(1.11000, abs=1e-9)
    assert o.stop.price == pytest.approx(1.104166, abs=1e-4)

    assert [leg.label for leg in o.exits] == ["TP1"]
    assert o.exits[0].price == pytest.approx(1.13000, abs=1e-9)
    assert o.exits[0].fraction == pytest.approx(1.0)
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)

    assert o.stop.move_to_breakeven_on == "TP1"


def test_short_entry_matches_hand_computed_arithmetic(orders) -> None:
    """The short trade plan derived from the spec.

    At Bar 35 (index 35):
    # §3 EMA(3) converges to 1/3 * 1.1100 + 2/3 * 1.1110 at Bar 34, so EMA[34] = 1.110666
    # §3 EMA(3)[35] = Close[35]*0.5 + EMA[34]*0.5 = 1.10000 * 0.5 + 1.110666 * 0.5 = 1.105333
    # §5 CCI(14) < -100 because price dropped 100 pips
    # §6 dist_ema = (EMA[t] - C[t]) + 5 pips = (1.105333 - 1.100000) + 0.00050 = 0.005833
    # §6 dist_cap = 200 pips = 0.02000
    # §6 dist = min(0.005833, 0.02000) = 0.005833
    # §6 stop = Close_t + dist = 1.100000 + 0.005833 = 1.105833
    # §7 TP1 = Close_t - 200 pips = 1.10000 - 0.02000 = 1.08000
    """
    o = orders[1]

    assert o.direction == -1
    assert o.entry == "market"
    assert o.decision_close == pytest.approx(1.10000, abs=1e-9)
    assert o.stop.price == pytest.approx(1.105833, abs=1e-4)

    assert [leg.label for leg in o.exits] == ["TP1"]
    assert o.exits[0].price == pytest.approx(1.08000, abs=1e-9)
    assert o.exits[0].fraction == pytest.approx(1.0)
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)


def test_strategy_is_free_of_lookahead(frames) -> None:
    """Every Wave-2 strategy must pass this on real data too."""
    assert_no_lookahead_v2(_FixtureScale(), frames)
