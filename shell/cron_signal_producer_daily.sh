#!/usr/bin/env bash
# Emit scored signals once, after the daily close. Installed via crontab.
#
# WHY ONCE A DAY AND NOT A LOOP
# -----------------------------
# `signals/run.py` defaults to a 60-second forever-loop, which assumes System 1 is
# always on. It is not: this machine's network drops without warning, and the design
# is that System 1 wakes, publishes to the cloud, and goes quiet. The live strategy
# (nnfx_backtrader, id 36) is a D1 strategy — it makes at most one decision per pair
# per day, at the daily close. A loop would perform 1,440 checks to catch one event.
#
# The producer is idempotent on (signal_id, score_run_id), so a retry after a network
# failure cannot double-emit. That is what makes a flaky connection survivable: if
# this run fails, the next one re-sends rather than skipping.
set -euo pipefail

REPO="/home/emmanuel/Documents/Scalable_Brain/scalable-brain"
VENV="/home/emmanuel/Documents/Scalable_Brain/.venv"

cd "$REPO"
# shellcheck disable=SC1091
source "$VENV/bin/activate"

exec python -m src.signals.run --once
