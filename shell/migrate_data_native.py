#!/usr/bin/env python3
"""
Native Database Migration - SQL Server to PostgreSQL
====================================================

Direct migration without Docker. Requires:
- Both SQL Server and PostgreSQL running on the network
- psycopg2 and pymssql installed
- Database credentials in .env

Usage:
    python migrate_data_native.py
    python migrate_data_native.py --dry-run
    python migrate_data_native.py --tables Dim_Asset Fact_Market_Prices
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, List, Tuple, Any, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
WORKSPACE_ROOT = REPO_ROOT.parent

# Try importing database drivers
try:
    import psycopg2
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")

try:
    import pymssql
    PYMSSQL_AVAILABLE = True
except ImportError:
    PYMSSQL_AVAILABLE = False
    print("WARNING: pymssql not installed for SQL Server migration.")
    print("Install with: pip install pymssql")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)

# Colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
END = '\033[0m'

# Tables to migrate (in order to respect foreign keys)
MIGRATION_ORDER = [
    'Dim_Asset',
    'Dim_Strategy_Registry',
    'Dim_Strategy',
    'Dim_Strategy_Config',
    'Dim_Strategy_Asset_Mapping',
    'Dim_Indicator_Library',
    'Fact_Market_Prices',
    'Fact_Market_Prices_H4',
    'Fact_Market_Prices_D1',
    'Fact_Market_Regime',
    'Fact_Market_Regime_V2',
    'Fact_Signals',
    'Fact_Signal_Processing_Log',
    'Fact_Live_Trades',
    'Fact_Trade_Outcomes',
    'Fact_Execution_Log',
    'Fact_Macro_Events',
]


def load_config():
    """Load database configuration from .env"""
    env_candidates = [
        REPO_ROOT / '.env',
        WORKSPACE_ROOT / 'scalable-brain' / '.env',
        Path('.env'),
    ]
    env_file = next((p for p in env_candidates if p.exists()), None)
    
    if env_file:
        load_dotenv(env_file)
    
    # Load from environment
    config = {
        'postgres': {
            'host': os.getenv('DB_SERVER', 'localhost'),
            'dbname': os.getenv('DB_NAME', 'ForexBrainDB'),
            'user': os.getenv('DB_USER', 'sa'),
            'password': os.getenv('DB_PASS', 'password'),
            'port': int(os.getenv('DB_PORT', '5432')),
        }
    }
    
    # SQL Server credentials (check if we're migrating from SQL Server)
    sqlserver_server = os.getenv('SQLSERVER_HOST')
    if sqlserver_server:
        config['sqlserver'] = {
            'server': sqlserver_server,
            'user': os.getenv('SQLSERVER_USER', 'sa'),
            'password': os.getenv('SQLSERVER_PASS', ''),
            'database': os.getenv('SQLSERVER_DB', 'ForexBrainDB'),
            'port': int(os.getenv('SQLSERVER_PORT', '1433')),
        }
    
    return config


def query_postgres(query: str, config: Dict) -> List[tuple]:
    """Execute query on PostgreSQL"""
    try:
        conn = psycopg2.connect(**config['postgres'])
        cursor = conn.cursor()
        cursor.execute(query)
        results = cursor.fetchall()
        conn.close()
        return results
    except psycopg2.Error as e:
        raise Exception(f"PostgreSQL error: {e}")


def execute_postgres(sql: str, params: Optional[List] = None, config: Dict = None) -> int:
    """Execute SQL statement on PostgreSQL"""
    try:
        conn = psycopg2.connect(**config['postgres'])
        cursor = conn.cursor()
        
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        
        conn.commit()
        rows_affected = cursor.rowcount
        conn.close()
        return rows_affected
    except psycopg2.Error as e:
        raise Exception(f"PostgreSQL error: {e}")


def check_table_exists_postgres(table_name: str, config: Dict) -> bool:
    """Check if table exists in PostgreSQL"""
    try:
        result = query_postgres(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s)",
            config
        )
        return bool(result[0][0])
    except:
        return False


def seed_default_data(config: Dict):
    """Seed default reference data if tables are empty"""
    logger.info("\nSeeding default data...")
    
    # Check if Dim_Asset is empty
    result = query_postgres(
        "SELECT COUNT(*) FROM Dim_Asset",
        config
    )
    
    if result[0][0] > 0:
        logger.info(f"{GREEN}✅ Dim_Asset already has data{END}")
        return
    
    logger.info("Populating Dim_Asset with default forex pairs...")
    
    default_assets = [
        (1, 'EUR_USD', 'Forex', True),
        (2, 'GBP_USD', 'Forex', True),
        (3, 'USD_JPY', 'Forex', True),
        (4, 'AUD_USD', 'Forex', True),
        (5, 'USD_CAD', 'Forex', True),
    ]
    
    try:
        conn = psycopg2.connect(**config['postgres'])
        cursor = conn.cursor()
        
        for asset_id, symbol, market_type, is_active in default_assets:
            cursor.execute(
                'INSERT INTO Dim_Asset (Asset_ID, Symbol, Market_Type, Is_Active) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING',
                (asset_id, symbol, market_type, is_active)
            )
        
        conn.commit()
        conn.close()
        
        logger.info(f"{GREEN}✅ Default assets created (5 forex pairs){END}")
    except Exception as e:
        logger.error(f"{RED}❌ Error seeding data: {e}{END}")


def migrate_from_sqlserver(config: Dict, tables: Optional[List[str]] = None, dry_run: bool = False):
    """Migrate data from SQL Server to PostgreSQL"""
    
    if 'sqlserver' not in config:
        logger.warning(f"{YELLOW}SQL Server not configured in .env (SQLSERVER_* variables){END}")
        logger.info("Skipping SQL Server migration")
        logger.info("To migrate from SQL Server, set these env variables:")
        logger.info("  SQLSERVER_HOST=your_server")
        logger.info("  SQLSERVER_USER=your_user")
        logger.info("  SQLSERVER_PASS=your_password")
        logger.info("  SQLSERVER_DB=ForexBrainDB")
        return
    
    if not PYMSSQL_AVAILABLE:
        logger.error(f"{RED}❌ pymssql not available. Cannot migrate from SQL Server.{END}")
        return
    
    logger.info(f"\n{BLUE}Connecting to SQL Server...{END}")
    
    try:
        sqlserver_config = config['sqlserver']
        sql_conn = pymssql.connect(
            server=sqlserver_config['server'],
            port=sqlserver_config['port'],
            user=sqlserver_config['user'],
            password=sqlserver_config['password'],
            database=sqlserver_config['database']
        )
        logger.info(f"{GREEN}✅ Connected to SQL Server{END}")
    except Exception as e:
        logger.error(f"{RED}❌ Failed to connect to SQL Server: {e}{END}")
        logger.info("Skipping SQL Server data migration")
        return
    
    tables_to_migrate = tables or MIGRATION_ORDER
    results = {}
    
    for table_name in tables_to_migrate:
        logger.info(f"\nMigrating {table_name}...")
        
        try:
            # Get data from SQL Server
            cursor = sql_conn.cursor(as_dict=False)
            cursor.execute(f"SELECT * FROM {table_name}")
            rows = cursor.fetchall()
            
            # Get column names
            cursor.execute(f"""
                SELECT COLUMN_NAME 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = '{table_name}'
                ORDER BY ORDINAL_POSITION
            """)
            columns = [row[0] for row in cursor.fetchall()]
            
            if not rows:
                logger.info(f"  No data to migrate (table is empty)")
                results[table_name] = 0
                continue
            
            logger.info(f"  Found {len(rows)} rows with {len(columns)} columns")
            
            if dry_run:
                logger.info(f"  DRY RUN: Would migrate {len(rows)} rows")
                results[table_name] = len(rows)
                continue
            
            # Insert into PostgreSQL
            conn = psycopg2.connect(**config['postgres'])
            cursor_pg = conn.cursor()
            
            col_names = ','.join([f'"{col}"' for col in columns])
            placeholders = ','.join(['%s'] * len(columns))
            query = f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
            
            batch_size = 1000
            for i in range(0, len(rows), batch_size):
                batch = rows[i:i+batch_size]
                try:
                    cursor_pg.executemany(query, batch)
                    conn.commit()
                except Exception as e:
                    logger.warning(f"  Warning during batch insert: {e}")
                    conn.commit()
            
            conn.close()
            logger.info(f"  {GREEN}✅ Migrated {len(rows)} rows{END}")
            results[table_name] = len(rows)
            
        except Exception as e:
            logger.error(f"  {RED}❌ Error: {e}{END}")
            results[table_name] = -1
    
    sql_conn.close()
    return results


def print_summary(results: Dict[str, int]):
    """Print migration summary"""
    logger.info(f"\n{BLUE}{'='*60}")
    logger.info("MIGRATION SUMMARY")
    logger.info(f"{'='*60}{END}\n")
    
    total_rows = 0
    success_tables = 0
    failed_tables = []
    
    for table_name, count in results.items():
        if count == -1:
            status = f"{RED}❌ FAIL{END}"
            failed_tables.append(table_name)
        elif count == 0:
            status = "⊘ EMPTY"
        else:
            status = f"{GREEN}✅{END}"
            total_rows += count
            success_tables += 1
        
        logger.info(f"  {status} {table_name:40} | {count:>10,} rows")
    
    logger.info(f"{'='*60}")
    logger.info(f"Total: {success_tables} tables, {total_rows:,} rows")
    
    if failed_tables:
        logger.warning(f"Failed: {', '.join(failed_tables)}")


def main():
    parser = argparse.ArgumentParser(description='Migrate data to PostgreSQL')
    parser.add_argument('--dry-run', action='store_true', help='Preview without migrating')
    parser.add_argument('--tables', nargs='+', help='Specific tables to migrate')
    parser.add_argument('--seed-only', action='store_true', help='Only seed default data')
    args = parser.parse_args()
    
    logger.info(f"{BLUE}{'='*60}")
    logger.info("NATIVE DATABASE MIGRATION")
    logger.info(f"{'='*60}{END}\n")
    
    # Load config
    config = load_config()
    
    logger.info(f"PostgreSQL: {config['postgres']['host']}:{config['postgres']['port']}/{config['postgres']['dbname']}")
    
    if args.seed_only:
        # Just seed default data
        if check_table_exists_postgres('Dim_Asset', config):
            seed_default_data(config)
            logger.info(f"{GREEN}✅ Seed complete{END}")
            return 0
        else:
            logger.error(f"{RED}❌ Table Dim_Asset does not exist (initialize schema first){END}")
            return 1
    
    # Migrate from SQL Server
    results = migrate_from_sqlserver(config, args.tables, args.dry_run)
    
    if results:
        print_summary(results)
    
    # Seed default data
    if not args.dry_run and check_table_exists_postgres('Dim_Asset', config):
        seed_default_data(config)
    
    logger.info(f"\n{GREEN}✅ Migration complete{END}\n")
    return 0


if __name__ == '__main__':
    sys.exit(main())
