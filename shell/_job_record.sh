#!/usr/bin/env bash
# R4.3 — shared job-run bookkeeping for the cron scripts.
#
# Source this AFTER $REPO and $VENV are set, passing the job name:
#
#     source "$REPO/shell/_job_record.sh" hourly_signals
#
# It opens a row in fact_job_runs and installs an EXIT trap that closes the row with
# `success` or `failed`. A job that never writes a completion row is reported as FAILED by
# `python -m src.monitoring.job_runs check` -- absence of a record is the alarm, which is
# the whole point: on 2026-08-24 a job simply stopped running, and nothing noticed until
# the DATA it feeds went stale twelve days later.
#
# WHY AN EXIT TRAP AND NOT `|| _finish failed`
# --------------------------------------------
# These scripts vary: some use `set -e`, cron_heartbeat_daily.sh deliberately does not
# (a non-zero heartbeat exit is a finding, not a script failure). An EXIT trap fires for
# every path out -- normal return, `set -e` abort, or an uncaught signal -- so the record
# is closed under all of them rather than only the ones someone remembered to handle.
#
# Bookkeeping must never break the job it books. Every call here is `|| true`: a run that
# happened but went unrecorded is a monitoring gap; a run that DIDN'T happen because
# monitoring failed is an outage we caused ourselves.

_JOB_NAME="${1:?_job_record.sh requires a job name}"
_JOB_STATUS="failed"

_JOB_RUN_ID="$("$VENV/bin/python" -m src.monitoring.job_runs start "$_JOB_NAME" 2>/dev/null || true)"

_job_record_finish() {
  if [ -n "${_JOB_RUN_ID:-}" ]; then
    "$VENV/bin/python" -m src.monitoring.job_runs finish "$_JOB_RUN_ID" \
      --status "$_JOB_STATUS" >/dev/null 2>&1 || true
  fi
}
trap _job_record_finish EXIT

# Call this on the last line of the script's happy path.
job_record_ok() { _JOB_STATUS="success"; }
