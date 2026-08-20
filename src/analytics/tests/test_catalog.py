"""strategy_catalog builder: every strategy present, qualification truth preserved."""

from __future__ import annotations

import pandas as pd

from src.analytics.catalog import build_catalog

STRATEGY_DIM = pd.DataFrame(
    {
        "strategy_id": [1, 10],
        "strategy_name": ["Trend_EMA_ADX_H1", "Range_Stochastic_Divergence"],
        "strategy_type": ["BACKTEST", "MEAN_REVERSION"],
        "description": ["ema/adx", "stoch divergence"],
        "is_active": [False, True],
    }
)

REGIME_MAP = {
    "qualification_run_id": "run-123",
    "gates": {"profit_factor": 1.5},
    "empty_regimes": ["High-Vol"],
    "regimes": {
        "Ranging": [
            {
                "strategy_id": 10,
                "variant": "Range_Stochastic_Divergence@H1",
                "metrics": {"profit_factor": 2.94},
            }
        ]
    },
}

VETTING = {
    "rejection_detail": [
        {
            "strategy_id": 1,
            "variant": "Trend_EMA_ADX_H1@H1",
            "regime": "Ranging",
            "failed_gates": ["PF=0.89 < 1.50"],
        }
    ]
}


def test_catalog_covers_all_strategies_with_qualification_truth():
    cat = build_catalog(
        STRATEGY_DIM,
        REGIME_MAP,
        VETTING,
        {1: ["H1"], 10: ["H1", "H4"]},
        "2026-01-01T00:00:00Z",
    )
    assert cat["qualification_run_id"] == "run-123"
    by_id = {s["strategy_id"]: s for s in cat["strategies"]}
    assert set(by_id) == {"1", "10"}

    winner = by_id["10"]
    assert winner["qualified"] is True
    assert winner["qualified_regimes"] == ["Ranging"]
    assert winner["family"] == "mean-reversion"
    assert winner["granularities"] == ["H1", "H4"]
    assert winner["gates_passed"]["Range_Stochastic_Divergence@H1@Ranging"] == {
        "profit_factor": 2.94
    }

    loser = by_id["1"]
    assert loser["qualified"] is False and loser["qualified_regimes"] == []
    assert loser["family"] == "trend"
    assert loser["gates_failed"]["Trend_EMA_ADX_H1@H1@Ranging"] == ["PF=0.89 < 1.50"]


def test_catalog_survives_missing_vetting_report():
    cat = build_catalog(STRATEGY_DIM, REGIME_MAP, None, {}, "2026-01-01T00:00:00Z")
    assert all(s["gates_failed"] == {} for s in cat["strategies"])
