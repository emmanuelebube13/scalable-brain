#!/usr/bin/env bash
# Daily: refresh prices, then emit signals. Runs after the 21:00 UTC daily close.
#
# WHY BOTH IN ONE SCRIPT, IN THIS ORDER
# -------------------------------------
# Signals are computed from the newest CLOSED bar. If prices are stale the watcher
# correctly refuses to act, and the run emits nothing — silently, because "no new bars"
# and "nothing to trade" look identical from the outside. Ingest must therefore succeed
# before signals are attempted, and a failed ingest must stop the run rather than let it
# proceed on old data.
#
# Until 2026-08-17 the only price ingest was WEEKLY (Saturday 00:00). The live strategy
# (nnfx_backtrader, id 36) is a D1 strategy that needs a fresh daily bar every day, so a
# weekly refresh left it with data up to six days old and it would never have fired.
#
# System 1 is not always-on: this machine's network drops without warning. Both stages are
# idempotent — ingest upserts on conflict, and the producer keys on
# (signal_id, score_run_id) — so re-running after a failure re-sends rather than
# double-sends. A missed day is a missed trade, not a corrupted state.
set -euo pipefail

REPO="/home/emmanuel/Documents/Scalable_Brain/scalable-brain"
VENV="/home/emmanuel/Documents/Scalable_Brain/.venv"

cd "$REPO"
# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "[$(date -u +%FT%TZ)] --- price ingest ---"
python src/layer0/ingest_data/ingest_oanda_prices.py

echo "[$(date -u +%FT%TZ)] --- signal producer ---"
python -m src.signals.run --once

echo "[$(date -u +%FT%TZ)] --- done ---"
