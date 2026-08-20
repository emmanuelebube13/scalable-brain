"""Publish contract: SHA256 verify before pointer flip; mismatch aborts cleanly."""

from __future__ import annotations

import json
import os

import pytest

from src.common.storage.local_fs import LocalFSBackend
from src.analytics import publish_analytics as PA


@pytest.fixture
def staging(tmp_path):
    d = tmp_path / "staging"
    d.mkdir()
    for name in PA.BUNDLE_FILES:
        (d / name).write_text(json.dumps({"schema_version": "1", "file": name}))
    (d / "manifest.json").write_text(
        json.dumps({"qualification_run_id": "run-123", "generated_at_utc": "t"})
    )
    return str(d)


@pytest.fixture
def storage(tmp_path):
    return LocalFSBackend(root=str(tmp_path / "bucket"))


def test_publish_flips_pointer_and_archives_previous(staging, storage):
    first = PA.publish(staging_dir=staging, storage=storage)
    assert storage.exists(PA.POINTER_KEY)
    assert first["qualification_run_id"] == "run-123"
    for name in (*PA.BUNDLE_FILES, "manifest.json"):
        assert storage.exists(f"{PA.REMOTE_ROOT}/{first['version']}/{name}")

    # a fresh build always changes the manifest (new generated_at_utc), so the
    # version string — timestamp + manifest sha — never collides across builds
    with open(os.path.join(staging, "manifest.json"), "w") as fh:
        json.dump({"qualification_run_id": "run-123", "generated_at_utc": "t2"}, fh)
    second = PA.publish(staging_dir=staging, storage=storage)
    assert storage.exists(PA.PREVIOUS_KEY)
    # previous.json now carries the first version; latest carries the second
    prev_path = os.path.join(staging, "_prev.json")
    storage.get_object(PA.PREVIOUS_KEY, prev_path)
    assert json.load(open(prev_path))["version"] == first["version"]
    latest_path = os.path.join(staging, "_latest.json")
    storage.get_object(PA.POINTER_KEY, latest_path)
    assert json.load(open(latest_path))["version"] == second["version"]


def test_checksum_mismatch_aborts_without_pointer(staging, storage, monkeypatch):
    monkeypatch.setattr(storage, "sha256", lambda key: "corrupted")
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        PA.publish(staging_dir=staging, storage=storage)
    assert not storage.exists(PA.POINTER_KEY)  # pointer never flipped
    assert list(storage.list(PA.REMOTE_ROOT)) == []  # partial version deleted


def test_publish_refuses_missing_staging(tmp_path, storage):
    with pytest.raises(SystemExit, match="missing staged"):
        PA.publish(staging_dir=str(tmp_path / "empty"), storage=storage)
