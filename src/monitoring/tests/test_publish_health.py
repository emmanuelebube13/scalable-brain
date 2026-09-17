"""The published health payload must carry the fields downstream was told to read."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from src.monitoring import publish_health as H

NOW = datetime(2026, 9, 16, 12, 0, 0, tzinfo=timezone.utc)

EMITTER = {
    "last_run_at": "2026-08-29T09:07:20Z",
    "last_run_outcome": "no_model_set",
    "last_run_signals_built": 0,
    "consecutive_faults": 1,
    "last_healthy_run_at": "2026-08-29T08:15:20Z",
    "last_signal_emitted_at": "2026-08-28T19:15:17Z",
    "signals_published_total": 49,
    "emitter_enabled": True,
}

# The LOCAL map (results/state/) — fresher than the published one, per the 2026-09-16
# defect: renewed 09-14 while the bundle still carried the 09-11 build.
LOCAL_MAP = {
    "generated_at_utc": "2026-09-14T16:21:25+00:00",
    "built_at_utc": "2026-09-14T16:21:25+00:00",
    "expires_at_utc": "2026-09-21T16:21:25+00:00",
    "source_label": "regime_structural",
    "qualification_run_id": "21d6d29b",
    "regimes": {"Ranging": [{"selection_basis": "qualified"}]},
}

MAP_PATH = "system1/1.2.3/regime_strategy_map.json"


def _published_map(built: datetime, expires: datetime) -> dict:
    """A map carrying every field the contract requires, with a chosen lifetime."""
    return {
        "generated_at_utc": built.isoformat(),
        "built_at_utc": built.isoformat(),
        "built_from_run_id": "aaaa1111",
        "source_label": "regime_structural",
        "labeller_version": "structural-v2.1.0",
        "code_git_sha": "deadbeef",
        "expires_at_utc": expires.isoformat(),
        "qualification_run_id": "aaaa1111",
        "data_through_utc": "2026-09-11T13:00:00+00:00",
        "evidence_age_days": 0.2,
        "empty_regimes": ["Trending-Down"],
        "regimes": {
            "Trending-Up": [
                {"selection_basis": "qualified"},
                {"selection_basis": "designated"},
            ],
            "Ranging": [{"selection_basis": "qualified"}],
        },
    }


def _manifest(status: str = "published", with_map: bool = True) -> dict:
    artifacts = [{"name": "champion.pkl", "path": "system1/1.2.3/champion.pkl"}]
    if with_map:
        artifacts.append({"name": "regime_strategy_map.json", "path": MAP_PATH})
    return {
        "model_set_id": "ms-2026-09-11",
        "status": status,
        "published_at": "2026-09-11T18:41:00+00:00",
        "artifacts": artifacts,
    }


class _FakeStorage:
    """Serves JSON objects by key, exactly like the storage abstraction's read side."""

    def __init__(self, objects: dict):
        self.objects = objects

    def exists(self, key: str) -> bool:
        return key in self.objects

    def get_object(self, key: str, dest: str) -> None:
        with open(dest, "w", encoding="utf-8") as fh:
            json.dump(self.objects[key], fh)


def _patch_local(monkeypatch, local_map=LOCAL_MAP):
    """Stub the local state files collect() reads from disk."""

    def _fake_read(path):
        if path.endswith("signal_emitter_state.json"):
            return EMITTER
        if path.endswith("regime_strategy_map.json"):
            return local_map if local_map else {}
        return {}

    monkeypatch.setattr(H, "_read_json", _fake_read)


def _patch_backend(monkeypatch, objects=None, error=None):
    """collect() imports build_storage INSIDE the function, so patch it at its source
    or the test quietly performs a real bucket read."""
    import src.common.storage as storage_mod

    if error is not None:

        def _boom(*a, **k):
            raise error

        monkeypatch.setattr(storage_mod, "build_storage", _boom)
    else:
        monkeypatch.setattr(
            storage_mod, "build_storage", lambda *a, **k: _FakeStorage(objects or {})
        )


def _collect(monkeypatch, objects=None, error=None, local_map=LOCAL_MAP):
    _patch_local(monkeypatch, local_map)
    _patch_backend(monkeypatch, objects=objects, error=error)
    return H.collect(now=NOW)


def _healthy_backend(map_obj=None):
    """Pointer + manifest + a published map, the shape a consumer actually downloads."""
    m = map_obj or _published_map(NOW - timedelta(days=1), NOW + timedelta(days=6))
    return {"latest.json": _manifest(), MAP_PATH: m}


def test_fault_counters_are_published(monkeypatch):
    """`consecutive_faults` / `last_healthy_run_at` distinguish a blip from an outage.

    The erratum of 2026-08-28 told Systems 2 and 3 to read exactly these two, and the
    payload carried neither — so from the outside a one-run fault beside a healthy run
    was indistinguishable from a dead producer. Pinned here because the advice is already
    in a sent message and cannot be retracted.
    """
    emitter = _collect(monkeypatch, error=RuntimeError("no bucket in tests"))["emitter"]
    assert emitter["consecutive_faults"] == 1
    assert emitter["last_healthy_run_at"] == "2026-08-29T08:15:20Z"
    assert emitter["last_run_outcome"] == "no_model_set"


def test_collect_never_mutates_state(monkeypatch):
    """A telemetry read that wrote state would be the defect it is meant to report on."""
    before = dict(EMITTER)
    _collect(monkeypatch, objects=_healthy_backend())
    assert EMITTER == before


def test_regime_map_block_describes_the_published_bundle(monkeypatch):
    """The glance must describe the map that ROUTES — the one inside the published bundle
    (signals/build.load_model_set reads the backend only, FIX-S1-016) — not the local
    file. On 2026-09-16 the local map was fresh while the published one was two days from
    expiry, and the health block reported the fresh one: structurally blind.
    """
    m = _collect(monkeypatch, objects=_healthy_backend())["regime_map"]
    assert m["source"] == "published_bundle"
    assert m["status"] == "ok"
    assert m["model_set_id"] == "ms-2026-09-11"
    assert m["map_path"] == MAP_PATH
    # These come from the PUBLISHED map, not the (different) local one.
    assert m["qualification_run_id"] == "aaaa1111"
    assert m["source_label"] == "regime_structural"
    assert m["n_cells"] == 3
    assert m["cells_by_selection_basis"] == {"qualified": 2, "designated": 1}
    assert m["cells_by_regime"] == {"Trending-Up": 2, "Ranging": 1}
    assert m["empty_regimes"] == ["Trending-Down"]
    assert m["expires_in_sec"] > 0


def test_admissibility_verdict_is_rendered(monkeypatch):
    """The block carries the producer's own verdict (map_contract.routing_refusals), so a
    human never has to eyeball a negative expires_in_sec to know routing has stopped."""
    healthy = _collect(monkeypatch, objects=_healthy_backend())["regime_map"]
    assert healthy["admissible"] is True
    assert healthy["refusals"] == []

    expired = _published_map(NOW - timedelta(days=9), NOW - timedelta(days=2))
    dead = _collect(monkeypatch, objects=_healthy_backend(expired))["regime_map"]
    assert dead["admissible"] is False
    assert any("expired" in r for r in dead["refusals"])
    assert dead["expires_in_sec"] < 0


def test_evidence_fields_are_carried_through(monkeypatch):
    m = _collect(monkeypatch, objects=_healthy_backend())["regime_map"]
    assert m["data_through_utc"] == "2026-09-11T13:00:00+00:00"
    assert m["evidence_age_days"] == 0.2


def test_local_map_sub_block_and_drift(monkeypatch):
    """Local-vs-published drift must be visible at a glance: a renewed local map that
    never shipped is exactly the 2026-09-16 blind spot."""
    m = _collect(monkeypatch, objects=_healthy_backend())["regime_map"]
    assert m["local_map"] == {
        "built_at_utc": "2026-09-14T16:21:25+00:00",
        "qualification_run_id": "21d6d29b",
        "expires_at_utc": "2026-09-21T16:21:25+00:00",
    }
    assert m["drift"] is True  # local 21d6d29b vs published aaaa1111

    synced = _published_map(NOW - timedelta(days=1), NOW + timedelta(days=6))
    synced["qualification_run_id"] = "21d6d29b"
    m2 = _collect(monkeypatch, objects=_healthy_backend(synced))["regime_map"]
    assert m2["drift"] is False


def test_missing_local_map_is_reported_not_dropped(monkeypatch):
    m = _collect(monkeypatch, objects=_healthy_backend(), local_map=None)["regime_map"]
    assert m["local_map"] == {"status": "missing"}
    assert m["drift"] is None  # unknown is not "no drift"


def test_unreachable_backend_is_an_alarm_not_an_empty_block(monkeypatch):
    """No readable published map is a routing emergency; it must never render as {}."""
    payload = _collect(monkeypatch, error=RuntimeError("no bucket"))
    m = payload["regime_map"]
    assert m["status"] == "error"
    assert m["admissible"] is False
    assert m["refusals"]
    assert "no bucket" in m["error"]
    # The fault degrades to the alarm shape; collect() itself still returned a payload.
    assert payload["model_set"] == {"error": "RuntimeError: no bucket"}


def test_no_published_model_set_is_an_alarm(monkeypatch):
    m = _collect(monkeypatch, objects={})["regime_map"]
    assert m["status"] == "missing"
    assert m["admissible"] is False
    assert m["refusals"]


def test_withdrawn_model_set_is_an_alarm(monkeypatch):
    """A withdrawn manifest means nothing routes — the map inside it is moot."""
    objects = _healthy_backend()
    objects["latest.json"] = _manifest(status="withdrawn")
    m = _collect(monkeypatch, objects=objects)["regime_map"]
    assert m["status"] == "withdrawn"
    assert m["admissible"] is False
    assert any("withdrawn" in r for r in m["refusals"])


def test_manifest_without_map_artifact_is_an_alarm(monkeypatch):
    objects = {"latest.json": _manifest(with_map=False)}
    m = _collect(monkeypatch, objects=objects)["regime_map"]
    assert m["status"] == "missing"
    assert m["admissible"] is False
    assert any("regime_strategy_map.json" in r for r in m["refusals"])


def test_map_artifact_listed_but_absent_is_an_alarm(monkeypatch):
    objects = {"latest.json": _manifest()}  # artifact listed, object not in the bucket
    m = _collect(monkeypatch, objects=objects)["regime_map"]
    assert m["status"] == "missing"
    assert m["admissible"] is False
    assert any(MAP_PATH in r for r in m["refusals"])


def test_collect_never_raises_on_a_corrupt_backend_object(monkeypatch):
    """The docstring promise: pure read, cannot raise. Corrupt JSON degrades to the alarm
    shape instead of propagating into the cron run that produced it."""

    class _Corrupt(_FakeStorage):
        def get_object(self, key, dest):
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write("{not json")

    _patch_local(monkeypatch)
    import src.common.storage as storage_mod

    monkeypatch.setattr(
        storage_mod,
        "build_storage",
        lambda *a, **k: _Corrupt({"latest.json": {}, MAP_PATH: {}}),
    )
    payload = H.collect(now=NOW)
    m = payload["regime_map"]
    assert m["admissible"] is False
    assert m["status"] in ("error", "missing")
