"""Golden fixture for outside_hma_klinger."""

import pandas as pd

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.outside_hma_klinger import OutsideHmaKlinger

# 65 bars total.
# 0-60: all 10.00 to warm up EMAs and HMA.
CLOSES = [10.00] * 61 + [10.20, 9.80, 10.00, 10.00]
OPENS = [10.00] * 61 + [10.00, 10.10, 10.00, 10.00]
HIGHS = [10.00] * 61 + [10.50, 10.40, 10.00, 10.00]
LOWS = [10.00] * 61 + [9.50, 9.60, 10.00, 10.00]
VOLS = [100.00] * 61 + [2000.00, 5000.00, 100.00, 100.00]


def _make_frames():
    dates = pd.date_range("2026-01-01", periods=65, freq="4h")
    df = pd.DataFrame(
        {
            "Open": OPENS,
            "High": HIGHS,
            "Low": LOWS,
            "Close": CLOSES,
            "Volume": VOLS,
        },
        index=dates,
    )
    return {"H4": df}


def test_long_setup_and_entry_logic():
    strat = OutsideHmaKlinger()
    orders = strat.generate_orders(_make_frames())

    assert len(orders) == 2
    long_order = orders[0]

    assert long_order.direction == 1
    assert long_order.entry == "market"
    assert long_order.entry_price is None


def test_long_exit_arithmetic():
    strat = OutsideHmaKlinger()
    orders = strat.generate_orders(_make_frames())
    long_order = orders[0]

    # §6 Initial stop (long): SL_long = A × 0.9880
    # A = Close = 10.20
    # §6 stop = 10.20 * 0.9880 = 10.07760
    assert abs(long_order.stop.price - 10.0776) < 1e-9

    # §7 TP1 (long): A × 1.0060
    # A = Close = 10.20
    # §7 tp1 = 10.20 * 1.0060 = 10.26120
    assert abs(long_order.exits[0].price - 10.2612) < 1e-9

    # Assert fraction sum is 1.0
    # §7 fraction = 1.0
    assert long_order.exits[0].fraction == 1.0


def test_short_setup_and_entry_logic():
    strat = OutsideHmaKlinger()
    orders = strat.generate_orders(_make_frames())
    short_order = orders[1]

    assert short_order.direction == -1
    assert short_order.entry == "market"
    assert short_order.entry_price is None


def test_short_exit_arithmetic():
    strat = OutsideHmaKlinger()
    orders = strat.generate_orders(_make_frames())
    short_order = orders[1]

    # §6 Initial stop (short): SL_short = A × 1.0150
    # A = Close = 9.80
    # §6 stop = 9.80 * 1.0150 = 9.94700
    assert abs(short_order.stop.price - 9.947) < 1e-9

    # §7 TP1 (short): A × 0.9925
    # A = Close = 9.80
    # §7 tp1 = 9.80 * 0.9925 = 9.72650
    assert abs(short_order.exits[0].price - 9.7265) < 1e-9

    # Assert fraction sum is 1.0
    # §7 fraction = 1.0
    assert short_order.exits[0].fraction == 1.0


def test_no_lookahead():
    strat = OutsideHmaKlinger()
    frames = _make_frames()
    assert_no_lookahead_v2(strat, frames)
