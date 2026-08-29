#!/usr/bin/env bash
# =============================================================================
# CRON JOB: rebuild fact_trade_outcomes
# =============================================================================
# Description:  Re-backtests every registered strategy and upserts the resulting
#               trades into fact_trade_outcomes. This is the ONLY writer of that
#               table. Before 2026-08-29 it had no caller at all: outcomes were
#               written by hand, went stale on 2026-08-16, and the regime map
#               published on 2026-08-24 was vetted against 14-day-old evidence.
#
# Schedule:     0 2 * * 2-6   (Tue-Sat 02:00 UTC)
#
#               Deliberately AFTER cron_daily_ingest_and_signals.sh (22:30 Mon-Fri,
#               which advances fact_market_prices) and BEFORE
#               cron_publish_strategy_stats.sh (05:40 daily, which reads this
#               table). Tue-Sat because it consumes the prior weekday's close.
#
#               It is a SEPARATE job, not an append to the nightly ingest script,
#               because that script also emits live signals — a slow or failing
#               backtest must never be able to delay or kill signal emission.
#
# Runtime:      ~4 min for a full 10-year rebuild of the whole registry.
#
# Reconciliation: --reconcile is NOT passed here. The upsert never deletes, so
#               strategies whose code stops loading keep their old rows forever.
#               Deleting them is destructive and owner-gated; the run reports the
#               count in results/state/outcomes_writer_state.json and the
#               heartbeat surfaces it. Run by hand with --reconcile to act on it.
# =============================================================================
set -uo pipefail

REPO="/home/emmanuel/Documents/Scalable_Brain/scalable-brain"
VENV="/home/emmanuel/Documents/Scalable_Brain/.venv"
LOCK="$REPO/results/state/persist_outcomes.lock"
LOG="$REPO/logs/persist_outcomes.log"

cd "$REPO" || exit 1
mkdir -p "$REPO/logs" "$REPO/results/state"

# A full rebuild takes minutes; a second copy would fight the first over the same
# rows. Skip rather than queue — the next slot is only a day away.
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) persist_outcomes already running; skipping" >> "$LOG"
  exit 0
fi

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] --- persist trade outcomes ---" >> "$LOG"
"$VENV/bin/python" -m src.outcomes.persist_all 2>&1 | tee -a "$LOG"
STATUS=${PIPESTATUS[0]}

if [ "$STATUS" -ne 0 ]; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) persist_outcomes exited $STATUS — fact_trade_outcomes left as it was" >> "$LOG"
fi
exit "$STATUS"
