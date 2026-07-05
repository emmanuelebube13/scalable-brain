#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
PYTHON_SCRIPT="${PROJECT_ROOT}/src/layer0/ingest_data/ingest_oanda_prices.py"

echo "Starting OANDA Ingestion Loop..."

while true; do
    # Run your python script
    python3 "$PYTHON_SCRIPT"
    
    # Capture the exit code of the Python script
    EXIT_CODE=$?
    
    # The Python script returns 0 only if everything succeeded perfectly
    if [ $EXIT_CODE -eq 0 ]; then
        echo "Ingestion completed successfully! Exiting loop."
        break
    fi
    
    # If it failed (rate limit, network drop), wait 60 seconds and loop again
    echo "Script exited with code $EXIT_CODE. Likely rate limited. Waiting 60 seconds before restarting..."
    sleep 60
done