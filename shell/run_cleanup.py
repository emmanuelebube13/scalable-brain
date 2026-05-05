import os
import psycopg2
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
WORKSPACE_ROOT = REPO_ROOT.parent

# Get database credentials from .env
env_candidates = [
    REPO_ROOT / '.env',
    WORKSPACE_ROOT / 'scalable-brain' / '.env',
    Path('.env'),
]
env_file = next((p for p in env_candidates if p.exists()), None)
credentials = {}

if env_file:
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
port = credentials.get('DB_PORT', '5432')

# Build PostgreSQL connection parameters
conn_params = {
    'host': server,
    'dbname': database,
    'user': user,
    'password': password,
    'port': int(port),
    'connect_timeout': 10
}

try:
    print(f"[*] Connecting to PostgreSQL: {server}:{port}/{database}...")
    conn = psycopg2.connect(**conn_params)
    cursor = conn.cursor()
    
    # Read and execute the cleanup script
    cleanup_sql_file = REPO_ROOT / 'src' / 'sql' / 'cleanup_deprecated_tables.sql'
    sql_script = cleanup_sql_file.read_text()
    
    # Execute the script - PostgreSQL doesn't use 'GO', so split by semicolons
    print("\n[*] Executing cleanup script...")
    for statement in sql_script.split(';'):
        if statement.strip():
            try:
                cursor.execute(statement)
                conn.commit()
            except Exception as e:
                print(f"⚠️  Warning: {e}")
    
    print("\n✅ Cleanup completed successfully!")
    
    # Verify remaining tables
    print("\n[*] Verifying remaining tables...")
    cursor.execute("""
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """)
    
    tables = cursor.fetchall()
    print(f"\nRemaining tables in ForexBrainDB ({len(tables)} total):")
    for table in tables:
        print(f"  - {table[0]}")
    
    cursor.close()
    conn.close()
    
except psycopg2.Error as e:
    print(f"❌ PostgreSQL Error: {e}")
    exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    exit(1)
