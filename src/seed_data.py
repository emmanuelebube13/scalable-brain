import os
import pyodbc
from dotenv import load_dotenv

load_dotenv()

# Config
SERVER = os.getenv("DB_SERVER", "localhost")
USER = os.getenv("DB_USER", "sa")
PASS = os.getenv("DB_PASS")
DB_NAME = "ForexBrainDB"
DRIVER = "ODBC Driver 17 for SQL Server"

# NOTE: autocommit=True in the string doesn't always work for inserts. 
# We will use explicit commit() below.
CONN_STR = f"DRIVER={{{DRIVER}}};SERVER={SERVER};UID={USER};PWD={PASS};DATABASE={DB_NAME};TrustServerCertificate=yes"

def seed_database():
    try:
        conn = pyodbc.connect(CONN_STR)
        cursor = conn.cursor()

        print("--- 1. Verifying Tables ---")
        cursor.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"Found {len(tables)} tables.")

        print("\n--- 2. Seeding 'Dim_Asset' ---")
        assets = [
            ('EUR_USD', 'Forex'),
            ('GBP_USD', 'Forex'),
            ('USD_JPY', 'Forex'),
            ('BTC_USD', 'Crypto') 
        ]
        
        for symbol, market in assets:
            check_sql = f"SELECT Asset_ID FROM Dim_Asset WHERE Symbol = '{symbol}'"
            cursor.execute(check_sql)
            if not cursor.fetchone():
                print(f"   Inserting {symbol}...")
                cursor.execute("INSERT INTO Dim_Asset (Symbol, Market_Type) VALUES (?, ?)", (symbol, market))
            else:
                print(f"   {symbol} already exists.")

        print("\n--- 3. Seeding 'Dim_Market_Regime' ---")
        regimes = [
            ('Bullish_Trend', 'Low'),
            ('Bearish_Trend', 'Low'),
            ('Sideways_Choppy', 'High'),
            ('Extreme_Volatility', 'High')
        ]

        for name, vol in regimes:
            check_sql = f"SELECT Regime_ID FROM Dim_Market_Regime WHERE Regime_Name = '{name}'"
            cursor.execute(check_sql)
            if not cursor.fetchone():
                print(f"   Inserting {name}...")
                cursor.execute("INSERT INTO Dim_Market_Regime (Regime_Name, Volatility_Index) VALUES (?, ?)", (name, vol))
            else:
                print(f"   {name} already exists.")

        # --- CRITICAL FIX: SAVE CHANGES ---
        conn.commit()
        print("\n✅ COMMITTED: Data permanently saved to Database.")
        
        conn.close()

    except Exception as e:
        print(f"❌ ERROR: {e}")

if __name__ == "__main__":
    seed_database()
