#!/bin/bash
# =============================================================================
# MIGRATION EXECUTION HELPER SCRIPT
# =============================================================================
# Execute Fact_Live_Trades schema migration via sqlcmd
#
# This script:
# 1. Runs pre-migration verification
# 2. Executes the main migration
# 3. Runs post-migration verification
#
# Requirements:
# - sqlcmd command available (SQL Server tools installed)
# - .env file with DB credentials in project root
# - MSSQL instance running and accessible
#
# Usage:
#   ./execute_migration.sh          # Interactive mode (asks for confirmations)
#   ./execute_migration.sh --force   # Non-interactive (runs all steps)
# =============================================================================

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_PATH="${PROJECT_ROOT}/.venv"
MIGRATIONS_DIR="${PROJECT_ROOT}/scalable-brain/src/sql/migrations"

# Load environment variables
if [ -f "${PROJECT_ROOT}/scalable-brain/.env" ]; then
    source "${PROJECT_ROOT}/scalable-brain/.env"
else
    echo "❌ ERROR: .env file not found at ${PROJECT_ROOT}/scalable-brain/.env"
    echo "Please create .env with: DB_SERVER, DB_USER, DB_PASS, DB_NAME, DB_PORT"
    exit 1
fi

# Validate required env vars
if [ -z "$DB_SERVER" ] || [ -z "$DB_USER" ] || [ -z "$DB_PASS" ] || [ -z "$DB_NAME" ]; then
    echo "❌ ERROR: Missing required environment variables"
    echo "Required: DB_SERVER, DB_USER, DB_PASS, DB_NAME"
    exit 1
fi

# Set port default
DB_PORT="${DB_PORT:-1433}"

# Build sqlcmd connection string
SQLCMD_CONN="-S ${DB_SERVER},${DB_PORT} -U ${DB_USER} -P ${DB_PASS} -d ${DB_NAME}"

echo "=============================================================================="
echo "FACT_LIVE_TRADES SCHEMA MIGRATION"
echo "=============================================================================="
echo ""
echo "Target: ${DB_SERVER}:${DB_PORT} / ${DB_NAME}"
echo "Migrations directory: ${MIGRATIONS_DIR}"
echo ""

# Parse arguments
FORCE_MODE=${1:-""}

# Step 1: Pre-migration verification
echo "📋 STEP 1: PRE-MIGRATION VERIFICATION"
echo "════════════════════════════════════"

if [ "$FORCE_MODE" != "--force" ]; then
    read -p "Run pre-migration schema check? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Skipped"
    else
        if sqlcmd $SQLCMD_CONN -i "${MIGRATIONS_DIR}/00_verify_schema_before_migration.sql"; then
            echo "✓ Pre-migration check complete"
        else
            echo "✗ Pre-migration check failed"
            exit 1
        fi
    fi
else
    if sqlcmd $SQLCMD_CONN -i "${MIGRATIONS_DIR}/00_verify_schema_before_migration.sql"; then
        echo "✓ Pre-migration check complete"
    else
        echo "✗ Pre-migration check failed"
        exit 1
    fi
fi

echo ""
echo "📋 STEP 2: EXECUTE MAIN MIGRATION"
echo "════════════════════════════════════"

if [ "$FORCE_MODE" != "--force" ]; then
    echo ""
    echo "⚠️  WARNING: This migration will:"
    echo "   - Create backup of existing data (Fact_Live_Trades_Backup)"
    echo "   - Reconstruct Fact_Live_Trades table with Trade_ID primary key"
    echo "   - Migrate all existing records (if any)"
    echo "   - Create new indexes for performance"
    echo ""
    read -p "Proceed with migration? (yes/no) " -r
    echo
    if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        echo "❌ Migration cancelled"
        exit 1
    fi
fi

echo "Executing migration..."
if sqlcmd $SQLCMD_CONN -i "${MIGRATIONS_DIR}/fix_schema_trade_id_2026_04_05.sql"; then
    echo "✓ Migration completed successfully"
else
    echo "✗ Migration failed"
    exit 1
fi

echo ""
echo "📋 STEP 3: POST-MIGRATION VERIFICATION"
echo "════════════════════════════════════"

if [ "$FORCE_MODE" != "--force" ]; then
    read -p "Run post-migration verification? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Skipped"
    else
        if sqlcmd $SQLCMD_CONN -i "${MIGRATIONS_DIR}/01_verify_schema_after_migration.sql"; then
            echo "✓ Post-migration verification complete"
        else
            echo "✗ Post-migration verification failed"
            exit 1
        fi
    fi
else
    if sqlcmd $SQLCMD_CONN -i "${MIGRATIONS_DIR}/01_verify_schema_after_migration.sql"; then
        echo "✓ Post-migration verification complete"
    else
        echo "✗ Post-migration verification failed"
        exit 1
    fi
fi

echo ""
echo "=============================================================================="
echo "✅ MIGRATION COMPLETE"
echo "=============================================================================="
echo ""
echo "Next steps:"
echo "1. Database is now ready for Layer 4 live trading"
echo "2. Ensure .env has OANDA_API_KEY and account credentials"
echo "3. Run Layer 4 pipeline: python src/layer4_executor/live_pipeline.py"
echo ""
