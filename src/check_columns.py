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

def check_structure():
    conn = pyodbc.connect(CONN_STR)
    cursor = conn.cursor()
    
    print(f"🔎 Inspecting table: Fact_Market_Prices")
    cursor.execute("""
        SELECT COLUMN_NAME 
        FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_NAME = 'Fact_Market_Prices'
    """)
    
    columns = [row[0] for row in cursor.fetchall()]
    print(f"   Found Columns: {columns}")
    
    if "Granularity" in columns:
        print("✅ SUCCESS: 'Granularity' column exists!")
    else:
        print("❌ FAILURE: 'Granularity' is MISSING. The patch didn't save.")
    
    conn.close()

if __name__ == "__main__":
    check_structure()
