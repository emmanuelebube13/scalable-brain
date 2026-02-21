import os
import pyodbc
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
CONN_STR = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={os.getenv('DB_SERVER')};UID={os.getenv('DB_USER')};PWD={os.getenv('DB_PASS')};DATABASE=ForexBrainDB;TrustServerCertificate=yes"

def debug_database():
    conn = pyodbc.connect(CONN_STR)
    cursor = conn.cursor()
    
    print("🔎 --- DIAGNOSTIC REPORT ---")
    
    # 1. Check Asset IDs
    print("\n1. ASSETS IN DATABASE:")
    assets = pd.read_sql("SELECT * FROM Dim_Asset", conn)
    print(assets)
    
    # 2. Check Data Counts
    print("\n2. DATA COUNTS BY GRANULARITY:")
    query = """
    SELECT Asset_ID, Granularity, COUNT(*) as Count 
    FROM Fact_Market_Prices 
    GROUP BY Asset_ID, Granularity
    """
    counts = pd.read_sql(query, conn)
    print(counts)
    
    # 3. Peek at the Raw Data (First 3 rows)
    print("\n3. SAMPLE DATA (First 3 rows):")
    sample = pd.read_sql("SELECT TOP 3 * FROM Fact_Market_Prices", conn)
    print(sample)

    conn.close()

if __name__ == "__main__":
    debug_database()
