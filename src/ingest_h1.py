import os
import pyodbc
import oandapyV20
import oandapyV20.endpoints.instruments as instruments
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
API_KEY = os.getenv("OANDA_API_KEY")
ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
CONN_STR = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={os.getenv('DB_SERVER')};UID={os.getenv('DB_USER')};PWD={os.getenv('DB_PASS')};DATABASE=ForexBrainDB;TrustServerCertificate=yes"

client = oandapyV20.API(access_token=API_KEY)

def get_assets():
    conn = pyodbc.connect(CONN_STR)
    df = pd.read_sql("SELECT Asset_ID, Symbol FROM Dim_Asset", conn)
    conn.close()
    return df.values.tolist()

def save_candles(asset_id, candles):
    if not candles:
        return
    
    conn = pyodbc.connect(CONN_STR)
    cursor = conn.cursor()
    
    data_to_insert = []
    for c in candles:
        time_str = c['time'].replace('T', ' ').split('.')[0]
        data_to_insert.append((
            asset_id, 
            time_str, 
            float(c['mid']['o']), 
            float(c['mid']['h']), 
            float(c['mid']['l']), 
            float(c['mid']['c']), 
            int(c['volume']),
            'H1'
        ))
    
    # --- FIX: Changed 'Open_Price' to '[Open]' to match your DB ---
    sql = """
    MERGE Fact_Market_Prices AS target
    USING (VALUES (?, ?, ?, ?, ?, ?, ?, ?)) AS source (Asset_ID, Timestamp, [Open], [High], [Low], [Close], Volume, Granularity)
    ON target.Asset_ID = source.Asset_ID AND target.Timestamp = source.Timestamp AND target.Granularity = source.Granularity
    WHEN MATCHED THEN
        UPDATE SET 
            [Open] = source.[Open], 
            [High] = source.[High], 
            [Low] = source.[Low], 
            [Close] = source.[Close],
            Volume = source.Volume
    WHEN NOT MATCHED THEN
        INSERT (Asset_ID, Timestamp, [Open], [High], [Low], [Close], Volume, Granularity)
        VALUES (source.Asset_ID, source.Timestamp, source.[Open], source.[High], source.[Low], source.[Close], source.Volume, source.Granularity);
    """
    
    try:
        cursor.executemany(sql, data_to_insert)
        conn.commit()
        print(f"   ✅ Saved {len(candles)} H1 candles.")
    except Exception as e:
        print(f"   ❌ SQL Error: {e}")
    finally:
        conn.close()

def fetch_h1_data():
    assets = get_assets()
    
    for asset_id, symbol in assets:
        print(f"📥 Fetching H1 Data for {symbol}...")
        
        params = {
            "count": 5000,
            "granularity": "H1"
        }
        
        try:
            r = instruments.InstrumentsCandles(instrument=symbol, params=params)
            client.request(r)
            candles = r.response['candles']
            save_candles(asset_id, candles)
            
        except Exception as e:
            print(f"   ❌ Error fetching {symbol}: {e}")

if __name__ == "__main__":
    fetch_h1_data()
