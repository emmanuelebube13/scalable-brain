"""R4.2 — the risk-off gate the producer reads before emitting.

The failure being defended against is not "we had no check". The heartbeat detected
`fact_market_regime_v2` going stale on 2026-08-24 and reported CRITICAL every morning for
twelve days. Nothing consumed that verdict, so the producer kept emitting. These tests pin
the *consequence*: a blocking breach must stop emission, and the ways it could silently
stop stopping are what is enumerated below.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from src.monitoring import risk_off as RO

# A Wednesday 12:00 UTC — market open, so staleness is measured against `now`.
OPEN_NOW = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
# A Saturday — market shut, so staleness is measured against the Friday close.
CLOSED_NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)


def _contract(**kw):
    base = dict(
        name="fact_market_prices",
        max_staleness_hours=3.0,
        blocking=True,
        why="test",
        bar_hours=1.0,
    )
    base.update(kw)
    return RO.Contract(**base)


# --------------------------------------------------------------------------- #
# The flag file
# --------------------------------------------------------------------------- #
def test_absent_flag_means_no_reasons(tmp_path, monkeypatch):
    monkeypatch.setattr(RO, "RISK_OFF_FLAG", str(tmp_path / "RISK_OFF"))
    assert RO.flag_reasons() == []


def test_set_and_clear_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(RO, "RISK_OFF_FLAG", str(tmp_path / "RISK_OFF"))
    RO.set_flag(["regimes stale"])
    assert RO.flag_reasons() == ["regimes stale"]
    RO.clear_flag()
    assert RO.flag_reasons() == []


def test_unreadable_flag_counts_as_SET(tmp_path, monkeypatch):
    """A corrupt flag must not become a way to resume trading.

    The file exists to stop emission. If it cannot be parsed, the safe reading is "someone
    stopped trading and the record is damaged", never "no reason found, carry on".
    """
    flag = tmp_path / "RISK_OFF"
    flag.write_text("{not json")
    monkeypatch.setattr(RO, "RISK_OFF_FLAG", str(flag))
    reasons = RO.flag_reasons()
    assert reasons and "treating as set" in reasons[0]


def test_flag_with_no_reasons_still_blocks(tmp_path, monkeypatch):
    flag = tmp_path / "RISK_OFF"
    flag.write_text(json.dumps({"set_at_utc": "2026-09-05T00:00:00+00:00"}))
    monkeypatch.setattr(RO, "RISK_OFF_FLAG", str(flag))
    assert RO.flag_reasons() != []


# --------------------------------------------------------------------------- #
# Staleness arithmetic
# --------------------------------------------------------------------------- #
def test_when_the_market_is_shut_staleness_is_measured_from_the_close():
    """Otherwise every weekend is a false alarm, and an alarm that cries wolf gets muted.

    That is not hypothetical here: `freshness.py`'s own docstring records that naive
    thresholds "false-alarm every weekend ... which is how the last two outages stayed
    invisible".
    """
    assert RO._reference_time(CLOSED_NOW) == RO.last_market_close(CLOSED_NOW)
    assert RO._reference_time(OPEN_NOW) == OPEN_NOW


def test_bar_open_allowance_prevents_a_healthy_series_reading_as_stale(monkeypatch):
    """Bars are stamped at their OPEN, so a fresh D1 row is already ~24h 'old'.

    Without the allowance a perfectly healthy daily series breaches a 2h contract
    permanently — and a contract that is always red is a contract someone switches off.
    """
    contract = _contract(
        name="fact_market_regime_v2", max_staleness_hours=6.0, bar_hours=24.0
    )
    fresh_d1 = OPEN_NOW - timedelta(hours=25)
    monkeypatch.setattr(RO, "_latest_row", lambda *a, **k: fresh_d1)
    assert RO._evaluate_table(contract, OPEN_NOW) is None


def test_breach_is_reported_with_the_numbers(monkeypatch):
    contract = _contract()
    monkeypatch.setattr(
        RO, "_latest_row", lambda *a, **k: OPEN_NOW - timedelta(hours=50)
    )
    breach = RO._evaluate_table(contract, OPEN_NOW)
    assert breach is not None
    assert "50.0h" in breach.detail
    assert breach.blocking is True


# --------------------------------------------------------------------------- #
# Fail-closed
# --------------------------------------------------------------------------- #
def test_a_missing_table_is_a_breach_not_an_exemption(monkeypatch):
    """ "The input I must check is absent" is never a reason to proceed."""

    def boom(*a, **k):
        raise LookupError("table fact_regime_structural does not exist")

    monkeypatch.setattr(RO, "_latest_row", boom)
    breach = RO._evaluate_table(_contract(name="fact_regime_structural"), OPEN_NOW)
    assert breach is not None
    assert "does not exist" in breach.detail


def test_an_empty_table_is_a_breach(monkeypatch):
    monkeypatch.setattr(RO, "_latest_row", lambda *a, **k: None)
    breach = RO._evaluate_table(_contract(), OPEN_NOW)
    assert breach is not None and "empty" in breach.detail


def test_a_db_error_is_a_breach_not_a_pass(monkeypatch):
    """An unevaluatable contract must block. Failing to measure is not measuring OK."""

    def boom(*a, **k):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(RO, "_latest_row", boom)
    breach = RO._evaluate_table(_contract(), OPEN_NOW)
    assert breach is not None and "could not evaluate" in breach.detail


# --------------------------------------------------------------------------- #
# Blocking vs alerting
# --------------------------------------------------------------------------- #
def test_non_blocking_breaches_do_not_stop_emission(tmp_path, monkeypatch):
    """`fact_market_regime_v2` is research-only; its staleness alerts but must not gate."""
    monkeypatch.setattr(RO, "RISK_OFF_FLAG", str(tmp_path / "RISK_OFF"))
    alert_only = RO.Breach(_contract(blocking=False), "stale", 999.0)
    monkeypatch.setattr(RO, "evaluate_contracts", lambda now=None: [alert_only])
    assert RO.refuse_reasons(OPEN_NOW) == []


def test_blocking_breaches_stop_emission(tmp_path, monkeypatch):
    monkeypatch.setattr(RO, "RISK_OFF_FLAG", str(tmp_path / "RISK_OFF"))
    blocker = RO.Breach(_contract(blocking=True), "stale", 999.0)
    monkeypatch.setattr(RO, "evaluate_contracts", lambda now=None: [blocker])
    assert RO.refuse_reasons(OPEN_NOW) != []


def test_flag_and_measurement_are_ORed_never_ANDed(tmp_path, monkeypatch):
    """A design where two things must agree before trading stops fails open."""
    flag = tmp_path / "RISK_OFF"
    monkeypatch.setattr(RO, "RISK_OFF_FLAG", str(flag))
    monkeypatch.setattr(RO, "evaluate_contracts", lambda now=None: [])

    RO.set_flag(["manual halt"])
    assert RO.refuse_reasons(OPEN_NOW) == ["manual halt"], "flag alone must block"


def test_the_live_regime_table_contract_is_not_blocking():
    """It is written BY the producer, so gating the producer on it would deadlock.

    R2.2 also requires its write to be wrapped so that a logging failure "can never block
    a signal". An observer that can halt what it observes is not an observer.
    """
    live = next(c for c in RO.CONTRACTS if c.name == "fact_regime_structural_live")
    assert live.blocking is False


def test_the_canonical_regime_table_contract_IS_blocking():
    canonical = next(c for c in RO.CONTRACTS if c.name == "fact_regime_structural")
    assert canonical.blocking is True
