import os
import json
import pyodbc
import oandapyV20
import oandapyV20.endpoints.instruments as instruments
from dotenv import load_dotenv

# Load credentials
load_dotenv()

def test_sql_connection():
    print("\n--- 🧪 TEST 1: SQL SERVER CONNECTIVITY ---")
    server = os.getenv("DB_SERVER", "localhost")
    user = os.getenv("DB_USER", "sa")
    password = os.getenv("DB_PASS")
    driver = "ODBC Driver 17 for SQL Server"
    
    conn_str = f"DRIVER={{{driver}}};SERVER={server};UID={user};PWD={password};TrustServerCertificate=yes;"
    
    try:
        conn = pyodbc.connect(conn_str, timeout=5)
        cursor = conn.cursor()
        cursor.execute("SELECT @@VERSION")
        row = cursor.fetchone()
        print(f"✅ SUCCESS: Connected to {row[0][:50]}...")
        conn.close()
        return True
    except Exception as e:
        print(f"❌ FAILURE: Could not connect to SQL Server.\nError: {e}")
        return False

def test_oanda_data_structure():
    print("\n--- 🧪 TEST 2: OANDA DATA STRUCTURE ---")
    api_key = os.getenv("OANDA_API_KEY")
    account_id = os.getenv("OANDA_ACCOUNT_ID")
    
    if not api_key or not account_id:
        print("❌ FAILURE: OANDA_API_KEY or OANDA_ACCOUNT_ID missing in .env")
        return False

    client = oandapyV20.API(access_token=api_key)
    
    # Fetch just 1 candle to inspect the "DNA" of the data
    params = {"count": 1, "granularity": "H1"}
    r = instruments.InstrumentsCandles(instrument="EUR_USD", params=params)
    
    try:
        client.request(r)
        raw_candle = r.response['candles'][0]
        
        print(f"📥 Raw Oanda JSON (One Candle):")
        print(json.dumps(raw_candle, indent=2))
        
        # Verify mapping against your ERD (Fact_Market_Prices)
        # Your ERD expects: Timestamps, Open, High, Low, Close, Volume
        
        print("\n🔎 Mapping Check (Oanda -> Your ERD):")
        
        # Check Timestamp
        try:
            ts = raw_candle['time']
            print(f"   [OK] Timestamp found: {ts}")
        except KeyError:
            print("   [FAIL] Timestamp missing")

        # Check OHLC (Oanda nests these under 'mid')
        try:
            ohlc = raw_candle['mid']
            print(f"   [OK] Open:  {ohlc['o']}")
            print(f"   [OK] High:  {ohlc['h']}")
            print(f"   [OK] Low:   {ohlc['l']}")
            print(f"   [OK] Close: {ohlc['c']}")
        except KeyError:
             print("   [FAIL] OHLC data missing (Check if you are using 'mid' price)")
             
        # Check Volume
        try:
            vol = raw_candle['volume']
            print(f"   [OK] Volume: {vol}")
        except KeyError:
             print("   [FAIL] Volume missing")

        return True
        
    except Exception as e:
        print(f"❌ FAILURE: Oanda Request Failed.\nError: {e}")
        return False

if __name__ == "__main__":
    sql_ok = test_sql_connection()
    oanda_ok = test_oanda_data_structure()
    
    if sql_ok and oanda_ok:
        print("\n🚀 ALL SYSTEMS GO. Ready to run Schema script.")
    else:
        print("\n🛑 HALT. Fix errors before creating tables.")
