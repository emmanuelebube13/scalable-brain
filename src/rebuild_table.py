import os
import pyodbc
from dotenv import load_dotenv

load_dotenv()
SERVER = os.getenv("DB_SERVER", "localhost")
USER = os.getenv("DB_USER", "sa")
PASS = os.getenv("DB_PASS")
DB_NAME = "ForexBrainDB"
DRIVER = "ODBC Driver 17 for SQL Server"

CONN_STR = f"DRIVER={{{DRIVER}}};SERVER={SERVER};UID={USER};PWD={PASS};DATABASE={DB_NAME};TrustServerCertificate=yes"

def rebuild_prices_table():
    try:
        conn = pyodbc.connect(CONN_STR)
        cursor = conn.cursor()
        print(f"🔌 Connected to {DB_NAME}")

        # 1. DROP the old table (Nuclear Option)
        # We must drop child tables (foreign keys) first if they exist, but for now we likely just have Prices
        print("💥 Dropping old 'Fact_Market_Prices' table...")
        try:
            # We first drop dependencies if they exist (Results -> Signals -> Prices)
            # Just in case you created them, let's be safe:
            cursor.execute("IF OBJECT_ID('Fact_Trade_Results', 'U') IS NOT NULL DROP TABLE Fact_Trade_Results")
            cursor.execute("IF OBJECT_ID('Fact_Signals', 'U') IS NOT NULL DROP TABLE Fact_Signals")
            cursor.execute("IF OBJECT_ID('Fact_Indicator_Values', 'U') IS NOT NULL DROP TABLE Fact_Indicator_Values")
            
            # Now drop the main table
            cursor.execute("IF OBJECT_ID('Fact_Market_Prices', 'U') IS NOT NULL DROP TABLE Fact_Market_Prices")
            conn.commit()
            print("   ✅ Old table deleted.")
        except Exception as e:
            print(f"   ⚠️ Drop Warning: {e}")

        # 2. CREATE the new table (With Granularity)
        print("🔨 Creating new 'Fact_Market_Prices' with Granularity...")
        create_sql = """
        CREATE TABLE Fact_Market_Prices (
            Price_ID BIGINT IDENTITY(1,1) PRIMARY KEY,
            Asset_ID INT FOREIGN KEY REFERENCES Dim_Asset(Asset_ID),
            Timestamp DATETIME NOT NULL,
            [Open] DECIMAL(18,5) NOT NULL,
            High DECIMAL(18,5) NOT NULL,
            Low DECIMAL(18,5) NOT NULL,
            [Close] DECIMAL(18,5) NOT NULL,
            Volume BIGINT,
            Granularity VARCHAR(10) NOT NULL, -- <--- The New Column
            
            -- New Composite Key: Asset + Time + Granularity must be unique
            CONSTRAINT UQ_Asset_Time_Granularity UNIQUE(Asset_ID, Timestamp, Granularity)
        );
        """
        cursor.execute(create_sql)
        conn.commit()
        print("   ✅ New table created successfully.")

        # 3. Verify it worked
        cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'Fact_Market_Prices'")
        cols = [row[0] for row in cursor.fetchall()]
        print(f"🔎 Verification - Columns Found: {cols}")
        
        if "Granularity" in cols:
            print("🚀 SUCCESS: Database is ready for Multi-Timeframe Ingestion.")
        else:
            print("❌ FAILURE: Column still missing.")

        conn.close()

    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")

if __name__ == "__main__":
    rebuild_prices_table()
