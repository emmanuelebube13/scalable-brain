"""FIX-S1-010 — guard tests for the governed top-level model-set manifest.

The bug this closes: nothing in System 1 wrote the top-level ``latest.json`` that System
2's downloader reads. It was hand-authored and on 2026-07-24 still pointed at the
2026-07-01 bundle while ``system1/latest.json`` had moved to 2026-07-19 — two promotions
of drift, invisible to every per-bundle integrity check.
"""

from __future__ import annotations

import json
import os

import pytest

from src.system1.serializer import publish_model_set as PMS


class FakeStorage:
    """In-memory StorageBackend double (objects: key -> bytes)."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.pointer_writes: list[str] = []

    def put_json(self, key, payload):
        self.objects[key] = json.dumps(payload).encode()

    def put_blob(self, key, data=b"x"):
        self.objects[key] = data

    def exists(self, key):
        return key in self.objects

    def get_object(self, key, local_path):
        with open(local_path, "wb") as fh:
            fh.write(self.objects[key])

    def head(self, key):
        import hashlib

        return {
            "size": len(self.objects[key]),
            "sha256": hashlib.sha256(self.objects[key]).hexdigest(),
        }

    def atomic_pointer_update(self, key, payload):
        self.pointer_writes.append(key)
        self.put_json(key, payload)


def _complete_bucket():
    s = FakeStorage()
    s1v, gkv = "2026-07-19T00-28-32Z-87628c72", "2026-07-19T01-00-00Z-deadbeef"
    s.put_json(
        "system1/latest.json", {"bundle_version": s1v, "path": f"system1/{s1v}/"}
    )
    s.put_json(
        "models/gatekeeper/latest.json",
        {"version": gkv, "path": f"models/gatekeeper/{gkv}/"},
    )
    for name in PMS.S1_ARTIFACTS:
        s.put_blob(f"system1/{s1v}/{name}", name.encode())
    for name in PMS.GK_ARTIFACTS:
        s.put_blob(f"models/gatekeeper/{gkv}/{name}", name.encode())
    return s, s1v, gkv


def test_manifest_is_assembled_from_the_live_sub_pointers():
    s, s1v, gkv = _complete_bucket()
    m = PMS.build_manifest(s)

    assert m["system1_bundle_version"] == s1v
    assert m["gatekeeper_version"] == gkv
    assert m["model_set_id"] == f"{s1v}_gk-deadbeef"
    assert len(m["artifacts"]) == len(PMS.S1_ARTIFACTS) + len(PMS.GK_ARTIFACTS)
    # Every SHA comes from the backend, so the manifest describes what a consumer downloads.
    for a in m["artifacts"]:
        assert a["sha256"] == s.head(a["path"])["sha256"]
        assert a["bytes"] == s.head(a["path"])["size"]


def test_pointer_flips_last_and_archives_the_previous_set():
    s, _, _ = _complete_bucket()
    s.put_json(PMS.POINTER_KEY, {"model_set_id": "older-set"})

    out = PMS.publish(storage=s)

    assert out["published"] is True
    assert out["supersedes"] == "older-set"
    assert json.loads(s.objects[PMS.PREVIOUS_KEY])["model_set_id"] == "older-set"
    assert s.pointer_writes[-1] == PMS.POINTER_KEY  # live pointer written LAST


def test_incomplete_set_is_refused_and_pointer_untouched():
    """A missing artifact must abort — an incomplete set is worse than a stale one."""
    s, s1v, _ = _complete_bucket()
    s.put_json(PMS.POINTER_KEY, {"model_set_id": "older-set"})
    del s.objects[f"system1/{s1v}/strategy_weights.json"]

    with pytest.raises(PMS.ModelSetRefused, match="missing object"):
        PMS.publish(storage=s)

    assert json.loads(s.objects[PMS.POINTER_KEY])["model_set_id"] == "older-set"
    assert PMS.POINTER_KEY not in s.pointer_writes


@pytest.mark.parametrize(
    "drop", ["system1/latest.json", "models/gatekeeper/latest.json"]
)
def test_missing_sub_pointer_refuses(drop):
    s, _, _ = _complete_bucket()
    del s.objects[drop]
    with pytest.raises(PMS.ModelSetRefused):
        PMS.publish(storage=s)


def test_republish_of_an_unchanged_set_is_a_no_op():
    s, _, _ = _complete_bucket()
    PMS.publish(storage=s)
    first = json.loads(s.objects[PMS.POINTER_KEY])

    out = PMS.publish(storage=s)

    assert out.get("unchanged") is True
    assert (
        json.loads(s.objects[PMS.POINTER_KEY])["published_at"] == first["published_at"]
    )


def test_dry_run_never_writes():
    s, _, _ = _complete_bucket()
    out = PMS.publish(dry_run=True, storage=s)
    assert out["published"] is False
    assert s.pointer_writes == []
    assert PMS.POINTER_KEY not in s.objects
