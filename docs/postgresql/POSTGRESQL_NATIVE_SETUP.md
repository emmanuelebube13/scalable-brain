# PostgreSQL Native Setup - Without Docker

**Status**: Ready to Deploy  
**Date**: April 25, 2026

##  Quick Start (5 minutes)

```bash
cd /home/emmanuel/Documents/Scalable_Brain

# Activate your Python environment
source .venv/bin/activate

# 1. Setup PostgreSQL (creates database, user, schema)
python setup_postgresql_native.py

# 2. Migrate data (if you have SQL Server running)
python migrate_data_native.py

# 3. Test connection
python test_postgresql_connection.py
```

Done! 

---

##  Prerequisites

### 1. PostgreSQL Installed

Check if PostgreSQL is installed:
```bash
psql --version
```

If NOT installed:
```bash
# Ubuntu/Debian
sudo apt install postgresql postgresql-contrib

# macOS  
brew install postgresql

# Windows
# Download from https://www.postgresql.org/download/windows/
```

### 2. PostgreSQL Running

Start PostgreSQL:
```bash
# Ubuntu/Debian (systemctl)
sudo systemctl start postgresql

# macOS (brew)
brew services start postgresql

# Windows
# Start SQL Server service via Services.msc or pgAdmin
```

Verify it's running:
```bash
psql -U postgres -c "SELECT 1"
```

### 3. Python Dependencies

```bash
cd /home/emmanuel/Documents/Scalable_Brain
source .venv/bin/activate
pip install -q psycopg2-binary pymssql
```

### 4. Environment File (.env)

Already fixed in `scalable-brain/.env`:
```bash
DB_SERVER=localhost
DB_USER=sa
DB_PASS=Emm5$manuel
DB_NAME=ForexBrainDB
DB_PORT=5432
```

---

##  Step-by-Step Setup

### Step 1: Verify PostgreSQL Installation

```bash
# Check version
psql --version

# Should output: psql (PostgreSQL X.X)
```

**If not installed**, install using commands above.

### Step 2: Start PostgreSQL Service

```bash
# Linux
sudo systemctl status postgresql
sudo systemctl start postgresql

# macOS
brew services list | grep postgresql
brew services start postgresql

# Verify it's running
psql -U postgres -c "SELECT 1"
```

**If you get "Connection refused"**, PostgreSQL is not running. Start it with commands above.

### Step 3: Run Native Setup

```bash
cd /home/emmanuel/Documents/Scalable_Brain
source .venv/bin/activate

# This will:
# 1. Create 'sa' user with password
# 2. Create 'ForexBrainDB' database
# 3. Initialize schema with all tables
# 4. Verify everything works

python setup_postgresql_native.py
```

**Expected Output**:
```
 PostgreSQL found: psql (PostgreSQL 16.x)
 PostgreSQL service is running
 User 'sa' already exists
 Database 'ForexBrainDB' already exists
 Schema initialized successfully
 Connection verified successfully
 POSTGRESQL SETUP COMPLETED SUCCESSFULLY
```

### Step 4: Migrate Data (Optional - Only if you have SQL Server)

If you have SQL Server running and want to migrate data:

**Add to `.env`**:
```bash
SQLSERVER_HOST=localhost
SQLSERVER_USER=sa
SQLSERVER_PASS=your_sql_server_password
SQLSERVER_DB=ForexBrainDB
SQLSERVER_PORT=1433
```

Then run:
```bash
python migrate_data_native.py
```

**If you DON'T have SQL Server**, the script will skip migration and seed default data instead.

### Step 5: Verify Setup

```bash
python test_postgresql_connection.py
```

**Expected Output**:
```
 PASS - Basic Connection
 PASS - SQLAlchemy
 PASS - Tables Exist
 PASS - TimescaleDB
⊘ EMPTY - Sample Data (OK - no data yet)
 PASS - Connection Pool

Result: 6/6 tests passed
```

---

##  Troubleshooting

### Error: "psql: command not found"

PostgreSQL is not installed or not in PATH.

**Fix**:
```bash
# Ubuntu/Debian
sudo apt install postgresql

# macOS
brew install postgresql

# Windows
# Add PostgreSQL bin to PATH:
# C:\Program Files\PostgreSQL\16\bin
```

### Error: "FATAL: Connection refused"

PostgreSQL service is not running.

**Fix**:
```bash
# Linux
sudo systemctl start postgresql
sudo systemctl status postgresql

# macOS
brew services start postgresql

# Verify
psql -U postgres -c "SELECT 1"
```

### Error: "ROLE sa does not exist"

**Fix** (run as postgres user):
```bash
sudo -u postgres psql -c "CREATE USER sa WITH PASSWORD 'Emm5\$manuel' CREATEDB;"
```

Or let the setup script create it:
```bash
python setup_postgresql_native.py
```

### Error: "Database ForexBrainDB does not exist"

**Fix**:
```bash
# Let the setup script create it
python setup_postgresql_native.py

# Or manually
psql -U postgres -c "CREATE DATABASE ForexBrainDB OWNER sa;"
```

### Error: "Password authentication failed"

The `sa` user password is incorrect or not set.

**Fix**:
```bash
# Check .env file for DB_PASS
cat scalable-brain/.env | grep DB_PASS

# Should be: DB_PASS=Emm5$manuel

# If wrong, reset password
sudo -u postgres psql -c "ALTER USER sa WITH PASSWORD 'Emm5\$manuel';"
```

### Error: Python "psycopg2 not found"

**Fix**:
```bash
source .venv/bin/activate
pip install psycopg2-binary pymssql
```

---

##  Verification Commands

After setup, verify everything works:

```bash
# 1. PostgreSQL service running
sudo systemctl status postgresql

# 2. Can connect as sa user
psql -h localhost -U sa -d ForexBrainDB

# 3. Tables exist
psql -h localhost -U sa -d ForexBrainDB -c "\dt"

# 4. Sample count
psql -h localhost -U sa -d ForexBrainDB -c "SELECT COUNT(*) FROM Dim_Asset;"

# 5. Python connection test
python test_postgresql_connection.py
```

---

##  Manual Commands Reference

### Connect to Database

```bash
psql -h localhost -U sa -d ForexBrainDB
# Password: Emm5$manuel
```

### List Databases

```bash
psql -U postgres -l
```

### List Tables

```bash
psql -U sa -d ForexBrainDB -c "\dt"
```

### Reset Everything ( CAUTION)

```bash
# Drop database
psql -U postgres -c "DROP DATABASE IF EXISTS ForexBrainDB;"

# Drop user
psql -U postgres -c "DROP USER IF EXISTS sa;"

# Then run setup again
python setup_postgresql_native.py
```

---

##  Next Steps After Setup

### 1. Test Layer 0 (Data Ingestion)

```bash
source .venv/bin/activate
cd scalable-brain

python src/layer0/ingest_oanda_prices.py \
  --symbols EUR_USD \
  --granularities H1 \
  --days-back 10 \
  --dry-run
```

### 2. Test Layer 1 (Regime Detection)

```bash
python src/layer1_regime/Fact_market_regime_v2.py
```

### 3. Test Layer 5 (API Dashboard)

```bash
python src/layer5/run.py
# Visit: http://localhost:8001
```

### 4. Monitor Database

```bash
# Check table sizes
psql -U sa -d ForexBrainDB -c "
  SELECT 
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
  FROM pg_tables
  WHERE schemaname = 'public'
  ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;"
```

---

##  Starting Fresh

If you need to reset everything:

```bash
# Stop PostgreSQL
sudo systemctl stop postgresql

# Delete PostgreSQL data directory ( irreversible)
sudo rm -rf /var/lib/postgresql/*/main

# Start PostgreSQL (it will auto-initialize)
sudo systemctl start postgresql

# Run setup
python setup_postgresql_native.py
```

---

##  Useful psql Commands

```bash
# List all commands
psql -U sa -d ForexBrainDB -c "\?"

# List tables
\dt

# List databases
\l

# Describe table
\d Dim_Asset

# Count rows in all tables
SELECT tablename, (SELECT COUNT(*) FROM 
  information_schema.schemata) FROM pg_tables WHERE schemaname='public';

# Show current user
SELECT current_user;

# Exit psql
\q
```

---

##  Quick Reference

| Task | Command |
|------|---------|
| Check PostgreSQL | `psql --version` |
| Start service | `sudo systemctl start postgresql` |
| Connect to DB | `psql -U sa -d ForexBrainDB` |
| Setup all | `python setup_postgresql_native.py` |
| Migrate data | `python migrate_data_native.py` |
| Test connection | `python test_postgresql_connection.py` |
| View logs | `sudo journalctl -u postgresql -f` |

---

##  Getting Help

1. **Check if PostgreSQL is running**:
   ```bash
   sudo systemctl status postgresql
   ```

2. **Check PostgreSQL logs**:
   ```bash
   sudo journalctl -u postgresql -f
   ```

3. **Test basic connection**:
   ```bash
   psql -U postgres -c "SELECT 1"
   ```

4. **Run detailed diagnostics**:
   ```bash
   python test_postgresql_connection.py --verbose
   ```

---

**Status**:  Ready to Use  
**Last Updated**: April 25, 2026
