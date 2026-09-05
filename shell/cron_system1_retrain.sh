#!/usr/bin/env bash
# MODEL-009 — System 1 weekly retrain (Sunday 00:00 UTC).
# Crontab (UTC):  0 0 * * 0  /bin/bash /home/emmanuel/Documents/Scalable_Brain/scalable-brain/shell/cron_system1_retrain.sh
#
# Performance-triggered runs use the same orchestrator on a frequent poll (e.g. hourly):
#   0 * * * *  ... orchestrator (it evaluates triggers + cooldown and no-ops when not needed)
set -euo pipefail

REPO="/home/emmanuel/Documents/Scalable_Brain/scalable-brain"
VENV="/home/emmanuel/Documents/Scalable_Brain/.venv"
cd "$REPO"


# R4.3 -- record that this job ran, so its ABSENCE is detectable.
source "$REPO/shell/_job_record.sh" system1_retrain

"$VENV/bin/python" -m src.scheduler.orchestrator 2>&1 \
  | tee -a "$REPO/logs/system1_retrain.log"

job_record_ok
