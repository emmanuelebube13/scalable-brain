import os
import pyodbc
import pandas as pd
import numpy as np
import joblib
from dotenv import load_dotenv

# --- CONFIGURATION ---
load_dotenv()
CONN_STR = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={os.getenv('DB_SERVER')};UID={os.getenv('DB_USER')};PWD={os.getenv('DB_PASS')};DATABASE=ForexBrainDB;TrustServerCertificate=yes"

def generate_signals(asset_id, confidence_threshold=0.75):
    print(f"🔌 Connecting Scalable Brain to Database for Asset {asset_id}...")
    
    # 1. Load the Model and the Data
    model_path = f'models/xgboost_asset_{asset_id}_v1.pkl'
    data_path = f'data/processed/asset_{asset_id}_ml_data_final.csv'
    
    if not os.path.exists(model_path) or not os.path.exists(data_path):
        print("⚠️ Error: Model or Data not found. Run training pipeline first.")
        return

    xgb_model = joblib.load(model_path)
    df = pd.read_csv(data_path)
    
    # 2. Prepare the data (Drop targets and non-features)
    # We use the most recent 100 hours to simulate "Live" signal generation
    recent_df = df.tail(100).copy() 
    X_recent = recent_df.drop(columns=['Timestamp', 'Open', 'High', 'Low', 'Close', 'Target_Class'])
    
    # 3. Generate Probabilities
    print(f"🧠 Analyzing recent market data (Confidence Threshold: {confidence_threshold * 100}%)...")
    probabilities = xgb_model.predict_proba(X_recent)
    
    # 4. Filter for High Confidence Trades
    signals_to_insert = []
    
    for i in range(len(probabilities)):
        prob_sell = probabilities[i][0]
        prob_buy = probabilities[i][2]
        
        signal_type = None
        confidence = 0.0
        
        if prob_buy >= confidence_threshold:
            signal_type = 'BUY'
            confidence = prob_buy
        elif prob_sell >= confidence_threshold:
            signal_type = 'SELL'
            confidence = prob_sell
            
        # Only log trades that meet our strict business rules
        if signal_type:
            # Extract the corresponding timestamp and price for the database
            timestamp = recent_df.iloc[i]['Timestamp']
            close_price = recent_df.iloc[i]['Close']
            
            signals_to_insert.append({
                'Asset_ID': asset_id,
                'Timestamp': timestamp,
                'Signal_Type': signal_type,
                'Confidence': float(confidence),
                'Price_At_Signal': float(close_price)
            })

    # 5. Insert into SQL Database (Fact_Signals)
    if not signals_to_insert:
        print("⏸️ No high-confidence signals found in recent data. Capital preserved.")
        return

    print(f"🚀 Found {len(signals_to_insert)} High-Confidence Signals! Writing to DB...")
    
    conn = pyodbc.connect(CONN_STR)
    cursor = conn.cursor()
    
    for sig in signals_to_insert:
        # Check if signal already exists to prevent duplicates
        cursor.execute(f"SELECT COUNT(*) FROM Fact_Signals WHERE Asset_ID={sig['Asset_ID']} AND Timestamp='{sig['Timestamp']}'")
        if cursor.fetchone()[0] == 0:
            insert_query = """
                INSERT INTO Fact_Signals (Asset_ID, Timestamp, Signal_Type, Confidence_Score, Price_At_Signal)
                VALUES (?, ?, ?, ?, ?)
            """
            cursor.execute(insert_query, (sig['Asset_ID'], sig['Timestamp'], sig['Signal_Type'], sig['Confidence'], sig['Price_At_Signal']))
    
    conn.commit()
    conn.close()
    print("✅ Signals successfully locked into Fact_Signals table.")

if __name__ == "__main__":
    generate_signals(5, confidence_threshold=0.75)
