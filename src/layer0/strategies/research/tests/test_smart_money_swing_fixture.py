import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.smart_money_swing import SmartMoneySwing


class _FixtureScale(SmartMoneySwing):
    @property
    def warmup_bars(self) -> int:
        return 200


@pytest.fixture(scope="module")
def frames() -> dict:
    CLOSES = (
        [10.00] * 300
        + [10.10, 10.20, 10.30, 10.40, 10.50, 10.60, 10.70, 10.80, 10.90, 11.00]
        + [10.50, 10.35, 10.65]
        + [10.00] * 300
        + [9.90, 9.80, 9.70, 9.60, 9.50, 9.40, 9.30, 9.20, 9.10, 9.00]
        + [9.50, 9.65, 9.35]
    )
    idx = pd.date_range("2020-01-01", periods=len(CLOSES), freq="4h", tz="UTC")
    h4 = pd.DataFrame(
        {
            "Open": CLOSES,
            "High": [c + 0.10 for c in CLOSES],
            "Low": [c - 0.10 for c in CLOSES],
            "Close": CLOSES,
            "Volume": 1.00,
        },
        index=idx,
    )
    d1 = (
        h4.resample("1D")
        .agg(
            {
                "Open": "first",
                "High": "max",
                "Low": "min",
                "Close": "last",
                "Volume": "sum",
            }
        )
        .dropna()
    )
    return {"H4": h4, "D1": d1}


@pytest.fixture(scope="module")
def orders(frames) -> list:
    return list(_FixtureScale().generate_orders(frames))


def test_long_setup(orders) -> None:
    # §6 stop = min(Low[t-9 ... t]) = 10.35 - 0.10 = 10.25
    # R = Close - stop = 10.65 - 10.25 = 0.40
    # §7 TP1 = Close + 1.0 * R = 10.65 + 0.40 = 11.05
    # §7 TP2 = Close + 2.0 * R = 10.65 + 0.80 = 11.45
    o = orders[0]
    assert o.direction == 1
    assert o.entry == "market"
    assert o.decision_close == pytest.approx(10.65, abs=1e-9)
    assert o.stop.price == pytest.approx(10.25, abs=1e-9)

    assert o.exits[0].price == pytest.approx(11.05, abs=1e-9)
    assert o.exits[1].price == pytest.approx(11.45, abs=1e-9)


def test_short_setup(orders) -> None:
    # §6 stop = max(High[t-9 ... t]) = 9.65 + 0.10 = 9.75
    # R = stop - Close = 9.75 - 9.35 = 0.40
    # §7 TP1 = Close - 1.0 * R = 9.35 - 0.40 = 8.95
    # §7 TP2 = Close - 2.0 * R = 9.35 - 0.80 = 8.55
    o = orders[1]
    assert o.direction == -1
    assert o.entry == "market"
    assert o.decision_close == pytest.approx(9.35, abs=1e-9)
    assert o.stop.price == pytest.approx(9.75, abs=1e-9)

    assert o.exits[0].price == pytest.approx(8.95, abs=1e-9)
    assert o.exits[1].price == pytest.approx(8.55, abs=1e-9)


def test_exits_and_fractions(orders) -> None:
    """
    §7 exit legs must sum to exactly 1.00
    §6 trail_atr_multiple = 2.00, BE after TP1
    """
    for o in orders:
        assert len(o.exits) == 2
        assert o.exits[0].label == "TP1"
        assert o.exits[1].label == "TP2"
        assert o.exits[0].fraction == pytest.approx(0.50, abs=1e-9)
        assert o.exits[1].fraction == pytest.approx(0.50, abs=1e-9)
        assert sum(leg.fraction for leg in o.exits) == pytest.approx(1.00, abs=1e-9)

        assert o.stop.move_to_breakeven_on == "TP1"
        assert o.stop.trail_atr_multiple == pytest.approx(2.00, abs=1e-9)


def test_no_lookahead(frames) -> None:
    """
    §9 causality audit must pass
    """
    assert_no_lookahead_v2(_FixtureScale(), frames)
