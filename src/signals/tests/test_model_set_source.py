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


def _map(status: str = "proposed") -> Dict[str, Any]:
    return {
        "status": status,
        "generated_at_utc": "2026-01-01T00:00:00Z",
        "regimes": {"High-Vol": [{"variant": "some_strategy@H4", "strategy_id": 42}]},
    }


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
