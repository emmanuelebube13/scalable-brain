"""D6 — guard tests for the risk/strategy_stats publisher.

Pins the System 3 contract (checksum recipe, document shape) and the verify-before-live
ordering: a corrupt upload must abort with the previous live document untouched.
"""

from __future__ import annotations

import hashlib
import json

import pandas as pd
import pytest

from src.system1.analytics import publish_strategy_stats as SS


class FakeStorage:
    def __init__(self, fail_verify=False):
        self.objects: dict[str, bytes] = {}
        self.fail_verify = fail_verify
        self.deleted: list[str] = []
        self.writes: list[str] = []

    def put_object(self, key, local_path, *, encrypt=True):
        with open(local_path, "rb") as fh:
            self.objects[key] = fh.read()
        self.writes.append(key)

    def get_object(self, key, local_path):
        with open(local_path, "wb") as fh:
            fh.write(self.objects[key])

    def exists(self, key):
        return key in self.objects

    def sha256(self, key):
        if self.fail_verify:
            return "0" * 64  # simulate a corrupt round-trip
        return hashlib.sha256(self.objects[key]).hexdigest()

    def delete_prefix(self, prefix):
        self.deleted.append(prefix)
        for k in [k for k in self.objects if k.startswith(prefix)]:
            del self.objects[k]

    def atomic_pointer_update(self, key, payload):
        # Mirrors the real backends: re-serialized with indent + sorted keys, so the
        # published bytes are NOT the staged bytes. The checksum must survive that.
        self.objects[key] = json.dumps(payload, indent=2, sort_keys=True).encode()
        self.writes.append(key)


def _trades():
    return pd.DataFrame(
        {
            "strategy_id": [10] * 5 + [7] * 4,
            "is_winner": [1, 1, 1, 0, 0] + [1, 0, 0, 0],
            "r_multiple": [2.0, 1.0, 3.0, -1.0, -1.0] + [1.0, -1.0, -1.0, -2.0],
            "is_oos": [True] * 9,
        }
    )


def test_checksum_matches_the_documented_recipe():
    """Reproduces the checksum of the pre-existing hand-seeded object exactly, proving
    wire-compatibility with System 3's validator."""
    seed = {
        "10": {"win_rate": 0.54, "avg_win": 40.0, "avg_loss": 30.0, "expectancy": 7.8}
    }
    assert (
        SS.canonical_checksum(seed)
        == "c7c78d021c751c4389da8b613b805b177ae3af65516ecc7046a4cb0359910bac"
    )


def test_stats_and_expectancy_identity():
    stats = SS.compute_stats(_trades())
    s10 = stats["10"]
    assert s10["win_rate"] == pytest.approx(0.6)
    assert s10["avg_win"] == pytest.approx(2.0)  # mean(2,1,3)
    assert s10["avg_loss"] == pytest.approx(1.0)  # |mean(-1,-1)| -- positive magnitude
    # The identity System 3 relies on: E = p*avg_win - (1-p)*avg_loss
    assert s10["expectancy"] == pytest.approx(
        s10["win_rate"] * s10["avg_win"] - (1 - s10["win_rate"]) * s10["avg_loss"]
    )


def test_no_losses_reports_zero_not_nan():
    """NaN is not representable in JSON and would break System 3's parse."""
    t = pd.DataFrame(
        {
            "strategy_id": [1, 1],
            "is_winner": [1, 1],
            "r_multiple": [1.0, 2.0],
            "is_oos": [True, True],
        }
    )
    s = SS.compute_stats(t)["1"]
    assert s["avg_loss"] == 0.0
    json.dumps(s)  # must not raise


def test_document_shape_and_self_consistency():
    doc = SS.build_document(SS.compute_stats(_trades()))
    for k in ("produced_at", "checksum", "strategies"):
        assert k in doc
    assert doc["checksum"] == SS.canonical_checksum(doc["strategies"])
    assert doc["unit"] == "r_multiple"


def test_checksum_survives_reserialization(monkeypatch, tmp_path):
    """The live write re-serializes with indent/sorted keys. Because the checksum covers
    the strategies MAP (not the file bytes), it must still validate."""
    monkeypatch.setattr(
        SS, "build", lambda engine=None: SS.build_document(SS.compute_stats(_trades()))
    )
    s = FakeStorage()
    out = SS.publish(storage=s, staging_dir=str(tmp_path))

    live = json.loads(s.objects[SS.POINTER_KEY])
    assert (
        SS.canonical_checksum(live["strategies"]) == live["checksum"] == out["checksum"]
    )
    assert out["live_verified"] is True


def test_ordering_versioned_upload_precedes_live_write(monkeypatch, tmp_path):
    monkeypatch.setattr(
        SS, "build", lambda engine=None: SS.build_document(SS.compute_stats(_trades()))
    )
    s = FakeStorage()
    SS.publish(storage=s, staging_dir=str(tmp_path))

    assert s.writes[-1] == SS.POINTER_KEY  # live key written LAST
    assert any(
        w.endswith(SS.ARTIFACT_NAME) and w != SS.POINTER_KEY for w in s.writes[:-1]
    )


def test_corrupt_upload_aborts_and_leaves_previous_live_document_untouched(
    monkeypatch, tmp_path
):
    """The core safety property: a failed round-trip verify must never reach latest.json."""
    monkeypatch.setattr(
        SS, "build", lambda engine=None: SS.build_document(SS.compute_stats(_trades()))
    )
    s = FakeStorage(fail_verify=True)
    previous = json.dumps({"checksum": "previous", "strategies": {}}).encode()
    s.objects[SS.POINTER_KEY] = previous

    with pytest.raises(SS.StrategyStatsRefused, match="round-trip checksum mismatch"):
        SS.publish(storage=s, staging_dir=str(tmp_path))

    assert s.objects[SS.POINTER_KEY] == previous  # byte-for-byte untouched
    assert SS.POINTER_KEY not in s.writes
    assert s.deleted  # the partial version was cleaned up


def test_dry_run_writes_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(
        SS, "build", lambda engine=None: SS.build_document(SS.compute_stats(_trades()))
    )
    s = FakeStorage()
    out = SS.publish(dry_run=True, storage=s, staging_dir=str(tmp_path))
    assert out["published"] is False
    assert s.objects == {} and s.writes == []
