import os
import pyodbc
import pandas as pd
from dotenv import load_dotenv

# --- CONFIGURATION ---
load_dotenv()
CONN_STR = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={os.getenv('DB_SERVER')};UID={os.getenv('DB_USER')};PWD={os.getenv('DB_PASS')};DATABASE=ForexBrainDB;TrustServerCertificate=yes"

def view_signals():
    conn = pyodbc.connect(CONN_STR)
    
    # We join with Dim_Asset so we see "EUR_USD" instead of "5"
    query = """
    SELECT 
        s.Signal_ID,
        a.Symbol,
        s.Timestamp,
        s.Signal_Type,
        FORMAT(s.Entry_Price, 'N5') as Entry,
        FORMAT(s.Stop_Loss, 'N5') as Stop_Loss,
        s.Signal_Strength
    FROM Fact_Signals s
    JOIN Dim_Asset a ON s.Asset_ID = a.Asset_ID
    ORDER BY s.Timestamp DESC
    """
    
    try:
        df = pd.read_sql(query, conn)
        if df.empty:
            print("📭 No signals found in the database.")
        else:
            print(f"\n🚀 FOUND {len(df)} SIGNALS:\n")
            # Make it look pretty in the terminal
            print(df.to_string(index=False))
            
    except Exception as e:
        print(f"❌ Error viewing signals: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    view_signals()
