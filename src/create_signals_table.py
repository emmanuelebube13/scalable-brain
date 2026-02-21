import os
import pyodbc
from dotenv import load_dotenv

load_dotenv()
CONN_STR = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={os.getenv('DB_SERVER')};UID={os.getenv('DB_USER')};PWD={os.getenv('DB_PASS')};DATABASE=ForexBrainDB;TrustServerCertificate=yes"

def create_signals_table():
    try:
        conn = pyodbc.connect(CONN_STR)
        cursor = conn.cursor()
        
        print("🔨 Creating 'Fact_Signals' table...")
        
        sql = """
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Fact_Signals' AND xtype='U')
        BEGIN
            CREATE TABLE Fact_Signals (
                Signal_ID BIGINT IDENTITY(1,1) PRIMARY KEY,
                Asset_ID INT FOREIGN KEY REFERENCES Dim_Asset(Asset_ID),
                Strategy_ID INT, -- We will link this to Strategy Registry later
                Timestamp DATETIME NOT NULL,
                
                Signal_Type VARCHAR(10) NOT NULL, -- 'BUY' or 'SELL'
                Entry_Price DECIMAL(18,5) NOT NULL,
                Stop_Loss DECIMAL(18,5) NOT NULL,
                Take_Profit DECIMAL(18,5) NOT NULL,
                
                Signal_Strength DECIMAL(5,2), -- 1.0 = Perfect Setup, 0.5 = Weak
                Created_At DATETIME DEFAULT GETDATE()
            );
            PRINT '✅ Table Created.'
        END
        ELSE
        BEGIN
            PRINT '⚠️ Table already exists.'
        END
        """
        
        cursor.execute(sql)
        conn.commit()
        print("🚀 Signal Table is ready.")
        conn.close()

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    create_signals_table()
