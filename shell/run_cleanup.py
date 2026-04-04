import os
import pyodbc
from pathlib import Path

# Get database credentials from .env
env_file = Path('scalable-brain/.env')
credentials = {}

if env_file.exists():
    with open(env_file, 'r') as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                credentials[key] = value.strip("'\"")

# Extract connection details
server = credentials.get('DB_SERVER', 'localhost')
user = credentials.get('DB_USER', 'sa')
password = credentials.get('DB_PASS', '')
database = credentials.get('DB_NAME', 'ForexBrainDB')
port = credentials.get('DB_PORT', '1433')

# Build connection string
connection_string = f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server},{port};UID={user};PWD={password};DATABASE={database}'

try:
    print(f"[*] Connecting to {server}:{port}/{database}...")
    conn = pyodbc.connect(connection_string)
    cursor = conn.cursor()
    
    # Read and execute the cleanup script
    sql_script = Path('scalable-brain/src/sql/cleanup_deprecated_tables.sql').read_text()
    
    # Execute the script
    print("\n[*] Executing cleanup script...")
    for statement in sql_script.split('GO'):
        if statement.strip():
            try:
                cursor.execute(statement)
            except Exception as e:
                print(f"⚠️  Warning: {e}")
    
    conn.commit()
    print("\n✅ Cleanup completed successfully!")
    
    # Verify remaining tables
    print("\n[*] Verifying remaining tables...")
    cursor.execute("""
        SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES 
        WHERE TABLE_SCHEMA = 'dbo' AND TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_NAME
    """)
    
    tables = cursor.fetchall()
    print(f"\nRemaining tables in ForexBrainDB ({len(tables)} total):")
    for table in tables:
        print(f"  - {table[0]}")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"❌ Error: {e}")
    exit(1)
