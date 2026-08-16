import pytest
from unittest.mock import patch
from datetime import datetime, timezone

from src.common.db import get_psycopg2_connection
from src.regime_aware.outcomes import write_trial_outcomes

@pytest.fixture(autouse=True)
def clean_table():
    conn = get_psycopg2_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM fact_regime_trial_outcomes")
        conn.commit()
    finally:
        conn.close()

def get_db_rows():
    conn = get_psycopg2_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM fact_regime_trial_outcomes")
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()

def make_trade(**kwargs):
    trade = {
        "timestamp": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "asset_id": 1,
        "granularity": "H1",
        "arm": "blind",
        "regime_at_entry": "UNKNOWN",
        "regime_source": "d1_trend",
        "run_id": "run_1",
        "strategy_key": "test_strat",
        "engine": "position_engine_v2",
        "is_winner": 1,
        "r_multiple": 2.0,
        "holding_bars": 5
    }
    trade.update(kwargs)
    return trade

def test_idempotent_writes():
    trade = make_trade()
    # Write once
    write_trial_outcomes([trade])
    rows = get_db_rows()
    assert len(rows) == 1

    # Write again
    write_trial_outcomes([trade])
    rows2 = get_db_rows()
    assert len(rows2) == 1

def test_invalid_arm_rejected():
    with pytest.raises(ValueError, match="Invalid or missing arm"):
        write_trial_outcomes([make_trade(arm="invalid")])

def test_missing_regime_source_rejected():
    with pytest.raises(ValueError, match="Invalid or missing regime_source"):
        write_trial_outcomes([make_trade(regime_source=None)])

def test_unknown_regime_round_trips():
    trade = make_trade(regime_at_entry="UNKNOWN")
    write_trial_outcomes([trade])
    rows = get_db_rows()
    assert len(rows) == 1
    assert rows[0]["regime_at_entry"] == "UNKNOWN"

def test_different_run_ids_kept_separate():
    write_trial_outcomes([make_trade(run_id="run_1")])
    write_trial_outcomes([make_trade(run_id="run_2")])
    rows = get_db_rows()
    assert len(rows) == 2
    assert {"run_1", "run_2"} == {r["run_id"] for r in rows}

def test_walk_forward_module_used():
    with patch("src.regime_aware.outcomes.WF.assign_oos") as mock_assign:
        import pandas as pd
        # Return dummy arrays that pandas can safely assign
        mock_assign.return_value = (
            pd.Series([True]),
            pd.Series([99])
        )
        
        with patch("src.regime_aware.outcomes.WF.series_bounds") as mock_bounds:
            mock_bounds.return_value = (pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-02"))
            
            with patch("src.regime_aware.outcomes.WF.default_folds") as mock_folds:
                mock_folds.return_value = ["dummy_fold"]
                
                trade = make_trade()
                write_trial_outcomes([trade])
                
                assert mock_assign.called
                
                rows = get_db_rows()
                assert len(rows) == 1
                assert rows[0]["is_oos"] is True
                assert rows[0]["fold_id"] == 99
