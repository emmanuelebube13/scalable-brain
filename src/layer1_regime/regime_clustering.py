import os
import pyodbc
import pandas as pd
import numpy as np
import ta
from dotenv import load_dotenv
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score

# --- Configuration & DB Connection ---
load_dotenv()
CONN_STR = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={os.getenv('DB_SERVER', 'localhost')};DATABASE=ForexBrainDB;UID={os.getenv('DB_USER', 'sa')};PWD={os.getenv('DB_PASS')}"

def fetch_data(asset_id, limit=10000):
    """Fetches historical OHLCV data for clustering."""
    conn = pyodbc.connect(CONN_STR)
    query = f"""
        SELECT TOP {limit} Timestamp, [Open], High, Low, [Close], Volume 
        FROM Fact_Market_Prices 
        WHERE Asset_ID = {asset_id} 
        ORDER BY Timestamp DESC
    """
    df = pd.read_sql(query, conn, index_col='Timestamp')
    conn.close()
    return df.sort_index() # Sort ascending for indicator math

def calculate_regime_features(df):
    """Calculates ADX (Trend) and ATR (Volatility)."""
    # ATR (Volatility)
    df['ATR'] = ta.volatility.AverageTrueRange(df['High'], df['Low'], df['Close'], window=14).average_true_range()
    
    # ADX (Trend Strength)
    adx_ind = ta.trend.ADXIndicator(df['High'], df['Low'], df['Close'], window=14)
    df['ADX'] = adx_ind.adx()
    
    df.dropna(inplace=True)
    return df[['ATR', 'ADX']]

def evaluate_and_cluster(features_df, symbol):
    """Scales data, runs K-Means, and calculates the Silhouette Score."""
    print(f"\n--- Processing {symbol} ---")
    
    # 1. Scale the Data (Crucial for K-Means so ADX and ATR have equal weight)
    scaler = StandardScaler()
    scaled_data = scaler.fit_transform(features_df)
    
    # 2. Train the Unsupervised Model
    kmeans = KMeans(n_clusters=4, random_state=42, n_init=10)
    cluster_labels = kmeans.fit_predict(scaled_data)
    
    # 3. Calculate Performance Metrics
    inertia = kmeans.inertia_
    sil_score = silhouette_score(scaled_data, cluster_labels)
    
    print(f"Model Inertia: {inertia:,.2f}")
    print(f"Silhouette Score: {sil_score:.4f} ", end="")
    if sil_score > 0.5:
        print("(Excellent separation ✅)")
    elif sil_score > 0.3:
        print("(Acceptable separation ⚠️)")
    else:
        print("(Poor separation ❌)")

    # 4. Map Clusters to Business Logic
    centers = scaler.inverse_transform(kmeans.cluster_centers_)
    features_df = features_df.copy()
    features_df['Cluster'] = cluster_labels
    
    print("\nRegime Centroids (The mathematical center of each weather state):")
    print(f"{'Cluster':<8} | {'Avg ATR (Vol)':<15} | {'Avg ADX (Trend)':<15}")
    print("-" * 45)
    for i, center in enumerate(centers):
        print(f"{i:<8} | {center[0]:<15.5f} | {center[1]:<15.2f}")

if __name__ == "__main__":
    print("Initializing Layer 1 Regime Detection Engine...")
    
    # Dictionary mapping your Asset IDs
    assets = {5: "EUR_USD", 6: "GBP_USD", 7: "USD_JPY"}
    
    for asset_id, symbol in assets.items():
        # Fetch a robust sample size (10,000 hours) to train the model
        raw_df = fetch_data(asset_id, limit=10000)
        
        if not raw_df.empty:
            feature_df = calculate_regime_features(raw_df)
            evaluate_and_cluster(feature_df, symbol)
        else:
            print(f"No data found for {symbol}.")
