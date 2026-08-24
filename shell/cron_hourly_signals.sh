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

# Single-flight: an hourly cadence can outrun a slow ingest, and two concurrent producers
# are exactly the double-publish hazard the cutover plan forbids. flock exits quietly if
# the previous run is still going.
exec 9>"$REPO/results/state/hourly_signals.lock"
flock -n 9 || { echo "[$(date -u +%FT%TZ)] previous hourly run still active — skipping"; exit 0; }

echo "[$(date -u +%FT%TZ)] --- hourly ingest ---"
"$VENV/bin/python" -m src.ingestion.multi_timeframe_ingest

echo "[$(date -u +%FT%TZ)] --- hourly signal producer ---"
"$VENV/bin/python" -m src.signals.run --once

# Health telemetry LAST, and never fatal (|| true): it reports on the run above, so a
# telemetry failure must not mark a successful ingest+emit as failed. Write-on-action --
# there is no daemon and no uptime requirement; consumers read staleness as the signal.
echo "[$(date -u +%FT%TZ)] --- publish health telemetry ---"
"$VENV/bin/python" -m src.monitoring.publish_health >/dev/null || true

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
