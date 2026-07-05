# PostgreSQL Native Migration - Swing Trading System Setup

> **SWING TRADING SYSTEM** | Non-Docker PostgreSQL deployment for swing trade persistence

**Status**:  Ready to Deploy  
**Date**: April 25, 2026  
**Setup Time**: ~10-15 minutes  
**Trading System**: Swing Trading infrastructure

---

##  What You Have

Complete **non-Docker** PostgreSQL setup with your existing credentials:

###  Documentation Files
- **POSTGRESQL_COMPLETE_GUIDE.md** - Full step-by-step guide (START HERE)
- **POSTGRESQL_NATIVE_SETUP.md** - Reference and troubleshooting
- **POSTGRESQL_QUICK_REFERENCE.md** - Commands cheat sheet

###  Setup Scripts
- **install_postgresql.sh** - Install PostgreSQL + TimescaleDB (run once)
- **setup_postgresql_native.py** - Create database and schema
- **migrate_data_native.py** - Migrate from SQL Server or seed defaults
- **test_postgresql_connection.py** - Verify everything works

###  Fixed Files
- **scalable-brain/.env** - Fixed password formatting (no quotes)
- **scalable-brain/requirements.txt** - Updated: psycopg2, no pyodbc
- **scalable-brain/shell/run_cleanup.py** - Updated for PostgreSQL
- **scalable-brain/src/layer3_ml/train_ml_gatekeeper.py** - Fixed SQL syntax

---

##  Quick Start (3 Commands)

```bash
cd /home/emmanuel/Documents/Scalable_Brain

# 1. Install PostgreSQL (first time only)
chmod +x install_postgresql.sh
./install_postgresql.sh

# 2. Setup database
source .venv/bin/activate
python setup_postgresql_native.py

# 3. Verify
python test_postgresql_connection.py
```

Expected time: **5-10 minutes**

---

##  Your Configuration

Already set in `scalable-brain/.env`:

```
DB_SERVER=localhost
DB_USER=sa
DB_PASS=Emm5$manuel
DB_NAME=ForexBrainDB
DB_PORT=5432            Changed from 1433
```

This matches your old SQL Server credentials but uses PostgreSQL defaults.

---

##  Step-by-Step

### Step 1: Install PostgreSQL (Ubuntu/Debian)

```bash
chmod +x install_postgresql.sh
./install_postgresql.sh
```

This will:
- Install PostgreSQL 16
- Install TimescaleDB extension
- Start PostgreSQL service
- Enable auto-start on boot

### Step 2: Setup Database

```bash
source .venv/bin/activate
python setup_postgresql_native.py
```

This will:
- Create `sa` user with password
- Create `ForexBrainDB` database
- Initialize schema (17 tables)
- Test connection

### Step 3: Migrate Data (Optional)

```bash
# If you have SQL Server, add to .env:
# SQLSERVER_HOST=localhost
# SQLSERVER_USER=sa
# SQLSERVER_PASS=your_old_password

python migrate_data_native.py

# Or just seed default currencies:
python migrate_data_native.py --seed-only
```

### Step 4: Verify

```bash
python test_postgresql_connection.py

# Should show:  6/6 tests passed
```

---

##  If PostgreSQL Isn't Installed

The system needs `psql` command-line tool. On Ubuntu/Debian:

```bash
# Install PostgreSQL server and client
sudo apt update
sudo apt install -y postgresql postgresql-contrib

# Or use the provided 
./install_postgresql.sh
```

---

##  Key Differences from Docker Version

| Aspect | Docker | Native |
|--------|--------|--------|
| **Installation** | Pre-configured image | Install via apt |
| **Management** | docker-compose up/down | systemctl start/stop |
| **Data Storage** | Docker volume | `/var/lib/postgresql` |
| **Complexity** | Simple (one command) | Medium (installed on system) |
| **Resource Usage** | Isolated | Shared with system |
| **Persistence** | Survives container restart | Survives system reboot |

---

##  What's Configured

 Database: `ForexBrainDB`  
 User: `sa` (with password from old config)  
 Port: `5432` (PostgreSQL standard)  
 TimescaleDB: Installed (for time-series optimization)  
 Schema: 17 tables (dimensions + facts + hypertables)  
 Driver: psycopg2 (Python connection)  
 Python dependencies: Updated in requirements.txt  

---

##  Your .env File

Fixed version at `scalable-brain/.env`:

```bash
# Database (formerly SQL Server, now PostgreSQL)
DB_SERVER=localhost
DB_USER=sa
DB_PASS=Emm5$manuel           # Note: NO QUOTES
DB_NAME=ForexBrainDB
DB_PORT=5432
DB_DRIVER=PostgreSQL

# OANDA (unchanged from your old config)
OANDA_API_KEY=5de5a147dfd0...
OANDA_ACCOUNT_ID_DEMO=101-002-38449021-001
OANDA_ACCOUNT_ID=101-002-38449021-001
OANDA_ENV=practice
OANDA_URL=https://api-fxpractice.oanda.com

# SMTP (unchanged)
SMTP_USER=emmanuelebubembachu@gmail.com
SMTP_PASS=qwgnmwehrdqvwcmy

# Layer settings (unchanged)
LAYER3_APPROVAL_THRESHOLD=0.20
```

---

##  Troubleshooting

### PostgreSQL Not Found

```bash
# Install it
./install_postgresql.sh

# Or manually
sudo apt install postgresql
```

### PostgreSQL Not Running

```bash
sudo systemctl start postgresql
sudo systemctl status postgresql
```

### Connection Refused

```bash
# Check service is running
sudo systemctl status postgresql

# Wait a moment and test
sleep 3
psql -U postgres -c "SELECT 1"
```

### Password Wrong

```bash
# Reset sa user password
sudo -u postgres psql -c "ALTER USER sa WITH PASSWORD 'Emm5\$manuel';"
```

See **POSTGRESQL_NATIVE_SETUP.md** for more troubleshooting.

---

##  After Setup - Next Steps

### 1. Test Layer 0 (Data Ingestion)
```bash
cd scalable-brain
python src/layer0/ingest_oanda_prices.py --dry-run
```

### 2. Test Layer 5 (API)
```bash
python src/layer5/run.py
# Visit http://localhost:8001
```

### 3. Run Full System
```bash
# Layer by layer (add your logic)
python src/layer1_regime/Fact_market_regime_v2.py
python src/layer2_signals/generate_signals.py
```

---

##  Key Files & Their Purposes

| File | Purpose | When Used |
|------|---------|-----------|
| `install_postgresql.sh` | Install PostgreSQL server | First time only |
| `setup_postgresql_native.py` | Create database & schema | First time only |
| `migrate_data_native.py` | Import data | When setting up |
| `test_postgresql_connection.py` | Verify setup | Debug/verify |
| `scalable-brain/.env` | Configuration | Always (read by Python) |
| `scalable-brain/requirements.txt` | Python deps | After venv setup |

---

##  Learning Resources

- **PostgreSQL Docs**: https://www.postgresql.org/docs/
- **TimescaleDB Docs**: https://docs.timescale.com/
- **psycopg2 Docs**: https://www.psycopg.org/psycopg2/
- **SQL Cheat Sheet**: https://sql.bolaji.dev/

---

##  Complete Checklist

- [ ] PostgreSQL installed: `psql --version`
- [ ] PostgreSQL running: `sudo systemctl status postgresql`
- [ ] Python venv active: `source .venv/bin/activate`
- [ ] Dependencies installed: `pip install psycopg2-binary pymssql`
- [ ] Run setup: `python setup_postgresql_native.py`
- [ ] Verify connection: `python test_postgresql_connection.py`
- [ ] Test Layer 0: `python scalable-brain/src/layer0/...py --dry-run`

---

##  Entire Process (Time Estimate)

| Step | Time | Command |
|------|------|---------|
| 1. Install PostgreSQL | 3 min | `./install_postgresql.sh` |
| 2. Setup database | 2 min | `python setup_postgresql_native.py` |
| 3. Seed data | 1 min | `python migrate_data_native.py --seed-only` |
| 4. Test | 1 min | `python test_postgresql_connection.py` |
| **Total** | **~7 minutes** | |

---

##  GET STARTED

1. Read: [POSTGRESQL_COMPLETE_GUIDE.md](POSTGRESQL_COMPLETE_GUIDE.md)
2. Run: `./install_postgresql.sh`
3. Setup: `python setup_postgresql_native.py`
4. Verify: `python test_postgresql_connection.py`

That's it! 

---

**Version**: 2.0 (Native, No Docker)  
**Status**: Ready for Production  
**Last Updated**: April 25, 2026
