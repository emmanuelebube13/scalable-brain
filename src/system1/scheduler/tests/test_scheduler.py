"""MODEL-009 trigger + orchestrator tests (no DB/network; injectable pipeline/promote)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from src.system1.scheduler import orchestrator as O
from src.system1.scheduler import triggers as TR


# ---- triggers ----
def test_scheduled_window():
    assert TR.is_scheduled_window(
        datetime(2026, 6, 21, 0, 30, tzinfo=timezone.utc)
    )  # Sunday 00h
    assert not TR.is_scheduled_window(
        datetime(2026, 6, 22, 0, 30, tzinfo=timezone.utc)
    )  # Monday
    assert not TR.is_scheduled_window(
        datetime(2026, 6, 21, 1, 30, tzinfo=timezone.utc)
    )  # Sun 01h


def test_performance_triggers_independent():
    assert TR.evaluate_performance_triggers({"sharpe_14d": 0.1}) == [
        "sharpe_14d=0.100<0.3"
    ]
    assert TR.evaluate_performance_triggers({"regime_accuracy": 0.5})[0].startswith(
        "regime_accuracy"
    )
    assert TR.evaluate_performance_triggers({"circuit_breaker": True}) == [
        "circuit_breaker"
    ]


def test_missing_metrics_failsafe():
    # No metrics present → no trigger fires (no false positive on absent telemetry).
    assert TR.evaluate_performance_triggers({}) == []
    assert TR.evaluate_performance_triggers({"sharpe_14d": None}) == []


def test_cooldown_debounce():
    now = datetime(2026, 6, 21, 0, 5, tzinfo=timezone.utc)
    state = {"last_run_utc": (now - timedelta(hours=1)).isoformat()}
    should, reasons = TR.decide(
        now, {"circuit_breaker": True}, state, cooldown_seconds=6 * 3600
    )
    assert not should and "cooldown" in reasons[0]


# ---- orchestrator ----
# A "good" candidate clears every gate: above the accuracy floor, non-empty map, and a
# non-negative, bootstrap-significant OOS uplift (FIX-S1-006 — uplift is no longer None).
def _good():
    return {
        "regime_accuracy": 0.88,
        "n_qualified_strategies": 3,
        "oos_uplift": 0.05,
        "oos_uplift_significant": True,
    }


def _bad():
    return {
        "regime_accuracy": 0.50,
        "n_qualified_strategies": 0,
        "oos_uplift": 0.05,
        "oos_uplift_significant": True,
    }


def test_degraded_candidate_not_promoted(tmp_path, monkeypatch):
    monkeypatch.setattr(O, "RETRAIN_STATE", str(tmp_path / "state.json"))
    monkeypatch.setattr(O, "LOCK_FILE", str(tmp_path / "lock"))
    monkeypatch.setattr(O, "STATE_DIR", str(tmp_path))
    promoted = {"called": False}

    def promote(candidate):
        promoted["called"] = True
        return {"bundle_version": "x"}

    d = O.run(force=True, pipeline_fn=_bad, promote_fn=promote, register_mlflow=False)
    assert d["ran"] and not d["promoted"] and d["outcome"] == "skipped_gates_failed"
    assert not promoted["called"]


def test_passing_candidate_promoted(tmp_path, monkeypatch):
    monkeypatch.setattr(O, "RETRAIN_STATE", str(tmp_path / "state.json"))
    monkeypatch.setattr(O, "LOCK_FILE", str(tmp_path / "lock"))
    monkeypatch.setattr(O, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(O, "LATEST_JSON", str(tmp_path / "nope.json"))  # no incumbent
    d = O.run(
        force=True,
        pipeline_fn=_good,
        promote_fn=lambda c: {"bundle_version": "v1"},
        register_mlflow=False,
    )
    assert d["ran"] and d["promoted"] and d["bundle_version"] == "v1"


def test_single_flight_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(O, "RETRAIN_STATE", str(tmp_path / "state.json"))
    monkeypatch.setattr(O, "LOCK_FILE", str(tmp_path / "lock"))
    monkeypatch.setattr(O, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(O, "LATEST_JSON", str(tmp_path / "nope.json"))
    held = O.SingleFlightLock(str(tmp_path / "lock"))
    held.__enter__()
    try:
        d = O.run(
            force=True,
            pipeline_fn=_good,
            promote_fn=lambda c: {"bundle_version": "v"},
            register_mlflow=False,
        )
        assert "aborted" in d["outcome"] and not d["promoted"]
    finally:
        held.__exit__()


def test_no_trigger_no_run(tmp_path, monkeypatch):
    monkeypatch.setattr(O, "RETRAIN_STATE", str(tmp_path / "state.json"))
    monkeypatch.setattr(O, "STATE_DIR", str(tmp_path))
    now = datetime(
        2026, 6, 22, 12, 0, tzinfo=timezone.utc
    )  # Monday noon, healthy metrics
    d = O.run(
        now=now,
        metrics={"sharpe_14d": 1.2, "regime_accuracy": 0.9},
        pipeline_fn=_good,
        promote_fn=lambda c: {},
        register_mlflow=False,
    )
    assert not d["ran"] and d["outcome"] == "no_trigger_or_cooldown"


# ---- FIX-S1-006: the two structurally-inert gates can now reject ----
def test_oos_uplift_gate_rejects_missing_uplift():
    """No gatekeeper result (oos_uplift=None) FAILS CLOSED — pre-fix this was a silent pass."""
    candidate = {
        "regime_accuracy": 0.88,
        "n_qualified_strategies": 3,
        "oos_uplift": None,
    }
    passed, gates = O.deployment_gates(candidate, incumbent={})
    assert not gates["oos_uplift_ok"]
    assert not passed


def test_oos_uplift_gate_rejects_insignificant_uplift():
    """A positive-but-not-significant uplift FAILS — pre-fix significance was ignored."""
    candidate = {
        "regime_accuracy": 0.88,
        "n_qualified_strategies": 3,
        "oos_uplift": 0.05,
        "oos_uplift_significant": False,
    }
    passed, gates = O.deployment_gates(candidate, incumbent={})
    assert not gates["oos_uplift_ok"]
    assert not passed


def test_oos_uplift_gate_rejects_below_min_uplift():
    """A significant but sub-MIN_UPLIFT (negative) uplift FAILS the absolute floor."""
    candidate = {
        "regime_accuracy": 0.88,
        "n_qualified_strategies": 3,
        "oos_uplift": O.MIN_UPLIFT - 0.01,
        "oos_uplift_significant": True,
    }
    passed, gates = O.deployment_gates(candidate, incumbent={})
    assert not gates["oos_uplift_ok"]
    assert not passed


def test_oos_uplift_missing_allowed_with_override():
    """The explicit --allow-missing-uplift override lets a missing result pass the gate."""
    candidate = {
        "regime_accuracy": 0.88,
        "n_qualified_strategies": 3,
        "oos_uplift": None,
    }
    passed, gates = O.deployment_gates(
        candidate, incumbent={}, allow_missing_uplift=True
    )
    assert gates["oos_uplift_ok"] and passed


def test_beats_incumbent_rejects_worse_candidate():
    """A candidate whose regime_accuracy is below the incumbent's persisted score FAILS."""
    candidate = {
        "regime_accuracy": 0.80,
        "n_qualified_strategies": 3,
        "oos_uplift": 0.05,
        "oos_uplift_significant": True,
    }
    incumbent = {"bundle_version": "live", "metrics": {"regime_accuracy": 0.90}}
    passed, gates = O.deployment_gates(candidate, incumbent)
    assert not gates["beats_incumbent"]
    assert not passed


def test_first_ever_comparison_fails_open():
    """No incumbent metric => beats_incumbent fails OPEN (nothing to beat); absolute gates bind."""
    candidate = {
        "regime_accuracy": 0.80,
        "n_qualified_strategies": 3,
        "oos_uplift": 0.05,
        "oos_uplift_significant": True,
    }
    passed, gates = O.deployment_gates(candidate, incumbent={})
    assert gates["beats_incumbent"] and passed


def test_incumbent_regime_accuracy_round_trips_and_blocks_worse(tmp_path, monkeypatch):
    """Integration: publish an incumbent bundle with regime_accuracy, confirm _incumbent() reads it
    back, then run the orchestrator with a deliberately-worse candidate and confirm it is rejected.
    Pre-fix the serializer never persisted regime_accuracy, so _incumbent() saw None and a worse
    candidate sailed through as 'promoted'."""
    from src.system1.serializer import serialize as S

    # Stage valid source artifacts for the serializer (a non-empty regime map).
    sources = {}
    for name in S.SOURCES:
        p = tmp_path / name
        p.write_text("{}")
        sources[name] = str(p)
    regime_map = tmp_path / "regime_strategy_map.json"
    regime_map.write_text(json.dumps({"regimes": {"Ranging": [{"strategy_id": 1}]}}))
    sources["regime_strategy_map.json"] = str(regime_map)
    for name, path in sources.items():
        monkeypatch.setitem(S.SOURCES, name, path)

    # Local storage rooted at tmp/model-artifacts so the orchestrator's _REPO_ROOT layout matches.
    root = tmp_path / "model-artifacts"
    monkeypatch.setenv("STORAGE_PROVIDER", "local")
    monkeypatch.setenv("STORAGE_LOCAL_ROOT", str(root))

    bundle = S.publish(register_mlflow=False, metrics={"regime_accuracy": 0.90})

    monkeypatch.setattr(O, "_REPO_ROOT", str(tmp_path))
    monkeypatch.setattr(O, "LATEST_JSON", str(root / "latest.json"))

    inc = O._incumbent()
    assert inc["bundle_version"] == bundle["bundle_version"]
    assert (
        inc["metrics"]["regime_accuracy"] == 0.90
    )  # round-trips (pre-fix: KeyError/None)

    monkeypatch.setattr(O, "RETRAIN_STATE", str(tmp_path / "state.json"))
    monkeypatch.setattr(O, "LOCK_FILE", str(tmp_path / "lock"))
    monkeypatch.setattr(O, "STATE_DIR", str(tmp_path / "state"))

    worse = {
        "regime_accuracy": 0.80,  # below the 0.90 incumbent
        "n_qualified_strategies": 3,
        "oos_uplift": 0.05,
        "oos_uplift_significant": True,
    }
    promoted = {"called": False}

    def promote(candidate):
        promoted["called"] = True
        return {"bundle_version": "x"}

    d = O.run(
        force=True, pipeline_fn=lambda: worse, promote_fn=promote, register_mlflow=False
    )
    assert d["outcome"] == "skipped_gates_failed"
    assert not d["gates"]["beats_incumbent"]
    assert not promoted["called"]
