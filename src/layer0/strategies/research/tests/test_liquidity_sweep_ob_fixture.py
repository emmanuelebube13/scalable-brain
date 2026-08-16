from typing import Mapping

import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.liquidity_sweep_ob import LiquiditySweepOb


class _FixtureScale(LiquiditySweepOb):
    @property
    def warmup_bars(self) -> int:
        return 12


def _make_long_frames() -> Mapping[str, pd.DataFrame]:
    OPENS = [1.1500] * 30
    HIGHS = [1.1600] * 30
    LOWS = [1.1400] * 30
    CLOSES = [1.1500] * 30

    HIGHS[5] = 1.2500
    LOWS[5] = 1.1200
    for i in range(5):
        HIGHS[i] = 1.2000 + i * 0.0010
        LOWS[i] = 1.1300 - i * 0.0010
    for i in range(6, 11):
        HIGHS[i] = 1.2000 - (i - 6) * 0.0010
        LOWS[i] = 1.1300 + (i - 6) * 0.0010

    # Bar 15: OB (Bearish)
    OPENS[15] = 1.1380
    CLOSES[15] = 1.1320
    HIGHS[15] = 1.1400
    LOWS[15] = 1.1300

    # Bar 16: Bullish BOS (Close > 1.2500)
    OPENS[16] = 1.1200
    CLOSES[16] = 1.2600
    HIGHS[16] = 1.2700
    LOWS[16] = 1.1150

    # Bar 17: Sweep Low (Low < 1.1200, Close > 1.1200)
    OPENS[17] = 1.2600
    CLOSES[17] = 1.1250
    HIGHS[17] = 1.2600
    LOWS[17] = 1.1150

    # Bar 18: Valid Decision
    OPENS[18] = 1.1250
    CLOSES[18] = 1.1800
    HIGHS[18] = 1.1900
    LOWS[18] = 1.1250

    h4 = pd.DataFrame(
        {"Open": OPENS, "High": HIGHS, "Low": LOWS, "Close": CLOSES},
        index=pd.date_range("2026-01-01", periods=30, freq="4h"),
    )
    return {"H4": h4}


def _make_short_frames() -> Mapping[str, pd.DataFrame]:
    OPENS = [1.1500] * 30
    HIGHS = [1.1600] * 30
    LOWS = [1.1400] * 30
    CLOSES = [1.1500] * 30

    HIGHS[5] = 1.1800
    LOWS[5] = 1.0500

    for i in range(5):
        LOWS[i] = 1.1000 - i * 0.0010
        HIGHS[i] = 1.1700 + i * 0.0010
    for i in range(6, 11):
        LOWS[i] = 1.1000 + (i - 6) * 0.0010
        HIGHS[i] = 1.1700 - (i - 6) * 0.0010

    # Bar 15: OB (Bullish)
    OPENS[15] = 1.1620
    CLOSES[15] = 1.1680
    HIGHS[15] = 1.1700
    LOWS[15] = 1.1600

    # Bar 16: Bearish BOS (Close < 1.0500)
    OPENS[16] = 1.1800
    CLOSES[16] = 1.0400
    LOWS[16] = 1.0300
    HIGHS[16] = 1.1850

    # Bar 17: Sweep High (High > 1.1800, Close < 1.1800)
    OPENS[17] = 1.0400
    CLOSES[17] = 1.1750
    HIGHS[17] = 1.1850
    LOWS[17] = 1.0300

    # Bar 18: Valid Decision
    OPENS[18] = 1.1750
    CLOSES[18] = 1.1200
    LOWS[18] = 1.1100
    HIGHS[18] = 1.1750

    h4 = pd.DataFrame(
        {"Open": OPENS, "High": HIGHS, "Low": LOWS, "Close": CLOSES},
        index=pd.date_range("2026-01-01", periods=30, freq="4h"),
    )
    return {"H4": h4}


def test_liquidity_sweep_ob_long():
    frames = _make_long_frames()
    orders = _FixtureScale().generate_orders(frames)

    assert len(orders) == 1
    o = orders[0]

    assert o.direction == 1
    assert o.entry == "buy_limit"

    # §4 entry_price = OB_high = 1.1400
    assert o.entry_price == pytest.approx(1.1400)

    # §6 stop.price = OB_low - 4.0 pip = 1.1300 - 0.0004 = 1.1296
    assert o.stop.price == pytest.approx(1.1296)
    assert o.stop.move_to_breakeven_on is None

    # §7 exits
    assert len(o.exits) == 1
    ex = o.exits[0]

    # §7 fraction must sum to exactly 1.0
    assert ex.fraction == 1.0
    assert ex.kind == "take_profit"

    # §7 TP = nearest confirmed swing high > entry = 1.2500
    assert ex.price == pytest.approx(1.2500)


def test_liquidity_sweep_ob_short():
    frames = _make_short_frames()
    orders = _FixtureScale().generate_orders(frames)

    assert len(orders) == 1
    o = orders[0]

    assert o.direction == -1
    assert o.entry == "sell_limit"

    # §5 entry_price = OB_low - 1.0 pip = 1.1600 - 0.0001 = 1.1599
    assert o.entry_price == pytest.approx(1.1599)

    # §6 stop.price = OB_high + 4.0 pip = 1.1700 + 0.0004 = 1.1704
    assert o.stop.price == pytest.approx(1.1704)
    assert o.stop.move_to_breakeven_on is None

    assert len(o.exits) == 1
    ex = o.exits[0]

    # §7 fraction must sum to exactly 1.0
    assert ex.fraction == 1.0
    assert ex.kind == "take_profit"

    # §7 TP = nearest confirmed swing low < entry = 1.0500
    assert ex.price == pytest.approx(1.0500)


def test_liquidity_sweep_ob_rr_floor():
    frames = _make_long_frames()

    # §7 if RR < 2.0, no OrderIntent is emitted
    # Old TP = 1.2500. Entry = 1.1400, Risk = 0.0104.
    # We change the swing high so that RR < 2.0. Let's set TP to 1.1500.
    frames["H4"].loc[frames["H4"].index[5], "High"] = 1.1500

    orders = _FixtureScale().generate_orders(frames)
    assert len(orders) == 0


def test_liquidity_sweep_ob_no_lookahead():
    assert_no_lookahead_v2(_FixtureScale(), _make_long_frames())
