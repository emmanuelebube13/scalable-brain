"""MODEL-001 — lineage manifest, DQ/gap report, and resumable cursor state.

All writes are atomic (write-temp + ``os.replace``) so a reader never sees a partial
file and an interrupted run leaves valid state. Paths follow orchestration/FOLDER_STRUCTURE.md:

  * ``results/state/ingest_progress.json``           — resumable cursors (per instrument/granularity)
  * ``results/reports/ingest_manifest_{ts}.json``    — per-run lineage manifest
  * ``results/reports/dq_gap_report_{ts}.json``      — per-run DQ + gap report
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Repo root = three levels up from this file (src/system1/ingestion/reports.py)
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
STATE_DIR = os.path.join(_REPO_ROOT, "results", "state")
REPORTS_DIR = os.path.join(_REPO_ROOT, "results", "reports")
INGEST_PROGRESS = os.path.join(STATE_DIR, "ingest_progress.json")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ts_compact(dt: Optional[datetime] = None) -> str:
    return (dt or _utc_now()).strftime("%Y%m%dT%H%M%SZ")


def _atomic_write_json(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    os.replace(tmp, path)


# --------------------------------------------------------------------------- #
# Resumable cursor state
# --------------------------------------------------------------------------- #
def load_progress() -> Dict[str, Any]:
    if not os.path.exists(INGEST_PROGRESS):
        return {"instruments": {}}
    with open(INGEST_PROGRESS, encoding="utf-8") as f:
        return json.load(f)


def update_cursor(
    instrument: str,
    granularity: str,
    last_bar_utc: Optional[datetime],
    backfill_complete: bool,
    history_start_override: Optional[str] = None,
) -> None:
    """Persist the resume cursor for one (instrument, granularity)."""
    state = load_progress()
    inst = state.setdefault("instruments", {}).setdefault(instrument, {})
    entry: Dict[str, Any] = {
        "last_bar_utc": last_bar_utc.isoformat() if last_bar_utc else None,
        "backfill_complete": backfill_complete,
        "updated_at_utc": _utc_now().isoformat(),
    }
    if history_start_override:
        entry["history_start_override"] = history_start_override
    inst[granularity] = entry
    _atomic_write_json(INGEST_PROGRESS, state)


# --------------------------------------------------------------------------- #
# Per-run reports
# --------------------------------------------------------------------------- #
def write_manifest(manifest: Dict[str, Any], ts: Optional[datetime] = None) -> str:
    """Write results/reports/ingest_manifest_{ts}.json. Returns the path."""
    path = os.path.join(REPORTS_DIR, f"ingest_manifest_{_ts_compact(ts)}.json")
    _atomic_write_json(path, manifest)
    return path


def write_dq_gap_report(report: Dict[str, Any], ts: Optional[datetime] = None) -> str:
    """Write results/reports/dq_gap_report_{ts}.json. Returns the path."""
    path = os.path.join(REPORTS_DIR, f"dq_gap_report_{_ts_compact(ts)}.json")
    _atomic_write_json(report_path := path, report)
    return report_path
