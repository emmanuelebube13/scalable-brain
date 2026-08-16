"""GOLDEN FIXTURE - PSAR GBPJPY Daily."""

from __future__ import annotations

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2, StrategyMetadataV2
from src.layer0.strategies.research.psar_gbpjpy_daily import PsarGbpjpyDaily

# Hand written bars.
# 36 D1 bars to give enough warmup and two trend reversals.
# High/Low are Close +/- 1.00 on every bar.
CLOSES = [
    # 0..10: Uptrend
    100.00,
    101.00,
    102.00,
    103.00,
    104.00,
    105.00,
    106.00,
    107.00,
    108.00,
    109.00,
    110.00,
    # 11..21: Downtrend (reversal occurs at 11)
    108.00,
    106.00,
    104.00,
    102.00,
    100.00,
    98.00,
    96.00,
    94.00,
    92.00,
    90.00,
    88.00,
    # 22..35: Uptrend (reversal occurs at 23)
    90.00,
    92.00,
    94.00,
    96.00,
    98.00,
    100.00,
    102.00,
    104.00,
    106.00,
    108.00,
    110.00,
    112.00,
    114.00,
    116.00,
]


class _FixtureScale(PsarGbpjpyDaily):
    ATR_PERIOD = 2  # Shrink ATR period

    @property
    def warmup_bars(self) -> int:
        return 3

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="psar_gbpjpy_daily",
            name="PSAR GBPJPY Daily",
            version="0.1.0",
            author="n5-fleet",
            hypothesis="GBP/JPY daily trends persist for weeks at a time...",
            granularities=["D1"],
            pairs=["GBP_USD"],  # dummy pair to pass validation
            primary_granularity="D1",
            context_granularities=(),
            simulate_on="H1",
        )


@pytest.fixture(scope="module")
def frames() -> dict:
    idx = pd.date_range("2020-01-01", periods=len(CLOSES), freq="1D", tz="UTC")
    d1 = pd.DataFrame(
        {
            "Open": CLOSES,
            "High": [c + 1.00 for c in CLOSES],
            "Low": [c - 1.00 for c in CLOSES],
            "Close": CLOSES,
            "Volume": 1.0,
        },
        index=idx,
    )
    return {"D1": d1}


@pytest.fixture(scope="module")
def orders(frames) -> list:
    return list(_FixtureScale().generate_orders(frames))


def test_emits_exactly_the_expected_reversals(orders) -> None:
    """Rule §4 and §5: fire only on direction state flips.

    At t=11 (2020-01-12), trend flips long to short.
    At t=23 (2020-01-24), trend flips short to long.
    """
    assert [str(o.decision_bar) for o in orders] == [
        "2020-01-12 00:00:00+00:00",
        "2020-01-24 00:00:00+00:00",
    ]


def test_first_order_matches_hand_computed_arithmetic(orders) -> None:
    """The short trade plan, derived from the spec §6 and §7.

    At t=11 (bar index 11), a long-to-short reversal occurs:
    # §3 Low_11 (107.00) < SAR_11 (108.00).
    # §4.2 The extreme point of the prior long trend is High_10.
    # §6 SAR_12 = EP of prior long trend = High_10 = 110.00 + 1.00 = 111.00.
    """
    o = orders[0]

    assert o.direction == -1
    assert o.entry == "market"
    assert o.entry_price is None

    # §6 stop = EP of prior long trend = 111.00
    assert o.stop.price == pytest.approx(111.00, abs=1e-9)
    assert o.stop.trail_atr_multiple == pytest.approx(2.0, abs=1e-9)


def test_second_order_matches_hand_computed_arithmetic(orders) -> None:
    """The long trade plan, derived from the spec §6 and §7.

    At t=23 (bar index 23), a short-to-long reversal occurs:
    # §3 High_23 (93.00) > SAR_23 (91.00).
    # §4.2 The extreme point of the prior short trend is Low_21.
    # §6 SAR_24 = EP of prior short trend = Low_21 = 88.00 - 1.00 = 87.00.
    """
    o = orders[1]

    assert o.direction == 1
    assert o.entry == "market"
    assert o.entry_price is None

    # §6 stop = EP of prior short trend = 87.00
    assert o.stop.price == pytest.approx(87.00, abs=1e-9)
    assert o.stop.trail_atr_multiple == pytest.approx(2.0, abs=1e-9)


def test_exit_legs_are_correct(orders) -> None:
    """Rule §7: Exit leg must be time backstop, 126 bars, fraction 1.0."""
    for o in orders:
        assert len(o.exits) == 1
        leg = o.exits[0]
        # §7 Fraction must be exactly 1.0
        assert leg.fraction == pytest.approx(1.0, abs=1e-9)
        assert leg.kind == "time"
        assert leg.bars == 126
        assert leg.label == "time-backstop"


def test_strategy_is_free_of_lookahead(frames) -> None:
    """Every Wave-2 strategy must pass this on real data too."""
    assert_no_lookahead_v2(_FixtureScale(), frames)
