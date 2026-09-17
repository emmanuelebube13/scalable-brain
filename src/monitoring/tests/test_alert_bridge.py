"""Tests for src.monitoring.alert_bridge — the state-file → Telegram bridge.

All tests are hermetic: tmp_path for filesystem, monkeypatched env vars, a
fake ``requests.post`` that never touches the network.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# We monkeypatch the module-level path constants before importing functions,
# so each test gets its own tmp_path for state files.
import src.monitoring.alert_bridge as bridge

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect all state paths into tmp_path so tests never touch real state."""
    monkeypatch.setattr(bridge, "_STATE_DIR", tmp_path)
    monkeypatch.setattr(bridge, "_HEARTBEAT_ALERT", tmp_path / "HEARTBEAT_ALERT")
    monkeypatch.setattr(
        bridge, "_EMITTER_STATE", tmp_path / "signal_emitter_state.json"
    )
    monkeypatch.setattr(bridge, "_BRIDGE_STATE", tmp_path / "alert_bridge_state.json")


@pytest.fixture()
def emitter_state(tmp_path: Path):
    """Write a signal_emitter_state.json and return the path helper."""

    def _write(**fields) -> Path:
        default = {
            "consecutive_faults": 0,
            "last_run_outcome": "no_signals_generated",
            "last_run_fault_detail": None,
            "last_signal_emitted_at": None,
        }
        default.update(fields)
        p = tmp_path / "signal_emitter_state.json"
        p.write_text(json.dumps(default))
        return p

    return _write


@pytest.fixture()
def heartbeat_alert(tmp_path: Path):
    """Create a HEARTBEAT_ALERT flag file."""

    def _write(text: str = "CRITICAL: stale prices") -> Path:
        p = tmp_path / "HEARTBEAT_ALERT"
        p.write_text(text)
        return p

    return _write


def _fake_post_ok(*args, **kwargs):
    resp = MagicMock()
    resp.status_code = 200
    return resp


def _fake_post_fail(*args, **kwargs):
    resp = MagicMock()
    resp.status_code = 500
    resp.text = "Internal Server Error"
    return resp


# ---------------------------------------------------------------------------
# Alert condition tests
# ---------------------------------------------------------------------------


class TestHeartbeatAlertFires:
    def test_heartbeat_alert_present(self, heartbeat_alert):
        heartbeat_alert("CRITICAL: stale prices")
        alerts = bridge.collect_alerts(
            datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
        )
        assert any(a["key"] == "heartbeat_alert" for a in alerts)
        ha = [a for a in alerts if a["key"] == "heartbeat_alert"][0]
        assert ha["severity"] == "critical"
        assert "stale prices" in ha["message"]

    def test_heartbeat_alert_absent(self):
        alerts = bridge.collect_alerts(
            datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
        )
        assert not any(a["key"] == "heartbeat_alert" for a in alerts)


class TestEmitterFaults:
    def test_faults_at_threshold(self, emitter_state):
        emitter_state(consecutive_faults=3, last_run_fault_detail="model_set missing")
        alerts = bridge.collect_alerts(
            datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
        )
        assert any(a["key"] == "emitter_faults" for a in alerts)

    def test_faults_below_threshold(self, emitter_state):
        emitter_state(consecutive_faults=2)
        alerts = bridge.collect_alerts(
            datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
        )
        assert not any(a["key"] == "emitter_faults" for a in alerts)


class TestEmitterStaleness:
    def test_stale_during_weekday(self, emitter_state):
        # Wednesday noon, last emitted 2 days ago (well over 26 open hours)
        emitter_state(last_signal_emitted_at="2026-09-14T12:00:00Z")
        # Wednesday 2026-09-16 12:00 UTC
        now = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
        alerts = bridge.collect_alerts(now)
        assert any(a["key"] == "emitter_stale" for a in alerts)

    def test_not_stale(self, emitter_state):
        # Last emitted 2 hours ago on a weekday
        now = datetime(2026, 9, 17, 14, 0, tzinfo=timezone.utc)
        emitter_state(last_signal_emitted_at="2026-09-17T12:00:00Z")
        alerts = bridge.collect_alerts(now)
        assert not any(a["key"] == "emitter_stale" for a in alerts)

    def test_weekend_does_not_fire_staleness(self, emitter_state):
        """Weekends must not fire the stale-emission alert.

        Friday 21:00 → Sunday 21:00 is 48 wall-clock hours but 0 market hours.
        A signal emitted Friday afternoon should NOT be flagged stale on Saturday.
        """
        # Last emitted Friday 15:00 UTC
        emitter_state(last_signal_emitted_at="2026-09-18T15:00:00Z")
        # Saturday 12:00 UTC — 21 wall-clock hours, but only ~6 open hours
        # (Friday 15:00 → Friday 21:00 = 6h, then market is closed)
        now = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
        alerts = bridge.collect_alerts(now)
        assert not any(a["key"] == "emitter_stale" for a in alerts)


class TestRecovery:
    def test_recovery_message_sent(self, tmp_path: Path):
        """When an alert stops firing, one 'recovered' message is sent."""
        # Prime state with a previously-notified key
        state = {"notified": {"heartbeat_alert": 0.0}}
        (tmp_path / "alert_bridge_state.json").write_text(json.dumps(state))

        now = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
        # No alerts firing → heartbeat_alert should be "recovered"
        alerts: list[dict] = []
        messages, new_state = bridge._decide_notifications(alerts, state, now)
        assert any("recovered" in m and "heartbeat_alert" in m for m in messages)
        assert "heartbeat_alert" not in new_state.get("notified", {})


# ---------------------------------------------------------------------------
# Dedup window
# ---------------------------------------------------------------------------


class TestDedupWindow:
    def test_dedup_within_window(self):
        """Same key within 6h → no repeat notification."""
        now = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
        state = {"notified": {"heartbeat_alert": now.timestamp() - 3600}}  # 1h ago
        alerts = [{"key": "heartbeat_alert", "severity": "critical", "message": "x"}]
        messages, _ = bridge._decide_notifications(alerts, state, now)
        assert len(messages) == 0

    def test_dedup_after_window(self):
        """Same key after 6h → re-notify."""
        now = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
        state = {
            "notified": {
                "heartbeat_alert": now.timestamp() - 7 * 3600,  # 7h ago
            }
        }
        alerts = [{"key": "heartbeat_alert", "severity": "critical", "message": "x"}]
        messages, _ = bridge._decide_notifications(alerts, state, now)
        assert len(messages) == 1


# ---------------------------------------------------------------------------
# Telegram send
# ---------------------------------------------------------------------------


class TestSendTelegram:
    def test_missing_env_vars_returns_false(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        assert bridge.send_telegram("hello") is False

    def test_missing_token_returns_false(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        assert bridge.send_telegram("hello") is False

    def test_success(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
        with patch("src.monitoring.alert_bridge.requests.post", _fake_post_ok):
            assert bridge.send_telegram("hello") is True

    def test_api_failure_returns_false(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
        with patch("src.monitoring.alert_bridge.requests.post", _fake_post_fail):
            assert bridge.send_telegram("hello") is False

    def test_network_error_returns_false(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")

        def _raise(*a, **kw):
            raise ConnectionError("no network")

        with patch("src.monitoring.alert_bridge.requests.post", _raise):
            assert bridge.send_telegram("hello") is False


# ---------------------------------------------------------------------------
# Unreadable state → notify (never silence)
# ---------------------------------------------------------------------------


class TestUnreadableState:
    def test_corrupt_state_degrades_to_notify(self, tmp_path: Path):
        """Unreadable bridge state must degrade to notify, never to silence."""
        (tmp_path / "alert_bridge_state.json").write_text("{{{broken json")
        state = bridge._load_bridge_state()
        assert state == {}  # empty means no dedup → will notify

    def test_missing_state_degrades_to_notify(self):
        state = bridge._load_bridge_state()
        assert state == {}


# ---------------------------------------------------------------------------
# --dry-run sends nothing
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_does_not_send(
        self, heartbeat_alert, monkeypatch: pytest.MonkeyPatch, capsys
    ):
        heartbeat_alert()
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")

        call_count = 0

        def _counting_post(*a, **kw):
            nonlocal call_count
            call_count += 1
            return _fake_post_ok(*a, **kw)

        with patch("src.monitoring.alert_bridge.requests.post", _counting_post):
            bridge.main([])  # default is --dry-run

        assert call_count == 0
        captured = capsys.readouterr()
        assert "dry-run" in captured.out.lower()

    def test_send_flag_does_send(
        self, heartbeat_alert, monkeypatch: pytest.MonkeyPatch
    ):
        heartbeat_alert()
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")

        call_count = 0

        def _counting_post(*a, **kw):
            nonlocal call_count
            call_count += 1
            return _fake_post_ok(*a, **kw)

        with patch("src.monitoring.alert_bridge.requests.post", _counting_post):
            bridge.main(["--send"])

        assert call_count >= 1
