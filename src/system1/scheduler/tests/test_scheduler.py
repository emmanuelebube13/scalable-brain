"""MODEL-009 trigger + orchestrator tests (no DB/network; injectable pipeline/promote)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from src.system1.scheduler import orchestrator as O
from src.system1.scheduler import triggers as TR


@pytest.fixture(autouse=True)
def _isolate_storage(tmp_path_factory, monkeypatch):
    """Point the storage backend at an empty per-test local dir.

    ``_incumbent()`` now reads the pointer through ``build_storage()``; without isolation it
    would hit the real ``model-artifacts/`` (or GCS when ``STORAGE_PROVIDER=gcs`` in the env),
    making these unit tests order-dependent and network-bound. An empty root ⇒ no incumbent by
    default; tests that need one publish into their own root (overriding these env vars).
    """
    root = tmp_path_factory.mktemp("storage")
    monkeypatch.setenv("STORAGE_PROVIDER", "local")
    monkeypatch.setenv("STORAGE_LOCAL_ROOT", str(root))


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
    # No incumbent: the autouse _isolate_storage fixture roots storage at an empty dir.
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

    # Publish to a local storage root; _incumbent() reads the incumbent back through the SAME
    # backend (no _REPO_ROOT / local-latest.json workaround needed after the 2026-07-01 fix).
    root = tmp_path / "model-artifacts"
    monkeypatch.setenv("STORAGE_PROVIDER", "local")
    monkeypatch.setenv("STORAGE_LOCAL_ROOT", str(root))

    bundle = S.publish(register_mlflow=False, metrics={"regime_accuracy": 0.90})

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


def test_incumbent_tracks_storage_backend_not_local_file(tmp_path, monkeypatch):
    """Regression (2026-07-01): _incumbent reads the pointer from the STORAGE BACKEND, not a
    fixed local model-artifacts/latest.json.

    Rooted at an empty backend it returns {} regardless of any local file that happens to exist
    on disk; after publishing to that backend it returns the published bundle + metrics. Pre-fix
    _incumbent read a hard-coded local path, so with STORAGE_PROVIDER=gcs the local pointer went
    stale after a real (GCS) promotion and beats_incumbent never bound on the next retrain — this
    test would return the stale local incumbent instead of {} and fail."""
    from src.system1.serializer import serialize as S

    root = tmp_path / "backend"
    monkeypatch.setenv("STORAGE_PROVIDER", "local")
    monkeypatch.setenv("STORAGE_LOCAL_ROOT", str(root))

    # Empty backend => no incumbent, even though the repo's real model-artifacts/latest.json exists.
    # FIX-S1-010: the absent case is now reported explicitly rather than as a bare {}, so a
    # fail-open beats_incumbent is distinguishable in the retrain log from a real comparison.
    empty = O._incumbent()
    assert empty.get("resolution") == "absent"
    assert "bundle_version" not in empty

    # Publish into THIS backend, then confirm _incumbent reads it back through the same backend.
    for name in S.SOURCES:
        (tmp_path / name).write_text("{}")
        monkeypatch.setitem(S.SOURCES, name, str(tmp_path / name))
    rmap = tmp_path / "regime_strategy_map.json"
    rmap.write_text(json.dumps({"regimes": {"Ranging": [{"strategy_id": 1}]}}))
    monkeypatch.setitem(S.SOURCES, "regime_strategy_map.json", str(rmap))
    bundle = S.publish(register_mlflow=False, metrics={"regime_accuracy": 0.83})

    inc = O._incumbent()
    assert inc["bundle_version"] == bundle["bundle_version"]
    assert inc["metrics"]["regime_accuracy"] == 0.83
    assert inc["resolution"] == "prefixed"


def test_incumbent_falls_back_to_legacy_model_set(tmp_path, monkeypatch):
    """FIX-S1-010: a bundle published before the ``system1/`` prefix migration must still
    resolve as the incumbent.

    Regression from 2026-07-19: the prefix change left the pre-existing bundle at the
    bucket root, so ``system1/latest.json`` did not exist, ``_incumbent()`` returned {},
    and ``beats_incumbent`` took its first-publish fail-open branch — the candidate was
    promoted without ever being compared. The top-level model set still named the old
    ``model_metadata.json``, so the comparison was recoverable; it just wasn't attempted.
    """
    from src.common.storage import build_storage
    from src.system1.serializer import publish_model_set as PMS

    root = tmp_path / "backend"
    monkeypatch.setenv("STORAGE_PROVIDER", "local")
    monkeypatch.setenv("STORAGE_LOCAL_ROOT", str(root))
    storage = build_storage()

    meta = tmp_path / "model_metadata.json"
    meta.write_text(json.dumps({"metrics": {"regime_accuracy": 0.91}}))
    storage.put_object("2026-07-01T12-56-32Z/model_metadata.json", str(meta))
    storage.atomic_pointer_update(
        PMS.POINTER_KEY,
        {
            "model_set_id": "2026-07-01T12-56-32Z_gk-656f09e2",
            "system1_bundle_version": "2026-07-01T12-56-32Z",
            "artifacts": [
                {
                    "name": "model_metadata.json",
                    "path": "2026-07-01T12-56-32Z/model_metadata.json",
                }
            ],
        },
    )

    inc = O._incumbent()
    assert inc["resolution"] == "legacy_model_set"
    assert inc["metrics"]["regime_accuracy"] == 0.91

    # And the gate now actually binds against it, instead of failing open.
    passed, gates = O.deployment_gates(
        {
            "regime_accuracy": 0.85,
            "n_qualified_strategies": 4,
            "oos_uplift": 0.03,
            "oos_uplift_significant": True,
        },
        inc,
    )
    assert gates["beats_incumbent"] is False
    assert passed is False


# ---- FIX-S1-010: staged rollout flags ----
def test_gatekeeper_autopromote_is_opt_in(monkeypatch):
    """Stage 1 of the rollout must survive a scheduled retrain.

    The FIX-S1-010 wiring makes _default_promote capable of promoting the gatekeeper and
    flipping the model set. Without an opt-in flag the next Sunday-00UTC trigger would
    execute rollout Stage 3 by itself, undoing "code applied, nothing promoted"."""
    monkeypatch.delenv("GATEKEEPER_AUTOPROMOTE", raising=False)
    called = {"promote": False}

    def _boom(*a, **k):
        called["promote"] = True
        raise AssertionError("must not promote while auto-promotion is disabled")

    monkeypatch.setattr("src.system1.gatekeeper.promote.promote_proposed", _boom)

    out = O._promote_gatekeeper()
    assert out == {"promoted": False, "reason": "autopromote_disabled"}
    assert not called["promote"]


def test_gatekeeper_autopromote_enabled_runs_the_path(monkeypatch):
    monkeypatch.setenv("GATEKEEPER_AUTOPROMOTE", "true")
    monkeypatch.setattr(
        "src.system1.gatekeeper.promote.promote_proposed", lambda d: {"model_path": "m"}
    )
    monkeypatch.setattr(
        "src.system1.serializer.publish_gatekeeper.publish", lambda: {"version": "gk-1"}
    )
    assert O._promote_gatekeeper() == {"promoted": True, "version": "gk-1"}


def test_gatekeeper_publish_refusal_does_not_fail_the_promote(monkeypatch):
    """A candidate that does not beat the incumbent is a legitimate outcome, not an error:
    the regime/weights bundle can improve while the gatekeeper does not."""
    from src.system1.serializer import publish_gatekeeper as PG

    monkeypatch.setenv("GATEKEEPER_AUTOPROMOTE", "true")
    monkeypatch.setattr(
        "src.system1.gatekeeper.promote.promote_proposed", lambda d: {"model_path": "m"}
    )

    def _refuse():
        raise PG.PublishRefused("does not beat incumbent")

    monkeypatch.setattr("src.system1.serializer.publish_gatekeeper.publish", _refuse)

    out = O._promote_gatekeeper()
    assert out["promoted"] is False and "refused" in out["reason"]


def test_promote_never_touches_real_analytics_staging(tmp_path, monkeypatch):
    """Guard: the promote path must not build/publish the REAL analytics bundle.

    ``_default_analytics`` builds into ``results/state/analytics_staging/`` (a tracked
    path) from the live DB and then uploads via ``build_storage()``. Any test reaching
    the promote branch must do neither. This asserts the tracked staging files are
    byte-identical across a forced promote, which is the invariant that actually
    matters -- and which was silently violated until 2026-08-01.
    """
    import hashlib
    import os

    staging = os.path.join(O._REPO_ROOT, "results", "state", "analytics_staging")

    def _digest():
        if not os.path.isdir(staging):
            return {}
        return {
            f: hashlib.sha256(open(os.path.join(staging, f), "rb").read()).hexdigest()
            for f in sorted(os.listdir(staging))
            if f.endswith(".json")
        }

    before = _digest()

    monkeypatch.setattr(O, "RETRAIN_STATE", str(tmp_path / "state.json"))
    monkeypatch.setattr(O, "LOCK_FILE", str(tmp_path / "lock"))
    monkeypatch.setattr(O, "STATE_DIR", str(tmp_path))

    d = O.run(
        force=True,
        pipeline_fn=_good,
        promote_fn=lambda c: {"bundle_version": "v1"},
        register_mlflow=False,
    )

    assert d["promoted"]
    assert _digest() == before, "promote path rewrote the tracked analytics staging dir"
