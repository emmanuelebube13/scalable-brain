import os
import json
import pytest
import pandas as pd
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from src.signals.watcher import BarWatcher, LATENCY_THRESHOLDS
from src.signals.build import build_signals, load_model_set
from src.signals.run import run_once
from src.queue_producer.producer import ScoredSignalProducer


@pytest.fixture
def mock_engine():
    return MagicMock()


def test_forming_bar_produces_no_signal():
    # Watcher filters for complete=true, so unclosed bar is excluded at SQL level.
    # We can mock the read_sql to return only complete=true or assert the query contains 'complete = true'.
    watcher = BarWatcher(engine=MagicMock())
    with patch("pandas.read_sql") as mock_read_sql:
        mock_read_sql.return_value = pd.DataFrame()
        watcher.get_new_closed_bars("H1")
        query = mock_read_sql.call_args[0][0].text
        assert "complete = true" in query


def test_same_closed_bar_processed_twice_emits_one_message():
    watcher = BarWatcher(engine=MagicMock())
    watcher.state = {}

    ts = datetime.now(timezone.utc) - timedelta(minutes=5)
    df = pd.DataFrame(
        [
            {
                "asset_id": 1,
                "instrument": "EUR_USD",
                "timestamp": ts,
                "Open": 1.0,
                "high": 1.1,
                "low": 0.9,
                "Close": 1.05,
                "volume": 100,
                "rn": 1,
            }
        ]
    )

    with patch("pandas.read_sql", return_value=df):
        with patch("src.signals.watcher.save_state"):
            bars1 = watcher.get_new_closed_bars("H1")
            assert len(bars1) == 1

            # Second time it should be filtered out by state
            bars2 = watcher.get_new_closed_bars("H1")
            assert len(bars2) == 0


def test_missing_model_set_emits_nothing():
    with patch("src.signals.run.load_model_set", return_value=None):
        producer = MagicMock()
        watcher = MagicMock()
        scorer = MagicMock()
        run_once(watcher, scorer, producer, dry_run=False)
        producer.publish_signals.assert_not_called()


def test_signal_missing_direction_refused(caplog):
    model_set = {
        "status": "published",
        "generated_at_utc": "2026-08-16T12:00:00Z",
        "regimes": {
            "Trending-Up": [
                {
                    "strategy_id": 10,
                    "strategy_key": "Range_Stochastic_Divergence",
                    "selection_basis": "qualified",
                    "direction": "auto",
                    "exits": {"sl_atr_multiple": 1.5, "tp_atr_multiple": 2.0},
                }
            ]
        },
    }

    bars_df = pd.DataFrame(
        [
            {
                "instrument": "EUR_USD",
                "timestamp": datetime.now(timezone.utc),
                "Close": 1.05,
                "granularity": "H1",
            }
        ]
    )
    current_regimes = {"EUR_USD": "Trending-Up"}

    # Mock catalog
    class MockIntent:
        direction = "auto"  # Still auto, meaning missing
        entry = 1.05
        stop = 1.04
        target = 1.06

    class MockStrat:
        def process_closed_bar(self, frame, current_position):
            return [MockIntent()]

    with patch("src.registry.catalog.by_id"):
        with patch("src.registry.catalog.instantiate", return_value=MockStrat()):
            signals = build_signals(bars_df, model_set, current_regimes)
            assert len(signals) == 0
            assert "missing or invalid direction" in caplog.text


def test_restart_after_crash_resumes():
    # If state is saved, next instance loads it
    ts = datetime.now(timezone.utc) - timedelta(minutes=10)

    watcher1 = BarWatcher(engine=MagicMock())
    watcher1.state = {"EUR_USD_H1": ts.isoformat()}

    with patch("src.signals.watcher.load_state", return_value=watcher1.state):
        watcher2 = BarWatcher(engine=MagicMock())
        assert watcher2.state["EUR_USD_H1"] == ts.isoformat()


def test_ingest_lag_suppresses_emission(caplog):
    watcher = BarWatcher(engine=MagicMock())
    watcher.state = {}

    # Very old bar (e.g. 5 hours ago for H1)
    ts = datetime.now(timezone.utc) - timedelta(hours=5)
    df = pd.DataFrame(
        [
            {
                "asset_id": 1,
                "instrument": "EUR_USD",
                "timestamp": ts,
                "Open": 1.0,
                "high": 1.1,
                "low": 0.9,
                "Close": 1.05,
                "volume": 100,
                "rn": 1,
            }
        ]
    )

    with patch("pandas.read_sql", return_value=df):
        with patch("src.signals.watcher.save_state"):
            bars = watcher.get_new_closed_bars("H1")
            assert len(bars) == 0
            assert "Ingest is behind for EUR_USD H1" in caplog.text


def test_dry_run_emits_nothing():
    producer = MagicMock()
    watcher = MagicMock()
    scorer = MagicMock()

    with patch("src.signals.run.load_model_set", return_value={"status": "published"}):
        with patch("src.signals.run.get_current_regimes", return_value=({}, {})):
            run_once(watcher, scorer, producer, dry_run=True)
            producer.publish_signals.assert_not_called()


def test_unrecognised_selection_basis_refused(caplog):
    model_set = {
        "status": "published",
        "regimes": {
            "Trending-Up": [
                {
                    "strategy_id": 10,
                    "strategy_key": "Strat1",
                    "selection_basis": "unknown_basis",
                    "direction": "long",
                }
            ]
        },
    }
    bars_df = pd.DataFrame(
        [
            {
                "instrument": "EUR_USD",
                "timestamp": datetime.now(timezone.utc),
                "Close": 1.05,
            }
        ]
    )
    current_regimes = {"EUR_USD": "Trending-Up"}

    signals = build_signals(bars_df, model_set, current_regimes)
    assert len(signals) == 0
    assert "Unknown selection_basis" in caplog.text


def test_designated_strategy_carries_basis():
    model_set = {
        "status": "published",
        "generated_at_utc": "2026-08-16T12:00:00Z",
        "regimes": {
            "Trending-Up": [
                {
                    "strategy_id": 10,
                    "strategy_key": "Strat1",
                    "selection_basis": "designated",
                    "direction": "long",
                    "exits": {"sl_atr_multiple": 1.5, "tp_atr_multiple": 2.0},
                }
            ]
        },
    }
    bars_df = pd.DataFrame(
        [
            {
                "instrument": "EUR_USD",
                "timestamp": datetime.now(timezone.utc),
                "Close": 1.05,
                "granularity": "H1",
            }
        ]
    )
    current_regimes = {"EUR_USD": "Trending-Up"}

    class MockIntent:
        direction = "long"
        entry = 1.05
        stop = 1.04
        target = 1.06

    class MockStrat:
        def process_closed_bar(self, frame, current_position):
            return [MockIntent()]

    with patch("src.registry.catalog.by_id"):
        with patch("src.registry.catalog.instantiate", return_value=MockStrat()):
            signals = build_signals(bars_df, model_set, current_regimes)
            assert len(signals) == 1
            assert signals[0]["selection_basis"] == "designated"
