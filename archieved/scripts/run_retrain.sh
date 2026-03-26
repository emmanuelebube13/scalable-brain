#!/bin/bash
# ===========================================================================
# run_retrain.sh - Scalable Brain CT Pipeline Wrapper
# ===========================================================================
# Activates the quant_env virtual environment, runs the Python retraining
# orchestrator, and catches fatal exit codes for cron/systemd visibility.
#
# Usage:
#   Manual:  bash scripts/run_retrain.sh
#   Cron:    0 2 * * 0  /home/eem/Documents/trading_system/scripts/run_retrain.sh >> /home/eem/Documents/trading_system/scripts/retrain_cron.log 2>&1
# ===========================================================================

set -euo pipefail

PROJECT_ROOT="/home/eem/Documents/trading_system"
VENV_PATH="${PROJECT_ROOT}/quant_env/bin/activate"
ORCHESTRATOR="${PROJECT_ROOT}/scripts/retrain_orchestrator.py"
LOG_FILE="${PROJECT_ROOT}/scripts/retrain_cron.log"

echo "========================================================="
echo " Scalable Brain - Continuous Training Pipeline"
echo " Started: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================================="

# Activate virtual environment
if [ -f "$VENV_PATH" ]; then
    source "$VENV_PATH"
    echo "[OK] Virtual environment activated: quant_env"
else
    echo "[ERROR] Virtual environment not found at: $VENV_PATH"
    echo "        Create it with: python3 -m venv ${PROJECT_ROOT}/quant_env"
    exit 1
fi

# Run the orchestrator
python3 "$ORCHESTRATOR"
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "========================================================="
    echo "[FATAL] Orchestrator exited with code $EXIT_CODE"
    echo " Check logs: ${PROJECT_ROOT}/logs/retrain_orchestrator.log"
    echo "========================================================="
    exit $EXIT_CODE
fi

echo "========================================================="
echo " Pipeline finished successfully: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================================="
exit 0
