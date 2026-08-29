"""The published health payload must carry the fields downstream was told to read."""

from __future__ import annotations

from src.monitoring import publish_health as H

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


def _collect(monkeypatch):
    """collect() with the three local state files stubbed and the bucket read disabled."""

    def _fake_read(path):
        if path.endswith("signal_emitter_state.json"):
            return EMITTER
        return {}

    monkeypatch.setattr(H, "_read_json", _fake_read)

    # collect() imports build_storage INSIDE the function, so it has to be patched at
    # its source or the test quietly performs a real bucket read.
    import src.common.storage as storage_mod

    def _no_bucket(*a, **k):
        raise RuntimeError("no bucket in tests")

    monkeypatch.setattr(storage_mod, "build_storage", _no_bucket)
    return H.collect()


def test_fault_counters_are_published(monkeypatch):
    """`consecutive_faults` / `last_healthy_run_at` distinguish a blip from an outage.

    The erratum of 2026-08-28 told Systems 2 and 3 to read exactly these two, and the
    payload carried neither — so from the outside a one-run fault beside a healthy run
    was indistinguishable from a dead producer. Pinned here because the advice is already
    in a sent message and cannot be retracted.
    """
    emitter = _collect(monkeypatch)["emitter"]
    assert emitter["consecutive_faults"] == 1
    assert emitter["last_healthy_run_at"] == "2026-08-29T08:15:20Z"
    assert emitter["last_run_outcome"] == "no_model_set"


def test_collect_never_mutates_state(monkeypatch):
    """A telemetry read that wrote state would be the defect it is meant to report on."""
    before = dict(EMITTER)
    _collect(monkeypatch)
    assert EMITTER == before
