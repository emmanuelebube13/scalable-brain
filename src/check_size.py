import os, pyodbc
from dotenv import load_dotenv

load_dotenv()
CONN_STR = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={os.getenv('DB_SERVER')};UID={os.getenv('DB_USER')};PWD={os.getenv('DB_PASS')};DATABASE=ForexBrainDB;TrustServerCertificate=yes"

conn = pyodbc.connect(CONN_STR)
cursor = conn.cursor()

# Ask SQL Server for its own size
cursor.execute("SELECT (size * 8) / 1024 AS Size_MB FROM sys.master_files WHERE name = 'ForexBrainDB'")
print(f"📉 Database Size: {cursor.fetchone()[0]} MB")
conn.close()
