"""FIX-S1-016 — the model set must be read from the backend, not the local map.

The bug this pins: ``load_model_set`` read ``results/state/regime_strategy_map.json`` and
required ``status == "published"`` on it. ``vet.py`` hardcodes ``"status": "proposed"``
and nothing in the codebase ever writes ``"published"`` into that file, so the condition
could never be true. The producer refused to emit on every run, System 2's queue stayed
empty for weeks, and nothing in the logs said anything stronger than a warning.

The load-bearing test is :func:`test_map_status_proposed_does_not_block` — it is the
exact shape of the original defect.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

import pytest

from src.signals import build


class FakeStorage:
    """Minimal stand-in for the storage backend: a dict of key -> JSON-able object."""

    def __init__(self, objects: Dict[str, Any]) -> None:
        self._objects = objects

    def exists(self, key: str) -> bool:
        return key in self._objects

    def get_object(self, key: str, local_path: str) -> None:
        if key not in self._objects:
            raise KeyError(key)
        with open(local_path, "w", encoding="utf-8") as handle:
            json.dump(self._objects[key], handle)


MAP_KEY = "system1/2026-01-01T00-00-00Z-abc/regime_strategy_map.json"


def _manifest(status: str = "published") -> Dict[str, Any]:
    return {
        "status": status,
        "model_set_id": "2026-01-01T00-00-00Z-abc_gk-def",
        "published_at": "2026-01-01T00:00:00Z",
        "artifacts": [
            {"name": "regime_strategy_map.json", "path": MAP_KEY},
            {"name": "champion_model.pkl", "path": "models/gatekeeper/x/champion.pkl"},
        ],
    }


def _map(status: str = "proposed", **overrides: Any) -> Dict[str, Any]:
    """A map that is ADMISSIBLE for routing except for whatever a test overrides.

    The provenance block (R1.2) is part of the baseline fixture rather than something each
    test opts into, because the question these tests exist to answer is "does the map's own
    ``status`` field block emission?" — and that question is only meaningful when nothing
    *else* is blocking it. Building the fixture without provenance would make every test
    here pass or fail for the wrong reason.

    ``built_at_utc`` is anchored to "now" rather than to the 2026-01-01 date used elsewhere
    in the fixture, because the map-age check is relative to the clock: a fixed date would
    make these tests start failing once it drifted past MAP_MAX_AGE_DAYS, which is a test
    that breaks with the calendar rather than with the code.
    """
    from datetime import datetime, timedelta, timezone

    from src.vetting import map_contract as MC

    now = datetime.now(timezone.utc)
    base = {
        "status": status,
        "generated_at_utc": "2026-01-01T00:00:00Z",
        "regimes": {"High-Vol": [{"variant": "some_strategy@H4", "strategy_id": 42}]},
        **MC.provenance_header(
            run_id="test-run",
            source_label=MC.ROUTING_SOURCE_LABEL,
            labeller_version="structural-test",
            built_at=now - timedelta(hours=1),
        ),
    }
    base.update(overrides)
    return base


@pytest.fixture()
def patched(monkeypatch):
    """Patch build_storage and POINTER_KEY resolution to use a FakeStorage."""

    def install(objects: Dict[str, Any]):
        import src.common.storage as storage_mod

        monkeypatch.setattr(
            storage_mod, "build_storage", lambda *a, **k: FakeStorage(objects)
        )
        return objects

    return install


def _pointer_key() -> str:
    from src.serializer.publish_model_set import POINTER_KEY

    return POINTER_KEY


def test_map_status_proposed_does_not_block(patched) -> None:
    """THE regression test. A published manifest wrapping a 'proposed' map must load.

    The map's ``status`` is vetting's own field and is always ``"proposed"``. Publication
    state lives on the manifest. Conflating them is what stalled the producer.
    """
    patched({_pointer_key(): _manifest("published"), MAP_KEY: _map("proposed")})

    result = build.load_model_set()

    assert result is not None, (
        "a published model set whose map says 'proposed' was refused — this is the "
        "FIX-S1-016 defect, and it silently stops every signal System 2 depends on"
    )
    assert result["regimes"]["High-Vol"][0]["variant"] == "some_strategy@H4"
    assert result["model_set_id"] == "2026-01-01T00-00-00Z-abc_gk-def"


def test_unpublished_manifest_is_refused(patched) -> None:
    """Fail-closed: a withdrawn or unknown manifest status emits nothing."""
    for status in ("withdrawn", "proposed", "", "surprise"):
        patched({_pointer_key(): _manifest(status), MAP_KEY: _map()})
        assert build.load_model_set() is None, f"status {status!r} should refuse"


def test_missing_pointer_is_refused(patched) -> None:
    patched({MAP_KEY: _map()})
    assert build.load_model_set() is None


def test_manifest_without_map_artifact_is_refused(patched) -> None:
    manifest = _manifest()
    manifest["artifacts"] = [{"name": "champion_model.pkl", "path": "x"}]
    patched({_pointer_key(): manifest})
    assert build.load_model_set() is None


def test_empty_regimes_is_refused(patched) -> None:
    """An empty map is the honest-zero state and must not be treated as tradable."""
    empty = _map()
    empty["regimes"] = {}
    patched({_pointer_key(): _manifest(), MAP_KEY: empty})
    assert build.load_model_set() is None


def test_local_map_is_not_consulted(patched, tmp_path, monkeypatch) -> None:
    """Even a local file claiming 'published' must not make a withdrawn set load.

    CLAUDE.md: the backend copy is authoritative and the local file may be stale in
    either direction. This asserts the local path has no influence at all.
    """
    local = tmp_path / "regime_strategy_map.json"
    local.write_text(json.dumps({"status": "published", "regimes": {"X": [{}]}}))
    monkeypatch.setattr(build, "MAP_PATH", os.fspath(local))

    patched({_pointer_key(): _manifest("withdrawn"), MAP_KEY: _map()})
    assert build.load_model_set() is None


# --------------------------------------------------------------------------- #
# R1.3 — a map that exists but is not allowed to route
# --------------------------------------------------------------------------- #
def test_label_mismatched_map_is_refused_end_to_end(patched) -> None:
    """The 2026-08-24 defect, exercised through the real producer entry point.

    A map selected under ``regime_causal`` while signals route on ``regime_structural``
    must stop emission. Before R1.3 this returned a perfectly usable model set and the
    producer traded on it for twelve days.
    """
    patched(
        {
            _pointer_key(): _manifest("published"),
            MAP_KEY: _map("published", source_label="regime_causal"),
        }
    )

    assert build.load_model_set() is None, (
        "a map selected under a different regime label than the one signals are routed "
        "by was accepted — this is the defect R1.3 exists to stop"
    )


def test_refusal_is_distinguishable_from_no_model_set(patched) -> None:
    """ "There is no map" and "the map is wrong" must not share an outcome.

    Both emit nothing, but only one of them is an alarm. ``run.py`` keys the recorded
    outcome off ``last_refusal()``, so if this ever stops being populated the producer
    silently reclassifies a bad map as an absent one.
    """
    patched(
        {
            _pointer_key(): _manifest("published"),
            MAP_KEY: _map("published", source_label="regime_causal"),
        }
    )
    build.load_model_set()

    refusal = build.last_refusal()
    assert refusal is not None
    assert refusal["reason"] == "map_inadmissible"
    assert any("SELECTED under" in r for r in refusal["refusals"])


def test_a_successful_load_clears_any_previous_refusal(patched) -> None:
    """A stale refusal must never be re-reported as the current state."""
    patched(
        {
            _pointer_key(): _manifest("published"),
            MAP_KEY: _map("published", source_label="regime_causal"),
        }
    )
    build.load_model_set()
    assert build.last_refusal() is not None

    patched({_pointer_key(): _manifest("published"), MAP_KEY: _map("published")})
    assert build.load_model_set() is not None
    assert build.last_refusal() is None


def test_expired_map_is_refused_end_to_end(patched) -> None:
    """A map that outlives its evidence stops trading rather than keeping on."""
    from datetime import datetime, timedelta, timezone

    from src.vetting import map_contract as MC

    stale = _map(
        "published",
        **MC.provenance_header(
            run_id="test-run",
            source_label=MC.ROUTING_SOURCE_LABEL,
            labeller_version="structural-test",
            built_at=datetime.now(timezone.utc) - timedelta(days=30),
        ),
    )
    patched({_pointer_key(): _manifest("published"), MAP_KEY: stale})

    assert build.load_model_set() is None
