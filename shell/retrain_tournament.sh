#!/bin/bash
# =============================================================================
# Author:       Emmanuel Mbachu
# Date:         2026-03-21
# Description:  ICE 4 & 5 - ML Model Automation Package.
#               Executes the full algorithm tournament (XGBoost vs LightGBM vs 
#               Random Forest vs LSTM), selects the champion, saves the .pkl,
#               and logs the final tournament results.
# =============================================================================

echo "========================================================"
echo " Starting Scalable Brain ML Tournament & Retraining..."
echo "========================================================"

# 1. Navigate to the project directory
cd /home/eem/Documents/trading_system

# 2. Activate the quantitative virtual environment
source quant_env/bin/activate

# 3. Ensure the logs directory exists
mkdir -p logs

# 4. Run the full tournament script and pipe the output to the required text file
python src/layer3_ml/train_ml_gatekeeper.py | tee logs/model_performance_results.txt

echo "========================================================"
echo " Package execution complete."
echo " Champion model saved to: models/best_ml_gatekeeper.pkl"
echo " Tournament results saved to: logs/model_performance_results.txt"
echo "========================================================"
