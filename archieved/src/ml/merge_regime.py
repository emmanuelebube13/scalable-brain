import os
import pyodbc
import pandas as pd
from dotenv import load_dotenv

# --- CONFIGURATION ---
load_dotenv()
CONN_STR = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={os.getenv('DB_SERVER')};UID={os.getenv('DB_USER')};PWD={os.getenv('DB_PASS')};DATABASE=ForexBrainDB;TrustServerCertificate=yes"

def merge_daily_regime(asset_id):
    print(f"🔗 Merging Daily Regime into H1 Dataset for Asset {asset_id}...")
    
    # 1. Load the new H1 dataset (which now has Session & MTF data)
    filepath = f'data/processed/asset_{asset_id}_ml_data.csv'
    df_h1 = pd.read_csv(filepath)
    df_h1['Timestamp'] = pd.to_datetime(df_h1['Timestamp'])
    df_h1['Date'] = df_h1['Timestamp'].dt.date
    
    # 2. Fetch the Daily Regime
    conn = pyodbc.connect(CONN_STR)
    query = f"SELECT Date, Regime_Type FROM Fact_Daily_Regime WHERE Asset_ID = {asset_id}"
    df_regime = pd.read_sql(query, conn)
    conn.close()
    
    df_regime['Date'] = pd.to_datetime(df_regime['Date']).dt.date
    
    # 3. Merge
    df_final = pd.merge(df_h1, df_regime, on='Date', how='left')
    df_final['Regime_Type'] = df_final['Regime_Type'].fillna('UNKNOWN')
    
    # 4. One-Hot Encoding for Regimes
    print("🔢 Converting text regimes to ML-friendly numbers...")
    regime_dummies = pd.get_dummies(df_final['Regime_Type'], prefix='Regime').astype(int) 
    df_final = pd.concat([df_final, regime_dummies], axis=1)
    
    # THE FIX: Only drop Date and Regime_Type (Future_Close is already gone)
    df_final = df_final.drop(columns=['Date', 'Regime_Type'])
    
    # Save the finalized, ML-Ready training set
    final_filepath = f'data/processed/asset_{asset_id}_ml_data_final.csv'
    df_final.to_csv(final_filepath, index=False)
    
    print(f"✅ Merge Complete! Final dataset saved to: {final_filepath}")
    print("\n🧠 Columns ready for the AI to study:")
    for col in df_final.columns:
        print(f"   - {col}")

if __name__ == "__main__":
    merge_daily_regime(5)
