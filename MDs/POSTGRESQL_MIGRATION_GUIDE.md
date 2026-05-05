# PostgreSQL Migration Guide - Scalable Brain Swing Trading System

> **SWING TRADING SYSTEM** | Infrastructure migration for multi-timeframe swing trade signal persistence

##  Overview

This guide covers migrating from **SQL Server** to **PostgreSQL** with **TimescaleDB** extension for the Scalable Brain swing trading system.

**Trading Type:** Swing Trading | **Database Focus:** Real-time price ingestion + signal/outcome persistence

- **Database**: ForexBrainDB
- **Target**: PostgreSQL 16 + TimescaleDB
- **Downtime**: ~5-15 minutes
- **Data Loss Risk**: None (backup created before migration)
- **Rollback**: Possible by reverting Docker volume

---

##  Prerequisites

### 1. Docker & Docker Compose
```bash
docker --version    # >= 20.10
docker-compose --version  # >= 2.0
```

### 2. Python Dependencies
```bash
cd /home/emmanuel/Documents/Scalable_Brain
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r scalable-brain/requirements.txt
```

### 3. Environment Configuration

Update `.env` in the repo root or `scalable-brain/.env`:

```bash
# PostgreSQL connection (default for Docker)
DB_SERVER=postgres          # Docker service name or hostname
DB_USER=sa                  # Postgres username
DB_PASS=your_secure_password  # Postgres password
DB_NAME=ForexBrainDB        # Database name
DB_PORT=5432                # PostgreSQL port

# OANDA credentials (unchanged)
OANDA_API_KEY=your_api_key
OANDA_ACCOUNT_ID_DEMO=your_demo_account
OANDA_ACCOUNT_ID=your_live_account
OANDA_ENV=practice

# Optional
DB_DRIVER=PostgreSQL        # For clarity
BATCH_SIZE=5000
LOG_LEVEL=INFO
```

**Important**: Use a strong password and store it securely.

---

##  Step 1: Start PostgreSQL + TimescaleDB

### Option A: Using Docker Compose (Recommended)

```bash
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain

# Build and start PostgreSQL container
docker-compose up -d postgres

# Verify it's running
docker-compose logs postgres | tail -20
```

Expected output:
```
postgres | LOG:  database system is ready to accept connections
```

### Option B: Check Connection

```bash
# From your host machine
psql -h localhost -U sa -d ForexBrainDB

# Password: (enter DB_PASS)
# You should see: psql (PostgreSQL 16.x)
```

---

##  Step 2: Initialize PostgreSQL Schema

The Docker initialization automatically runs `init-db/01-create-database.sql`:

```bash
# Verify schema was created
docker-compose exec postgres psql -U sa -d ForexBrainDB -c "\dt"

# Expected output: List of relations
#       Schema |                   Name                   | Type  | Owner 
# 
#  public        | dim_asset                                | table | sa
#  public        | dim_strategy                             | table | sa
#  ... (all dimension and fact tables)
```

---

##  Step 3: Migrate Data from SQL Server to PostgreSQL

### Prerequisites for Migration

You need **both** SQL Server and PostgreSQL running and accessible.

#### If You Have SQL Server Running:
```bash
# Use the migration script
cd /home/emmanuel/Documents/Scalable_Brain
source .venv/bin/activate

python scalable-brain/src/sql/migrate_sqlserver_to_postgresql.py
```

This script will:
- Connect to SQL Server (from .env `DB_SERVER`, `DB_USER`, `DB_PASS`)
- Connect to PostgreSQL (defaults to same credentials on localhost:5432)
- Migrate all tables in the correct order (respecting foreign keys)
- Report progress and summary

#### If You Don't Have SQL Server Running:

Skip this step if you're starting fresh. The PostgreSQL schema is already initialized with empty tables.

### Advanced Migration Options

```bash
# Dry run (show what would be migrated)
python scalable-brain/src/sql/migrate_sqlserver_to_postgresql.py --dry-run

# Migrate specific tables only
python scalable-brain/src/sql/migrate_sqlserver_to_postgresql.py \
  --tables Dim_Asset Dim_Strategy_Registry

# Use different source/target servers
python scalable-brain/src/sql/migrate_sqlserver_to_postgresql.py \
  --source-server old-sqlserver.example.com \
  --target-server pg-prod.example.com
```

---

##  Step 4: Verify Migration Success

### Check Table Counts

```bash
cd /home/emmanuel/Documents/Scalable_Brain
source .venv/bin/activate

# Quick verification script
python << 'EOF'
import psycopg2
from dotenv import load_dotenv
import os

load_dotenv('scalable-brain/.env')

conn = psycopg2.connect(
    host=os.getenv('DB_SERVER', 'localhost'),
    dbname=os.getenv('DB_NAME', 'ForexBrainDB'),
    user=os.getenv('DB_USER', 'sa'),
    password=os.getenv('DB_PASS'),
    port=int(os.getenv('DB_PORT', '5432'))
)

cursor = conn.cursor()
cursor.execute("""
    SELECT table_name, COUNT(*) 
    FROM information_schema.tables 
    WHERE table_schema='public' 
    GROUP BY table_name
""")

print("Table Verification:")
print("-" * 50)
for table_name, count in cursor.fetchall():
    print(f"  {table_name:40} {count:>10}")

conn.close()
EOF
```

### Connection Test from Python

```python
from src.common.db_client import PostgresClient

client = PostgresClient()
if client.test_connection():
    print(" PostgreSQL connection successful!")
else:
    print(" PostgreSQL connection failed")
```

---

##  Step 5: Update Application Code (If Needed)

The codebase has already been updated for PostgreSQL:

 `requirements.txt` - Updated to use `psycopg2-binary` instead of `pyodbc`
 `src/common/db_client.py` - PostgreSQL connection manager
 `src/layer*/` - All layers use PostgreSQL connections
 `shell/run_cleanup.py` - Updated for PostgreSQL

Verify by checking: `grep -r "psycopg2" scalable-brain/src/`

---

##  Step 6: Run Layers to Verify Integration

### Layer 0: Data Ingestion
```bash
cd /home/emmanuel/Documents/Scalable_Brain
source .venv/bin/activate

python scalable-brain/src/layer0/ingest_oanda_prices.py \
  --symbols EUR_USD GBP_USD \
  --granularities H1 D1 \
  --days-back 10
```

### Layer 1: Regime Detection
```bash
python scalable-brain/src/layer1_regime/Fact_market_regime_v2.py
```

### Layer 2: Signal Generation
```bash
python scalable-brain/src/layer2_signals/generate_signals.py \
  --symbols EUR_USD \
  --granularities H1 H4 \
  --strategy SMA_Crossover
```

### Layer 5: API & Dashboard
```bash
python scalable-brain/src/layer5/run.py
# Visit http://localhost:8001
```

---

##  Stop & Clean Up PostgreSQL (If Needed)

### Stop Container
```bash
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain
docker-compose down
```

### Reset Data (Delete Volume)
```bash
#  WARNING: This deletes all PostgreSQL data
docker volume rm scalable-brain_postgres-data
```

### Restart Fresh
```bash
docker-compose up -d postgres
```

---

##  Troubleshooting

### Connection Refused
```bash
# Check if PostgreSQL is running
docker-compose ps

# View logs
docker-compose logs postgres

# Restart
docker-compose restart postgres
```

### Authentication Failed

**Error**: `FATAL: password authentication failed for user "sa"`

**Fix**:
```bash
# Verify .env password has no special characters that need escaping
export DB_PASS="your_password"
echo $DB_PASS  # Check it's correct

# Test with psql
psql -h localhost -U sa -d ForexBrainDB
```

If password contains special characters, escape them:
```
DB_PASS=MyP@ss\$word  # Backslash before $
```

### Migration Fails - Table Not Found

**Error**: `Table X not found in SQL Server`

**Fix**: This table may not exist yet. Skip and continue.

### Query Returns 0 Rows in Layer 0

**Error**: `SELECT returned 0 rows after joins`

**Fix**: This is normal on first run. Populate sample data:
```bash
python scalable-brain/src/layer0/ingest_oanda_prices.py \
  --symbols EUR_USD --granularities H4 --days-back 30 --dry-run
```

---

##  Key Differences: SQL Server  PostgreSQL

| Feature | SQL Server | PostgreSQL |
|---------|-----------|-----------|
| **Connection String** | `server=host;database=db;uid=user;pwd=pass` | `host=host dbname=db user=user password=pass` |
| **Driver** | pyodbc (ODBC Driver 17) | psycopg2 |
| **Timestamp** | `DATETIME2` | `TIMESTAMPTZ` |
| **Limit Syntax** | `SELECT TOP 100 *` | `SELECT * LIMIT 100` |
| **Identity** | `IDENTITY(1,1)` | `SERIAL` / `GENERATED ALWAYS AS IDENTITY` |
| **Time-series** | Manual partitioning | TimescaleDB hypertables |
| **Reserved Words** | Quoted: `[Close]` | Quoted: `"Close"` |
| **Case Sensitivity** | Collation-dependent | Case-insensitive by default |

---

##  Migration Checklist

- [ ] PostgreSQL + TimescaleDB installed
- [ ] Environment variables configured
- [ ] Docker container running: `docker-compose up -d postgres`
- [ ] Schema initialized: verified with `docker-compose exec postgres psql -c "\dt"`
- [ ] Data migrated (if from SQL Server)
- [ ] Layer 0 ingests data successfully
- [ ] Layer 5 API dashboard responds
- [ ] Monitor logs for errors: `docker-compose logs postgres`

---

##  Rollback Plan

If something goes wrong:

### Option 1: Restore Docker Volume (Best)
```bash
# Stop and remove container
docker-compose down

# Delete volume
docker volume rm scalable-brain_postgres-data

# Restart (fresh schema)
docker-compose up -d postgres
```

### Option 2: Keep SQL Server Running

Leave SQL Server running as fallback:
1. Revert `.env` to old SQL Server connection
2. Update code to use old connection strings
3. App continues on SQL Server

### Option 3: Restore from Backup

If you created a PostgreSQL backup:
```bash
docker-compose exec postgres pg_restore -U sa -d ForexBrainDB /backup/forex_brain_backup.sql
```

---

##  Additional Resources

- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [TimescaleDB Documentation](https://docs.timescale.com/)
- [psycopg2 Documentation](https://www.psycopg.org/psycopg2/)
- [Docker PostgreSQL Official Image](https://hub.docker.com/_/postgres)

---

##  Support & Questions

For issues or questions:
1. Check logs: `docker-compose logs postgres | tail -100`
2. Verify environment: `echo $DB_SERVER $DB_PORT $DB_USER`
3. Test connection manually: `psql -h $DB_SERVER -U $DB_USER -d $DB_NAME`

---

**Last Updated**: April 25, 2026
**Status**:  Ready for Production
