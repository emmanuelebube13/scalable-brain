#!/usr/bin/env bash

# =============================================================================
# CRON JOB: Layer 3 ML Gatekeeper Retraining (Biweekly)
# =============================================================================
# Author:       Emmanuel Mbachu
# Date:         2026-04-07
# Description:  Retrains the Layer 3 ML gatekeeper and optionally promotes
#               the resulting champion artifact.
#
# Schedule:     Every Sunday at 02:00 UTC with an every-14-days guard
# Crontab:      0 2 * * 0 /bin/bash /home/emmanuel/Documents/Scalable_Brain/scalable-brain/shell/cron_layer3_retrain_biweekly.sh >> /home/emmanuel/Documents/Scalable_Brain/scalable-brain/logs/layer3_retrain_cron.log 2>&1
#
# Notes:
# - Cron has no native "every 2 weeks" syntax. This script enforces it with
#   an anchor date and day-difference modulo check.
# - Change BIWEEKLY_ANCHOR_UTC to shift which Sundays execute.
# =============================================================================

set -u

PROJECT_ROOT="/home/emmanuel/Documents/Scalable_Brain/scalable-brain"
VENV_PATH="/home/emmanuel/Documents/Scalable_Brain/.venv"
PYTHON_SCRIPT="src/layer3_ml/training/train_ml_gatekeeper.py"
LOG_DIR="${PROJECT_ROOT}/logs"
LOG_FILE="${LOG_DIR}/layer3_retrain_cron.log"

# Biweekly guard anchor in UTC; must be a date that should run.
BIWEEKLY_ANCHOR_UTC="2026-04-12"

# Layer 3 training options
SELECTION_MODE="fallback"
PROMOTE_CHAMPION="true"
MIN_TURNOVER="0.005"
MAX_TURNOVER="0.50"
MIN_EXPECTANCY="-0.05"

log() {
    local level="$1"
    local msg="$2"
    echo "[$(date -u '+%Y-%m-%d %H:%M:%S')] [$level] $msg" | tee -a "$LOG_FILE"
}

should_run_biweekly() {
    local anchor_epoch now_epoch day_delta
    anchor_epoch=$(date -u -d "$BIWEEKLY_ANCHOR_UTC" +%s 2>/dev/null || true)
    now_epoch=$(date -u +%s)

    if [ -z "$anchor_epoch" ]; then
        log "ERROR" "Invalid BIWEEKLY_ANCHOR_UTC: $BIWEEKLY_ANCHOR_UTC"
        return 2
    fi

    day_delta=$(( (now_epoch - anchor_epoch) / 86400 ))
    if [ "$day_delta" -lt 0 ]; then
        log "WARN" "Current date is before BIWEEKLY_ANCHOR_UTC; skipping run"
        return 1
    fi

    if [ $((day_delta % 14)) -eq 0 ]; then
        return 0
    fi

    return 1
}

mkdir -p "$LOG_DIR"

log "INFO" "=========================================================================="
log "INFO" "Starting Layer 3 biweekly retraining cron"
log "INFO" "Anchor date (UTC): ${BIWEEKLY_ANCHOR_UTC}"
log "INFO" "=========================================================================="

if ! should_run_biweekly; then
    rc=$?
    if [ "$rc" -eq 1 ]; then
        log "INFO" "Biweekly guard not matched today; exiting without retraining"
        exit 0
    fi

    log "ERROR" "Biweekly guard failed"
    exit "$rc"
fi

if [ ! -d "$PROJECT_ROOT" ]; then
    log "ERROR" "Project root not found: $PROJECT_ROOT"
    exit 1
fi

if [ ! -x "${VENV_PATH}/bin/python" ]; then
    log "ERROR" "Python not found in venv: ${VENV_PATH}/bin/python"
    exit 1
fi

if [ ! -f "${PROJECT_ROOT}/${PYTHON_SCRIPT}" ]; then
    log "ERROR" "Layer 3 training script not found: ${PROJECT_ROOT}/${PYTHON_SCRIPT}"
    exit 1
fi

if [ ! -f "${PROJECT_ROOT}/.env" ]; then
    log "ERROR" ".env file not found at ${PROJECT_ROOT}/.env"
    exit 1
fi

cd "$PROJECT_ROOT" || exit 1

ARGS=(
    --selection-mode "$SELECTION_MODE"
    --min-turnover "$MIN_TURNOVER"
    --max-turnover "$MAX_TURNOVER"
    --min-expectancy "$MIN_EXPECTANCY"
)

if [ "$PROMOTE_CHAMPION" = "true" ]; then
    ARGS+=(--promote-as-champion)
fi

log "INFO" "Executing: ${VENV_PATH}/bin/python ${PYTHON_SCRIPT} ${ARGS[*]}"
"${VENV_PATH}/bin/python" "$PYTHON_SCRIPT" "${ARGS[@]}" 2>&1 | tee -a "$LOG_FILE"
EXIT_CODE=${PIPESTATUS[0]}

if [ "$EXIT_CODE" -eq 0 ]; then
    log "INFO" "Layer 3 retraining completed successfully"
else
    log "ERROR" "Layer 3 retraining failed with exit code ${EXIT_CODE}"
fi

exit "$EXIT_CODE"