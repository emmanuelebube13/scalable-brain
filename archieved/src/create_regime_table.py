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

def create_regime_table():
    try:
        print("🔌 Connecting to Database...")
        conn = pyodbc.connect(CONN_STR)
        cursor = conn.cursor()

        # This is the SQL command, wrapped in a Python string
        sql_command = """
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Fact_Daily_Regime' AND xtype='U')
        BEGIN
            CREATE TABLE Fact_Daily_Regime (
                Regime_ID BIGINT IDENTITY(1,1) PRIMARY KEY,
                Asset_ID INT FOREIGN KEY REFERENCES Dim_Asset(Asset_ID),
                Date DATE NOT NULL,
                
                -- The Core Metrics
                SMA_50 DECIMAL(18,5),
                SMA_200 DECIMAL(18,5),
                ATR_14 DECIMAL(18,5),
                
                -- The Classification
                Regime_Type VARCHAR(20) NOT NULL,
                Is_High_Volatility BIT DEFAULT 0,
                
                CONSTRAINT UQ_Asset_Date UNIQUE(Asset_ID, Date)
            );
            PRINT '✅ Table Fact_Daily_Regime created successfully.'
        END
        ELSE
        BEGIN
            PRINT '⚠️ Table Fact_Daily_Regime already exists.'
        END
        """
        
        cursor.execute(sql_command)
        conn.commit()
        conn.close()

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    create_regime_table()
