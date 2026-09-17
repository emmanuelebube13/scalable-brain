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

# Owner decision 2026-09-16: the weekly retrain PUBLISHES the model set (the map expires
# every 7 days; before this, renewal required a human to run publish_model_set and a
# forgotten week silently stopped trading at Friday's expiry). Publication is still gated:
# map gates (regime_accuracy_ok, non_empty_map) must pass, and the governed writer
# (publish_model_set) does the SHA256-verified, pointer-flip-last publish.
# GATEKEEPER_AUTOPROMOTE stays UNSET on purpose — champion promotion remains gated on all
# four deployment gates and is currently blocked by O-30/O-31; the model set pairs the
# fresh bundle with the incumbent gatekeeper (`promoted_map_only`).
export MODEL_SET_AUTOPUBLISH=true

"$VENV/bin/python" -m src.scheduler.orchestrator 2>&1 \
  | tee -a "$REPO/logs/system1_retrain.log"

job_record_ok
