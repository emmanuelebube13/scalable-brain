# Complete PostgreSQL Native Migration Guide - Scalable Brain Swing Trading

> **SWING TRADING SYSTEM** | PostgreSQL infrastructure setup for swing trade data persistence

**For**: Scalable Brain Swing Trading System  
**Date**: April 25, 2026  
**Environment**: Linux (Ubuntu/Debian) without Docker  
**Trading Type:** Swing Trading (multi-timeframe signal + execution tracking)

---

##  QUICK START (Copy & Run)

```bash
#!/bin/bash
cd /home/emmanuel/Documents/Scalable_Brain

# Step 1: Install PostgreSQL (one-time)
chmod +x install_postgresql.sh
./install_postgresql.sh  # Run with sudo or without (will ask)

# Step 2: Setup database and schema
source .venv/bin/activate
python setup_postgresql_native.py

# Step 3: Migrate data (if you have SQL Server)
python migrate_data_native.py  # Or --seed-only for default data

# Step 4: Verify everything works
python test_postgresql_connection.py

# Step 5: Start using!
python scalable-brain/src/layer0/ingest_oanda_prices.py --dry-run
```

---

##  Full Steps Explained

### Step 0: Verify Your System

Check what you have:
```bash
# Check Python
python3 --version  # Should be 3.8+

# Check pip
pip --version

# Check OS
lsb_release -a  # Ubuntu/Debian

# Current directory
pwd  # Should show: /home/emmanuel/Documents/Scalable_Brain
```

---

### Step 1: Install PostgreSQL (First Time Only)

#### Method 1: Using the provided script (EASIEST)

```bash
cd /home/emmanuel/Documents/Scalable_Brain
chmod +x install_postgresql.sh

# Run with sudo (will ask for password once)
./install_postgresql.sh
```

**What this does:**
- Updates system package list
- Installs PostgreSQL 16
- Installs TimescaleDB extension (for time-series data)
- Starts PostgreSQL service
- Verifies installation

**Expected output:**
```
 Installation Complete!
PostgreSQL 16.1
TimescaleDB 2.x.x
```

#### Method 2: Manual installation (if script doesn't work)

```bash
# Update packages
sudo apt update

# Install PostgreSQL
sudo apt install -y postgresql postgresql-contrib

# Install TimescaleDB
sudo apt install -y timescaledb-2-postgresql-16

# Start service
sudo systemctl start postgresql
sudo systemctl enable postgresql  # Auto-start on boot

# Verify
psql -U postgres -c "SELECT version();"
```

#### Verify PostgreSQL is Running

```bash
# Check service status
sudo systemctl status postgresql

# Test connection as postgres user
sudo -u postgres psql -c "SELECT 1;"

# Should output: 
# SELECT 1
#  ?column? 
# ----------
#        1
```

---

### Step 2: Activate Python Environment

```bash
cd /home/emmanuel/Documents/Scalable_Brain

# Check if venv exists
ls -la | grep venv

# If it exists, activate it
source .venv/bin/activate

# You should see: (.venv) $

# If it doesn't exist, create it
python3 -m venv .venv
source .venv/bin/activate
pip install -q --upgrade pip
```

---

### Step 3: Install Python Dependencies

```bash
# Make sure you're in the venv
source .venv/bin/activate

# Install PostgreSQL and SQL Server drivers
pip install -q psycopg2-binary pymssql

# Verify
python -c "import psycopg2; import pymssql; print(' Installed')"
```

---

### Step 4: Setup PostgreSQL Database

This creates the `sa` user and `ForexBrainDB` database with schema:

```bash
# Make sure you're in the right directory
cd /home/emmanuel/Documents/Scalable_Brain

# Make sure venv is active
source .venv/bin/activate

# Run setup
python setup_postgresql_native.py
```

**What happens:**
1.  Checks PostgreSQL is installed
2.  Checks PostgreSQL service is running
3.  Creates user `sa` with password `Emm5$manuel`
4.  Creates database `ForexBrainDB`
5.  Loads all table schemas
6.  Tests connection

**Expected output:**
```
 PostgreSQL found: psql (PostgreSQL 16.x)
 PostgreSQL service is running
 User 'sa' created successfully
 Database created successfully  
 Schema initialized successfully
 Connection verified successfully

 POSTGRESQL SETUP COMPLETED SUCCESSFULLY
```

**If you see warnings**, they're usually harmless:
- "already exists" - means it was already created 
- "if not exists" - part of normal idempotent setup 

---

### Step 5: Migrate Data (Optional)

#### Option A: From SQL Server (if you have it running)

First, **add SQL Server credentials to `.env`**:

```bash
# Edit scalable-brain/.env
nano scalable-brain/.env

# Add these lines:
SQLSERVER_HOST=localhost
SQLSERVER_USER=sa
SQLSERVER_PASS=your_sql_server_password
SQLSERVER_DB=ForexBrainDB
SQLSERVER_PORT=1433
```

Then run migration:
```bash
source .venv/bin/activate
python migrate_data_native.py
```

#### Option B: Seed Default Data (Recommended if NO SQL Server)

If you don't have SQL Server, just seed default reference data:

```bash
source .venv/bin/activate
python migrate_data_native.py --seed-only
```

This creates:
- 5 forex currency pairs (EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD)
- Empty fact tables ready for data

---

### Step 6: Verify Everything Works

```bash
source .venv/bin/activate
python test_postgresql_connection.py
```

**Expected output:**
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

##  Manual Verification

You can also verify manually using psql:

```bash
# Connect to the database
psql -h localhost -U sa -d ForexBrainDB

# Password: Emm5$manuel

# Once connected, try:
SELECT COUNT(*) FROM Dim_Asset;
SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name;
\dt
\q  # to exit
```

---

##  Test the System

After setup, test individual layers:

### Test Layer 0 (Data Ingestion)

```bash
cd /home/emmanuel/Documents/Scalable_Brain
source .venv/bin/activate
cd scalable-brain

# Download and store candlestick data
python src/layer0/ingest_oanda_prices.py \
  --symbols EUR_USD GBP_USD \
  --granularities H1 H4 \
  --days-back 10 \
  --dry-run  # Remove --dry-run to actually insert data
```

### Test Layer 1 (Regime Detection)

```bash
python src/layer1_regime/Fact_market_regime_v2.py
```

### Test Layer 5 (API Dashboard)

```bash
python src/layer5/run.py

# Open browser: http://localhost:8001
```

---

##  Troubleshooting

### "PostgreSQL not installed"

**Fix:**
```bash
cd /home/emmanuel/Documents/Scalable_Brain
chmod +x install_postgresql.sh
./install_postgresql.sh
```

### "PostgreSQL service not running"

**Fix:**
```bash
# Start it manually
sudo systemctl start postgresql

# Verify
sudo systemctl status postgresql

# Enable auto-start on boot
sudo systemctl enable postgresql
```

### "Cannot connect: Connection refused"

**Fix:**
```bash
# Make sure service is running
sudo systemctl status postgresql

# If not, start it
sudo systemctl start postgresql

# Wait a moment
sleep 3

# Try connecting
psql -U postgres -c "SELECT 1"
```

### "FATAL: password authentication failed"

The passwords don't match. Check:
```bash
# Verify .env password
grep DB_PASS scalable-brain/.env

# Should show: DB_PASS=Emm5$manuel

# Reset postgres superuser password
sudo -u postgres psql -c "ALTER USER postgres WITH PASSWORD 'postgres';"

# Reset sa user password
sudo -u postgres psql -c "ALTER USER sa WITH PASSWORD 'Emm5\$manuel';"
```

**Note**: The `$` in `Emm5$manuel` needs to be escaped as `\$` in some contexts.

### "ROLE sa does not exist"

**Fix:**
```bash
# Create it manually
sudo -u postgres psql -c "CREATE USER sa WITH PASSWORD 'Emm5\$manuel' CREATEDB;"

# Or run setup script
python setup_postgresql_native.py
```

### "Database ForexBrainDB does not exist"

**Fix:**
```bash
# Create it manually
sudo -u postgres psql -c "CREATE DATABASE ForexBrainDB OWNER sa;"

# Or run setup script
python setup_postgresql_native.py
```

### "psycopg2 not found" (Python error)

**Fix:**
```bash
source .venv/bin/activate
pip install psycopg2-binary pymssql
```

---

##  Environment File (.env)

Your file is already configured at `scalable-brain/.env`:

```bash
DB_SERVER=localhost           # PostgreSQL host
DB_USER=sa                    # PostgreSQL user
DB_PASS=Emm5$manuel           # PostgreSQL password (NO QUOTES)
DB_NAME=ForexBrainDB          # Database name
DB_PORT=5432                  # PostgreSQL port (NOT 1433)
DB_DRIVER=PostgreSQL          # For clarity

# OANDA (unchanged)
OANDA_API_KEY=...
OANDA_ACCOUNT_ID_DEMO=...
```

**Important**: No quotes around DB_PASS (this was fixed from the old config).

---

##  Useful PostgreSQL Commands

```bash
# Connect to database
psql -h localhost -U sa -d ForexBrainDB

# Within psql prompt:
\l                           # List databases
\dt                          # List tables
\d Dim_Asset                 # Describe table
SELECT COUNT(*) FROM Dim_Asset;  # Query table
\q                           # Quit
```

```bash
# From command line (no prompt)
psql -U sa -d ForexBrainDB -c "SELECT COUNT(*) FROM Dim_Asset;"

# Run SQL file
psql -U sa -d ForexBrainDB -f init-db/01-create-database.sql

# Backup database
pg_dump -U sa ForexBrainDB > backup.sql

# Restore database
psql -U sa ForexBrainDB < backup.sql
```

---

##  Starting Fresh

If you need to reset everything:

```bash
# Stop PostgreSQL
sudo systemctl stop postgresql

# Delete database ( irreversible - loses all data)
sudo rm -rf /var/lib/postgresql/16/main

# Start PostgreSQL (it auto-initializes)
sudo systemctl start postgresql

# Setup again
python setup_postgresql_native.py
```

Or just drop the database:

```bash
sudo -u postgres psql -c "DROP DATABASE IF EXISTS ForexBrainDB;"
sudo -u postgres psql -c "DROP USER IF EXISTS sa;"

# Then setup
python setup_postgresql_native.py
```

---

##  Checklist Before Using

- [ ] PostgreSQL installed: `psql --version`
- [ ] PostgreSQL running: `sudo systemctl status postgresql`
- [ ] Python venv active: `source .venv/bin/activate`
- [ ] Dependencies installed: `pip list | grep psycopg`
- [ ] `sa` user created: `psql -U sa -c "\du"`
- [ ] `ForexBrainDB` exists: `psql -U sa -c "\l"`
- [ ] Schema loaded: `psql -U sa -d ForexBrainDB -c "\dt"`
- [ ] Connection works: `python test_postgresql_connection.py`

---

##  Files in This Setup

| File | Purpose |
|------|---------|
| `install_postgresql.sh` | Automated PostgreSQL installation |
| `setup_postgresql_native.py` | Create user, database, schema |
| `migrate_data_native.py` | Migrate from SQL Server or seed defaults |
| `test_postgresql_connection.py` | Verify everything works |
| `scalable-brain/.env` | Database credentials |
| `POSTGRESQL_NATIVE_SETUP.md` | Detailed reference guide |
| `scalable-brain/init-db/01-create-database.sql` | Database schema |

---

##  Common Tasks After Setup

### Check Database Size
```bash
psql -U sa -d ForexBrainDB -c "
  SELECT 
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
  FROM pg_tables
  WHERE schemaname = 'public'
  ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;"
```

### Monitor Active Connections
```bash
psql -U sa -d ForexBrainDB -c "SELECT usename, application_name, state FROM pg_stat_activity;"
```

### Check PostgreSQL Logs
```bash
sudo tail -f /var/log/postgresql/postgresql-16-main.log
```

### Backup Database
```bash
pg_dump -U sa ForexBrainDB > backup_$(date +%Y%m%d_%H%M%S).sql
```

### Restore from Backup
```bash
psql -U sa ForexBrainDB < backup_20260425_120000.sql
```

---

##  What's Configured for You

 Linux (Ubuntu/Debian) PostgreSQL installation  
 Database and user creation  
 Schema with 17 tables (dimensions + facts + hypertables)  
 TimescaleDB extension for time-series optimization  
 Python psycopg2 driver installed  
 Connection pooling configured  
 Default asset data seeding  
 Full verification and testing  

---

**Status**:  Ready to Deploy  
**Last Updated**: April 25, 2026  
**Time to Complete**: ~10-15 minutes total
