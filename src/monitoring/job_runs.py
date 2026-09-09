"""R4.3 — a scheduled job's success is a written record, not an absence of errors.

Why "did the table advance?" is the wrong question
--------------------------------------------------
``heartbeat.py`` checks freshness by reading ``max(timestamp)`` on the tables a job is
supposed to advance. That detects one failure mode well and is blind to the rest, because
it cannot distinguish:

* the job ran and correctly wrote nothing (a quiet market, no new bars),
* the job ran, crashed halfway, and wrote nothing,
* the job never ran at all because its cron entry was removed,
* the job ran against the wrong database and wrote nothing *here*.

All four look identical from the far end of a ``max(timestamp)``. The 2026-08-24 regime
stall was the third of those, and it took the *data* going stale to reveal that the *job*
had stopped — which is a slower and less specific signal than simply noticing the job
stopped reporting.

So every scheduled job writes a row saying it ran, when, how it ended, how much it wrote,
and from which commit. A job that has not written a completion row inside its expected
interval is **failed**, not idle. Absence of a record is itself the alarm.

Usage
-----
From Python::

    from src.monitoring.job_runs import record_job

    with record_job("ingest_prices") as run:
        n = do_the_work()
        run.rows_affected = n

From a shell script, where wrapping the whole body is awkward::

    RUN_ID=$(python -m src.monitoring.job_runs start ingest_prices)
    ...
    python -m src.monitoring.job_runs finish "$RUN_ID" --status success --rows 1234
"""

from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterator, List, Optional

from sqlalchemy import text

from src.common.db import get_engine

logger = logging.getLogger("system1.monitoring.job_runs")

TABLE = "fact_job_runs"

STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"

#: How long a job may go without a SUCCESSFUL run before it is considered failed, in
#: hours. Derived from the installed crontab (see the R4.1 inventory in the remediation
#: report), with roughly 2x headroom so a single missed run is a warning rather than an
#: immediate alarm — except where the cadence is hourly, where one missed run matters.
#:
#: A job absent from this mapping is NOT silently exempt; `stale_jobs()` reports unknown
#: job names so the mapping cannot drift out of date unnoticed.
EXPECTED_INTERVAL_HOURS: Dict[str, float] = {
    "hourly_signals": 3.0,  # cron: 15 * * * *
    # Runs INSIDE cron_hourly_signals.sh and cron_daily_ingest_and_signals.sh, between the
    # ingest and the producer, rather than from its own crontab line — the producer must
    # not run at all if labelling failed, and two separately-scheduled jobs cannot express
    # that. It is registered here so it is still discoverable as scheduled work and its
    # absence is still an alarm, without the coupling being optional.
    "structural_labels": 3.0,  # inside cron: 15 * * * *
    "daily_ingest_and_signals": 30.0,  # cron: 30 22 * * 1-5
    "oanda_ingest_saturday": 8 * 24.0,  # cron: 0 0 * * 6
    "heartbeat": 30.0,  # cron: 0 6 * * *
    "publish_strategy_stats": 30.0,  # cron: 40 5 * * *
    "persist_outcomes": 30.0,  # cron: 0 2 * * 2-6
    "system1_retrain": 3.0,  # cron: 0 * * * *
}

DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    job_run_id      BIGSERIAL PRIMARY KEY,
    job_name        TEXT        NOT NULL,
    started_at_utc  TIMESTAMPTZ NOT NULL,
    ended_at_utc    TIMESTAMPTZ,
    status          TEXT        NOT NULL,
    rows_affected   BIGINT,
    code_git_sha    TEXT,
    host            TEXT,
    detail          TEXT
);
CREATE INDEX IF NOT EXISTS ix_job_runs_name_started
    ON {TABLE} (job_name, started_at_utc DESC);
CREATE INDEX IF NOT EXISTS ix_job_runs_status
    ON {TABLE} (status, started_at_utc DESC);
COMMENT ON TABLE {TABLE} IS
  'One row per scheduled-job execution. A job with no successful row inside its expected '
  'interval is FAILED, not idle -- absence of a record is the alarm. Written by '
  'src/monitoring/job_runs.py; never hand-edited.';
"""


def ensure_table() -> None:
    with get_engine().begin() as conn:
        for stmt in DDL.strip().split(";\n"):
            if stmt.strip():
                conn.execute(text(stmt))


@dataclass
class JobRun:
    job_name: str
    job_run_id: Optional[int] = None
    rows_affected: Optional[int] = None
    detail: Optional[str] = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def _git_sha() -> Optional[str]:
    from src.vetting.map_contract import git_sha

    return git_sha()


def start(job_name: str) -> int:
    """Open a run record and return its id."""
    ensure_table()
    with get_engine().begin() as conn:
        return int(
            conn.execute(
                text(
                    f"INSERT INTO {TABLE} "
                    "(job_name, started_at_utc, status, code_git_sha, host) "
                    "VALUES (:n, :s, :st, :g, :h) RETURNING job_run_id"
                ),
                {
                    "n": job_name,
                    "s": datetime.now(timezone.utc),
                    "st": STATUS_RUNNING,
                    "g": _git_sha(),
                    "h": socket.gethostname(),
                },
            ).scalar()
        )


def finish(
    job_run_id: int,
    status: str,
    rows_affected: Optional[int] = None,
    detail: Optional[str] = None,
) -> None:
    with get_engine().begin() as conn:
        conn.execute(
            text(
                f"UPDATE {TABLE} SET ended_at_utc = :e, status = :st, "
                "rows_affected = :r, detail = :d WHERE job_run_id = :i"
            ),
            {
                "e": datetime.now(timezone.utc),
                "st": status,
                "r": rows_affected,
                "d": (detail or "")[:4000] or None,
                "i": job_run_id,
            },
        )


@contextmanager
def record_job(job_name: str) -> Iterator[JobRun]:
    """Record a job execution, marking it failed if the body raises.

    The exception is re-raised. This records what happened; it does not change it.
    """
    run = JobRun(job_name=job_name)
    try:
        run.job_run_id = start(job_name)
    except Exception as exc:  # noqa: BLE001
        # Never let bookkeeping take down the job it is bookkeeping for. A run that
        # happened but was not recorded is a monitoring gap; a run that did not happen
        # because monitoring failed is an outage we caused.
        logger.error("Could not open job-run record for %s: %s", job_name, exc)
        yield run
        return

    try:
        yield run
    except BaseException as exc:
        try:
            finish(
                run.job_run_id,
                STATUS_FAILED,
                run.rows_affected,
                f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-2000:]}",
            )
        except Exception as inner:  # noqa: BLE001
            logger.error("Could not record failure for %s: %s", job_name, inner)
        raise
    else:
        try:
            finish(run.job_run_id, STATUS_SUCCESS, run.rows_affected, run.detail)
        except Exception as inner:  # noqa: BLE001
            logger.error("Could not record success for %s: %s", job_name, inner)


@dataclass(frozen=True)
class JobStatus:
    job_name: str
    last_success: Optional[datetime]
    hours_since: Optional[float]
    expected_hours: Optional[float]
    stale: bool
    detail: str


def job_statuses(now: Optional[datetime] = None) -> List[JobStatus]:
    """Freshness of every job we expect to run, plus any job we did not expect."""
    now = now or datetime.now(timezone.utc)
    ensure_table()
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT job_name, max(started_at_utc) FROM {TABLE} "
                "WHERE status = :ok GROUP BY job_name"
            ),
            {"ok": STATUS_SUCCESS},
        ).all()
    last: Dict[str, datetime] = {r[0]: r[1] for r in rows}

    out: List[JobStatus] = []
    for name, expected in sorted(EXPECTED_INTERVAL_HOURS.items()):
        ts = last.get(name)
        if ts is None:
            out.append(
                JobStatus(
                    name,
                    None,
                    None,
                    expected,
                    True,
                    "no successful run has EVER been recorded",
                )
            )
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        hours = (now - ts).total_seconds() / 3600.0
        stale = hours > expected
        out.append(
            JobStatus(
                name,
                ts,
                hours,
                expected,
                stale,
                (
                    f"last success {ts.isoformat()} ({hours:.1f}h ago, "
                    f"expected within {expected:.0f}h)"
                ),
            )
        )

    # A job writing records under a name we do not track is reported rather than ignored:
    # an untracked job is one whose failure nobody has agreed to notice.
    for name in sorted(set(last) - set(EXPECTED_INTERVAL_HOURS)):
        out.append(
            JobStatus(
                name,
                last[name],
                None,
                None,
                False,
                "job is writing records but has no entry in EXPECTED_INTERVAL_HOURS",
            )
        )
    return out


def stale_jobs(now: Optional[datetime] = None) -> List[JobStatus]:
    return [s for s in job_statuses(now) if s.stale]


def main() -> None:
    parser = argparse.ArgumentParser(description="R4.3 scheduled-job run records")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_start = sub.add_parser("start", help="open a run record; prints the id")
    p_start.add_argument("job_name")

    p_finish = sub.add_parser("finish", help="close a run record")
    p_finish.add_argument("job_run_id", type=int)
    p_finish.add_argument(
        "--status", choices=[STATUS_SUCCESS, STATUS_FAILED], required=True
    )
    p_finish.add_argument("--rows", type=int, default=None)
    p_finish.add_argument("--detail", default=None)

    sub.add_parser("check", help="report stale jobs; exit 2 if any are stale")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.cmd == "start":
        print(start(args.job_name))
    elif args.cmd == "finish":
        finish(args.job_run_id, args.status, args.rows, args.detail)
    else:
        statuses = job_statuses()
        worst = 0
        for s in statuses:
            mark = "STALE" if s.stale else "ok   "
            print(f"{mark} {s.job_name:28s} {s.detail}")
            if s.stale:
                worst = 2
        sys.exit(worst)


if __name__ == "__main__":
    main()
