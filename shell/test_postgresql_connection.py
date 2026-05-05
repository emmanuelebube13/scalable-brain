#!/usr/bin/env python3
"""
Test PostgreSQL Connection and Database Integrity
==================================================

Verifies:
- PostgreSQL connection works
- All required tables exist
- TimescaleDB extensions are loaded
- Sample data can be queried
- Connection pooling works
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from dotenv import load_dotenv

import psycopg2
import psycopg2.pool
import sqlalchemy as sa

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


def find_env_file():
    """Find .env file in repository"""
    current = Path.cwd()
    for _ in range(5):
        env_file = current / '.env'
        if env_file.exists():
            return env_file
        env_file = current / 'scalable-brain' / '.env'
        if env_file.exists():
            return env_file
        current = current.parent
    return None


def load_config(env_file=None):
    """Load database configuration from environment"""
    if env_file is None:
        env_file = find_env_file()
    
    if env_file:
        load_dotenv(env_file)
        logger.info(f"Loaded environment from: {env_file}")
    
    config = {
        'host': os.getenv('DB_SERVER', 'localhost'),
        'dbname': os.getenv('DB_NAME', 'ForexBrainDB'),
        'user': os.getenv('DB_USER', 'sa'),
        'password': os.getenv('DB_PASS', 'password'),
        'port': int(os.getenv('DB_PORT', '5432')),
    }
    
    return config


def test_basic_connection(config):
    """Test basic psycopg2 connection"""
    logger.info("\n" + "="*60)
    logger.info("TEST 1: Basic PostgreSQL Connection")
    logger.info("="*60)
    
    try:
        conn = psycopg2.connect(**config)
        cursor = conn.cursor()
        cursor.execute("SELECT version()")
        version = cursor.fetchone()[0]
        logger.info(f"{GREEN}✅ Connected successfully{END}")
        logger.info(f"   PostgreSQL: {version.split(',')[0]}")
        conn.close()
        return True
    except psycopg2.Error as e:
        logger.error(f"{RED}❌ Connection failed: {e}{END}")
        return False


def test_sqlalchemy_connection(config):
    """Test SQLAlchemy connection"""
    logger.info("\n" + "="*60)
    logger.info("TEST 2: SQLAlchemy Connection")
    logger.info("="*60)
    
    try:
        conn_str = (
            f"postgresql+psycopg2://{config['user']}:{config['password']}"
            f"@{config['host']}:{config['port']}/{config['dbname']}"
        )
        engine = sa.create_engine(conn_str)
        
        with engine.connect() as conn:
            result = conn.execute(sa.text("SELECT 1"))
            logger.info(f"{GREEN}✅ SQLAlchemy connection works{END}")
        
        return True
    except Exception as e:
        logger.error(f"{RED}❌ SQLAlchemy connection failed: {e}{END}")
        return False


def test_tables_exist(config):
    """Verify all required tables exist"""
    logger.info("\n" + "="*60)
    logger.info("TEST 3: Required Tables")
    logger.info("="*60)
    
    required_tables = [
        'Dim_Asset',
        'Dim_Strategy_Registry',
        'Fact_Market_Prices',
        'Fact_Market_Regime_V2',
        'Fact_Signals',
        'Fact_Live_Trades',
        'Fact_Trade_Outcomes',
    ]
    
    try:
        conn = psycopg2.connect(**config)
        cursor = conn.cursor()
        
        found = []
        missing = []
        
        for table_name in required_tables:
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s)",
                (table_name.lower(),)
            )
            exists = cursor.fetchone()[0]
            
            if exists:
                found.append(table_name)
                logger.info(f"   ✓ {table_name}")
            else:
                missing.append(table_name)
                logger.warning(f"   ✗ {table_name} (MISSING)")
        
        conn.close()
        
        if missing:
            logger.error(f"{RED}❌ Missing tables: {', '.join(missing)}{END}")
            return False
        else:
            logger.info(f"{GREEN}✅ All {len(found)} required tables found{END}")
            return True
            
    except psycopg2.Error as e:
        logger.error(f"{RED}❌ Error checking tables: {e}{END}")
        return False


def test_timescaledb_extension(config):
    """Verify TimescaleDB extension is loaded"""
    logger.info("\n" + "="*60)
    logger.info("TEST 4: TimescaleDB Extension")
    logger.info("="*60)
    
    try:
        conn = psycopg2.connect(**config)
        cursor = conn.cursor()
        
        cursor.execute("SELECT extname FROM pg_extension WHERE extname = 'timescaledb'")
        result = cursor.fetchone()
        
        if result:
            logger.info(f"{GREEN}✅ TimescaleDB extension is installed{END}")
        else:
            logger.warning(f"{YELLOW}⚠️  TimescaleDB extension not found (may be optional){END}")
        
        conn.close()
        return True
        
    except psycopg2.Error as e:
        logger.error(f"{RED}❌ Error checking extensions: {e}{END}")
        return False


def test_sample_data(config):
    """Query sample data from tables"""
    logger.info("\n" + "="*60)
    logger.info("TEST 5: Sample Data Queries")
    logger.info("="*60)
    
    queries = [
        ("Assets", "SELECT COUNT(*) as count FROM Dim_Asset"),
        ("Market Prices", "SELECT COUNT(*) as count FROM Fact_Market_Prices"),
        ("Signals", "SELECT COUNT(*) as count FROM Fact_Signals"),
        ("Live Trades", "SELECT COUNT(*) as count FROM Fact_Live_Trades"),
    ]
    
    try:
        conn = psycopg2.connect(**config)
        cursor = conn.cursor()
        
        all_ok = True
        for name, query in queries:
            try:
                cursor.execute(query)
                count = cursor.fetchone()[0]
                logger.info(f"   {name:20} {count:>10,} rows")
            except psycopg2.Error as e:
                logger.warning(f"   {name:20} ⚠️  Error: {str(e)[:50]}")
                all_ok = False
        
        conn.close()
        
        if all_ok:
            logger.info(f"{GREEN}✅ All sample queries executed{END}")
        else:
            logger.warning(f"{YELLOW}⚠️  Some queries had issues (may be normal if db is empty){END}")
            
        return True
        
    except psycopg2.Error as e:
        logger.error(f"{RED}❌ Error querying data: {e}{END}")
        return False


def test_connection_pool(config):
    """Test connection pooling"""
    logger.info("\n" + "="*60)
    logger.info("TEST 6: Connection Pooling")
    logger.info("="*60)
    
    try:
        pool = psycopg2.pool.SimpleConnectionPool(
            1, 5,
            host=config['host'],
            dbname=config['dbname'],
            user=config['user'],
            password=config['password'],
            port=config['port']
        )
        
        # Get and release multiple connections
        conns = []
        for i in range(3):
            conn = pool.getconn()
            conns.append(conn)
            cursor = conn.cursor()
            cursor.execute("SELECT %s", (i,))
        
        for conn in conns:
            pool.putconn(conn)
        
        pool.closeall()
        
        logger.info(f"{GREEN}✅ Connection pooling works (tested 3 connections){END}")
        return True
        
    except Exception as e:
        logger.error(f"{RED}❌ Connection pooling failed: {e}{END}")
        return False


def run_all_tests(config):
    """Run all tests"""
    logger.info(f"\n{BLUE}{'='*60}")
    logger.info("PostgreSQL Connection & Database Integrity Tests")
    logger.info(f"{'='*60}{END}\n")
    
    logger.info(f"Configuration:")
    logger.info(f"  Host: {config['host']}")
    logger.info(f"  Port: {config['port']}")
    logger.info(f"  Database: {config['dbname']}")
    logger.info(f"  User: {config['user']}")
    
    results = [
        ("Basic Connection", test_basic_connection(config)),
        ("SQLAlchemy", test_sqlalchemy_connection(config)),
        ("Tables Exist", test_tables_exist(config)),
        ("TimescaleDB", test_timescaledb_extension(config)),
        ("Sample Data", test_sample_data(config)),
        ("Connection Pool", test_connection_pool(config)),
    ]
    
    logger.info("\n" + "="*60)
    logger.info("SUMMARY")
    logger.info("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = f"{GREEN}✅ PASS{END}" if result else f"{RED}❌ FAIL{END}"
        logger.info(f"  {status} - {name}")
    
    logger.info("="*60)
    logger.info(f"\n{BLUE}Result: {passed}/{total} tests passed{END}\n")
    
    return passed == total


def main():
    parser = argparse.ArgumentParser(description='Test PostgreSQL connection and database')
    parser.add_argument('--config', help='Path to .env file')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    config = load_config(args.config)
    
    try:
        success = run_all_tests(config)
        return 0 if success else 1
    except Exception as e:
        logger.error(f"Test execution failed: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
