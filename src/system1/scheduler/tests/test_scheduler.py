"""MODEL-009 trigger + orchestrator tests (no DB/network; injectable pipeline/promote)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.system1.scheduler import orchestrator as O
from src.system1.scheduler import triggers as TR


# ---- triggers ----
def test_scheduled_window():
    assert TR.is_scheduled_window(datetime(2026, 6, 21, 0, 30, tzinfo=timezone.utc))  # Sunday 00h
    assert not TR.is_scheduled_window(datetime(2026, 6, 22, 0, 30, tzinfo=timezone.utc))  # Monday
    assert not TR.is_scheduled_window(datetime(2026, 6, 21, 1, 30, tzinfo=timezone.utc))  # Sun 01h


def test_performance_triggers_independent():
    assert TR.evaluate_performance_triggers({"sharpe_14d": 0.1}) == ["sharpe_14d=0.100<0.3"]
    assert TR.evaluate_performance_triggers({"regime_accuracy": 0.5})[0].startswith("regime_accuracy")
    assert TR.evaluate_performance_triggers({"circuit_breaker": True}) == ["circuit_breaker"]


def test_missing_metrics_failsafe():
    # No metrics present → no trigger fires (no false positive on absent telemetry).
    assert TR.evaluate_performance_triggers({}) == []
    assert TR.evaluate_performance_triggers({"sharpe_14d": None}) == []


def test_cooldown_debounce():
    now = datetime(2026, 6, 21, 0, 5, tzinfo=timezone.utc)
    state = {"last_run_utc": (now - timedelta(hours=1)).isoformat()}
    should, reasons = TR.decide(now, {"circuit_breaker": True}, state, cooldown_seconds=6 * 3600)
    assert not should and "cooldown" in reasons[0]


# ---- orchestrator ----
def _good(): return {"regime_accuracy": 0.88, "n_qualified_strategies": 3, "oos_uplift": None}
def _bad(): return {"regime_accuracy": 0.50, "n_qualified_strategies": 0, "oos_uplift": None}


def test_degraded_candidate_not_promoted(tmp_path, monkeypatch):
    monkeypatch.setattr(O, "RETRAIN_STATE", str(tmp_path / "state.json"))
    monkeypatch.setattr(O, "LOCK_FILE", str(tmp_path / "lock"))
    monkeypatch.setattr(O, "STATE_DIR", str(tmp_path))
    promoted = {"called": False}
    def promote(): promoted["called"] = True; return {"bundle_version": "x"}
    d = O.run(force=True, pipeline_fn=_bad, promote_fn=promote, register_mlflow=False)
    assert d["ran"] and not d["promoted"] and d["outcome"] == "skipped_gates_failed"
    assert not promoted["called"]


def test_passing_candidate_promoted(tmp_path, monkeypatch):
    monkeypatch.setattr(O, "RETRAIN_STATE", str(tmp_path / "state.json"))
    monkeypatch.setattr(O, "LOCK_FILE", str(tmp_path / "lock"))
    monkeypatch.setattr(O, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(O, "LATEST_JSON", str(tmp_path / "nope.json"))  # no incumbent
    d = O.run(force=True, pipeline_fn=_good, promote_fn=lambda: {"bundle_version": "v1"},
              register_mlflow=False)
    assert d["ran"] and d["promoted"] and d["bundle_version"] == "v1"


def test_single_flight_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(O, "RETRAIN_STATE", str(tmp_path / "state.json"))
    monkeypatch.setattr(O, "LOCK_FILE", str(tmp_path / "lock"))
    monkeypatch.setattr(O, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(O, "LATEST_JSON", str(tmp_path / "nope.json"))
    held = O.SingleFlightLock(str(tmp_path / "lock"))
    held.__enter__()
    try:
        d = O.run(force=True, pipeline_fn=_good, promote_fn=lambda: {"bundle_version": "v"},
                  register_mlflow=False)
        assert "aborted" in d["outcome"] and not d["promoted"]
    finally:
        held.__exit__()


def test_no_trigger_no_run(tmp_path, monkeypatch):
    monkeypatch.setattr(O, "RETRAIN_STATE", str(tmp_path / "state.json"))
    monkeypatch.setattr(O, "STATE_DIR", str(tmp_path))
    now = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)  # Monday noon, healthy metrics
    d = O.run(now=now, metrics={"sharpe_14d": 1.2, "regime_accuracy": 0.9},
              pipeline_fn=_good, promote_fn=lambda: {}, register_mlflow=False)
    assert not d["ran"] and d["outcome"] == "no_trigger_or_cooldown"
