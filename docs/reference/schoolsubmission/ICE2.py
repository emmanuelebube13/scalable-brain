"""
=============================================================================
Author:       Emmanuel Mbachu
Date:         2026-03-21
Description:  ICE 2 - Machine Learning Algorithm Development.
              This script connects to ForexBrainDB, extracts historical 
              trade signals and market regimes, and trains an XGBoost 
              Classifier to predict trade outcomes (Win/Loss). It outputs 
              the AUC/ROC metric, generates an ROC curve plot, and saves 
              the finalized model to disk for live pipeline integration.
=============================================================================
"""

import os
import urllib.parse
import warnings
import pandas as pd
import numpy as np
import xgboost as xgb
import joblib
import sqlalchemy as sa
import matplotlib.pyplot as plt
from dotenv import load_dotenv
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score, roc_auc_score, RocCurveDisplay

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
# Use SQLAlchemy engine for enterprise-grade pandas ingestion
engine = sa.create_engine(f"mssql+pyodbc:///?odbc_connect={params}")

print("Connected to ForexBrainDB successfully.")

# The exact, correct schema pulling our Layer 1 and Layer 2 data
query = """
SELECT 
    fmr.Regime_Label, 
    fmr.ATR_Value, 
    fmr.ADX_Value, 
    fs.Asset_ID, 
    fs.Strategy_ID, 
    fs.Signal_Value, 
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

print("Fetching historical data from database. This may take a moment...")
df = pd.read_sql(query, engine)
print(f"Data loaded successfully. Shape: {df.shape}")

# Data Preprocessing
print("Starting data preprocessing...")
df = df.dropna()

# One-hot encode categorical variables so the math works
df = pd.get_dummies(df, columns=['Regime_Label', 'Asset_ID', 'Strategy_ID'], drop_first=True)
print("Categorical variables encoded.")

X = df.drop('Is_Winner', axis=1)
y = df['Is_Winner']

# CRITICAL: Time-series split. Train on the past (80%), Test on the future (20%)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)
print(f"Train shape: {X_train.shape}, Test shape: {X_test.shape}")

# Model Training
print("Initializing XGBoost Classifier...")
model = xgb.XGBClassifier(n_estimators=100, max_depth=5, learning_rate=0.1, random_state=42)

print("Training model... (The AI is now learning)")
model.fit(X_train, y_train)
print("Training complete.")

# Evaluation
print("\n========================================")
print("EVALUATING MODEL ON 20% FUTURE TEST SET")
print("========================================")
y_pred = model.predict(X_test)
y_pred_proba = model.predict_proba(X_test)[:, 1] # Get probabilities for ROC

accuracy = accuracy_score(y_test, y_pred)
auc_score = roc_auc_score(y_test, y_pred_proba)

print(f"Accuracy:        {accuracy:.4f}")
print(f"ROC / AUC Score: {auc_score:.4f}  <--- (REQUIRED FOR ICE 2)")
print("\nClassification Report:\n", classification_report(y_test, y_pred))

# Save Model
os.makedirs('models', exist_ok=True)
model_path = 'models/best_ml_gatekeeper.pkl'
joblib.dump(model, model_path)
print(f"\nModel successfully saved to {model_path}")

# Generate ROC Curve Plot for ICE 2 Screenshot
print("\nGenerating ROC Curve Plot for ICE 2 Screenshot...")
fig, ax = plt.subplots(figsize=(8, 6))
RocCurveDisplay.from_estimator(model, X_test, y_test, ax=ax, color='darkorange')
ax.plot([0, 1], [0, 1], color='navy', lw=2, linestyle='--')
plt.title('Receiver Operating Characteristic (ROC) Curve\nScalable Brain Gatekeeper (XGBoost)')
plt.xlabel('False Positive Rate')
plt.ylabel('True Positive Rate')
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()