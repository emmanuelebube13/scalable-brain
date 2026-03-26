#!/bin/bash

# Scalable Brain - Weekly Retraining Pipeline
echo "================================================="
echo "Starting Scalable Brain Weekly Sync and Retrain"
echo "Time: $(date)"
echo "================================================="

# NOTE: If you are using a Python virtual environment, uncomment and update the line below:
# source /home/eem/Documents/trading_system/venv/bin/activate

# I am assuming your sync script is in a data folder, update the path if it's elsewhere:
SYNC_SCRIPT="/home/eem/Documents/trading_system/src/data_ingestion/oanda_historical_sync.py"
SIGNALS_SCRIPT="/home/eem/Documents/trading_system/src/layer2_signals/generate_signals.py"
LABELS_SCRIPT="/home/eem/Documents/trading_system/src/layer3_ml/evaluate_trades_atr.py"
TRAIN_SCRIPT="/home/eem/Documents/trading_system/src/layer3_ml/train_ml_gatekeeper.py"

echo "-> Step 1: Fetching new H1 candles from Oanda..."
python3 $SYNC_SCRIPT

echo "-> Step 2: Generating base strategy signals and features..."
python3 $SIGNALS_SCRIPT

echo "-> Step 3: Evaluating past trades to create ML labels..."
python3 $LABELS_SCRIPT

echo "-> Step 4: Retraining the ML Gatekeeper models..."
python3 $TRAIN_SCRIPT

echo "================================================="
echo "Weekly pipeline complete! Champion model saved."
echo "================================================="