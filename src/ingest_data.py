import os
import pyodbc
import oandapyV20
import oandapyV20.endpoints.instruments as instruments
from dotenv import load_dotenv
from datetime import datetime, timedelta

# --- CONFIGURATION ---
SYMBOLS = ["EUR_USD", "GBP_USD"]  # Add more pairs here
TIMEFRAMES = ["H1", "H4", "D"]    # The timeframes you need for analysis
LOOKBACK_DAYS = 365 * 2           # 2 Years of history

# ---------------------

load_dotenv()
API_KEY = os.getenv("OANDA_API_KEY")
ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
SERVER = os.getenv("DB_SERVER", "localhost")
USER = os.getenv("DB_USER", "sa")
PASS = os.getenv("DB_PASS")
DB_NAME = "ForexBrainDB"
DRIVER = "ODBC Driver 17 for SQL Server"
CONN_STR = f"DRIVER={{{DRIVER}}};SERVER={SERVER};UID={USER};PWD={PASS};DATABASE={DB_NAME};TrustServerCertificate=yes"

def get_asset_id(cursor, symbol):
    cursor.execute("SELECT Asset_ID FROM Dim_Asset WHERE Symbol = ?", symbol)
    row = cursor.fetchone()
    return row[0] if row else None

def ingest_all():
    client = oandapyV20.API(access_token=API_KEY)
    conn = pyodbc.connect(CONN_STR)
    cursor = conn.cursor()
    
    for symbol in SYMBOLS:
        asset_id = get_asset_id(cursor, symbol)
        if not asset_id:
            print(f"⚠️ Skipping {symbol} (Not in Dim_Asset)")
            continue
            
        for tf in TIMEFRAMES:
            print(f"\n📥 PROCESSING: {symbol} [{tf}]")
            
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=LOOKBACK_DAYS)
            
            params = {
                "granularity": tf,
                "count": 5000,
                "to": end_date.strftime("%Y-%m-%dT%H:%M:%S.000000000Z")
            }

            while True:
                # print(f"   Fetching chunk ending {params['to']}...")
                try:
                    r = instruments.InstrumentsCandles(instrument=symbol, params=params)
                    client.request(r)
                except Exception as e:
                    print(f"   ❌ API Error: {e}")
                    break

                candles = r.response['candles']
                if not candles: break

                batch_data = []
                min_time = None

                for c in candles:
                    if c['complete']:
                        # Clean Timestamp
                        ts = c['time'].split(".")[0].replace("T", " ")
                        o = c['mid']['o']
                        h = c['mid']['h']
                        l = c['mid']['l']
                        c_price = c['mid']['c']
                        v = c['volume']
                        
                        # Add 'tf' (Granularity) to the data tuple
                        batch_data.append((asset_id, ts, o, h, l, c_price, v, tf))
                        
                        raw_time = c['time']
                        if min_time is None or raw_time < min_time:
                            min_time = raw_time

                if batch_data:
                    # Note the new column in the INSERT statement
                    query = """
                    INSERT INTO Fact_Market_Prices 
                    (Asset_ID, Timestamp, [Open], High, Low, [Close], Volume, Granularity)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    try:
                        cursor.executemany(query, batch_data)
                        conn.commit()
                        print(f"   --> Saved {len(batch_data)} candles ({min_time})")
                    except pyodbc.IntegrityError:
                        print("   ⚠️ Skipped duplicates.")
                        conn.rollback()

                # Loop Logic
                current_dt = datetime.strptime(min_time[:19], "%Y-%m-%dT%H:%M:%S")
                if current_dt < start_date:
                    print(f"   ✅ {symbol} {tf} Complete.")
                    break
                params['to'] = min_time

    conn.close()

if __name__ == "__main__":
    ingest_all()
