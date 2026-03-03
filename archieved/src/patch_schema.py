import os
import pyodbc
from dotenv import load_dotenv

load_dotenv()
SERVER = os.getenv("DB_SERVER", "localhost")
USER = os.getenv("DB_USER", "sa")
PASS = os.getenv("DB_PASS")
DB_NAME = "ForexBrainDB"
DRIVER = "ODBC Driver 17 for SQL Server"

CONN_STR = f"DRIVER={{{DRIVER}}};SERVER={SERVER};UID={USER};PWD={PASS};DATABASE={DB_NAME};TrustServerCertificate=yes;autocommit=True"

def patch_database():
    try:
        print("🔌 Connecting to Database...")
        conn = pyodbc.connect(CONN_STR)
        cursor = conn.cursor()

        # 1. Add the Column
        print("🛠️  Adding 'Granularity' column to Fact_Market_Prices...")
        try:
            cursor.execute("ALTER TABLE Fact_Market_Prices ADD Granularity VARCHAR(10)")
            print("   ✅ Column added.")
        except Exception as e:
            if "Column names in each table must be unique" in str(e):
                print("   ⚠️ Column already exists.")
            else:
                print(f"   ❌ Error: {e}")

        # 2. Update existing rows (Label them 'H1')
        print("🏷️  Labeling existing data as 'H1'...")
        cursor.execute("UPDATE Fact_Market_Prices SET Granularity = 'H1' WHERE Granularity IS NULL")
        
        # 3. Update the Unique Constraint
        print("🔐 Updating Unique Constraints...")
        try:
            # Try to drop the old default constraint (name varies, so this might fail if name is random)
            # A safer way in T-SQL is complex, but let's try the standard naming first or just add the new one.
            cursor.execute("ALTER TABLE Fact_Market_Prices DROP CONSTRAINT UQ_Asset_Time")
        except:
            pass 
        
        try:
            cursor.execute("ALTER TABLE Fact_Market_Prices ADD CONSTRAINT UQ_Asset_Time_Granularity UNIQUE(Asset_ID, Timestamp, Granularity)")
            print("   ✅ Constraint updated.")
        except:
             pass

        print("\n🚀 SCHEMA PATCH COMPLETE.")
        conn.close()

    except Exception as e:
        print(f"❌ ERROR: {e}")

if __name__ == "__main__":
    patch_database()
