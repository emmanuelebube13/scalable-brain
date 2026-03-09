import pyodbc
from dotenv import load_dotenv
import os
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
import xgboost as xgb
import joblib
import numpy as np
import warnings
import sqlalchemy as sa

# Suppress warnings for clean output
warnings.filterwarnings('ignore')

# Load environment variables
load_dotenv()
DB_SERVER = os.getenv('DB_SERVER')
DB_USER = os.getenv('DB_USER')
DB_PASS = os.getenv('DB_PASS')
DB_NAME = 'ForexBrainDB'

import urllib.parse

# Safely encode the exact pyodbc string that we know already works
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

print("Fetching historical data from database. This may take a moment for 900k+ rows...")
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

# CRITICAL: Time-series split. Do NOT shuffle. 
# Train on the past (80%), Test on the future (20%)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)
print(f"Train shape: {X_train.shape}, Test shape: {X_test.shape}")

# Model Training
print("Initializing XGBoost Classifier...")
model = xgb.XGBClassifier(n_estimators=100, max_depth=5, learning_rate=0.1, random_state=42)

print("Training model... (The AI is now learning)")
model.fit(X_train, y_train)
print("Training complete.")

# Evaluation
print("Evaluating model on the 20% future test set...")
y_pred = model.predict(X_test)

accuracy = accuracy_score(y_test, y_pred)
print(f"\nAccuracy: {accuracy:.4f}")

report = classification_report(y_test, y_pred)
print("Classification Report:\n", report)

# Feature Importances
importances = model.feature_importances_
feature_names = X.columns
sorted_indices = np.argsort(importances)[::-1]
top_10 = sorted_indices[:10]

print("Top 10 Feature Importances (What the AI cares about most):")
for idx in top_10:
    print(f"{feature_names[idx]}: {importances[idx]:.4f}")

# Save Model
os.makedirs('models', exist_ok=True)
model_path = 'models/xgboost_gatekeeper.pkl'
joblib.dump(model, model_path)
print(f"\nModel saved to {model_path}")