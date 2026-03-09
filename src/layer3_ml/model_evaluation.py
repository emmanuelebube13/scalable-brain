import pyodbc
from dotenv import load_dotenv
import os
import pandas as pd
from sklearn.model_selection import train_test_split
import joblib
import warnings
import sqlalchemy as sa
import urllib.parse

# Suppress warnings for clean output
warnings.filterwarnings('ignore')

# Load environment variables
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

print("Connected to ForexBrainDB successfully.")

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

print("Fetching historical data from database...")
df = pd.read_sql(query, engine, parse_dates=['Timestamp'])

# Data Preprocessing
df = df.dropna()

# One-hot encode categorical variables
df = pd.get_dummies(df, columns=['Regime_Label', 'Asset_ID', 'Strategy_ID'], drop_first=True)

# Time-series split. Do NOT shuffle. 
train_df, test_df = train_test_split(df, test_size=0.2, shuffle=False)

# FIX: Create a clean copy in memory to prevent pandas warnings
test_df = test_df.copy()

# Load the trained model
model_path = 'models/xgboost_gatekeeper.pkl'
model = joblib.load(model_path)
print("Trained XGBoost model loaded successfully.")

# FIX: Drop Timestamp from X_test so the AI doesn't crash!
X_test = test_df.drop(['Is_Winner', 'Forward_Return', 'Timestamp'], axis=1)

# Extract PROBABILITY scores instead of flat predictions
y_prob = model.predict_proba(X_test)[:, 1]  

# ---------------------------------------------------------
# THE CTO RUTHLESSNESS THRESHOLD
# 0.50 = 50% sure (Coin flip)
# 0.60 = 60% sure (We demand higher confidence)
# ---------------------------------------------------------
approval_threshold = 0.60
y_pred = (y_prob >= approval_threshold).astype(int)

# 3. Business Metric Calculation (The CFO Math)
print("\nCalculating metrics...")

# Shorts reverse the sign
test_df['Realized_Return'] = test_df['Forward_Return'] * test_df['Signal_Value']
test_df['AI_Approval'] = y_pred

# --- Baseline Metrics ---
total_baseline = len(test_df)
baseline_win_rate = test_df['Is_Winner'].mean() * 100
baseline_avg_win = test_df[test_df['Is_Winner'] == 1]['Realized_Return'].mean()
baseline_avg_loss = test_df[test_df['Is_Winner'] == 0]['Realized_Return'].mean()

# --- AI Metrics ---
ai_approved_df = test_df[test_df['AI_Approval'] == 1].copy()
total_ai = len(ai_approved_df)
ai_win_rate = ai_approved_df['Is_Winner'].mean() * 100 if total_ai > 0 else 0
ai_avg_win = ai_approved_df[ai_approved_df['Is_Winner'] == 1]['Realized_Return'].mean() if (ai_approved_df['Is_Winner'] == 1).any() else 0
ai_avg_loss = ai_approved_df[ai_approved_df['Is_Winner'] == 0]['Realized_Return'].mean() if (ai_approved_df['Is_Winner'] == 0).any() else 0

rr_ratio = abs(ai_avg_win / ai_avg_loss) if ai_avg_loss != 0 else 0
expectancy = ((ai_win_rate / 100) * ai_avg_win) - ((1 - (ai_win_rate / 100)) * abs(ai_avg_loss))
total_return = ai_approved_df['Realized_Return'].sum()

# Trade Frequency Metrics
if not ai_approved_df.empty:
    ai_approved_df.set_index('Timestamp', inplace=True)
    trades_per_week = ai_approved_df.resample('W').size().mean()
else:
    trades_per_week = 0

# --- Output Report ---
print("\n======================================================================")
print(f" CFO EVALUATION: XGBoost Gatekeeper (Threshold: {approval_threshold*100}%)")
print("======================================================================")
print("**Baseline (Layer 2 Only - Blind Trading)**")
print(f"  Total Trades:       {total_baseline:,}")
print(f"  Win Rate:           {baseline_win_rate:.2f}%")
print(f"  Average Win:        {baseline_avg_win:.5f}")
print(f"  Average Loss:       {baseline_avg_loss:.5f}\n")

print("**AI Gatekeeper (Layer 3 - High Confidence Only)**")
print(f"  Total Approved:     {total_ai:,}")
print(f"  Avg Trades/Week:    {trades_per_week:.1f}")
print(f"  Win Rate:           {ai_win_rate:.2f}%")
print(f"  Average Win:        {ai_avg_win:.5f}")
print(f"  Average Loss:       {ai_avg_loss:.5f}")
print(f"  Risk:Reward (R:R):  {rr_ratio:.2f}")
print(f"  Expectancy/Trade:   {expectancy:.5f}")
print(f"  Total Sim Return:   {total_return:.5f}")
print("======================================================================")