"""Unit tests for MODEL-004 metrics + shrinkage (no DB/network)."""
from __future__ import annotations

import numpy as np

from src.system1.attribution import metrics as M


def test_win_rate():
    assert M.win_rate([1, 1, 0, 0]) == 0.5
    assert M.win_rate([]) == 0.0


def test_profit_factor():
    # gross profit 3, gross loss 1 -> 3.0
    assert M.profit_factor([2.0, 1.0, -1.0]) == 3.0
    assert M.profit_factor([1.0, 2.0]) == float("inf")  # no losses
    assert M.profit_factor([-1.0, -2.0]) == 0.0


def test_sharpe_annualized_by_trade_frequency():
    r = [0.1, -0.05, 0.2, -0.1, 0.15]
    s_17 = M.annualized_sharpe(r, trades_per_year=17.0)
    s_68 = M.annualized_sharpe(r, trades_per_year=68.0)
    # Sharpe scales with sqrt(trades_per_year); 4x cadence => 2x Sharpe (same mean/std).
    assert s_17 > 0
    assert np.isclose(s_68 / s_17, np.sqrt(68.0 / 17.0))


def test_sharpe_short_or_flat_series():
    assert np.isnan(M.annualized_sharpe([0.1], trades_per_year=17.0))  # < 2 trades
    assert M.annualized_sharpe([0.1, 0.1, 0.1], trades_per_year=17.0) == 0.0  # zero variance


def test_max_drawdown_bounded_for_any_input():
    # Invariant: drawdown is always a fraction in [0, 1], even for all-losing / extreme series.
    for series in ([1.0, -0.5, -0.5, 1.0], [-1.0] * 50, [-1000.0] * 10, [3.0, -1.0, -1.0, -1.0]):
        dd = M.max_drawdown(series)
        assert 0.0 <= dd <= 1.0, (series, dd)


def test_max_drawdown_known_value():
    # All losers at -1R with f=1%: each step multiplies equity by 0.99. After 3 losses the
    # trough is 0.99**3; peak is 1.0 (the start) => dd = 1 - 0.99**3.
    dd = M.max_drawdown([-1.0, -1.0, -1.0], risk_fraction=0.01)
    assert np.isclose(dd, 1.0 - 0.99 ** 3)


def test_risk_fraction_does_not_change_sharpe():
    # Sharpe is f-independent (f cancels in mean/std); only annualization basis matters.
    r = [0.4, -1.0, 0.8, -1.0, 1.2]
    assert M.annualized_sharpe(r, 20.0) == M.annualized_sharpe(r, 20.0)


def test_recovery_factor_is_return_over_drawdown():
    r = [1.0, -0.5, 0.8, -0.3, 0.6]
    eq = M.equity_curve(r, 0.01)
    expected = (eq[-1] - 1.0) / M.max_drawdown(r, 0.01)
    assert np.isclose(M.recovery_factor(r, 0.01), expected)


def test_validate_metrics_flags_impossible_values():
    assert M.validate_metrics({"max_drawdown": 0.2, "sharpe": 2.0}) == []
    assert M.validate_metrics({"max_drawdown": 1182.8, "sharpe": 2.0})  # >100% drawdown
    assert M.validate_metrics({"max_drawdown": 0.2, "sharpe": 42.5})    # implausible Sharpe


def test_shrinkage_boundary():
    # cell_n = N_min-1 -> low confidence (shrunk); cell_n = N_min -> high confidence (raw)
    v19, lc19 = M.bayesian_shrinkage(cell_metric=2.0, global_metric=1.0, cell_n=19, min_n=20)
    v20, lc20 = M.bayesian_shrinkage(cell_metric=2.0, global_metric=1.0, cell_n=20, min_n=20)
    assert lc19 is True and lc20 is False
    assert v20 == 2.0
    # shrunk value lies strictly between cell (2.0) and global (1.0)
    assert 1.0 < v19 < 2.0


def test_shrinkage_handles_inf():
    # inf profit factor in a thin cell should not produce inf after shrinkage
    v, lc = M.bayesian_shrinkage(float("inf"), 1.5, cell_n=5, min_n=20)
    assert lc is True and np.isfinite(v)
