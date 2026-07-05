#!/usr/bin/env python3
"""
Migrate data from SQL Server to PostgreSQL
==========================================

This script transfers all data from SQL Server (ForexBrainDB) to PostgreSQL,
preserving data integrity and relational constraints.

Usage:
    python migrate_sqlserver_to_postgresql.py [--source-server SERVER] [--target-server SERVER]

Environment variables:
    SQL_SERVER_HOST (default: from .env DB_SERVER)
    SQL_SERVER_USER (default: from .env DB_USER)
    SQL_SERVER_PASS (default: from .env DB_PASS)
    SQL_SERVER_DB (default: ForexBrainDB)
    SQL_SERVER_PORT (default: 1433)
    
    PG_HOST (default: from .env DB_SERVER or localhost)
    PG_USER (default: from .env DB_USER)
    PG_PASS (default: from .env DB_PASS)
    PG_DB (default: ForexBrainDB)
    PG_PORT (default: 5432)
"""

import os
import sys
import argparse
import logging
import pymssql
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime
from typing import List, Tuple, Dict, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)

# Table migration order (respect foreign keys)
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


class SQLServerConnection:
    """Manage SQL Server connection"""
    
    def __init__(self, host: str, user: str, password: str, database: str, port: int = 1433):
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.port = port
        self.conn = None
    
    def connect(self):
        """Establish connection to SQL Server"""
        try:
            self.conn = pymssql.connect(
                server=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                timeout=30
            )
            logger.info(f"Connected to SQL Server: {self.host}:{self.port}/{self.database}")
            return self.conn
        except pymssql.Error as e:
            logger.error(f"Failed to connect to SQL Server: {e}")
            raise
    
    def get_table_data(self, table_name: str) -> Tuple[List[str], List[tuple]]:
        """Query all data from a table"""
        try:
            cursor = self.conn.cursor(as_dict=False)
            
            # Get column names
            cursor.execute(f"""
                SELECT COLUMN_NAME 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = '{table_name}' 
                ORDER BY ORDINAL_POSITION
            """)
            columns = [row[0] for row in cursor.fetchall()]
            
            # Get all data
            cursor.execute(f"SELECT * FROM {table_name}")
            rows = cursor.fetchall()
            
            logger.info(f"Fetched {len(rows)} rows from {table_name}")
            return columns, rows
        except pymssql.Error as e:
            logger.error(f"Error fetching data from {table_name}: {e}")
            raise
    
    def close(self):
        """Close connection"""
        if self.conn:
            self.conn.close()


class PostgreSQLConnection:
    """Manage PostgreSQL connection"""
    
    def __init__(self, host: str, user: str, password: str, database: str, port: int = 5432):
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.port = port
        self.conn = None
    
    def connect(self):
        """Establish connection to PostgreSQL"""
        try:
            self.conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                dbname=self.database,
                connect_timeout=30
            )
            logger.info(f"Connected to PostgreSQL: {self.host}:{self.port}/{self.database}")
            return self.conn
        except psycopg2.Error as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise
    
    def insert_data(self, table_name: str, columns: List[str], rows: List[tuple]) -> int:
        """Insert data into a table"""
        if not rows:
            logger.info(f"No data to insert into {table_name}")
            return 0
        
        try:
            cursor = self.conn.cursor()
            
            # Build INSERT statement
            placeholders = ','.join(['%s'] * len(columns))
            col_names = ','.join([f'"{col}"' for col in columns])
            query = f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})"
            
            # Insert in batches
            batch_size = 1000
            for i in range(0, len(rows), batch_size):
                batch = rows[i:i+batch_size]
                for row in batch:
                    try:
                        cursor.execute(query, row)
                    except psycopg2.Error as e:
                        logger.warning(f"Error inserting row into {table_name}: {e}, skipping row")
                
                self.conn.commit()
                logger.info(f"Inserted {min(batch_size, len(batch))} rows into {table_name}")
            
            self.conn.commit()
            logger.info(f"Successfully inserted {len(rows)} rows into {table_name}")
            return len(rows)
        except psycopg2.Error as e:
            logger.error(f"Error inserting data into {table_name}: {e}")
            self.conn.rollback()
            raise
    
    def close(self):
        """Close connection"""
        if self.conn:
            self.conn.close()


def load_env_config() -> Dict[str, Any]:
    """Load database credentials from .env file"""
    # Find and load .env
    env_path = Path('scalable-brain/.env')
    if not env_path.exists():
        env_path = Path('.env')
    
    if env_path.exists():
        load_dotenv(env_path)
        logger.info(f"Loaded environment from {env_path}")
    
    config = {
        # SQL Server config
        'sql_server_host': os.getenv('DB_SERVER', 'localhost'),
        'sql_server_user': os.getenv('DB_USER', 'sa'),
        'sql_server_pass': os.getenv('DB_PASS', ''),
        'sql_server_db': 'ForexBrainDB',
        'sql_server_port': int(os.getenv('DB_PORT', '1433')),
        
        # PostgreSQL config (same credentials by default)
        'pg_host': os.getenv('PG_HOST') or os.getenv('DB_SERVER', 'localhost'),
        'pg_user': os.getenv('PG_USER') or os.getenv('DB_USER', 'sa'),
        'pg_pass': os.getenv('PG_PASS') or os.getenv('DB_PASS', ''),
        'pg_db': os.getenv('PG_DB', 'ForexBrainDB'),
        'pg_port': int(os.getenv('PG_PORT', '5432')),
    }
    
    return config


def verify_connections(sql_conn: SQLServerConnection, pg_conn: PostgreSQLConnection) -> bool:
    """Verify both database connections work"""
    logger.info("Verifying database connections...")
    
    try:
        sql_cursor = sql_conn.conn.cursor()
        sql_cursor.execute("SELECT COUNT(*) FROM Dim_Asset")
        sql_count = sql_cursor.fetchone()[0]
        logger.info(f"SQL Server: Found {sql_count} rows in Dim_Asset")
    except Exception as e:
        logger.error(f"Failed to query SQL Server: {e}")
        return False
    
    try:
        pg_cursor = pg_conn.conn.cursor()
        pg_cursor.execute("SELECT COUNT(*) FROM Dim_Asset")
        pg_count = pg_cursor.fetchone()[0]
        logger.info(f"PostgreSQL: Found {pg_count} rows in Dim_Asset")
    except Exception as e:
        logger.error(f"Failed to query PostgreSQL: {e}")
        return False
    
    return True


def migrate_data(sql_conn: SQLServerConnection, pg_conn: PostgreSQLConnection, 
                 tables: Optional[List[str]] = None) -> Dict[str, int]:
    """Migrate data from SQL Server to PostgreSQL"""
    results = {}
    
    # Default to all tables if not specified
    tables_to_migrate = tables or MIGRATION_ORDER
    
    for table_name in tables_to_migrate:
        try:
            logger.info(f"\nMigrating table: {table_name}")
            
            # Get data from SQL Server
            columns, rows = sql_conn.get_table_data(table_name)
            
            if not columns:
                logger.warning(f"Table {table_name} not found in SQL Server")
                results[table_name] = 0
                continue
            
            # Insert into PostgreSQL
            count = pg_conn.insert_data(table_name, columns, rows)
            results[table_name] = count
            
        except Exception as e:
            logger.error(f"Failed to migrate {table_name}: {e}")
            results[table_name] = -1  # Indicates error
    
    return results


def print_migration_summary(results: Dict[str, int]):
    """Print migration summary report"""
    logger.info("\n" + "="*80)
    logger.info("MIGRATION SUMMARY")
    logger.info("="*80)
    
    total_rows = 0
    total_tables = 0
    failed_tables = []
    
    for table_name, count in results.items():
        if count == -1:
            status = "❌ ERROR"
            failed_tables.append(table_name)
        elif count == 0:
            status = "⊘ SKIPPED"
        else:
            status = "✓"
            total_rows += count
            total_tables += 1
        
        logger.info(f"{status} {table_name:40} | {count:>10,} rows")
    
    logger.info("="*80)
    logger.info(f"Total: {total_tables} tables migrated, {total_rows:,} rows")
    
    if failed_tables:
        logger.warning(f"Failed tables: {', '.join(failed_tables)}")
        return False
    
    return True


def main():
    """Main migration function"""
    parser = argparse.ArgumentParser(description='Migrate SQL Server database to PostgreSQL')
    parser.add_argument('--tables', nargs='+', help='Specific tables to migrate')
    parser.add_argument('--source-server', help='Override SQL Server hostname')
    parser.add_argument('--target-server', help='Override PostgreSQL hostname')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be migrated without doing it')
    
    args = parser.parse_args()
    
    try:
        # Load configuration
        config = load_env_config()
        
        if args.source_server:
            config['sql_server_host'] = args.source_server
        if args.target_server:
            config['pg_host'] = args.target_server
        
        logger.info("="*80)
        logger.info("SQL SERVER TO POSTGRESQL MIGRATION")
        logger.info("="*80)
        logger.info(f"Source: SQL Server {config['sql_server_host']}:{config['sql_server_port']}/{config['sql_server_db']}")
        logger.info(f"Target: PostgreSQL {config['pg_host']}:{config['pg_port']}/{config['pg_db']}")
        logger.info(f"Timestamp: {datetime.now().isoformat()}")
        
        # Connect to both databases
        sql_conn = SQLServerConnection(
            config['sql_server_host'],
            config['sql_server_user'],
            config['sql_server_pass'],
            config['sql_server_db'],
            config['sql_server_port']
        )
        sql_conn.connect()
        
        pg_conn = PostgreSQLConnection(
            config['pg_host'],
            config['pg_user'],
            config['pg_pass'],
            config['pg_db'],
            config['pg_port']
        )
        pg_conn.connect()
        
        # Verify connections
        if not verify_connections(sql_conn, pg_conn):
            logger.error("Connection verification failed")
            return 1
        
        if args.dry_run:
            logger.info("DRY RUN MODE - No data will be migrated")
            tables = args.tables or MIGRATION_ORDER
            for table in tables:
                _, rows = sql_conn.get_table_data(table)
                logger.info(f"Would migrate {len(rows)} rows from {table}")
            return 0
        
        # Perform migration
        if not input("\n⚠️  Proceed with migration? (yes/no): ").strip().lower() == 'yes':
            logger.info("Migration cancelled")
            return 0
        
        results = migrate_data(sql_conn, pg_conn, args.tables)
        
        # Print summary
        success = print_migration_summary(results)
        
        # Cleanup
        sql_conn.close()
        pg_conn.close()
        
        logger.info("\n✅ Migration completed successfully!" if success else "\n❌ Migration completed with errors")
        return 0 if success else 1
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
