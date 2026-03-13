# data_loader.py
import os
import pyodbc
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
CONN_STR = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={os.getenv('DB_SERVER', 'localhost')};DATABASE=ForexBrainDB;UID={os.getenv('DB_USER', 'sa')};PWD={os.getenv('DB_PASS')}"

def fetch_real_data():
    print("Connecting to SQL Server...")
    conn = pyodbc.connect(CONN_STR)
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