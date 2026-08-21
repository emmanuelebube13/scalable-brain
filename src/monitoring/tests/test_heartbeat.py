"""Runner-level tests: the alert contract and failure containment.

These cover the parts that decide whether anyone finds out about a problem —
the flag file, the alert log, the exit code, and the guarantee that a check
which itself explodes still reports instead of taking the run down.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from src.monitoring import heartbeat as hb
from src.monitoring.freshness import CheckResult, Status


@pytest.fixture(autouse=True)
def no_real_holds(tmp_path, monkeypatch):
    """Point HOLDS_FILE at nothing, for every test in this module.

    ``run_checks`` reads the holds file, so without this a declared hold in the
    real ``results/state/`` would suppress a check inside a unit test — the
    suite would pass or fail depending on repo state it never set up.
    """
    monkeypatch.setattr(hb, "HOLDS_FILE", tmp_path / "absent" / "cron_holds.json")


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Redirect every artifact path so tests never touch real state."""
    state, logs = tmp_path / "state", tmp_path / "logs"
    state.mkdir(), logs.mkdir()
    monkeypatch.setattr(hb, "STATE_DIR", state)
    monkeypatch.setattr(hb, "LOG_DIR", logs)
    monkeypatch.setattr(hb, "SNAPSHOT", state / "heartbeat_latest.json")
    monkeypatch.setattr(hb, "ALERT_FLAG", state / "HEARTBEAT_ALERT")
    monkeypatch.setattr(hb, "ALERT_LOG", logs / "heartbeat_alerts.log")
    return state, logs


NOW = datetime(2026, 7, 29, 12, tzinfo=timezone.utc)


def test_healthy_run_writes_snapshot_and_no_alert(sandbox):
    state, logs = sandbox
    hb.persist([CheckResult("prices", Status.OK, "fresh")], NOW)

    snap = json.loads((state / "heartbeat_latest.json").read_text())
    assert snap["overall_status"] == "OK" and snap["exit_code"] == 0
    assert not (state / "HEARTBEAT_ALERT").exists()
    assert not (logs / "heartbeat_alerts.log").exists()


def test_failing_run_raises_the_flag_and_logs(sandbox):
    state, logs = sandbox
    hb.persist(
        [
            CheckResult("prices", Status.OK, "fresh"),
            CheckResult("outcomes", Status.CRITICAL, "12 days behind"),
        ],
        NOW,
    )

    flag = (state / "HEARTBEAT_ALERT").read_text()
    assert "CRITICAL outcomes" in flag and "12 days behind" in flag
    assert "prices" not in flag  # healthy checks stay out of the alert

    line = (logs / "heartbeat_alerts.log").read_text()
    assert "CRITICAL" in line and "outcomes=CRITICAL" in line

    snap = json.loads((state / "heartbeat_latest.json").read_text())
    assert snap["exit_code"] == 2


def test_recovery_clears_a_stale_flag(sandbox):
    """Once everything is healthy again the flag must disappear on its own."""
    state, _ = sandbox
    hb.persist([CheckResult("outcomes", Status.CRITICAL, "stale")], NOW)
    assert (state / "HEARTBEAT_ALERT").exists()

    hb.persist([CheckResult("outcomes", Status.OK, "fresh")], NOW)
    assert not (state / "HEARTBEAT_ALERT").exists()


def test_warnings_alert_too_but_exit_1(sandbox):
    state, _ = sandbox
    hb.persist([CheckResult("telemetry", Status.WARN, "26h old")], NOW)
    assert (state / "HEARTBEAT_ALERT").exists()
    assert json.loads((state / "heartbeat_latest.json").read_text())["exit_code"] == 1


def test_a_crashing_check_is_reported_not_propagated(monkeypatch):
    """A monitor that dies with the thing it monitors reports nothing."""

    def explode(now):
        raise RuntimeError("backend on fire")

    monkeypatch.setitem(hb.CHECKS, "prices", explode)
    results = hb.run_checks("prices", NOW)

    assert len(results) == 2
    assert results[0].status == Status.BLOCKED
    assert results[0].name == "prices"
    assert results[0].status is Status.BLOCKED
    assert (
        "RuntimeError" in results[0].detail and "backend on fire" in results[0].detail
    )


def test_blocked_check_fails_the_run(monkeypatch):
    """BLOCKED must never be mistaken for a pass — visible degradation."""

    monkeypatch.setitem(
        hb.CHECKS,
        "telemetry",
        lambda now: CheckResult("telemetry", Status.BLOCKED, "no GCS credentials"),
    )
    from src.monitoring.freshness import exit_code

    assert exit_code(hb.run_checks("telemetry", NOW)) == 2


def test_render_lists_every_check(sandbox):
    results = [
        CheckResult("prices", Status.OK, "fresh"),
        CheckResult("outcomes", Status.CRITICAL, "stale"),
    ]
    out = hb.render(results, NOW)
    assert "[PASS] prices" in out
    assert "[CRIT] outcomes" in out
    assert "overall: CRITICAL (exit 2)" in out


def test_every_documented_check_is_registered():
    assert set(hb.CHECKS) == {
        "prices",
        "outcomes",
        "regimes",
        "champion_bundle",
        "telemetry",
        "retrain_state",
        "cron_liveness",
        "imports",
    }
