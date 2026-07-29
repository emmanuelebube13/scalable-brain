"""frequency_stats builder: holding-time math, streaks, zero-month honesty."""

from __future__ import annotations

import pandas as pd
import pytest

from src.system1.analytics.frequency import (
    bar_hours,
    build_frequency_stats,
    max_consecutive_losses,
)


def test_bar_hours():
    assert bar_hours("H1") == 1.0
    assert bar_hours("H4") == 4.0
    assert bar_hours("D1") == 24.0
    assert bar_hours("M30") == 0.5
    with pytest.raises(ValueError):
        bar_hours("X9")


def test_max_consecutive_losses():
    assert (
        max_consecutive_losses(pd.Series([True, False, False, False, True, False])) == 3
    )
    assert max_consecutive_losses(pd.Series([True, True])) == 0
    assert max_consecutive_losses(pd.Series([], dtype=bool)) == 0


@pytest.fixture
def tagged():
    df = pd.DataFrame(
        {
            "strategy_id": [10] * 4,
            "regime": ["Ranging"] * 4,
            "granularity": ["H4"] * 4,
            "asset_id": [1] * 4,
            # 4 trades in Jan, then nothing until Apr — span has 2 empty months
            "entry_time": pd.to_datetime(
                ["2024-01-05", "2024-01-10", "2024-01-20", "2024-04-01"], utc=True
            ),
            "r_multiple": [2.0, -1.0, -1.0, 3.0],
            "is_winner": [True, False, False, True],
            "holding_bars": [6, 3, 3, 12],
            "is_oos": [True, True, True, False],  # last trade is in-sample
            "fold_id": pd.array([1, 1, 1, None], dtype="Int64"),
        }
    )
    return df


def test_cell_stats_oos_only_and_holding_hours(tagged):
    occupancy = pd.DataFrame(
        {
            "granularity": ["H4"],
            "asset_id": [1],
            "regime": ["Ranging"],
            "n_bars": [100],
            "occupancy": [0.4],
        }
    )
    out = build_frequency_stats(
        tagged, {(10, "Ranging", "H4")}, {1: "EUR_USD"}, occupancy, 0.34
    )
    cell = next(c for c in out["cells"] if c["pair"] == "EUR_USD")
    # in-sample Apr trade excluded: 3 trades, all in Jan 2024
    assert cell["n_trades"] == 3
    assert cell["trades_per_month"]["mean"] == 3.0  # single-month span, no dilution
    assert cell["holding_hours_mean"] == 16.0  # (6+3+3)*4h / 3
    assert cell["max_consecutive_losses"] == 2
    assert cell["avg_win_r"] == 2.0
    assert cell["avg_loss_r"] == -1.0
    assert out["gatekeeper_oos_approval_rate"] == 0.34
    occ = out["regime_occupancy"][0]
    assert occ["pair"] == "EUR_USD" and occ["occupancy"]["Ranging"] == 0.4
