# PostgreSQL Migration - Swing Trading System Implementation Summary

> **SWING TRADING SYSTEM** | SQL Server  PostgreSQL infrastructure migration

**Date**: April 25, 2026  
**Status**:  Complete and Ready for Use  
**Database**: SQL Server  PostgreSQL 16 + TimescaleDB  
**Trading System**: Swing Trading signal and execution persistence

---

##  What Was Done

### 1.  Updated Python Dependencies

**File**: [scalable-brain/requirements.txt](scalable-brain/requirements.txt)

**Changes**:
- Removed `pyodbc>=4.0.35` (SQL Server ODBC driver)
- Added `psycopg2-binary>=2.9.0` (PostgreSQL driver)
- Added `pymssql>=2.2.0` (For data migration from SQL Server)

**Result**: Codebase now uses PostgreSQL exclusively.

---

### 2.  Updated Shell Scripts

**File**: [scalable-brain/shell/run_cleanup.py](scalable-brain/shell/run_cleanup.py)

**Changes**:
- Replaced `pyodbc.connect()` with `psycopg2.connect()`
- Updated connection string format (`host/dbname/user/password` instead of ODBC)
- Changed SQL dialect for PostgreSQL (`information_schema.tables` instead of `INFORMATION_SCHEMA.TABLES`)
- Updated statement separator (`;` instead of `GO`)

**Result**: Cleanup script now works with PostgreSQL.

---

### 3.  Fixed SQL Syntax for PostgreSQL

**File**: [scalable-brain/src/layer3_ml/training/train_ml_gatekeeper.py](scalable-brain/src/layer3_ml/training/train_ml_gatekeeper.py)

**Changes**:
- Renamed `with_sqlserver_top()`  `add_limit_to_query()`
- Function already uses `LIMIT` (PostgreSQL syntax), not `TOP` (SQL Server)
- Updated usage in dry-run mode to reflect PostgreSQL naming

**Result**: Machine learning training layer works with PostgreSQL LIMIT syntax.

---

### 4.  Created Data Migration Script

**File**: [scalable-brain/src/sql/migrate_sqlserver_to_postgresql.py](scalable-brain/src/sql/migrate_sqlserver_to_postgresql.py)

**Features**:
- Connects to both SQL Server and PostgreSQL
- Respects foreign key order (imports dimensions first, then facts)
- Migrates all tables in correct order
- Shows progress and summary report
- Includes dry-run mode for preview
- Selective table migration support

**Usage**:
```bash
# Full migration
python scalable-brain/src/sql/migrate_sqlserver_to_postgresql.py

# Dry run (no changes)
python scalable-brain/src/sql/migrate_sqlserver_to_postgresql.py --dry-run

# Specific tables only
python scalable-brain/src/sql/migrate_sqlserver_to_postgresql.py \
  --tables Dim_Asset Fact_Market_Prices
```

**Result**: Easy automated data transfer from SQL Server to PostgreSQL.

---

### 5.  Created Migration Automation Script

**File**: [migrate_to_postgresql.sh](migrate_to_postgresql.sh)

**Features**:
- One-command setup of entire PostgreSQL environment
- Verifies Python environment and dependencies
- Starts Docker PostgreSQL container
- Initializes database schema
- Optional data migration from SQL Server
- Comprehensive verification and reporting

**Usage**:
```bash
# Full setup with data migration
./migrate_to_postgresql.sh --migrate-data

# Docker only (no data migration)
./migrate_to_postgresql.sh --docker-only

# Skip confirmations
./migrate_to_postgresql.sh --migrate-data --force
```

**Result**: One-click PostgreSQL setup for the entire system.

---

### 6.  Created Comprehensive Documentation

**File**: [scalable-brain/POSTGRESQL_MIGRATION_GUIDE.md](scalable-brain/POSTGRESQL_MIGRATION_GUIDE.md)

**Contents**:
- Step-by-step migration instructions
- Docker setup and verification
- Database initialization guide
- Layer testing procedures
- Troubleshooting section
- Rollback procedures
- SQL Server vs PostgreSQL comparison table
- Migration checklist

**Result**: Complete reference guide for migration and troubleshooting.

---

##  How to Perform the Migration

### Quick Start (5 minutes)

```bash
cd /home/emmanuel/Documents/Scalable_Brain

# Make migration script executable
chmod +x migrate_to_postgresql.sh

# Run migration (interactive, ask for confirmations)
./migrate_to_postgresql.sh --migrate-data

# Or skip confirmations (-force)
./migrate_to_postgresql.sh --migrate-data --force
```

### Manual Step-by-Step

```bash
cd /home/emmanuel/Documents/Scalable_Brain
source .venv/bin/activate

# 1. Update .env to use PostgreSQL
#    DB_PORT=5432 (instead of 1433)

# 2. Start PostgreSQL
cd scalable-brain
docker-compose up -d postgres
sleep 10

# 3. Verify schema
docker-compose exec postgres psql -U sa -d ForexBrainDB -c "\dt"

# 4. Migrate data (if you have SQL Server running)
python src/sql/migrate_sqlserver_to_postgresql.py

# 5. Test connection
python ../test_postgresql_connection.py
```

---

##  What's Already Done in the Codebase

The following code was **already updated for PostgreSQL**:

 `src/common/db_client.py` - PostgreSQL connection manager  
 `src/layer0/data_loader.py` - Uses psycopg2  
 `src/layer1_regime/Fact_market_regime_v2.py` - Uses PostgreSQL  
 `src/layer2_signals/signal_engine/config/` - PostgreSQL connection  
 `src/layer2_signals/signal_engine/persistence/` - PostgreSQL ORM  
 `src/layer5/services/db_client.py` - PostgreSQL + SQLAlchemy  
 `init-db/01-create-database.sql` - PostgreSQL schema  
 `docker-compose.yml` - PostgreSQL + TimescaleDB configured

---

##  Verification Commands

After migration, verify everything works:

### Check PostgreSQL Connection
```bash
source scalable-brain/.env
psql -h $DB_SERVER -U $DB_USER -d $DB_NAME

# You should see the psql prompt:
# ForexBrainDB=>
```

### Verify Tables Created
```bash
psql -h localhost -U sa -d ForexBrainDB -c "\dt"

# Should list all dimension and fact tables
```

### Test Data Migration
```bash
# Quick count check
psql -h localhost -U sa -d ForexBrainDB -c \
  "SELECT COUNT(*) FROM Dim_Asset; SELECT COUNT(*) FROM Fact_Market_Prices;"
```

### Run Layer Tests
```bash
cd /home/emmanuel/Documents/Scalable_Brain
source .venv/bin/activate

# Test Layer 0 (data ingestion)
python scalable-brain/src/layer0/ingest_oanda_prices.py \
  --symbols EUR_USD --granularities H1 --days-back 5 --dry-run

# Test Layer 5 (API)
python scalable-brain/src/layer5/run.py
# Visit: http://localhost:8001
```

---

##  Environment Variables Reference

### PostgreSQL Defaults (in .env or docker-compose)
```bash
DB_SERVER=postgres              # Docker service or hostname
DB_USER=sa                      # PostgreSQL username
DB_PASS=Emm5$manuel             # Secure password
DB_NAME=ForexBrainDB            # Database name
DB_PORT=5432                    # PostgreSQL default port
DB_DRIVER=PostgreSQL            # For clarity
```

### Important Notes
- `DB_PORT` changed from `1433` (SQL Server) to `5432` (PostgreSQL)
- `DB_DRIVER` changed from SQL Server to PostgreSQL
- All other variables remain the same
- Docker uses `DB_PASS_COMPOSE` and `DB_PASS` interchangeably

---

##  Troubleshooting Quick Fix

### Error: "Connection refused"
```bash
# Check if PostgreSQL is running
docker-compose ps

# Start it
docker-compose up -d postgres

# Wait for readiness
docker-compose exec postgres pg_isready -U sa
```

### Error: "Database ForexBrainDB does not exist"
```bash
# Schema auto-initializes on first run
# If not, manually initialize:
docker-compose exec postgres psql -U sa -d postgres \
  -f /docker-entrypoint-initdb.d/01-create-database.sql
```

### Error: "Password authentication failed"
```bash
# Check .env for password issues (special chars, spaces, quotes)
# Verify: echo $DB_PASS
# Should NOT have quotes around it
```

### Can't Connect from Python
```bash
# Test basic connectivity first
psql -h $DB_SERVER -U $DB_USER -d $DB_NAME

# Then test from Python
cd /home/emmanuel/Documents/Scalable_Brain
source .venv/bin/activate
python -c "import psycopg2; print(' psycopg2 installed')"
```

---

##  Migration Scope

### Tables Migrated (16 total)

**Dimension Tables:**
- Dim_Asset
- Dim_Strategy_Registry
- Dim_Strategy
- Dim_Strategy_Config
- Dim_Strategy_Asset_Mapping
- Dim_Indicator_Library

**Time-Series Fact Tables (Hypertables):**
- Fact_Market_Prices
- Fact_Market_Prices_H4
- Fact_Market_Prices_D1
- Fact_Market_Regime
- Fact_Market_Regime_V2
- Fact_Signals

**Operational Tables:**
- Fact_Signal_Processing_Log
- Fact_Live_Trades
- Fact_Trade_Outcomes
- Fact_Execution_Log
- Fact_Macro_Events

---

##  Migration Timeline

| Step | Time | Description |
|------|------|-------------|
| 1 | 1 min | Verify environment |
| 2 | 2 min | Install Python dependencies |
| 3 | 2 min | Start PostgreSQL container |
| 4 | 2 min | Initialize database schema |
| 5 | Variable | Migrate data (10 min - 1 hour depending on data volume) |
| 6 | 1 min | Verify and test |

**Total**: ~5-10 minutes with Docker-only setup, +10-60 minutes if migrating data from SQL Server

---

##  Post-Migration: What to Do Next

1. **Update documentation** to reference PostgreSQL instead of SQL Server
2. **Archive SQL Server** (keep running for backup, or completely decommission)
3. **Update deployment scripts** to reference PostgreSQL only
4. **Update team documentation** on database connections
5. **Schedule maintenance** for PostgreSQL backups (weekly FULL, daily INCREMENTAL)
6. **Monitor performance** with `EXPLAIN ANALYZE` on slow queries
7. **Set up monitoring** for database health (disk space, connection count, etc.)

---

##  Files Changed Summary

```
Modified:
   scalable-brain/requirements.txt
   scalable-brain/shell/run_cleanup.py
   scalable-brain/src/layer3_ml/training/train_ml_gatekeeper.py

Created:
   scalable-brain/src/sql/migrate_sqlserver_to_postgresql.py
   scalable-brain/POSTGRESQL_MIGRATION_GUIDE.md
   migrate_to_postgresql.sh
   POSTGRESQL_MIGRATION_SUMMARY.md (this file)

Already Configured for PostgreSQL:
   scalable-brain/init-db/01-create-database.sql
   scalable-brain/docker-compose.yml
   All Python layers (0-5)
   SQLAlchemy connection managers
```

---

##  Key Advantages of PostgreSQL

- **TimescaleDB**: Purpose-built for time-series data (candlesticks, indicators)
- **JSONB**: Native JSON support (already used in Dim_Strategy_Config)
- **Performance**: Better for high-volume data ingestion
- **Scalability**: Horizontal scaling with replicas
- **Cost**: Open-source, no licensing
- **Community**: Large ecosystem and third-party tools

---

**Status**:  Migration Ready  
**Last Updated**: April 25, 2026  
**Prepared By**: GitHub Copilot
