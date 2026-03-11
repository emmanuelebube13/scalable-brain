import pandas as pd
from sklearn.model_selection import train_test_split
import joblib
import warnings
import sqlalchemy as sa
import urllib.parse
import os
from dotenv import load_dotenv
import matplotlib.pyplot as plt
import numpy as np
from sklearn.utils import resample

# Suppress warnings for clean output
warnings.filterwarnings('ignore')

load_dotenv()
DB_SERVER = os.getenv('DB_SERVER')
DB_USER = os.getenv('DB_USER')
DB_PASS = os.getenv('DB_PASS')
DB_NAME = 'ForexBrainDB'

# Safely encode the pyodbc string
params = urllib.parse.quote_plus(
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={DB_SERVER};"
    f"DATABASE={DB_NAME};"
    f"UID={DB_USER};"
    f"PWD={DB_PASS}"
)
engine = sa.create_engine(f"mssql+pyodbc:///?odbc_connect={params}")

print("Connected to ForexBrainDB. Fetching historical data...")

# The schema pulling our Layer 1 and Layer 2 data, now with Timestamp
query = """
SELECT 
    fmr.Timestamp,
    fmr.Regime_Label, 
    fmr.ATR_Value, 
    fmr.ADX_Value, 
    fs.Asset_ID, 
    fs.Strategy_ID, 
    fs.Signal_Value, 
    fto.Forward_Return,
    fto.Is_Winner
FROM 
    Fact_Market_Regime fmr
INNER JOIN 
    Fact_Signals fs ON fmr.Timestamp = fs.Timestamp AND fmr.Asset_ID = fs.Asset_ID
INNER JOIN 
    Fact_Trade_Outcomes fto ON fs.Timestamp = fto.Timestamp AND fs.Asset_ID = fto.Asset_ID AND fs.Strategy_ID = fto.Strategy_ID
ORDER BY 
    fs.Timestamp ASC
"""

df = pd.read_sql(query, engine, parse_dates=['Timestamp'])
df = df.dropna()

# One-hot encode categorical variables
df = pd.get_dummies(df, columns=['Regime_Label', 'Asset_ID', 'Strategy_ID'], drop_first=True)

# Time-series split. Do NOT shuffle. 
train_df, test_df = train_test_split(df, test_size=0.2, shuffle=False)
test_df = test_df.copy()

# Load the Champion Model
model_path = 'models/best_ml_gatekeeper.pkl'
model = joblib.load(model_path)
print(f"Champion Model Loaded: {type(model).__name__}")

# Drop columns not used for prediction
X_test = test_df.drop(['Is_Winner', 'Forward_Return', 'Timestamp'], axis=1)

# Extract PROBABILITY scores
y_prob = model.predict_proba(X_test)[:, 1]  

# Normalize Realized_Return by ATR for risk-adjusted units
test_df['Realized_Return'] = test_df['Forward_Return'] / test_df['ATR_Value']

# --- Baseline Metrics (calculated once) ---
total_baseline = len(test_df)
baseline_win_rate = test_df['Is_Winner'].mean() * 100
baseline_avg_win = test_df[test_df['Is_Winner'] == 1]['Realized_Return'].mean()
baseline_avg_loss = test_df[test_df['Is_Winner'] == 0]['Realized_Return'].mean()

print("\n**Baseline (Blind 1:3 ATR Trading)**")
print(f"  Total Trades:       {total_baseline:,}")
print(f"  Win Rate:           {baseline_win_rate:.2f}%")
print(f"  Average Win:        {baseline_avg_win:.5f}")
print(f"  Average Loss:       {baseline_avg_loss:.5f}\n")

# Define thresholds to loop over (finer grid around promising area)
thresholds = [0.45, 0.50, 0.51, 0.52, 0.525, 0.53, 0.535, 0.54, 0.545, 0.55]
results = []

# Define slippage/spread cost per trade (adjust as needed, e.g., 0.0002 for typical FX spread)
trade_cost = 0.0005

print("Evaluating across thresholds...")

for threshold in thresholds:
    print(f"\nProcessing threshold: {threshold*100}%")
    
    y_pred = (y_prob >= threshold).astype(int)
    test_df['AI_Approval'] = y_pred
    
    # --- AI Metrics ---
    ai_approved_df = test_df[test_df['AI_Approval'] == 1].copy()
    total_ai = len(ai_approved_df)
    
    if total_ai == 0:
        print("  No trades approved at this threshold. Skipping detailed metrics.")
        results.append({
            'Threshold': threshold,
            'Total_Approved': 0,
            'Avg_Trades_Week': 0,
            'Win_Rate': 0,
            'Win_Rate_CI_Low': 0,
            'Win_Rate_CI_High': 0,
            'Avg_Win': 0,
            'Avg_Loss': 0,
            'RR_Ratio': 0,
            'Expectancy': 0,
            'Total_Return': 0
        })
        continue
    
    ai_win_rate = ai_approved_df['Is_Winner'].mean() * 100
    ai_avg_win = ai_approved_df[ai_approved_df['Is_Winner'] == 1]['Realized_Return'].mean() if (ai_approved_df['Is_Winner'] == 1).any() else 0
    ai_avg_loss = ai_approved_df[ai_approved_df['Is_Winner'] == 0]['Realized_Return'].mean() if (ai_approved_df['Is_Winner'] == 0).any() else 0
    
    # Bootstrap for Win Rate CI (95%)
    if total_ai > 1:
        bootstraps = [resample(ai_approved_df)['Is_Winner'].mean() * 100 for _ in range(1000)]
        win_rate_ci_low, win_rate_ci_high = np.percentile(bootstraps, [2.5, 97.5])
    else:
        win_rate_ci_low, win_rate_ci_high = ai_win_rate, ai_win_rate  # No CI for tiny samples
    
    rr_ratio = abs(ai_avg_win / ai_avg_loss) if ai_avg_loss != 0 else 0
    
    # Expectancy with costs
    expectancy = ((ai_win_rate / 100) * ai_avg_win) - ((1 - (ai_win_rate / 100)) * abs(ai_avg_loss)) - trade_cost
    
    total_return = ai_approved_df['Realized_Return'].sum()
    
    # Trade Frequency Metrics
    ai_approved_df.set_index('Timestamp', inplace=True)
    trades_per_week = ai_approved_df.resample('W').size().mean()
    
    results.append({
        'Threshold': threshold,
        'Total_Approved': total_ai,
        'Avg_Trades_Week': trades_per_week,
        'Win_Rate': ai_win_rate,
        'Win_Rate_CI_Low': win_rate_ci_low,
        'Win_Rate_CI_High': win_rate_ci_high,
        'Avg_Win': ai_avg_win,
        'Avg_Loss': ai_avg_loss,
        'RR_Ratio': rr_ratio,
        'Expectancy': expectancy,
        'Total_Return': total_return
    })
    
    # Highlight if meets criteria
    if trades_per_week > 1 and expectancy > 0:
        print("  **MEETS TARGET: >1 trade/week and positive expectancy!**")

# Convert results to DataFrame for summary and plotting
results_df = pd.DataFrame(results)
print("\n======================================================================")
print("Threshold Evaluation Summary")
print("======================================================================")
print(results_df.to_string(index=False))
print("======================================================================")

# Plot Trade-Off Curves
if not results_df.empty:
    plt.figure(figsize=(12, 6))
    
    # Plot 1: Win Rate vs. Avg Trades/Week
    plt.subplot(1, 2, 1)
    plt.plot(results_df['Avg_Trades_Week'], results_df['Win_Rate'], marker='o', linestyle='-', color='b')
    plt.title('Win Rate vs. Avg Trades/Week')
    plt.xlabel('Avg Trades/Week')
    plt.ylabel('Win Rate (%)')
    plt.grid(True)
    for i, thresh in enumerate(results_df['Threshold']):
        plt.annotate(f"{thresh*100}%", (results_df['Avg_Trades_Week'][i], results_df['Win_Rate'][i]))
    
    # Plot 2: Expectancy/Trade vs. Avg Trades/Week
    plt.subplot(1, 2, 2)
    plt.plot(results_df['Avg_Trades_Week'], results_df['Expectancy'], marker='o', linestyle='-', color='g')
    plt.title('Expectancy/Trade vs. Avg Trades/Week')
    plt.xlabel('Avg Trades/Week')
    plt.ylabel('Expectancy/Trade')
    plt.grid(True)
    for i, thresh in enumerate(results_df['Threshold']):
        plt.annotate(f"{thresh*100}%", (results_df['Avg_Trades_Week'][i], results_df['Expectancy'][i]))
    
    plt.tight_layout()
    plot_path = 'models/threshold_tradeoff_curves_2.png'
    plt.savefig(plot_path)
    plt.show()  # Show if running interactively
    print(f"Trade-off curves saved to {plot_path}")
else:
    print("No data to plot.")