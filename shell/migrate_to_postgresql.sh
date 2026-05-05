#!/bin/bash
# PostgreSQL Migration Script - Automates SQL Server to PostgreSQL migration
# Usage: ./migrate_to_postgresql.sh [options]
# Options:
#   --migrate-data     Also migrate data from SQL Server
#   --force           Skip confirmations
#   --docker-only     Only setup Docker (skip data migration)

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCALABLE_BRAIN_DIR="${PROJECT_ROOT}/scalable-brain"
VENV_PATH="${PROJECT_ROOT}/.venv"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Flags
MIGRATE_DATA=false
FORCE_MODE=false
DOCKER_ONLY=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --migrate-data)
            MIGRATE_DATA=true
            shift
            ;;
        --force)
            FORCE_MODE=true
            shift
            ;;
        --docker-only)
            DOCKER_ONLY=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Functions
print_header() {
    echo -e "\n${BLUE}════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════${NC}\n"
}

print_step() {
    echo -e "\n${YELLOW}📋 $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

confirm() {
    if [ "$FORCE_MODE" = true ]; then
        return 0
    fi
    read -p "$1 (yes/no): " -r
    [[ $REPLY =~ ^[Yy][Ee][Ss]?$ ]]
}

# Main migration process
main() {
    print_header "SCALABLE BRAIN - POSTGRESQL MIGRATION"
    
    # Step 1: Verify environment
    print_step "STEP 1: Verifying environment"
    
    if [ ! -f "${SCALABLE_BRAIN_DIR}/.env" ]; then
        print_error ".env file not found at ${SCALABLE_BRAIN_DIR}/.env"
        echo "Create .env with required database credentials:"
        cat << 'EOF'
DB_SERVER=localhost
DB_USER=sa
DB_PASS=your_secure_password
DB_NAME=ForexBrainDB
DB_PORT=5432
EOF
        exit 1
    fi
    
    # Load environment
    source "${SCALABLE_BRAIN_DIR}/.env"
    print_success ".env loaded"
    
    # Step 2: Setup Python environment
    print_step "STEP 2: Setting up Python environment"
    
    if [ ! -d "${VENV_PATH}" ]; then
        echo "Creating virtual environment..."
        python3 -m venv "${VENV_PATH}"
        print_success "Virtual environment created"
    fi
    
    source "${VENV_PATH}/bin/activate"
    print_success "Virtual environment activated"
    
    # Install dependencies
    echo "Installing dependencies..."
    pip install -q --upgrade pip
    pip install -q -r "${SCALABLE_BRAIN_DIR}/requirements.txt"
    print_success "Dependencies installed"
    
    # Step 3: Docker setup
    print_step "STEP 3: Docker - PostgreSQL + TimescaleDB"
    
    cd "${SCALABLE_BRAIN_DIR}"
    
    echo "Checking if PostgreSQL container is running..."
    if ! docker-compose ps | grep -q "postgres.*Up"; then
        echo "Starting PostgreSQL container..."
        docker-compose up -d postgres
        
        echo "Waiting for PostgreSQL to be ready..."
        sleep 10
        
        # Wait for health check
        for i in {1..30}; do
            if docker-compose exec -T postgres pg_isready -U sa -d ForexBrainDB > /dev/null 2>&1; then
                print_success "PostgreSQL is ready"
                break
            fi
            if [ $i -eq 30 ]; then
                print_error "PostgreSQL did not start in time"
                exit 1
            fi
            echo "  Waiting... ($i/30)"
            sleep 2
        done
    else
        print_success "PostgreSQL container already running"
    fi
    
    # Verify schema initialization
    echo "Verifying schema initialization..."
    table_count=$(docker-compose exec -T postgres psql -U sa -d ForexBrainDB -t -c \
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'" 2>/dev/null || echo "0")
    
    if [ "$table_count" -lt 10 ]; then
        echo "Database schema not fully initialized, running init script..."
        docker-compose exec -T postgres psql -U sa -d ForexBrainDB < "${SCALABLE_BRAIN_DIR}/init-db/01-create-database.sql"
        print_success "Schema initialized"
    else
        print_success "Schema already initialized ($table_count tables found)"
    fi
    
    # Step 4: Data migration (optional)
    if [ "$DOCKER_ONLY" != true ] && [ "$MIGRATE_DATA" = true ]; then
        print_step "STEP 4: Migrating data from SQL Server to PostgreSQL"
        
        echo "This will migrate all data from SQL Server to PostgreSQL."
        if ! confirm "Continue with data migration?"; then
            print_error "Data migration skipped"
        else
            echo "Starting migration..."
            python "${SCALABLE_BRAIN_DIR}/src/sql/migrate_sqlserver_to_postgresql.py" || {
                print_error "Data migration failed"
                exit 1
            }
            print_success "Data migration completed"
        fi
    fi
    
    # Step 5: Verification
    print_step "STEP 5: Verifying migration"
    
    echo "Testing database connection..."
    python << 'VERIFY_EOF'
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv('scalable-brain/.env')

try:
    conn = psycopg2.connect(
        host=os.getenv('DB_SERVER', 'localhost'),
        dbname=os.getenv('DB_NAME', 'ForexBrainDB'),
        user=os.getenv('DB_USER', 'sa'),
        password=os.getenv('DB_PASS'),
        port=int(os.getenv('DB_PORT', '5432'))
    )
    
    cursor = conn.cursor()
    
    # Check tables
    cursor.execute("""
        SELECT COUNT(*) FROM information_schema.tables 
        WHERE table_schema='public'
    """)
    table_count = cursor.fetchone()[0]
    
    # Check sample data
    cursor.execute("SELECT COUNT(*) FROM Dim_Asset")
    asset_count = cursor.fetchone()[0]
    
    print(f"✅ Connection successful")
    print(f"   - Tables: {table_count}")
    print(f"   - Assets: {asset_count}")
    
    conn.close()
except Exception as e:
    print(f"❌ Connection failed: {e}")
    import sys
    sys.exit(1)
VERIFY_EOF
    
    if [ $? -ne 0 ]; then
        exit 1
    fi
    
    print_success "Database verification passed"
    
    # Step 6: Summary
    print_header "MIGRATION COMPLETED SUCCESSFULLY"
    
    echo "Next steps:"
    echo "  1. Test Layer 0 (data ingestion):"
    echo "     python scalable-brain/src/layer0/ingest_data/ingest_oanda_prices.py --symbols EUR_USD --granularities H4"
    echo ""
    echo "  2. Test Layer 5 (API dashboard):"
    echo "     python scalable-brain/src/layer5/run.py"
    echo "     # Visit http://localhost:8001"
    echo ""
    echo "  3. View Docker logs:"
    echo "     docker-compose logs -f postgres"
    echo ""
    echo "✅ All done! Your system is now running on PostgreSQL."
}

# Run main function
main
