#!/bin/bash
# =============================================================================
# CRON JOB: OANDA Price Data Ingestion (Saturday Midnight)
# =============================================================================
# Author:       Emmanuel Mbachu
# Date:         2026-04-06
# Description:  Weekly ingestion of OANDA candle data into Fact_Market_Prices.
#               
#               This script performs ETL from OANDA (via v20 API) into SQL Server:
#               - Ingests all assets (Dim_Asset)
#               - Supports H1, H4, D1 granularities
#               - Resume mode: continues from MAX(Timestamp) per asset/granularity
#               - Idempotent: safe to re-run without duplicates (MERGE upsert)
#               - Rate limiting with exponential backoff and jitter
#
# Schedule:     Every Saturday at midnight (00:00 UTC)
# Crontab:      0 0 * * 6 /bin/bash /home/emmanuel/Documents/Scalable_Brain/scalable-brain/shell/cron_oanda_ingest_saturday.sh >> /home/emmanuel/Documents/Scalable_Brain/scalable-brain/logs/cron_oanda_ingest.log 2>&1
#
# Expected Runtime: ~30-60 minutes for full backfill, ~5-15 minutes for incremental
# =============================================================================

# -----------------------------------------------------------------------------
# CONFIGURATION
# -----------------------------------------------------------------------------
PROJECT_ROOT="/home/emmanuel/Documents/Scalable_Brain/scalable-brain"
VENV_PATH="/home/emmanuel/Documents/Scalable_Brain/.venv"
PYTHON_SCRIPT="src/layer0/ingest_oanda_prices.py"
LOG_DIR="${PROJECT_ROOT}/logs"
LOG_FILE="${LOG_DIR}/cron_oanda_ingest.log"

# Ingest options (leave empty to process all symbols/granularities)
SYMBOL=""           # Optional: filter to single symbol (e.g., "EUR_USD")
GRANULARITY=""      # Optional: filter to single granularity (e.g., "H1", "H4", "D1")
DRY_RUN="false"     # Set to "true" to validate without committing to DB

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
log_info " Starting OANDA Price Ingestion (Saturday Midnight Cron Job)"
log_info " Schedule: Every Saturday at 00:00 UTC"
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
    log_error "Ingest script not found: ${PROJECT_ROOT}/${PYTHON_SCRIPT}"
    exit 1
fi

# Check if .env file exists
if [ ! -f "${PROJECT_ROOT}/.env" ]; then
    log_error ".env file not found at ${PROJECT_ROOT}/.env - script requires OANDA_API_KEY, DB credentials"
    exit 1
fi

# Log job details
log_info "Project root: $PROJECT_ROOT"
log_info "Virtual env: $VENV_PATH"
log_info "Script: $PYTHON_SCRIPT"
log_info "Dry run: $DRY_RUN"
[ -n "$SYMBOL" ] && log_info "Symbol filter: $SYMBOL"
[ -n "$GRANULARITY" ] && log_info "Granularity filter: $GRANULARITY"

# -----------------------------------------------------------------------------
# ACTIVATE ENVIRONMENT & RUN INGEST
# -----------------------------------------------------------------------------
cd "$PROJECT_ROOT" || exit 1

log_info "Activating virtual environment: $VENV_PATH"
# shellcheck source=/dev/null
source "${VENV_PATH}/bin/activate"

# Verify Python is available
if ! command -v python &> /dev/null; then
    log_error "Python command not found after activating virtual environment"
    exit 1
fi

# Build command with optional filters
CMD="python $PYTHON_SCRIPT"

if [ "$DRY_RUN" = "true" ]; then
    CMD="$CMD --dry-run"
fi

if [ -n "$SYMBOL" ]; then
    CMD="$CMD --symbol $SYMBOL"
fi

if [ -n "$GRANULARITY" ]; then
    CMD="$CMD --granularity $GRANULARITY"
fi

# Run the ingestion
log_info "Starting ingest..."
log_info "Command: $CMD"

if eval "$CMD" >> "$LOG_FILE" 2>&1; then
    log_info "=========================================================================="
    log_info " OANDA Ingest completed successfully"
    log_info "=========================================================================="
    exit 0
else
    EXIT_CODE=$?
    log_error "=========================================================================="
    log_error " OANDA Ingest FAILED with exit code $EXIT_CODE"
    log_error "=========================================================================="
    exit "$EXIT_CODE"
fi
