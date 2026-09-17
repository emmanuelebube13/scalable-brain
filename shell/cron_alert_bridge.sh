#!/usr/bin/env bash
# Alert bridge — reads System-1 state files and sends Telegram notifications.
#
# Proposed crontab line (this machine runs in America/Halifax local time,
# which is UTC-3 in winter / UTC-4 in summer; there is no CRON_TZ support):
#
#   */30 * * * *  /bin/bash /home/emmanuel/Documents/Scalable_Brain/scalable-brain/shell/cron_alert_bridge.sh
#
# NOTE: the crontab line above uses local time. UTC-offset times like "every
# 30 minutes" are invariant across timezones so no manual adjustment is needed,
# but any future change to a fixed-hour schedule must account for Halifax time.
#
# The bridge is an OBSERVER: it reads state files written by the heartbeat and
# the signal emitter, and sends notifications. It never writes anything that
# another pipeline module reads.

set -uo pipefail

REPO="/home/emmanuel/Documents/Scalable_Brain/scalable-brain"
VENV="/home/emmanuel/Documents/Scalable_Brain/.venv"
LOCK="$REPO/results/state/alert_bridge.lock"
cd "$REPO"

# R4.3 -- record that this job ran, so its ABSENCE is detectable.
source "$REPO/shell/_job_record.sh" alert_bridge

# Single-flight: don't stack up runs.
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) alert_bridge already running; skipping" \
    >> "$REPO/logs/alert_bridge.log"
  exit 0
fi

"$VENV/bin/python" -m src.monitoring.alert_bridge --send 2>&1 \
  | tee -a "$REPO/logs/alert_bridge.log"

job_record_ok
