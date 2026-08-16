import pytest
import pandas as pd
from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.liquidity_grab_fade import LiquidityGrabFade

OPENS = [10.00, 10.15, 10.29, 10.40, 10.48, 10.50, 10.48, 10.40, 10.29, 10.15, 10.00, 9.85, 9.71, 9.60, 9.52, 9.50, 9.52, 9.60, 9.71, 9.85, 10.00, 10.15, 10.29, 10.40, 10.48, 10.50, 10.48, 10.40, 10.29, 10.15, 10.00, 10.20, 9.71, 9.60, 9.52, 9.95, 9.90, 9.60, 9.71, 9.85, 10.00, 10.15, 10.29, 10.40, 10.48, 10.50, 10.48, 10.40, 10.29, 10.15, 10.00, 9.85, 9.71, 9.60, 9.52, 9.50, 9.52, 9.60, 9.71, 9.85, 10.00, 9.60, 10.29, 10.40, 10.48, 9.85, 9.90, 10.40, 10.29, 10.15, 10.00, 9.85, 9.71, 9.60, 9.52, 9.50, 9.52, 9.60, 9.71, 9.85]
HIGHS = [10.10, 10.25, 10.39, 10.50, 10.58, 10.60, 10.58, 10.50, 10.39, 10.25, 10.10, 9.95, 9.81, 9.70, 9.62, 9.20, 9.62, 9.70, 9.81, 9.95, 10.10, 10.25, 10.39, 10.50, 10.58, 10.60, 10.58, 10.50, 10.39, 10.25, 10.10, 10.30, 9.81, 10.80, 9.62, 10.00, 10.50, 9.70, 9.81, 9.95, 10.10, 10.25, 10.39, 10.50, 10.58, 10.60, 10.58, 10.50, 10.39, 10.25, 10.10, 9.95, 9.81, 9.70, 9.62, 9.60, 9.62, 9.70, 9.81, 9.95, 10.10, 9.90, 10.39, 10.50, 10.58, 10.00, 9.95, 10.50, 10.39, 10.25, 10.10, 9.95, 9.81, 9.70, 9.62, 9.60, 9.62, 9.70, 9.81, 9.95]
LOWS = [9.90, 10.05, 10.19, 10.30, 10.38, 10.40, 10.38, 10.30, 10.19, 10.05, 9.90, 9.75, 9.61, 9.50, 9.42, 9.00, 9.42, 9.50, 9.61, 9.75, 9.90, 10.05, 10.19, 10.30, 10.38, 10.40, 10.38, 10.30, 10.19, 10.05, 9.90, 9.90, 9.61, 9.50, 9.42, 9.80, 9.80, 9.50, 9.61, 9.75, 9.90, 10.05, 10.19, 10.30, 10.38, 10.40, 10.38, 10.30, 10.19, 10.05, 9.90, 9.75, 9.61, 9.50, 9.42, 9.40, 9.42, 9.50, 9.61, 9.75, 9.90, 9.50, 10.19, 9.20, 10.38, 9.80, 9.30, 10.30, 10.19, 10.05, 9.90, 9.75, 9.61, 9.50, 9.42, 9.40, 9.42, 9.50, 9.61, 9.75]
CLOSES = [10.00, 10.15, 10.29, 10.40, 10.48, 10.50, 10.48, 10.40, 10.29, 10.15, 10.00, 9.85, 9.71, 9.60, 9.52, 9.50, 9.52, 9.60, 9.71, 9.85, 10.00, 10.15, 10.29, 10.40, 10.48, 10.50, 10.48, 10.40, 10.29, 10.15, 10.00, 10.00, 9.71, 10.70, 9.52, 9.90, 10.40, 9.60, 9.71, 9.85, 10.00, 10.15, 10.29, 10.40, 10.48, 10.50, 10.48, 10.40, 10.29, 10.15, 10.00, 9.85, 9.71, 9.60, 9.52, 9.50, 9.52, 9.60, 9.71, 9.85, 10.00, 9.80, 10.29, 9.30, 10.48, 9.90, 9.40, 10.40, 10.29, 10.15, 10.00, 9.85, 9.71, 9.60, 9.52, 9.50, 9.52, 9.60, 9.71, 9.85]

class TestLiquidityGrabFade(LiquidityGrabFade):
    @property
    def warmup_bars(self) -> int:
        return 20

@pytest.fixture
def frames():
    df = pd.DataFrame({
        "Open": OPENS,
        "High": HIGHS,
        "Low": LOWS,
        "Close": CLOSES,
    }, index=pd.date_range("2020-01-01", periods=80, freq="4h"))
    return {"H4": df}

def test_long_entry_and_levels(frames):
    strat = TestLiquidityGrabFade()
    orders = strat.generate_orders(frames)
    
    assert len(orders) == 2
    long_order = orders[0]
    
    assert long_order.direction == 1
    assert long_order.entry == "market"
    assert long_order.entry_price is None
    
    # §6 Initial stop: G_t - 4.0 * pip = 9.42 - 0.0004 = 9.4196
    # G_t is the grab extreme, which is LOWS[34] = 9.42
    assert abs(long_order.stop.price - 9.4196) < 1e-6
    
    # §7 TP: nearest confirmed swing high > 10.40 (Close[t])
    # The confirmed swing high from i=25 is 10.60
    assert abs(long_order.exits[0].price - 10.60) < 1e-6

def test_short_entry_and_levels(frames):
    strat = TestLiquidityGrabFade()
    orders = strat.generate_orders(frames)
    
    short_order = orders[1]
    assert short_order.direction == -1
    assert short_order.entry == "market"
    
    # §6 Initial stop: G_t + 4.0 * pip = 10.58 + 0.0004 = 10.5804
    # G_t is the grab extreme, which is HIGHS[64] = 10.58
    assert abs(short_order.stop.price - 10.5804) < 1e-6
    
    # §7 TP: nearest confirmed swing low < 9.40 (Close[t])
    # The confirmed swing low from i=15 is 9.00
    assert abs(short_order.exits[0].price - 9.00) < 1e-6

def test_fractions_sum_to_one(frames):
    strat = TestLiquidityGrabFade()
    orders = strat.generate_orders(frames)
    
    # fractions sum to exactly 1.00 (single leg)
    # §7 Exit legs
    assert orders[0].exits[0].fraction == 1.00
    assert sum(leg.fraction for leg in orders[0].exits) == 1.00
    
    assert orders[1].exits[0].fraction == 1.00
    assert sum(leg.fraction for leg in orders[1].exits) == 1.00

def test_no_lookahead(frames):
    strat = TestLiquidityGrabFade()
    assert_no_lookahead_v2(strat, frames)
