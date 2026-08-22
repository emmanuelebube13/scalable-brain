"""FIX-S1-010 — guard tests for the governed top-level model-set manifest.

The bug this closes: nothing in System 1 wrote the top-level ``latest.json`` that System
2's downloader reads. It was hand-authored and on 2026-07-24 still pointed at the
2026-07-01 bundle while ``system1/latest.json`` had moved to 2026-07-19 — two promotions
of drift, invisible to every per-bundle integrity check.
"""

from __future__ import annotations

import hashlib
import json
import os

import pytest

from src.serializer import publish_model_set as PMS


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

    def put_object(self, key, local_path, *, encrypt=True):
        if key in self.objects:
            raise FileExistsError(f"Object already exists (immutable): {key}")
        with open(local_path, "rb") as fh:
            self.objects[key] = fh.read()

    def delete_prefix(self, prefix):
        # The real backends delete anything under ``prefix``; every caller in this
        # module passes a single leaf key (code_bundle.zip, the pub key), so an exact
        # match is all these tests need.
        self.objects.pop(prefix, None)


def _complete_bucket(qualification_run_id="run-abc123"):
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
    # The map is a real JSON artifact, not an opaque blob — the manifest reads its
    # qualification_run_id back out of the backend.
    s.put_json(
        f"system1/{s1v}/regime_strategy_map.json",
        {"qualification_run_id": qualification_run_id, "regimes": {}},
    )
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


# --- FIX-S1-015 — withdrawal -------------------------------------------------
#
# The gap: ``publish()`` can only move the pointer FORWARD to a better model set. When
# FIX-S1-014 disqualified the only qualified strategy the correct live state became
# "there is no model", the ``non_empty_map`` gate rightly refused to promote an empty
# bundle, and so the pointer went on serving a map whose only strategy cannot fire.


def test_published_manifest_states_its_status():
    """System 2 rejects anything whose status is not exactly "published"."""
    s, _, _ = _complete_bucket()
    assert PMS.build_manifest(s)["status"] == PMS.STATUS_PUBLISHED


def test_manifest_carries_the_qualification_run_that_produced_its_map():
    """Provenance binding — the check that caught System 2's two agreeing stale mirrors.

    Age and status both missed it: the mirrors were internally consistent with each
    other. Only the run id ties an artefact to the qualification run actually live.
    """
    s, _, _ = _complete_bucket(qualification_run_id="4f608511-run")
    assert PMS.build_manifest(s)["qualification_run_id"] == "4f608511-run"


def test_withdrawal_is_empty_states_withdrawn_and_keeps_the_reason():
    s, _, _ = _complete_bucket()
    s.put_json(PMS.POINTER_KEY, {"model_set_id": "live-set"})

    out = PMS.withdraw(reason="strategy 10 disqualified for look-ahead", storage=s)

    live = json.loads(s.objects[PMS.POINTER_KEY])
    assert out["published"] is True
    assert live["status"] == PMS.STATUS_WITHDRAWN
    assert live["artifacts"] == []
    assert live["model_set_id"] is None
    assert live["supersedes"] == "live-set"
    assert "look-ahead" in live["reason"]
    assert s.pointer_writes[-1] == PMS.POINTER_KEY  # live pointer written LAST


def test_withdrawal_archives_the_superseded_set_and_deletes_nothing():
    s, _, _ = _complete_bucket()
    s.put_json(PMS.POINTER_KEY, {"model_set_id": "live-set", "artifacts": [{"a": 1}]})
    before = set(s.objects)

    PMS.withdraw(reason="because", storage=s)

    assert json.loads(s.objects[PMS.PREVIOUS_KEY])["model_set_id"] == "live-set"
    # Reinstating is an ordinary publish, so every artifact must survive untouched.
    assert before - {PMS.POINTER_KEY} <= set(s.objects)


def test_withdrawing_twice_does_not_clobber_the_rollback_breadcrumb():
    """The second call must not archive the withdrawal over the last real model set."""
    s, _, _ = _complete_bucket()
    s.put_json(PMS.POINTER_KEY, {"model_set_id": "live-set"})
    PMS.withdraw(reason="first", storage=s)

    out = PMS.withdraw(reason="second", storage=s)

    assert out.get("unchanged") is True
    assert json.loads(s.objects[PMS.PREVIOUS_KEY])["model_set_id"] == "live-set"
    assert json.loads(s.objects[PMS.POINTER_KEY])["reason"] == "first"


def test_withdrawal_requires_a_reason_in_words():
    s, _, _ = _complete_bucket()
    for empty in ("", "   "):
        with pytest.raises(ValueError, match="mandatory"):
            PMS.withdraw(reason=empty, storage=s)
    assert s.pointer_writes == []


def test_withdrawal_dry_run_never_writes():
    s, _, _ = _complete_bucket()
    s.put_json(PMS.POINTER_KEY, {"model_set_id": "live-set"})

    out = PMS.withdraw(reason="rehearsal", dry_run=True, storage=s)

    assert out["published"] is False
    assert s.pointer_writes == []
    assert json.loads(s.objects[PMS.POINTER_KEY])["model_set_id"] == "live-set"


def test_publish_reinstates_a_withdrawn_pointer():
    """Withdrawal must be reversible by the ordinary verb, with no special flag."""
    s, s1v, _ = _complete_bucket()
    s.put_json(PMS.POINTER_KEY, {"model_set_id": "live-set"})
    PMS.withdraw(reason="nothing qualifies", storage=s)

    out = PMS.publish(storage=s)

    assert out["published"] is True
    live = json.loads(s.objects[PMS.POINTER_KEY])
    assert live["status"] == PMS.STATUS_PUBLISHED
    assert live["system1_bundle_version"] == s1v
    assert len(live["artifacts"]) == len(PMS.S1_ARTIFACTS) + len(PMS.GK_ARTIFACTS)


def test_the_orchestrator_cannot_withdraw():
    """An automated retrain must never decide on its own to blank the live model.

    This is the single-flag failure mode System 2 objected to on 2026-08-02: two
    independent controls beat one, and withdrawal is a human verb.
    """
    src = os.path.join(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(PMS.__file__)))
        ),
        # Path drift: the modules were flattened out of ``src/system1/`` in 4593d88,
        # so the orchestrator now lives at ``src/scheduler/``. The test had kept the
        # pre-flatten path and was failing on FileNotFoundError rather than on the
        # property it exists to guard.
        "src",
        "scheduler",
        "orchestrator.py",
    )
    with open(src, encoding="utf-8") as fh:
        assert "withdraw" not in fh.read()


# --- code_bundle.zip regression tests (D2/D3/D4/D6) --------------------------
#
# D2: the zip was built once, gated on "does the key already exist", so evidence
#     files added after the first build were never picked up.
# D3: DETERMINISM.md / reference_vector.json / candle_fingerprint.json were added
#     with `if os.path.exists(...)` guards — silently omitted if missing.
# D4: the zip embedded per-file mtimes and used filesystem-walk ordering, so
#     identical source produced different bytes on different machines/checkouts.
# D6: signing was wrapped in a bare `except Exception: log and continue`, so a
#     broken/unreadable key produced a silent, unsigned publish.


def test_code_bundle_missing_required_artifact_refuses(monkeypatch):
    """D3 — a missing inference-parity file must abort the publish, not be skipped."""
    s, _, _ = _complete_bucket()
    # Force a "required" filename that cannot exist, without touching the real
    # DETERMINISM.md / reference_vector.json / candle_fingerprint.json on disk.
    monkeypatch.setattr(
        PMS, "CODE_BUNDLE_REQUIRED_FILES", ("no_such_evidence_file.json",)
    )

    with pytest.raises(PMS.ModelSetRefused, match="inference-parity artifact missing"):
        PMS.publish(storage=s)


def test_code_bundle_zip_is_byte_identical_across_builds(tmp_path):
    """D4 — identical source must produce byte-identical zips on every build."""
    z1 = tmp_path / "a.zip"
    z2 = tmp_path / "b.zip"
    PMS._build_code_bundle_zip(str(z1))
    PMS._build_code_bundle_zip(str(z2))

    assert (
        hashlib.sha256(z1.read_bytes()).hexdigest()
        == hashlib.sha256(z2.read_bytes()).hexdigest()
    )


def test_code_bundle_zip_is_rebuilt_when_stale_and_republish_is_idempotent():
    """D2 — a zip stored before it was complete must be refreshed, not left stale;
    once refreshed, republishing unchanged inputs must not attempt a second upload
    (the backend's put_object refuses to overwrite an existing, immutable key)."""
    s, s1v, _ = _complete_bucket()  # code_bundle.zip here is a placeholder blob
    bundle_key = f"system1/{s1v}/code_bundle.zip"
    placeholder_sha = s.head(bundle_key)["sha256"]

    PMS.publish(storage=s)
    rebuilt_sha = s.head(bundle_key)["sha256"]
    assert rebuilt_sha != placeholder_sha  # the stale placeholder got replaced

    # Nothing about the code changed, so a second publish must not re-upload —
    # FakeStorage.put_object raises FileExistsError if it tries.
    PMS.publish(storage=s)
    assert s.head(bundle_key)["sha256"] == rebuilt_sha


def test_signature_is_rewritten_on_a_genuinely_new_publish():
    """Guards a collision D6's fail-closed fix would otherwise introduce: ``.sig``
    lives at a fixed key and legitimately changes on every publish (it's over the
    manifest, which always changes), so it must be replaced rather than left to
    collide with put_object's immutability guard on the second real publish."""
    s, _, _ = _complete_bucket()
    PMS.publish(storage=s)
    first_sig = s.objects[f"{PMS.POINTER_KEY}.sig"]

    # A genuinely different model set: promote a new gatekeeper version.
    new_gkv = "2026-07-20T01-00-00Z-cafefeed"
    s.put_json(
        "models/gatekeeper/latest.json",
        {"version": new_gkv, "path": f"models/gatekeeper/{new_gkv}/"},
    )
    for name in PMS.GK_ARTIFACTS:
        s.put_blob(f"models/gatekeeper/{new_gkv}/{name}", name.encode())

    out = PMS.publish(storage=s)

    assert out["published"] is True
    assert out["gatekeeper_version"] == new_gkv
    second_sig = s.objects[f"{PMS.POINTER_KEY}.sig"]
    assert second_sig != first_sig  # rewritten for the new manifest, not left stale


def test_signing_failure_aborts_the_publish_before_the_pointer_flips(monkeypatch):
    """D6 — signing must fail CLOSED: a broken key aborts, it does not degrade to
    an unsigned publish. Ordering matters here too: abort must happen before the
    live pointer is flipped (upload -> verify -> flip is load-bearing)."""
    from cryptography.hazmat.primitives import serialization as real_serialization

    s, _, _ = _complete_bucket()
    s.put_json(PMS.POINTER_KEY, {"model_set_id": "older-set"})

    def _boom(*_args, **_kwargs):
        raise ValueError("corrupt or unreadable key")

    monkeypatch.setattr(real_serialization, "load_pem_private_key", _boom)

    with pytest.raises(PMS.ModelSetRefused, match="signing failed"):
        PMS.publish(storage=s)

    assert json.loads(s.objects[PMS.POINTER_KEY])["model_set_id"] == "older-set"
    assert PMS.POINTER_KEY not in s.pointer_writes


# --- pointer-freshness regression (found in pass-3 verification) -------------


def test_changed_artifact_hash_is_not_treated_as_unchanged():
    """A rebuilt bundle must flip the pointer even when model_set_id is stable.

    Found in production during ADR-001 verification. ``model_set_id`` is derived from the
    two sub-pointer *versions*, so it stays constant while artifact content changes
    underneath it. The code bundle was rebuilt to include the determinism evidence, the
    new zip was uploaded, and the guard declined to republish -- leaving the manifest
    advertising a SHA256 that no longer matched the object in the bucket.

    A consumer following ``docs/BUNDLE-CONSUMER-GUIDE.md`` verifies every artifact hash
    and refuses the whole model set on a single mismatch. So this silently bricked the
    bundle for every downstream system while reporting success.
    """
    base = {
        "model_set_id": "v1_gk-abc",
        "status": "published",
        "code_commit": "deadbeef",
        "published_at": "2026-01-01T00:00:00Z",
        "artifacts": [{"name": "code_bundle.zip", "path": "p", "sha256": "AAA"}],
    }
    # Same identity, same everything, only the wall clock moved -> genuinely unchanged.
    same = {**base, "published_at": "2026-02-02T00:00:00Z"}
    assert PMS._is_materially_identical(base, same) is True

    # Same model_set_id, but the bundle content changed -> MUST republish.
    rebuilt = {
        **same,
        "artifacts": [{"name": "code_bundle.zip", "path": "p", "sha256": "BBB"}],
    }
    assert PMS._is_materially_identical(base, rebuilt) is False

    # New source commit is also material -- provenance a consumer can observe.
    recommitted = {**same, "code_commit": "cafe1234"}
    assert PMS._is_materially_identical(base, recommitted) is False
