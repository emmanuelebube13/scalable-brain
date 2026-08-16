"""GOLDEN FIXTURE for pinbar_key_level_50pct."""

from __future__ import annotations

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.pinbar_key_level_50pct import PinbarKeyLevel50pct


class _FixtureScale(PinbarKeyLevel50pct):
    """Production logic, fixture-sized lookbacks."""

    SWING_PERIOD = 2
    ATR_PERIOD = 1

    @property
    def warmup_bars(self) -> int:
        return 9


BARS = [
    # 0
    (10.50, 11.00, 10.00, 10.50),
    # 1
    (10.00, 10.50, 9.50, 10.00),
    # 2 - swing low 1 (L=9.00) confirms at day 4
    (9.50, 10.00, 9.00, 9.50),
    # 3
    (10.00, 10.50, 9.50, 10.00),
    # 4
    (10.50, 11.00, 10.00, 10.50),
    # 5
    (11.50, 12.00, 11.00, 11.50),
    # 6 - swing high 1 (H=13.00) confirms at day 8
    (12.50, 13.00, 12.00, 12.50),
    # 7
    (11.50, 12.00, 11.00, 11.50),
    # 8
    (10.50, 11.00, 10.00, 10.50),
    # 9 - Setup C_prev = 10.00 for the long pin bar
    (10.50, 11.00, 10.00, 10.00),
    # 10: The Long Pin Bar (decision_bar: 2020-01-11 00:00:00+00:00)
    # H=10.00, L=9.00, O=9.80, C=9.90.
    # rng = 1.00. C_prev = 10.00 -> TR = 1.00 -> ATR = 1.00.
    # tail_dn = 9.80 - 9.00 = 0.80 >= 0.67
    # body = 9.90 - 9.80 = 0.10 <= 0.33
    (9.80, 10.00, 9.00, 9.90),
    # 11
    (10.00, 10.50, 9.50, 10.00),
    # 12
    (10.50, 11.00, 10.00, 10.50),
    # 13
    (11.50, 12.00, 11.00, 11.50),
    # 14 - Setup C_prev = 13.00 for the short pin bar
    (11.50, 13.00, 12.00, 13.00),
    # 15: The Short Pin Bar (decision_bar: 2020-01-16 00:00:00+00:00)
    # H=13.00, L=12.00, O=12.20, C=12.10.
    # rng = 1.00. C_prev = 13.00 -> TR = 1.00 -> ATR = 1.00.
    # tail_up = 13.00 - 12.20 = 0.80 >= 0.67
    # body = 12.20 - 12.10 = 0.10 <= 0.33
    (12.20, 13.00, 12.00, 12.10),
]


@pytest.fixture(scope="module")
def frames() -> dict:
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
    return {"D1": d1}


@pytest.fixture(scope="module")
def orders(frames) -> list:
    return list(_FixtureScale().generate_orders(frames))


def test_emits_exactly_two_orders(orders) -> None:
    # §4 and §5 entry conditions met on days 10 and 15
    assert len(orders) == 2
    assert [str(o.decision_bar) for o in orders] == [
        "2020-01-11 00:00:00+00:00",
        "2020-01-16 00:00:00+00:00",
    ]


def test_long_pin_bar_order(orders) -> None:
    """Check the long trade math and rules."""
    o = orders[0]

    assert o.direction == 1
    assert o.entry == "buy_limit"

    # §4 entry_price = (H_t + L_t) / 2 = (10.00 + 9.00) / 2 = 9.50
    assert o.entry_price == pytest.approx(9.50, abs=1e-9)

    # §6 stop = L_t - 0.10 * ATR14_t = 9.00 - 0.10 * 1.00 = 8.90
    assert o.stop.price == pytest.approx(8.90, abs=1e-9)

    # §4 TP = minimum confirmed swing-high > entry = 13.00
    assert o.exits[0].price == pytest.approx(13.00, abs=1e-9)

    # §7 exit fraction = 1.0
    assert o.exits[0].fraction == pytest.approx(1.0, abs=1e-9)
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)
    assert o.expires_after_bars == 24

    # §4 confluence = L_t = 9.00, matches confirmed swing low = 9.00. Diff = 0.00 <= 0.25 * 1.00 (ATR)
    # §4 2R gate = risk (0.60) * 2 = 1.20 <= reward (3.50)


def test_short_pin_bar_order(orders) -> None:
    """Check the short trade math and rules."""
    o = orders[1]

    assert o.direction == -1
    assert o.entry == "sell_limit"

    # §5 entry_price = (H_t + L_t) / 2 = (13.00 + 12.00) / 2 = 12.50
    assert o.entry_price == pytest.approx(12.50, abs=1e-9)

    # §6 stop = H_t + 0.10 * ATR14_t = 13.00 + 0.10 * 1.00 = 13.10
    assert o.stop.price == pytest.approx(13.10, abs=1e-9)

    # §5 TP = maximum confirmed swing-low < entry = 9.00
    assert o.exits[0].price == pytest.approx(9.00, abs=1e-9)

    # §7 exit fraction = 1.0
    assert o.exits[0].fraction == pytest.approx(1.0, abs=1e-9)
    assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.0, abs=1e-9)
    assert o.expires_after_bars == 24

    # §5 confluence = H_t = 13.00, matches confirmed swing high = 13.00. Diff = 0.00 <= 0.25 * 1.00 (ATR)
    # §5 2R gate = risk (0.60) * 2 = 1.20 <= reward (3.50)


def test_strategy_is_free_of_lookahead(frames) -> None:
    assert_no_lookahead_v2(_FixtureScale(), frames)
