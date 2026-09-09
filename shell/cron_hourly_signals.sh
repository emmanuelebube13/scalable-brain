#!/usr/bin/env bash
# Hourly: refresh prices, then emit signals. Companion to cron_daily_ingest_and_signals.sh.
#
# WHY HOURLY IS NEEDED, NOT JUST NICE
# -----------------------------------
# Two of the three live strategies are H4. H4 bars close six times a day (01, 05, 09, 13,
# 17, 21 UTC). The daily run at 22:30 can only ever act on the 21:00 bar, because the
# watcher's staleness threshold for H4 is 8h30m and every earlier bar is already past it.
# So a once-daily cron structurally discards five of every six H4 opportunities — not
# through error, but by arriving too late to be allowed to act.
#
# The staleness guard makes this self-limiting: outside market hours every granularity is
# stale, the watcher refuses, and the run is a cheap no-op. So running every hour, every
# day, needs no market-calendar logic and cannot act on old data.
#
# This does NOT make Computer 1 a dependable host — it cannot be, and ADR-001 exists to
# remove trading's dependence on it. This only stops the bridge from throwing away most of
# its own signals while that migration is built.
#
# Idempotent, like the daily run: ingest upserts on conflict, the producer keys on
# (signal_id, score_run_id). Overlapping or repeated runs re-send rather than double-send.
set -euo pipefail

REPO="/home/emmanuel/Documents/Scalable_Brain/scalable-brain"
VENV="/home/emmanuel/Documents/Scalable_Brain/.venv"

cd "$REPO"


# R4.3 -- record that this job ran, so its ABSENCE is detectable.
source "$REPO/shell/_job_record.sh" hourly_signals

# Single-flight: an hourly cadence can outrun a slow ingest, and two concurrent producers
# are exactly the double-publish hazard the cutover plan forbids. flock exits quietly if
# the previous run is still going.
exec 9>"$REPO/results/state/hourly_signals.lock"
flock -n 9 || { echo "[$(date -u +%FT%TZ)] previous hourly run still active — skipping"; exit 0; }

echo "[$(date -u +%FT%TZ)] --- hourly ingest ---"
"$VENV/bin/python" -m src.ingestion.multi_timeframe_ingest

# Bring the canonical structural label up to the newest D1 bar BEFORE the producer runs.
#
# This is deliberately a step in this script and not its own crontab line. run.py routes
# every signal on fact_regime_structural, so "the labeller failed" and "the table is
# stale" are the same condition and must produce the same refusal. Under `set -e` a
# non-zero exit here aborts the script and the producer below never starts — the coupling
# is structural rather than something a future edit can forget to check. A separate cron
# entry would leave a window where the producer runs against a table nothing refreshed.
#
# NOT `|| true`, unlike the telemetry steps at the bottom. Those report on the run; this
# one is an input to it.
#
# It is registered in job_runs.EXPECTED_INTERVAL_HOURS as `structural_labels`, so it still
# shows up in `python -m src.monitoring.job_runs check` and its absence is still an alarm.
echo "[$(date -u +%FT%TZ)] --- structural labels ---"
"$VENV/bin/python" -m src.regime.build_structural --incremental --all >/dev/null

# WALL-CLOCK BOUND on the producer, and it is load-bearing.
#
# The flock above is non-blocking: while one run holds the lock every later run exits
# immediately. That is correct for overlap, but it means a run that never FINISHES stops
# the cadence entirely rather than just delaying it. On 2026-09-09 one producer sat for
# over an hour on 2 seconds of CPU, blocked on an unacknowledged Pub/Sub publish, and
# every hourly run behind it was skipped — silently, because skipping is a normal outcome.
#
# 10 minutes is far longer than a healthy run (measured: ~15s end-to-end) and far shorter
# than an hour. Exceeding it means something is stuck, and the right response is to lose
# ONE run rather than all of them. Emission is idempotent — the producer keys on
# (signal_id, score_run_id) — so a killed run costs nothing a later one cannot redo.
#
# `|| true` because a timeout is not a script failure: the steps below still need to run
# so the state file and telemetry record what happened. The exit code is logged instead.
echo "[$(date -u +%FT%TZ)] --- hourly signal producer ---"
timeout --signal=TERM --kill-after=30s 10m "$VENV/bin/python" -m src.signals.run --once || {
  rc=$?
  if [ $rc -eq 124 ] || [ $rc -eq 137 ]; then
    echo "[$(date -u +%FT%TZ)] WARNING: producer exceeded 10m and was terminated (rc=$rc) — cadence preserved, this run abandoned"
  else
    echo "[$(date -u +%FT%TZ)] WARNING: producer exited non-zero (rc=$rc)"
  fi
}

# Health telemetry LAST, and never fatal (|| true): it reports on the run above, so a
# telemetry failure must not mark a successful ingest+emit as failed. Write-on-action --
# there is no daemon and no uptime requirement; consumers read staleness as the signal.
echo "[$(date -u +%FT%TZ)] --- publish health telemetry ---"
"$VENV/bin/python" -m src.monitoring.publish_health >/dev/null || true

# Gate-1 ledger: ship the rows the producer appended locally this run. Deliberately a
# SEPARATE process from the emit above, so a GCS outage cannot touch the emission path by
# construction rather than by exception handling. Non-fatal for the same reason as the
# other telemetry, and safe to miss: the ledger is append-only with a byte offset, so the
# next run sends whatever this one did not. --prune applies the stated 90-day local
# retention (results/README.md).
echo "[$(date -u +%FT%TZ)] --- publish signal ledger ---"
"$VENV/bin/python" -m src.signals.publish_ledger --prune >/dev/null || true

# Model card: MIRROR the card pinned inside the live model set — never recompute it here.
# The card is generated once, at publish time, and ships as an artifact of the set; this
# only re-asserts the frontend copy so a failed mirror during publish self-heals, and
# refreshes its age. Recomputing hourly would let the page drift away from the artifact it
# claims to describe, which is the exact parity failure the pinned card exists to prevent.
echo "[$(date -u +%FT%TZ)] --- mirror model card ---"
"$VENV/bin/python" -m src.monitoring.model_card --mirror >/dev/null || true

# Parity check is advisory here (non-fatal, like all telemetry in this script) but it logs
# loudly: a mismatch means the frontend is describing a different artifact than the one
# deployed.
"$VENV/bin/python" -m src.monitoring.model_card --verify >/dev/null || \
  echo "[$(date -u +%FT%TZ)] WARNING: model-card parity check FAILED"

echo "[$(date -u +%FT%TZ)] --- done ---"

job_record_ok
