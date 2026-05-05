#!/usr/bin/env bash

set -u

PROJECT_ROOT="/home/emmanuel/Documents/Scalable_Brain/scalable-brain"
VENV_PATH="/home/emmanuel/Documents/Scalable_Brain/.venv"
PYTHON_SCRIPT="src/layer4_executor/live_pipeline.py"
LOG_DIR="${PROJECT_ROOT}/logs"
LOG_FILE="${LOG_DIR}/layer4_cron.log"

DRY_RUN="false"
GRANULARITY="H1"
SKIP_CORRELATION="false"
PROCESS_ALL_SIGNALS="true"
ENABLE_THRESHOLD_OVERRIDE="true"
THRESHOLD_OVERRIDE="0.30"

mkdir -p "$LOG_DIR"

log() {
    local level="$1"
    local msg="$2"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$level] $msg" | tee -a "$LOG_FILE"
}

if [ ! -d "$PROJECT_ROOT" ]; then
    log "ERROR" "Project root not found: $PROJECT_ROOT"
    exit 1
fi

if [ ! -x "${VENV_PATH}/bin/python" ]; then
    log "ERROR" "Python not found in venv: ${VENV_PATH}/bin/python"
    exit 1
fi

if [ ! -f "${PROJECT_ROOT}/${PYTHON_SCRIPT}" ]; then
    log "ERROR" "Pipeline script not found: ${PROJECT_ROOT}/${PYTHON_SCRIPT}"
    exit 1
fi

cd "$PROJECT_ROOT" || exit 1

ARGS=(--granularity "$GRANULARITY")

if [ "$DRY_RUN" = "true" ]; then
    ARGS+=(--dry-run)
fi

if [ "$SKIP_CORRELATION" = "true" ]; then
    ARGS+=(--skip-correlation-check)
fi

if [ "$PROCESS_ALL_SIGNALS" = "true" ]; then
    ARGS+=(--all-signals)
fi

if [ "$ENABLE_THRESHOLD_OVERRIDE" = "true" ]; then
    ARGS+=(--enable-threshold-override --threshold-override "$THRESHOLD_OVERRIDE")
fi

log "INFO" "Starting Layer 4 cron pipeline"
log "INFO" "Executing: ${VENV_PATH}/bin/python ${PYTHON_SCRIPT} ${ARGS[*]}"

"${VENV_PATH}/bin/python" "$PYTHON_SCRIPT" "${ARGS[@]}" 2>&1 | tee -a "$LOG_FILE"
EXIT_CODE=${PIPESTATUS[0]}

if [ "$EXIT_CODE" -eq 0 ]; then
    log "INFO" "Layer 4 pipeline completed successfully"
else
    log "ERROR" "Layer 4 pipeline failed with exit code ${EXIT_CODE}"
fi

exit "$EXIT_CODE"
