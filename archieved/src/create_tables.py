import os
import pyodbc
from dotenv import load_dotenv

# Load Environment Variables
load_dotenv()
SERVER = os.getenv("DB_SERVER", "localhost")
USER = os.getenv("DB_USER", "sa")
PASS = os.getenv("DB_PASS")
DB_NAME = "ForexBrainDB"

# Connection String Template
DRIVER = "ODBC Driver 17 for SQL Server"
BASE_CONN_STR = f"DRIVER={{{DRIVER}}};SERVER={SERVER};UID={USER};PWD={PASS};TrustServerCertificate=yes"

def create_schema():
    try:
        # 1. Connect to 'master' to ensure DB exists
        print("🔌 Connecting to SQL Server...")
        conn = pyodbc.connect(BASE_CONN_STR, autocommit=True) # <--- FORCE AUTOCOMMIT HERE
        cursor = conn.cursor()
        
        cursor.execute(f"SELECT name FROM sys.databases WHERE name = '{DB_NAME}'")
        if not cursor.fetchone():
            print(f"🔨 Creating Database '{DB_NAME}'...")
            cursor.execute(f"CREATE DATABASE {DB_NAME}")
        else:
            print(f"✅ Database '{DB_NAME}' already exists.")
        conn.close()

        # 2. Connect to 'ForexBrainDB' and run the Schema
        print(f"📜 Applying Schema from 'database/schema_sqlserver.sql'...")
        db_conn = pyodbc.connect(f"{BASE_CONN_STR};DATABASE={DB_NAME}", autocommit=True)
        db_cursor = db_conn.cursor()

        with open("database/schema_sqlserver.sql", "r") as f:
            sql_script = f.read()

        # Split by ';' to execute commands individually
        commands = sql_script.split(';')
        
        for cmd in commands:
            if cmd.strip():
                try:
                    db_cursor.execute(cmd)
                except Exception as e:
                    if "There is already an object named" in str(e):
                        pass # Ignore "Table already exists" errors
                    else:
                        print(f"   ⚠️ Error executing command: {e}")

        print("✅ SCHEMA DEPLOYED SUCCESSFULLY!")
        db_conn.close()

    except Exception as e:
        print(f"❌ CRITICAL FAILURE: {e}")

if __name__ == "__main__":
    create_schema()
