#!/usr/bin/env bash
# D6 — publish risk/strategy_stats for System 3 (daily, 05:40 UTC).
# Crontab (UTC):  40 5 * * *  /bin/bash /home/emmanuel/Documents/Scalable_Brain/scalable-brain/shell/cron_publish_strategy_stats.sh
#
# System 3 sizes positions from this document. Before 2026-08-28 nothing regenerated it
# on any schedule, so it sat at the 2026-08-17 build for eleven days while System 3 kept
# sizing against it. That staleness is the whole reason this script exists.
#
# Runs at 05:40, twenty minutes ahead of the 06:00 heartbeat, so a failure here shows up
# in the same morning's heartbeat rather than a day later.
#
# The publisher is fail-closed by construction (src/analytics/publish_strategy_stats.py):
# it stages to an immutable versioned key, round-trip verifies the SHA256, and only then
# flips latest.json. On any mismatch it deletes the partial version and leaves the live
# document byte-for-byte untouched — so a bad run degrades to "yesterday's stats", never
# to a corrupt or empty risk document.
#
# NOTE: `set -e` is deliberately NOT used — a non-zero exit must still be logged.
set -uo pipefail

REPO="/home/emmanuel/Documents/Scalable_Brain/scalable-brain"
VENV="/home/emmanuel/Documents/Scalable_Brain/.venv"
LOCK="$REPO/results/state/strategy_stats.lock"
LOG="$REPO/logs/strategy_stats.log"
cd "$REPO"

# Single-flight: the regime tagging walks every instrument's full D1 history, so a slow
# run must not overlap the next day's.
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) strategy stats already running; skipping" >> "$LOG"
  exit 0
fi

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] --- publish strategy stats ---" >> "$LOG"
"$VENV/bin/python" -m src.analytics.publish_strategy_stats 2>&1 | tee -a "$LOG"
STATUS=${PIPESTATUS[0]}

if [ "$STATUS" -ne 0 ]; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) strategy stats publish exited $STATUS — live document left untouched" >> "$LOG"
fi

exit "$STATUS"
