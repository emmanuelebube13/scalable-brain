#!/usr/bin/env bash
# T4 — daily System-1 freshness heartbeat (06:00 UTC).
# Crontab (UTC):  0 6 * * *  /bin/bash /home/emmanuel/Documents/Scalable_Brain/scalable-brain/shell/cron_heartbeat_daily.sh
#
# Asserts freshness of prices, trade outcomes, regimes, the champion bundle,
# telemetry, retrain state, cron liveness, and the critical import chain.
# Holds are declared in results/state/cron_holds.json.
#
# Exit codes: 0 = all fresh · 1 = warnings · 2 = critical/blocked.
# On non-zero the run leaves results/state/HEARTBEAT_ALERT behind and appends to
# logs/heartbeat_alerts.log. That flag file is the signal — check for it.
#
# NOTE: `set -e` is deliberately NOT used. A non-zero exit is the heartbeat
# reporting a problem, not the script failing, and it must still be logged.
set -uo pipefail

REPO="/home/emmanuel/Documents/Scalable_Brain/scalable-brain"
VENV="/home/emmanuel/Documents/Scalable_Brain/.venv"
LOCK="$REPO/results/state/heartbeat.lock"
cd "$REPO"

# Single-flight: a hung run must not stack up daily.
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) heartbeat already running; skipping" \
    >> "$REPO/logs/heartbeat.log"
  exit 0
fi

"$VENV/bin/python" -m src.system1.monitoring.heartbeat 2>&1 \
  | tee -a "$REPO/logs/heartbeat.log"
STATUS=${PIPESTATUS[0]}

if [ "$STATUS" -ne 0 ]; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) heartbeat exited $STATUS — see results/state/HEARTBEAT_ALERT" \
    >> "$REPO/logs/heartbeat.log"
fi

exit "$STATUS"
