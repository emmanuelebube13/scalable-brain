"""Publish System 1's health to the telemetry bucket, so its silence is visible.

Why this exists
---------------
The telemetry dashboard reports Systems 2 and 3 in detail and says nothing about System 1.
That gap is not cosmetic: it is why the signal producer sat broken for weeks (FIX-S1-016).
Every indicator anyone could see was green, because nobody was looking at the system that
had gone quiet.

Design: write-on-action, not heartbeat
--------------------------------------
System 1 is an offline factory on a host with unreliable networking, and ADR-001 exists to
keep trading from depending on it. So this must NOT introduce an uptime requirement.

It doesn't. There is no daemon and no periodic ping. This runs as the last step of work
System 1 already does — the hourly cron — and writes one small object. Consumers read it
and compute age themselves, exactly as they already do for the model bundle.

The consequence is the important part: **when System 1 is off, the object simply gets
older, and "last successful run: 3 days ago" is the correct answer rather than a gap.**
Absence becomes a reading instead of a blind spot. A push heartbeat would do the opposite —
it would go dark on the very failure it is meant to report, leaving a consumer unable to
tell "System 1 is off" from "telemetry is broken".

Outcomes, not liveness
----------------------
A heartbeat would have been **green throughout the FIX-S1-016 outage**. The cron fired. The
process started and exited cleanly. It just never emitted a signal, because a status check
could never pass.

So the load-bearing field here is ``last_signal_emitted_at``. Null, or hours old, while
``last_run_at`` advances every hour, is precisely that failure — and it is a state a
liveness probe cannot express. Everything else is context for it.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("system1.monitoring.publish_health")

#: Read by the dashboard alongside ``telemetry/s1_analytics.json``. A distinct object, not
#: a section of ``telemetry/latest.json`` — that file is written by System 2's publisher on
#: another host, and two writers on one key is the stale-pointer failure all over again.
TELEMETRY_KEY = "telemetry/s1_health.json"

SCHEMA_VERSION = 1


def _age_seconds(ts: Optional[str], now: datetime) -> Optional[float]:
    """Age of an ISO-8601 timestamp in seconds, or None if absent/unparseable."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (now - dt).total_seconds()
    except Exception:
        return None


def _read_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as fh:
            result: Dict[str, Any] = json.load(fh)
            return result
    except Exception:
        return {}


def collect(now: Optional[datetime] = None) -> Dict[str, Any]:
    """Assemble the health payload. Pure read — never mutates state, never raises."""
    now = now or datetime.now(timezone.utc)
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    emitter = _read_json(
        os.path.join(repo, "results", "state", "signal_emitter_state.json")
    )
    heartbeat = _read_json(
        os.path.join(repo, "results", "state", "heartbeat_latest.json")
    )
    retrain = _read_json(os.path.join(repo, "results", "state", "retrain_state.json"))

    # The published model set, read from the BACKEND — what a consumer actually downloads,
    # not whatever the local copy happens to say (CLAUDE.md: the backend is authoritative).
    model_set: Dict[str, Any] = {}
    try:
        from src.common.storage import build_storage
        from src.serializer.publish_model_set import POINTER_KEY

        storage = build_storage()
        if storage.exists(POINTER_KEY):
            with tempfile.TemporaryDirectory() as td:
                p = os.path.join(td, "m.json")
                storage.get_object(POINTER_KEY, p)
                m = _read_json(p)
            model_set = {
                "model_set_id": m.get("model_set_id"),
                "status": m.get("status"),
                "published_at": m.get("published_at"),
                "age_sec": _age_seconds(m.get("published_at"), now),
                "code_commit": m.get("code_commit"),
                "code_dirty": m.get("code_dirty"),
                "artifact_count": len(m.get("artifacts") or []),
            }
    except Exception as e:  # a bucket read must never break the publish
        model_set = {"error": f"{type(e).__name__}: {str(e)[:120]}"}

    last_emit = emitter.get("last_signal_emitted_at")
    last_run = emitter.get("last_run_at")

    return {
        "schema_version": SCHEMA_VERSION,
        "as_of": now.isoformat().replace("+00:00", "Z"),
        "system": "system1",
        # Deliberately first: this is the field that was silently null for weeks while
        # everything else looked healthy.
        "emitter": {
            "enabled": emitter.get("emitter_enabled"),
            "last_run_at": last_run,
            "last_run_age_sec": _age_seconds(last_run, now),
            "last_run_outcome": emitter.get("last_run_outcome"),
            # Both of these were promised to Systems 2 and 3 in
            # TO-SYSTEM2-3-2026-08-28-stamping-disabled-erratum.md §6 — "read
            # consecutive_faults and last_healthy_run_at, not last_run_outcome alone" —
            # while this payload carried neither. The advice was un-actionable from the
            # outside: a single blip and a real outage looked identical in the only file
            # they can see. They are the whole point of that distinction, so they are
            # published.
            "consecutive_faults": emitter.get("consecutive_faults"),
            "last_healthy_run_at": emitter.get("last_healthy_run_at"),
            "last_signal_emitted_at": last_emit,
            "last_signal_age_sec": _age_seconds(last_emit, now),
            "signals_published_total": emitter.get("signals_published_total"),
            "last_run_signals_built": emitter.get("last_run_signals_built"),
            "never_emitted": last_emit is None,
        },
        "model_set": model_set,
        "retrain": {
            "last_run_utc": retrain.get("last_run_utc"),
            "last_decision": retrain.get("last_decision"),
            "last_bundle": retrain.get("last_bundle"),
            "age_sec": _age_seconds(retrain.get("last_run_utc"), now),
        },
        "freshness_checks": {
            "evaluated_at_utc": heartbeat.get("evaluated_at_utc"),
            "age_sec": _age_seconds(heartbeat.get("evaluated_at_utc"), now),
            "overall_status": heartbeat.get("overall_status"),
            "failing": [
                {
                    "name": c.get("name"),
                    "status": c.get("status"),
                    "detail": c.get("detail"),
                }
                for c in (heartbeat.get("checks") or [])
                if c.get("status") not in (None, "OK")
            ],
        },
        # Stated so a reader is not misled into treating this as a liveness probe.
        "semantics": (
            "write-on-action, not heartbeat: this object is refreshed when System 1 runs. "
            "A growing as_of age means System 1 has not run, which is a valid and expected "
            "state for an offline factory — read staleness as the signal, not as an outage "
            "of telemetry itself."
        ),
    }


def publish(dry_run: bool = False) -> Dict[str, Any]:
    """Collect and upload. Returns the payload; never raises into the caller's run."""
    payload = collect()
    if dry_run:
        return payload
    try:
        from src.common.storage import build_storage

        storage = build_storage()
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "s1_health.json")
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
            # Fixed key, and both backends refuse to overwrite, so replace explicitly.
            if storage.exists(TELEMETRY_KEY):
                storage.delete_prefix(TELEMETRY_KEY)
            storage.put_object(TELEMETRY_KEY, p)
        logger.info(
            "published %s | last_signal_age=%s outcome=%s",
            TELEMETRY_KEY,
            payload["emitter"]["last_signal_age_sec"],
            payload["emitter"]["last_run_outcome"],
        )
    except Exception as e:
        # Telemetry failing must never fail the run that produced it.
        logger.warning("Could not publish health telemetry: %s", e)
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="Print without uploading")
    args = ap.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    print(json.dumps(publish(dry_run=args.dry_run), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
