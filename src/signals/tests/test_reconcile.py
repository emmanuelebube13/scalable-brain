"""Tests for the emitter-counter reconciler.

The defect under test is a lifetime counter losing its history with nothing noticing, so
the tests are written around that shape rather than around the happy path: a zeroed file
must be detected, must be repairable from the ledger, and must come back to the value it
held before it was zeroed.
"""

import json

import pytest

from src.signals import reconcile as rc


def _row(**over):
    row = {
        "signal_id": "sig-1",
        "gate1_outcome": "scored",
        "wire_action": "published",
        "shadow_verdict": "would_refuse",
    }
    row.update(over)
    return row


@pytest.fixture
def ledger_dir(tmp_path):
    d = tmp_path / "signals"
    d.mkdir()
    return d


def _write(ledger_dir, day, rows):
    path = ledger_dir / f"{day}.ndjson"
    with open(path, "a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _state(tmp_path, **over):
    payload = {
        "last_run_at": "2026-09-11T14:16:08Z",
        "last_run_outcome": "no_signals_generated",
        "last_signal_emitted_at": "2026-09-04T21:15:44Z",
        "consecutive_faults": 0,
        "signals_published_total": 0,
        "signals_scored_total": 0,
        "signals_unscored_total": 0,
        "signals_dropped_total": 0,
        "shadow_would_pass_total": 0,
        "shadow_would_refuse_total": 0,
    }
    payload.update(over)
    p = tmp_path / "emitter.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_tally_counts_each_row_into_its_counter(ledger_dir):
    _write(
        ledger_dir,
        "2026-09-01",
        [
            _row(),
            _row(wire_action="suppressed", shadow_verdict="would_pass"),
            _row(gate1_outcome="unscored"),
            _row(gate1_outcome="dropped_corrupt_feature", wire_action="dropped"),
        ],
    )
    counts = rc.tally_ledger(str(ledger_dir))["counts"]
    # Rows 1 and 3 reached the wire; the suppressed and dropped rows did not.
    assert counts["signals_published_total"] == 2
    assert counts["signals_scored_total"] == 2
    assert counts["signals_unscored_total"] == 1
    assert counts["signals_dropped_total"] == 1
    assert counts["shadow_would_pass_total"] == 1
    assert counts["shadow_would_refuse_total"] == 3


def test_unknown_status_counts_as_unscored(ledger_dir):
    """``run.py`` emits `unknown_status` with a null score and tallies it as unscored.

    The ledger keeps the finer distinction; the counters must not invent a new bucket or
    the two stop reconciling.
    """
    _write(ledger_dir, "2026-09-01", [_row(gate1_outcome="unknown_status")])
    counts = rc.tally_ledger(str(ledger_dir))["counts"]
    assert counts["signals_unscored_total"] == 1
    assert counts["signals_scored_total"] == 0


def test_a_zeroed_counter_is_reported_as_a_shortfall(tmp_path, ledger_dir):
    _write(ledger_dir, "2026-09-01", [_row(), _row()])
    state = _state(tmp_path)
    report = rc.reconcile(str(state), str(ledger_dir))

    assert not report["ok"]
    names = {s["counter"] for s in report["shortfalls"]}
    assert "signals_published_total" in names
    short = next(
        s for s in report["shortfalls"] if s["counter"] == "signals_published_total"
    )
    assert (
        short["expected_floor"]
        == rc.LEDGER_EPOCH_BASELINE["signals_published_total"] + 2
    )


def test_the_self_contradiction_is_flagged_without_any_ledger(tmp_path, ledger_dir):
    """A non-null ``last_signal_emitted_at`` beside a zero publish count is impossible.

    This is the 2026-09-11 shape and it needs no ledger to detect — the file disagrees
    with itself. Kept separate from the shortfall list because it is not repairable
    evidence of lost history, it is proof of it.
    """
    state = _state(tmp_path)
    report = rc.reconcile(str(state), str(ledger_dir))
    assert any("contradicts itself" in m for m in report["inconsistencies"])


def test_a_counter_above_the_floor_is_a_surplus_not_a_failure(tmp_path, ledger_dir):
    """Pruned ledger days (O-19) and failed ledger appends (O-21) both land here."""
    _write(ledger_dir, "2026-09-01", [_row()])
    state = _state(
        tmp_path,
        signals_published_total=10_000,
        signals_scored_total=1,
        shadow_would_refuse_total=1,
    )
    report = rc.reconcile(str(state), str(ledger_dir))

    assert report["ok"]
    assert not report["shortfalls"]
    assert any(s["counter"] == "signals_published_total" for s in report["surpluses"])


def test_repair_restores_the_counter_from_baseline_plus_ledger(tmp_path, ledger_dir):
    _write(ledger_dir, "2026-09-01", [_row(), _row(), _row()])
    state = _state(tmp_path)

    rc.repair(str(state), str(ledger_dir))

    after = json.loads(state.read_text(encoding="utf-8"))
    assert (
        after["signals_published_total"]
        == rc.LEDGER_EPOCH_BASELINE["signals_published_total"] + 3
    )
    assert rc.reconcile(str(state), str(ledger_dir))["ok"]


def test_repair_never_lowers_a_counter(tmp_path, ledger_dir):
    """Monotonic on purpose: a surplus may be history the ledger can no longer see."""
    _write(ledger_dir, "2026-09-01", [_row()])
    state = _state(tmp_path, signals_published_total=10_000, signals_scored_total=9_000)

    rc.repair(str(state), str(ledger_dir))

    after = json.loads(state.read_text(encoding="utf-8"))
    assert after["signals_published_total"] == 10_000
    assert after["signals_scored_total"] == 9_000


def test_repair_leaves_the_run_level_fields_untouched(tmp_path, ledger_dir):
    """Only the cumulative totals are this module's business."""
    _write(ledger_dir, "2026-09-01", [_row()])
    state = _state(tmp_path, consecutive_faults=3, last_run_outcome="risk_off")
    before = json.loads(state.read_text(encoding="utf-8"))

    rc.repair(str(state), str(ledger_dir))

    after = json.loads(state.read_text(encoding="utf-8"))
    for key in (
        "last_run_at",
        "last_run_outcome",
        "last_signal_emitted_at",
        "consecutive_faults",
    ):
        assert after[key] == before[key], key


def test_repair_refuses_when_the_state_file_is_unreadable(tmp_path, ledger_dir):
    """Rewriting from scratch would silently drop the run-level fields.

    Losing `last_signal_emitted_at` manufactures the FIX-S1-016 alarm, so refusing is
    the safe direction even though it leaves the counters short.
    """
    _write(ledger_dir, "2026-09-01", [_row()])
    p = tmp_path / "emitter.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(RuntimeError):
        rc.repair(str(p), str(ledger_dir))


def test_unparseable_ledger_lines_are_counted_not_skipped(tmp_path, ledger_dir):
    """A truncated NDJSON tail must not read as a lost counter."""
    _write(ledger_dir, "2026-09-01", [_row()])
    with open(ledger_dir / "2026-09-01.ndjson", "a", encoding="utf-8") as fh:
        fh.write('{"signal_id": "trunc\n')

    led = rc.tally_ledger(str(ledger_dir))
    assert led["bad_lines"] == 1

    state = _state(tmp_path)
    report = rc.reconcile(str(state), str(ledger_dir))
    assert any("unparseable ledger line" in m for m in report["inconsistencies"])


def test_repair_writes_atomically(tmp_path, ledger_dir):
    """No .tmp may survive — the truncated-file path is what resets counters to zero."""
    import os

    _write(ledger_dir, "2026-09-01", [_row()])
    state = _state(tmp_path)
    rc.repair(str(state), str(ledger_dir))
    assert not [p for p in os.listdir(tmp_path) if p.endswith(".tmp")]


@pytest.mark.parametrize(
    "overrides, expected",
    [
        # The file contradicting itself cannot be true under any history.
        ({}, "CRITICAL"),
        # History lost but nothing impossible: repairable, so WARN.
        ({"last_signal_emitted_at": None}, "WARN"),
        # Reconciled.
        (
            {
                "last_signal_emitted_at": None,
                "signals_published_total": rc.LEDGER_EPOCH_BASELINE[
                    "signals_published_total"
                ]
                + 1,
                "signals_scored_total": 1,
                "shadow_would_refuse_total": 1,
            },
            "OK",
        ),
    ],
)
def test_the_heartbeat_check_consumes_the_reconciliation(
    tmp_path, ledger_dir, monkeypatch, overrides, expected
):
    """R4.2: a detector with no consumer is not a control.

    ``check_emitter_counters`` imports ``reconcile`` inside the function, so substituting
    it here is what the check actually calls. The real reconciler runs — against the
    fixture paths rather than the live state file.
    """
    from src.monitoring import heartbeat as hb

    _write(ledger_dir, "2026-09-01", [_row()])
    state = _state(tmp_path, **overrides)
    # The genuine reconciler, bound to the fixture paths instead of the live ones.
    original = rc.reconcile
    monkeypatch.setattr(
        rc, "reconcile", lambda *a, **k: original(str(state), str(ledger_dir))
    )

    res = hb.check_emitter_counters(hb._utcnow())
    assert res.name == "emitter_counters"
    assert res.status.name == expected
