#!/usr/bin/env python3
"""
Native PostgreSQL Setup - No Docker Required
=============================================

This script:
1. Checks if PostgreSQL is installed and accessible
2. Creates the ForexBrainDB database if it doesn't exist
3. Creates the 'sa' user with password if needed
4. Initializes the schema from SQL file
5. Verifies everything works

Usage:
    python setup_postgresql_native.py
    python setup_postgresql_native.py --drop-existing  # Recreate database
"""

import os
import sys
import subprocess
import argparse
import logging
import time
from pathlib import Path
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
WORKSPACE_ROOT = REPO_ROOT.parent

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


def sql_literal(value):
    """Safely quote a SQL string literal."""
    return "'" + str(value).replace("'", "''") + "'"


def sql_ident(value):
    """Safely quote a SQL identifier."""
    return '"' + str(value).replace('"', '""') + '"'


def ensure_admin_access():
    """Ensure sudo credentials are available for postgres admin commands."""
    try:
        probe = subprocess.run(['sudo', '-n', 'true'], capture_output=True, text=True)
        if probe.returncode == 0:
            return True
    except Exception:
        pass

    logger.info("Requesting sudo access to run PostgreSQL admin commands...")
    auth = subprocess.run(['sudo', '-v'])
    if auth.returncode == 0:
        return True

    logger.error(f"{RED}❌ Sudo authentication failed. Cannot manage postgres superuser tasks.{END}")
    return False


def run_admin_psql(script, database='postgres', timeout=20):
    """Run SQL as postgres OS user via sudo + local peer auth."""
    cmd = [
        'sudo', '-n', '-u', 'postgres', 'psql',
        '-v', 'ON_ERROR_STOP=1',
        '-d', database,
        '-f', '-'
    ]
    return subprocess.run(
        cmd,
        input=script,
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def check_postgresql_installed():
    """Check if PostgreSQL is installed and accessible"""
    logger.info(f"\n{BLUE}Checking PostgreSQL installation...{END}")
    
    try:
        result = subprocess.run(['psql', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            version = result.stdout.strip()
            logger.info(f"{GREEN}✅ PostgreSQL found: {version}{END}")
            return True
    except FileNotFoundError:
        pass
    
    logger.error(f"{RED}❌ PostgreSQL not found. Install with:{END}")
    print("  Ubuntu/Debian: sudo apt install postgresql postgresql-contrib")
    print("  macOS: brew install postgresql")
    print("  Windows: Download from https://www.postgresql.org/download/windows/")
    return False


def load_env_config():
    """Load configuration from .env file"""
    env_candidates = [
        REPO_ROOT / '.env',
        WORKSPACE_ROOT / 'scalable-brain' / '.env',
        Path('.env'),
    ]
    env_file = next((p for p in env_candidates if p.exists()), None)
    
    if env_file:
        load_dotenv(env_file)
        logger.info(f"Loaded environment from {env_file}")
    
    return {
        'db_server': os.getenv('DB_SERVER', 'localhost'),
        'db_user': os.getenv('DB_USER', 'sa'),
        'db_pass': os.getenv('DB_PASS', 'password'),
        'db_name': os.getenv('DB_NAME', 'ForexBrainDB'),
        'db_port': os.getenv('DB_PORT', '5432'),
    }


def check_postgres_running():
    """Check if PostgreSQL service is running"""
    logger.info("\nChecking PostgreSQL service status...")

    try:
        result = subprocess.run(
            ['pg_isready', '-h', 'localhost', '-p', '5432'],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            logger.info(f"{GREEN}✅ PostgreSQL service is running{END}")
            return True
    except subprocess.TimeoutExpired:
        logger.warning(f"{YELLOW}⚠️  PostgreSQL not responding{END}")
    except Exception as e:
        logger.warning(f"{YELLOW}⚠️  Could not verify running status: {e}{END}")
    
    logger.info("Starting PostgreSQL service...")
    try:
        # Try systemctl (Linux)
        subprocess.run(['sudo', '-n', 'systemctl', 'start', 'postgresql'], check=False)
        time.sleep(3)
        ready = subprocess.run(['pg_isready', '-h', 'localhost', '-p', '5432'], capture_output=True, text=True)
        if ready.returncode == 0:
            logger.info(f"{GREEN}✅ PostgreSQL started{END}")
            return True
    except:
        pass
    
    try:
        # Try brew services (macOS)
        subprocess.run(['brew', 'services', 'start', 'postgresql'], 
                       capture_output=True, timeout=10)
        time.sleep(3)
        logger.info(f"{GREEN}✅ PostgreSQL started{END}")
        return True
    except:
        pass
    
    logger.warning(f"{YELLOW}⚠️  Could not start PostgreSQL. Please start it manually.{END}")
    return True  # Continue anyway - might already be running


def create_user_if_not_exists(config):
    """Create database user if it doesn't exist"""
    logger.info(f"\nChecking if user '{config['db_user']}' exists...")
    username = sql_ident(config['db_user'])
    username_lit = sql_literal(config['db_user'])
    password_lit = sql_literal(config['db_pass'])

    script = f"""
SELECT format(
    'CREATE ROLE %I LOGIN PASSWORD %L CREATEDB',
    {username_lit},
    {password_lit}
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {username_lit})
\\gexec
ALTER ROLE {username} WITH LOGIN PASSWORD {password_lit} CREATEDB;
"""

    try:
        result = run_admin_psql(script, database='postgres', timeout=20)
        if result.returncode == 0:
            logger.info(f"{GREEN}✅ User '{config['db_user']}' is ready{END}")
            return True

        logger.error(f"{RED}❌ Failed to create user: {result.stderr}{END}")
        return False

    except subprocess.TimeoutExpired:
        logger.error(f"{RED}❌ Command timed out{END}")
        return False
    except Exception as e:
        logger.error(f"{RED}❌ Error: {e}{END}")
        return False


def create_database_if_not_exists(config):
    """Create database if it doesn't exist"""
    logger.info(f"\nChecking if database '{config['db_name']}' exists...")
    db_name = sql_ident(config['db_name'])
    db_name_lit = sql_literal(config['db_name'])
    owner_name = sql_ident(config['db_user'])

    script = f"""
SELECT 'CREATE DATABASE {db_name} OWNER {owner_name}'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = {db_name_lit})
\\gexec
"""

    try:
        result = run_admin_psql(script, database='postgres', timeout=20)
        if result.returncode == 0:
            logger.info(f"{GREEN}✅ Database '{config['db_name']}' is ready{END}")
            return True

        logger.error(f"{RED}❌ Failed to create database: {result.stderr}{END}")
        return False

    except subprocess.TimeoutExpired:
        logger.error(f"{RED}❌ Command timed out{END}")
        return False
    except Exception as e:
        logger.error(f"{RED}❌ Error: {e}{END}")
        return False


def initialize_schema(config):
    """Initialize database schema from SQL file"""
    logger.info(f"\nInitializing database schema...")
    
    schema_file = REPO_ROOT / 'init-db' / '01-create-database.sql'
    if not schema_file.exists():
        logger.error(f"{RED}❌ Schema file not found: {schema_file}{END}")
        return False
    
    try:
        with open(schema_file, 'r') as f:
            sql_content = f.read()

        def run_schema(content):
            return subprocess.run(
                ['psql', '-v', 'ON_ERROR_STOP=1', '-h', config['db_server'], '-U', config['db_user'],
                 '-d', config['db_name']],
                input=content,
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, 'PGPASSWORD': config['db_pass']}
            )

        # First attempt: full schema (with TimescaleDB)
        result = run_schema(sql_content)

        if result.returncode == 0:
            logger.info(f"{GREEN}✅ Schema initialized successfully{END}")
            return True

        # If TimescaleDB isn't preloaded, retry without Timescale-specific statements.
        lowered_err = (result.stderr or '').lower()
        if 'timescaledb' in lowered_err and 'must be preloaded' in lowered_err:
            logger.warning(f"{YELLOW}⚠️  TimescaleDB not preloaded. Retrying with plain PostgreSQL schema...{END}")
            filtered_lines = []
            for line in sql_content.splitlines():
                stripped = line.strip().lower()
                if stripped.startswith('create extension') and 'timescaledb' in stripped:
                    continue
                if stripped.startswith('select create_hypertable'):
                    continue
                filtered_lines.append(line)

            fallback_sql = '\n'.join(filtered_lines) + '\n'
            retry = run_schema(fallback_sql)
            if retry.returncode == 0:
                logger.info(f"{GREEN}✅ Schema initialized successfully (plain PostgreSQL mode){END}")
                return True

            logger.error(f"{RED}❌ Schema initialization failed in fallback mode:{END}")
            print(retry.stderr)
            return False

        logger.error(f"{RED}❌ Schema initialization failed:{END}")
        print(result.stderr)
        return False
        
    except subprocess.TimeoutExpired:
        logger.error(f"{RED}❌ Schema initialization timed out{END}")
        return False
    except Exception as e:
        logger.error(f"{RED}❌ Error: {e}{END}")
        return False


def verify_connection(config):
    """Verify database connection works"""
    logger.info(f"\nVerifying connection...")
    
    try:
        result = subprocess.run(
            ['psql', '-h', config['db_server'], '-U', config['db_user'],
             '-d', config['db_name'], '-c', 'SELECT COUNT(*) FROM Dim_Asset;'],
            capture_output=True,
            text=True,
            timeout=10,
            env={**os.environ, 'PGPASSWORD': config['db_pass']}
        )
        
        if result.returncode == 0:
            logger.info(f"{GREEN}✅ Connection verified successfully{END}")
            return True
        
        logger.error(f"{RED}❌ Connection failed: {result.stderr}{END}")
        return False
        
    except subprocess.TimeoutExpired:
        logger.error(f"{RED}❌ Connection test timed out{END}")
        return False
    except Exception as e:
        logger.error(f"{RED}❌ Error: {e}{END}")
        return False


def drop_database_and_user(config):
    """Drop database and user (careful!)"""
    logger.warning(f"\n{RED}Dropping database and user...{END}")
    db_name = sql_ident(config['db_name'])
    user_name = sql_ident(config['db_user'])
    script = f"""
DROP DATABASE IF EXISTS {db_name};
DROP ROLE IF EXISTS {user_name};
"""

    try:
        logger.info(f"Dropping database '{config['db_name']}' and user '{config['db_user']}'...")
        result = run_admin_psql(script, database='postgres', timeout=20)
        if result.returncode != 0:
            logger.error(f"{RED}❌ Failed to drop database/user: {result.stderr}{END}")
            return False
        logger.info(f"{GREEN}✅ Database and user dropped{END}")
        return True

    except Exception as e:
        logger.error(f"{RED}❌ Error: {e}{END}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Setup native PostgreSQL for Scalable Brain')
    parser.add_argument('--drop-existing', action='store_true', 
                       help='Drop existing database and user first')
    args = parser.parse_args()
    
    logger.info(f"{BLUE}{'='*60}")
    logger.info("NATIVE POSTGRESQL SETUP (NO DOCKER)")
    logger.info(f"{'='*60}{END}\n")
    
    # Step 1: Check PostgreSQL installed
    if not check_postgresql_installed():
        return 1
    
    # Step 2: Load configuration
    config = load_env_config()
    logger.info(f"\nConfiguration:")
    logger.info(f"  Server: {config['db_server']}")
    logger.info(f"  Port: {config['db_port']}")
    logger.info(f"  Database: {config['db_name']}")
    logger.info(f"  User: {config['db_user']}")

    # Step 2.5: Ensure sudo access for postgres admin tasks
    if not ensure_admin_access():
        return 1
    
    # Step 3: Ensure PostgreSQL is running
    check_postgres_running()
    
    # Step 4: Drop existing if requested
    if args.drop_existing:
        if drop_database_and_user(config):
            import time
            time.sleep(2)
    
    # Step 5: Create user
    if not create_user_if_not_exists(config):
        return 1
    
    # Step 6: Create database
    if not create_database_if_not_exists(config):
        return 1
    
    # Step 7: Initialize schema
    if not initialize_schema(config):
        logger.warning(f"{YELLOW}⚠️  Schema initialization had issues, but continuing...{END}")
    
    # Step 8: Verify connection
    if verify_connection(config):
        logger.info(f"\n{BLUE}{'='*60}")
        logger.info("✅ POSTGRESQL SETUP COMPLETED SUCCESSFULLY")
        logger.info(f"{'='*60}{END}\n")
        logger.info("Next steps:")
        logger.info("  1. Migrate data: python migrate_data_native.py")
        logger.info("  2. Test: python test_postgresql_connection.py")
        logger.info("  3. Run layers: python src/layer0/ingest_data/ingest_oanda_prices.py")
        return 0
    else:
        logger.error(f"\n{RED}Connection verification failed{END}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
