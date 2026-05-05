# data_loader.py
import os
import psycopg2
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
CONN_STR = f"host={os.getenv('DB_SERVER', 'localhost')} dbname=ForexBrainDB user={os.getenv('DB_USER', 'sa')} password={os.getenv('DB_PASS')} port=5432"

def fetch_real_data():
    print("Connecting to PostgreSQL...")
    conn = psycopg2.connect(CONN_STR)
    asset_map = {5: "EUR_USD", 6: "GBP_USD", 7: "USD_JPY"}
    data = {}
    for asset_id, symbol in asset_map.items():
        print(f"→ Downloading {symbol}...")
        df = pd.read_sql(f"""
            SELECT Timestamp, [Open], High, Low, [Close], Volume 
            FROM Fact_Market_Prices 
            WHERE Asset_ID = {asset_id} ORDER BY Timestamp ASC
        """, conn, index_col='Timestamp', parse_dates=True)
        data[symbol] = df
    conn.close()
    return data