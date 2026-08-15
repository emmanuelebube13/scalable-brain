import pytest
from datetime import datetime, timezone, timedelta
from src.system1.monitoring.freshness import CheckResult, Status
from src.system1.monitoring.holds import Hold, parse_holds, apply_hold, summarise

def dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))

def test_parse_holds_valid():
    payload = {
        "schema_version": 1,
        "holds": [
            {
                "checks": ["cron_liveness", "retrain_state"],
                "reason": "Test reason",
                "declared_by": "test",
                "declared_at_utc": "2026-08-01T00:00:00Z",
                "expires_utc": "2026-08-30T00:00:00Z",
                "evidence": "evidence"
            }
        ]
    }
    holds_by_check, problems = parse_holds(payload, dt("2026-08-15T00:00:00Z"))
    assert not problems
    assert "cron_liveness" in holds_by_check
    assert "retrain_state" in holds_by_check
    assert holds_by_check["cron_liveness"] is holds_by_check["retrain_state"]
    hold = holds_by_check["cron_liveness"]
    assert hold.reason == "Test reason"
    assert hold.expires_utc == dt("2026-08-30T00:00:00Z")

def test_parse_holds_invalid_schema():
    h, p = parse_holds({}, dt("2026-08-15T00:00:00Z"))
    assert p == ["missing or unsupported schema_version"]
    
    h, p = parse_holds({"schema_version": 2}, dt("2026-08-15T00:00:00Z"))
    assert p == ["missing or unsupported schema_version"]

def test_parse_holds_missing_keys():
    payload = {"schema_version": 1, "holds": [{"checks": ["cron_liveness"]}]}
    h, p = parse_holds(payload, dt("2026-08-15T00:00:00Z"))
    assert len(p) == 1
    assert "missing keys" in p[0]

def test_parse_holds_invalid_check():
    payload = {
        "schema_version": 1,
        "holds": [{
            "checks": ["imports"],
            "reason": "test", "declared_by": "test", "declared_at_utc": "2026-08-01T00:00:00Z",
            "expires_utc": "2026-08-30T00:00:00Z", "evidence": "test"
        }]
    }
    h, p = parse_holds(payload, dt("2026-08-15T00:00:00Z"))
    assert len(p) == 1
    assert "'imports' is not holdable" in p[0]

def test_parse_holds_naive_timestamp():
    payload = {
        "schema_version": 1,
        "holds": [{
            "checks": ["cron_liveness"],
            "reason": "test", "declared_by": "test", "declared_at_utc": "2026-08-01T00:00:00",
            "expires_utc": "2026-08-30T00:00:00Z", "evidence": "test"
        }]
    }
    h, p = parse_holds(payload, dt("2026-08-15T00:00:00Z"))
    assert p == ["hold[0]: declared_at_utc is naive"]

def test_parse_holds_duration_exceeded():
    payload = {
        "schema_version": 1,
        "holds": [{
            "checks": ["cron_liveness"],
            "reason": "test", "declared_by": "test", "declared_at_utc": "2026-08-01T00:00:00Z",
            "expires_utc": "2026-12-30T00:00:00Z", "evidence": "test"
        }]
    }
    h, p = parse_holds(payload, dt("2026-08-15T00:00:00Z"))
    assert p == ["hold[0]: duration exceeds 90 days"]

def test_apply_hold_active():
    h = Hold(["cron_liveness"], "test reason", "user", dt("2026-08-01T00:00:00Z"), dt("2026-08-30T00:00:00Z"), "evidence")
    cr = CheckResult("cron_liveness", Status.CRITICAL, "broken")
    out = apply_hold(cr, h, dt("2026-08-15T00:00:00Z"))
    assert out.status == Status.OK
    assert out.detail == "HELD until 2026-08-30 (15d left); underlying: broken"
    assert out.underlying_status == Status.CRITICAL
    assert out.held_reason == "test reason"

def test_apply_hold_expired():
    h = Hold(["cron_liveness"], "test reason", "user", dt("2026-08-01T00:00:00Z"), dt("2026-08-05T00:00:00Z"), "evidence")
    cr = CheckResult("cron_liveness", Status.CRITICAL, "broken")
    out = apply_hold(cr, h, dt("2026-08-15T00:00:00Z"))
    assert out is cr  # Returns unmodified

def test_summarise_ok():
    h = Hold(["cron_liveness"], "test", "user", dt("2026-08-01T00:00:00Z"), dt("2026-08-30T00:00:00Z"), "evidence")
    cr = summarise({"cron_liveness": h}, [], dt("2026-08-15T00:00:00Z"))
    assert cr.status == Status.OK
    assert cr.detail == "1 hold active, soonest expires in 15d"

def test_summarise_warn():
    h = Hold(["cron_liveness"], "test", "user", dt("2026-08-01T00:00:00Z"), dt("2026-08-18T00:00:00Z"), "evidence")
    cr = summarise({"cron_liveness": h}, [], dt("2026-08-15T00:00:00Z"))
    assert cr.status == Status.WARN
    assert "expires in 3d" in cr.detail

def test_summarise_critical():
    h = Hold(["cron_liveness"], "test", "user", dt("2026-08-01T00:00:00Z"), dt("2026-08-10T00:00:00Z"), "evidence")
    cr = summarise({"cron_liveness": h}, [], dt("2026-08-15T00:00:00Z"))
    assert cr.status == Status.CRITICAL
    assert "expired 5d ago" in cr.detail

def test_summarise_blocked():
    cr = summarise({}, ["some problem"], dt("2026-08-15T00:00:00Z"))
    assert cr.status == Status.BLOCKED
    assert cr.detail == "some problem"

def test_summarise_empty():
    cr = summarise({}, [], dt("2026-08-15T00:00:00Z"))
    assert cr.status == Status.OK
    assert cr.detail == "no holds declared"
