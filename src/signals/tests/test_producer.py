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


# --- contract-v2 doubles -------------------------------------------------------------
# These mirror the API `build_signals` actually calls: a strategy exposes
# `generate_orders(frames)` and `metadata`, and an intent carries `decision_bar`, an
# integer `direction`, `stop.price` and `exits[].price`. The previous doubles modelled
# `process_closed_bar()` and string directions — an API no strategy in the fleet has had
# since the v2 rewrite — so they asserted against a code path that no longer existed.


class _FakeExit:
    def __init__(self, price):
        self.price = price


class _FakeIntent:
    def __init__(self, decision_bar, direction=1, entry=1.05, stop=1.04, target=1.06):
        self.decision_bar = decision_bar
        self.direction = direction
        self.entry_price = entry
        self.stop = _FakeExit(stop)
        self.exits = [_FakeExit(target)]


class _FakeMetadata:
    pairs = ("EUR_USD", "GBP_USD")
    primary_granularity = "H1"
    context_granularities = ()


class _FakeStrategy:
    def __init__(self, intents):
        self._intents = intents
        self.metadata = _FakeMetadata()

    def generate_orders(self, frames):
        return self._intents


def _frames(bar_ts, n=60):
    """Real OHLC frame ending on the decision bar, so ATR is genuinely computed."""
    idx = pd.date_range(end=bar_ts, periods=n, freq="h", tz="UTC")
    base = pd.Series([1.05 + 0.0001 * i for i in range(n)], index=idx)
    return {
        "H1": pd.DataFrame(
            {
                "Open": base,
                "High": base + 0.0008,
                "Low": base - 0.0008,
                "Close": base,
                "Volume": 100.0,
            },
            index=idx,
        )
    }


def _bars_df(bar_ts, instrument="EUR_USD"):
    return pd.DataFrame(
        [
            {
                "instrument": instrument,
                "timestamp": bar_ts,
                "Close": 1.05,
                "granularity": "H1",
            }
        ]
    )


def _model_set(
    strategy_id=58,
    strategy_key="xard_ma_cross_daily_open",
    selection_basis="qualified",
    direction="both",
):
    return {
        "status": "published",
        "generated_at_utc": "2026-08-16T12:00:00Z",
        "model_set_id": "test-model-set",
        "regimes": {
            "Trending-Up": [
                {
                    "strategy_id": strategy_id,
                    "strategy_key": strategy_key,
                    "selection_basis": selection_basis,
                    "direction": direction,
                    "exits": {"sl_atr_multiple": 1.5, "tp_atr_multiple": 2.0},
                }
            ]
        },
    }


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
    bar_ts = pd.Timestamp("2026-08-19 11:00:00+00:00")
    model_set = _model_set(direction="both")
    bars_df = _bars_df(bar_ts)

    # contract_v2 encodes direction as +1 / -1. Anything else is undecodable and must be
    # refused rather than guessed — guessing a side is how the 2026-08-02 incident started.
    strat = _FakeStrategy([_FakeIntent(bar_ts, direction=0)])

    with patch("src.registry.catalog.by_id"), patch(
        "src.registry.catalog.instantiate", return_value=strat
    ), patch("src.signals.build.build_frames", return_value=_frames(bar_ts)):
        signals = build_signals(bars_df, model_set, {"EUR_USD": "Trending-Up"})

    assert len(signals) == 0
    assert "undecodable direction" in caplog.text


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
    bar_ts = pd.Timestamp("2026-08-19 11:00:00+00:00")
    model_set = _model_set(selection_basis="designated", direction="both")
    strat = _FakeStrategy([_FakeIntent(bar_ts, direction=1)])

    with patch("src.registry.catalog.by_id"), patch(
        "src.registry.catalog.instantiate", return_value=strat
    ), patch("src.signals.build.build_frames", return_value=_frames(bar_ts)):
        signals = build_signals(_bars_df(bar_ts), model_set, {"EUR_USD": "Trending-Up"})

    assert len(signals) == 1
    assert signals[0]["selection_basis"] == "designated"
    assert signals[0]["direction"] == "long"


def test_signal_carries_a_real_atr_from_the_decision_bar():
    """ATR is mandatory — a signal without one is refused, so this is a release gate.

    `_atr_at` called the ATR indicator with the wrong signature for its whole life, which
    silently dropped 100% of signals at the final step. Assert a real, plausible number
    rather than merely 'not None'.
    """
    bar_ts = pd.Timestamp("2026-08-19 11:00:00+00:00")
    strat = _FakeStrategy([_FakeIntent(bar_ts, direction=1)])

    with patch("src.registry.catalog.by_id"), patch(
        "src.registry.catalog.instantiate", return_value=strat
    ), patch("src.signals.build.build_frames", return_value=_frames(bar_ts)):
        signals = build_signals(
            _bars_df(bar_ts), _model_set(), {"EUR_USD": "Trending-Up"}
        )

    assert len(signals) == 1
    assert signals[0]["atr"] > 0
    assert 0.0001 < signals[0]["atr"] < 0.05, "ATR is not on a plausible FX scale"


def test_integrity_disqualified_strategy_never_reaches_the_wire():
    """Last line of defence: a barred strategy must be refused even if a map lists it."""
    bar_ts = pd.Timestamp("2026-08-19 11:00:00+00:00")
    model_set = _model_set(strategy_id=10, strategy_key="Range_Stochastic_Divergence")
    strat = _FakeStrategy([_FakeIntent(bar_ts, direction=1)])

    with patch("src.registry.catalog.by_id"), patch(
        "src.registry.catalog.instantiate", return_value=strat
    ), patch("src.signals.build.build_frames", return_value=_frames(bar_ts)):
        signals = build_signals(_bars_df(bar_ts), model_set, {"EUR_USD": "Trending-Up"})

    assert signals == []
