"""Alert bridge — the missing consumer for System-1 state detectors.

Problem
-------
The heartbeat (``monitoring/heartbeat.py``) and the signal emitter
(``signals/run.py``) both *detect* problems correctly — ``HEARTBEAT_ALERT``
was CRITICAL for 10 consecutive days during the 2026-08-24 regime stall and
nobody noticed, because nothing read those files.  A detector with no consumer
is not a control.

This module is the consumer.  It reads state files that other modules write,
evaluates alert conditions, and sends Telegram messages.  It **never writes
anything that another module reads** — it is an *observer*, not a participant.
Its own state (``alert_bridge_state.json``) is used only for dedup/recovery
tracking and is never consumed by any pipeline stage.

Design rule: the bridge may break without affecting any data path.  An
alerting failure must never look like a job failure to cron (exit 0 always).

Cite: 2026-08-24 regime stall — heartbeat CRITICAL for 10 days, unread.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from src.monitoring.freshness import open_hours_between

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths — all relative to the repo root
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parents[2]
_STATE_DIR = _ROOT / "results" / "state"
_HEARTBEAT_ALERT = _STATE_DIR / "HEARTBEAT_ALERT"
_EMITTER_STATE = _STATE_DIR / "signal_emitter_state.json"
_BRIDGE_STATE = _STATE_DIR / "alert_bridge_state.json"

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

#: Consecutive emitter faults before alerting.
EMITTER_FAULT_THRESHOLD = 3

#: Open-market hours since last signal emission before alerting.
EMITTER_STALE_HOURS = 26.0

#: Wall-clock seconds between repeat notifications for the same alert key.
DEDUP_WINDOW_SECONDS = 6 * 3600  # 6 hours


# ---------------------------------------------------------------------------
# Alert collection — pure reads, no side effects
# ---------------------------------------------------------------------------


def collect_alerts(
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Read state files and return alert dicts for active conditions.

    Each dict has ``{key, severity, message}`` where ``key`` is stable across
    runs (used for dedup) and ``severity`` is ``"warn"`` or ``"critical"``.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    alerts: list[dict[str, Any]] = []

    # --- 1. HEARTBEAT_ALERT flag file present --------------------------------
    if _HEARTBEAT_ALERT.exists():
        try:
            text = _HEARTBEAT_ALERT.read_text().strip()
        except OSError:
            text = "(unreadable)"
        alerts.append(
            {
                "key": "heartbeat_alert",
                "severity": "critical",
                "message": f"HEARTBEAT_ALERT flag present: {text}",
            }
        )

    # --- 2–3. Emitter state --------------------------------------------------
    emitter = _read_emitter_state()
    if emitter is not None:
        # 2. Consecutive faults
        faults = emitter.get("consecutive_faults", 0)
        if isinstance(faults, (int, float)) and faults >= EMITTER_FAULT_THRESHOLD:
            detail = emitter.get("last_run_fault_detail") or "(no detail)"
            alerts.append(
                {
                    "key": "emitter_faults",
                    "severity": "critical",
                    "message": (
                        f"Signal emitter: {int(faults)} consecutive faults "
                        f"(threshold {EMITTER_FAULT_THRESHOLD}). "
                        f"Last fault: {detail}"
                    ),
                }
            )

        # 3. Stale emission — open-market hours only (weekends don't fire)
        last_emitted = _parse_iso(emitter.get("last_signal_emitted_at"))
        if last_emitted is not None:
            open_hrs = open_hours_between(last_emitted, now)
            if open_hrs >= EMITTER_STALE_HOURS:
                alerts.append(
                    {
                        "key": "emitter_stale",
                        "severity": "warn",
                        "message": (
                            f"No signal emitted for {open_hrs:.1f} open-market hours "
                            f"(threshold {EMITTER_STALE_HOURS:.0f}h). "
                            f"Last emission: {last_emitted.isoformat()}"
                        ),
                    }
                )

    return alerts


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------


def send_telegram(text: str) -> bool:
    """POST to the Telegram Bot API.  Never raises.

    Returns True on success, False otherwise.  Missing env vars log one
    warning and return False — a misconfigured alert bridge must not crash.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        logger.warning(
            "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — cannot send alert"
        )
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
        if resp.status_code == 200:
            return True
        logger.warning(
            "Telegram API returned %s: %s", resp.status_code, resp.text[:200]
        )
        return False
    except Exception:
        logger.warning("Telegram send failed", exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Dedup / recovery state
# ---------------------------------------------------------------------------


def _load_bridge_state() -> dict[str, Any]:
    """Load the bridge's own dedup state.  Unreadable → empty (notify, never silence)."""
    try:
        return json.loads(_BRIDGE_STATE.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        if _BRIDGE_STATE.exists():
            logger.warning("Unreadable bridge state (%s) — degrading to notify", exc)
        return {}


def _save_bridge_state(state: dict[str, Any]) -> None:
    """Atomic write: tmp + os.replace."""
    _BRIDGE_STATE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(_BRIDGE_STATE.parent), suffix=".tmp", prefix="alert_bridge_"
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, str(_BRIDGE_STATE))
    except Exception:
        # Best-effort cleanup; don't mask the real error
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _decide_notifications(
    alerts: list[dict[str, Any]],
    state: dict[str, Any],
    now: datetime,
) -> tuple[list[str], dict[str, Any]]:
    """Return (messages_to_send, updated_state).

    Rules:
    - A new alert key → notify immediately.
    - A key still firing → re-notify only after DEDUP_WINDOW_SECONDS.
    - A key that was firing and is now absent → send one "recovered" message.
    """
    now_ts = now.timestamp()
    notified: dict[str, float] = state.get("notified", {})
    messages: list[str] = []
    new_notified: dict[str, float] = {}

    current_keys = {a["key"] for a in alerts}

    # Alerts that are firing
    for alert in alerts:
        key = alert["key"]
        last_sent = notified.get(key)
        if last_sent is None or (now_ts - last_sent) >= DEDUP_WINDOW_SECONDS:
            sev = alert["severity"].upper()
            messages.append(f"🔴 [{sev}] {alert['message']}")
            new_notified[key] = now_ts
        else:
            # Still within dedup window — carry forward the old timestamp
            new_notified[key] = last_sent

    # Keys that stopped firing → recovery
    for key, ts in notified.items():
        if key not in current_keys:
            messages.append(f"✅ recovered: {key}")
            # Do NOT carry forward into new_notified — it's resolved

    return messages, {"notified": new_notified}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    """CLI entry point.  Always exits 0 — alerting failures must not look like job failures."""
    parser = argparse.ArgumentParser(
        description="System-1 alert bridge — reads state files, sends Telegram alerts."
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Actually send Telegram messages (default is dry-run: print only).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Print alerts but do not send (this is the default).",
    )
    args = parser.parse_args(argv)

    # --send overrides --dry-run
    dry_run = not args.send

    now = datetime.now(timezone.utc)
    alerts = collect_alerts(now)
    state = _load_bridge_state()
    messages, new_state = _decide_notifications(alerts, state, now)

    if not messages:
        print(f"[{now:%Y-%m-%d %H:%M:%SZ}] No alerts to send.")
        # Still save state so recovered keys are cleared
        _save_bridge_state(new_state)
        return

    for msg in messages:
        print(msg)
        if not dry_run:
            ok = send_telegram(msg)
            if not ok:
                print(f"  ⚠ failed to send above message")

    _save_bridge_state(new_state)

    if dry_run:
        print(f"\n(dry-run mode — nothing was sent. Use --send to deliver.)")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_emitter_state() -> dict[str, Any] | None:
    try:
        return json.loads(_EMITTER_STATE.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        main()
    except Exception:
        # Exit 0 always — an alerting failure must never look like a job failure.
        logger.exception("Alert bridge crashed")
    sys.exit(0)
