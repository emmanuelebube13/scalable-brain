#!/bin/bash
# =============================================================================
# CRON JOB: Layer 4 Live Execution Pipeline
# =============================================================================
# Author:       Emmanuel Mbachu
# Date:         2026-04-05
# Description:  Hourly execution of the Layer 4 Live Trading Pipeline.
#               
#               This script consumes upstream artifacts from Layers 1-3 and
#               performs deterministic trade execution with risk checks:
#               - Stage 1: Load live signals with full features
#               - Stage 2: Load current market regime context  
#               - Stage 3: Load Layer 3 ML gatekeeper model artifact
#               - Stage 4: Compute ATR-based risk parameters
#               - Stage 5: Evaluate correlation/portfolio exposure gate
#               - Stage 6: Execute trades via broker API
#               - Stage 7: Log execution results for audit
#
# Schedule:     Runs every hour (0 * * * *)
# Crontab:      0 * * * * /bin/bash /home/emmanuel/Documents/Scalable_Brain/scalable-brain/shell/cron_layer4_pipeline.sh >> /home/emmanuel/Documents/Scalable_Brain/scalable-brain/logs/cron_layer4.log 2>&1
# =============================================================================

# -----------------------------------------------------------------------------
# CONFIGURATION - Modify these variables as needed
# -----------------------------------------------------------------------------
PROJECT_ROOT="/home/emmanuel/Documents/Scalable_Brain/scalable-brain"
VENV_PATH="/home/emmanuel/Documents/Scalable_Brain/.venv"
PYTHON_SCRIPT="src/layer4_executor/live_pipeline.py"
LOG_DIR="${PROJECT_ROOT}/logs"
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
LOG_FILE="${LOG_DIR}/layer4_cron_${TIMESTAMP}.log"

# Pipeline execution flags (set to "true" to enable)
DRY_RUN="false"           # Set to "true" for simulation without real trades
GRANULARITY="H1"          # H1 or H4 - must match Layer 3 model training
SKIP_CORRELATION="false"  # Skip correlation check for testing
PROCESS_ALL_SIGNALS="false"  # Process all pending signals (batch mode)

# -----------------------------------------------------------------------------
# UTILITY FUNCTIONS
# -----------------------------------------------------------------------------
log_info() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $1" | tee -a "$LOG_FILE"
}

log_warn() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [WARN] $1" | tee -a "$LOG_FILE"
}

# -----------------------------------------------------------------------------
# PRE-FLIGHT CHECKS
# -----------------------------------------------------------------------------
log_info "=========================================================================="
log_info " Starting Layer 4 Live Execution Pipeline (Cron Job)"
log_info " Schedule: Every hour at minute 0"
log_info "=========================================================================="

# Check if project directory exists
if [ ! -d "$PROJECT_ROOT" ]; then
    log_error "Project root directory not found: $PROJECT_ROOT"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "$VENV_PATH" ]; then
    log_error "Virtual environment not found: $VENV_PATH"
    exit 1
fi

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Check if Python script exists
if [ ! -f "${PROJECT_ROOT}/${PYTHON_SCRIPT}" ]; then
    log_error "Layer 4 pipeline script not found: ${PROJECT_ROOT}/${PYTHON_SCRIPT}"
    exit 1
fi

# Check if .env file exists
if [ ! -f "${PROJECT_ROOT}/.env" ]; then
    log_warn ".env file not found at ${PROJECT_ROOT}/.env - pipeline may fail if env vars not set"
fi

# -----------------------------------------------------------------------------
# ACTIVATE ENVIRONMENT & RUN PIPELINE
# -----------------------------------------------------------------------------
cd "$PROJECT_ROOT" || exit 1

# Activate virtual environment
log_info "Activating virtual environment: $VENV_PATH"
# shellcheck source=/dev/null
source "${VENV_PATH}/bin/activate"

# Verify Python is available
if ! command -v python &> /dev/null; then
    log_error "Python command not found after activating virtual environment"
    exit 1
fi

log_info "Python version: $(python --version)"
log_info "Working directory: $(pwd)"

# Build command arguments
ARGS="--granularity $GRANULARITY"

if [ "$DRY_RUN" = "true" ]; then
    ARGS="$ARGS --dry-run"
    log_info "DRY RUN MODE ENABLED - No real trades will be executed"
fi

if [ "$SKIP_CORRELATION" = "true" ]; then
    ARGS="$ARGS --skip-correlation-check"
    log_warn "Correlation check is DISABLED"
fi

if [ "$PROCESS_ALL_SIGNALS" = "true" ]; then
    ARGS="$ARGS --all-signals"
    log_info "Batch mode: Processing all pending signals"
fi

# -----------------------------------------------------------------------------
# EXECUTE PIPELINE
# -----------------------------------------------------------------------------
log_info "--------------------------------------------------------------------------"
log_info "Executing: python $PYTHON_SCRIPT $ARGS"
log_info "--------------------------------------------------------------------------"

python "$PYTHON_SCRIPT" $ARGS 2>&1 | tee -a "$LOG_FILE"
EXIT_CODE=${PIPESTATUS[0]}

# -----------------------------------------------------------------------------
# POST-EXECUTION SUMMARY
# -----------------------------------------------------------------------------
log_info "--------------------------------------------------------------------------"
if [ $EXIT_CODE -eq 0 ]; then
    log_info "Layer 4 Pipeline completed successfully (Exit Code: $EXIT_CODE)"
else
    log_error "Layer 4 Pipeline FAILED (Exit Code: $EXIT_CODE)"
    log_error "Check log file for details: $LOG_FILE"
fi
log_info "Log saved to: $LOG_FILE"
log_info "=========================================================================="
log_info " Cron Job Complete - Next run in 1 hour"
log_info "=========================================================================="

# Deactivate virtual environment
deactivate

exit $EXIT_CODE
