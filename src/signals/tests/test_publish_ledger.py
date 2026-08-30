"""Tests for the ledger uploader.

Every case here is a defect the 2026-08-30 audit found in the first cut. The two that
matter most are `test_a_failed_day_does_not_lose_an_earlier_days_offset` (which caused
duplicate remote rows) and `test_existing_key_is_not_deleted` (which deleted an object
that had already been round-trip verified).
"""

import json
import os

import pytest

from src.common.storage.local_fs import LocalFSBackend
from src.signals import ledger, publish_ledger


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolated ledger dir, publisher state and storage backend."""
    lg = tmp_path / "signals"
    lg.mkdir()
    monkeypatch.setattr(
        publish_ledger, "STATE_PATH", str(tmp_path / "publish_state.json")
    )
    return {
        "dir": str(lg),
        "storage": LocalFSBackend(root=str(tmp_path / "bucket")),
        "tmp": tmp_path,
    }


def _write_day(env, day, n, start=0):
    path = os.path.join(env["dir"], f"{day}.ndjson")
    with open(path, "a", encoding="utf-8") as fh:
        for i in range(n):
            fh.write(json.dumps({"signal_id": f"{day}-{start + i}"}) + "\n")
    return path


def _remote(env):
    return sorted(env["storage"].list("telemetry/signals"))


def test_uploads_then_advances_and_does_not_resend(env):
    _write_day(env, "2026-08-28", 3)
    first = publish_ledger.publish(ledger_dir=env["dir"], storage=env["storage"])
    assert first["rows"] == 3
    again = publish_ledger.publish(ledger_dir=env["dir"], storage=env["storage"])
    assert again["rows"] == 0
    assert len(_remote(env)) == 1


def test_only_new_rows_are_sent_on_the_second_run(env):
    _write_day(env, "2026-08-28", 2)
    publish_ledger.publish(ledger_dir=env["dir"], storage=env["storage"])
    _write_day(env, "2026-08-28", 1, start=2)
    second = publish_ledger.publish(ledger_dir=env["dir"], storage=env["storage"])
    assert second["rows"] == 1


def test_a_partial_final_line_is_held_back(env):
    path = _write_day(env, "2026-08-28", 1)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write('{"signal_id": "tor')  # still being written
    res = publish_ledger.publish(ledger_dir=env["dir"], storage=env["storage"])
    assert res["rows"] == 1
    # The torn row ships once it is complete, and is not lost.
    with open(path, "a", encoding="utf-8") as fh:
        fh.write('n"}\n')
    assert (
        publish_ledger.publish(ledger_dir=env["dir"], storage=env["storage"])["rows"]
        == 1
    )


def test_a_failed_day_does_not_lose_an_earlier_days_offset(env):
    """AUDIT 4a: state was saved once at the end, so a later failure discarded verified
    progress and the next run re-sent it under a new key — duplicating rows in the archive.
    """
    _write_day(env, "2026-08-28", 2)
    _write_day(env, "2026-08-29", 2)

    calls = {"n": 0}
    real_put = env["storage"].put_object

    def flaky(key, path, **kw):
        calls["n"] += 1
        if calls["n"] == 2:  # second day blows up
            raise RuntimeError("network")
        return real_put(key, path, **kw)

    env["storage"].put_object = flaky
    with pytest.raises(RuntimeError):
        publish_ledger.publish(ledger_dir=env["dir"], storage=env["storage"])

    # Day 1's verified advance survived the failure.
    saved = json.load(open(publish_ledger.STATE_PATH, encoding="utf-8"))
    assert saved["offsets"]["2026-08-28"] > 0

    env["storage"].put_object = real_put
    retry = publish_ledger.publish(ledger_dir=env["dir"], storage=env["storage"])
    assert retry["rows"] == 2  # only day 2 resent, not day 1 again

    bodies = []
    for key in _remote(env):
        dst = os.path.join(env["tmp"], "d")
        env["storage"].get_object(key, dst)
        bodies += [json.loads(x) for x in open(dst, encoding="utf-8") if x.strip()]
    ids = [b["signal_id"] for b in bodies]
    assert len(ids) == len(set(ids)) == 4, f"duplicate rows in the archive: {ids}"


def test_existing_key_is_not_deleted(env, monkeypatch):
    """AUDIT 4b: put_object refuses overwrite, and the version is second-resolution, so a
    retry in the same second hit FileExistsError — and the handler deleted the object it
    had already verified."""
    _write_day(env, "2026-08-28", 2)
    monkeypatch.setattr(
        publish_ledger, "_load_state", lambda: {"offsets": {}}
    )  # force a re-send of the same range

    publish_ledger.publish(ledger_dir=env["dir"], storage=env["storage"])
    before = _remote(env)
    assert len(before) == 1

    deleted = []
    env["storage"].delete_prefix = lambda p: deleted.append(p)
    # Same content, same UTC second -> same key -> FileExistsError.
    publish_ledger.publish(ledger_dir=env["dir"], storage=env["storage"])

    assert deleted == [], "deleted an already-verified remote object"
    assert _remote(env) == before


def test_dry_run_uploads_nothing_and_saves_no_state(env):
    _write_day(env, "2026-08-28", 2)
    res = publish_ledger.publish(
        ledger_dir=env["dir"], storage=env["storage"], dry_run=True
    )
    assert res["dry_run"] and res["rows"] == 2
    assert _remote(env) == []
    assert not os.path.exists(publish_ledger.STATE_PATH)


def test_prune_refuses_to_delete_rows_that_never_shipped(env):
    """AUDIT: prune deleted by mtime alone, so a day that failed to upload for 90 days was
    destroyed with no remote copy."""
    path = _write_day(env, "2026-01-01", 2)
    os.utime(path, (0, 0))  # far older than retention

    assert ledger.prune_local(ledger_dir=env["dir"], uploaded_offsets={}) == 0
    assert os.path.exists(path)

    size = os.path.getsize(path)
    assert (
        ledger.prune_local(ledger_dir=env["dir"], uploaded_offsets={"2026-01-01": size})
        == 1
    )
    assert not os.path.exists(path)
