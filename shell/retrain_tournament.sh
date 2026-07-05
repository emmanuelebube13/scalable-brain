#!/bin/bash
# =============================================================================
# retrain_tournament.sh — FIX-S1-009
#
# Retraining/promotion is governed by the System-1 orchestrator ONLY
# (triggers -> gated pipeline -> atomic promote). The previous version of
# this script invoked the retired legacy layer3_ml pipeline from a
# non-existent path; it must never write models/champion_* again.
# =============================================================================
set -euo pipefail

cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain
source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate

python -m src.system1.scheduler.orchestrator
