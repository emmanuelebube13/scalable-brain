# PostgreSQL Migration - Swing Trading Quick Reference Card

> **SWING TRADING SYSTEM** | Fast-track database migration commands

##  Quick Start (Copy & Paste)

```bash
#!/bin/bash
cd /home/emmanuel/Documents/Scalable_Brain

# 1. Make migration script executable
chmod +x migrate_to_postgresql.sh

# 2. Run full migration with data transfer
./migrate_to_postgresql.sh --migrate-data

# 3. Or setup Docker only (no data migration)
./migrate_to_postgresql.sh --docker-only

# 4. Test the setup
python test_postgresql_connection.py
```

---

##  Connection Strings

### psycopg2 (Python)
```python
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    dbname="ForexBrainDB",
    user="sa",
    password="your_password",
    port=5432
)
```

### SQLAlchemy (Python)
```python
from sqlalchemy import create_engine

engine = create_engine(
    "postgresql+psycopg2://sa:password@localhost:5432/ForexBrainDB"
)
```

### psql (Command Line)
```bash
psql -h localhost -U sa -d ForexBrainDB
# Password: (enter your DB_PASS)
```

### Environment Variables (.env)
```
DB_SERVER=localhost         # or postgres (Docker)
DB_USER=sa
DB_PASS=your_secure_password
DB_NAME=ForexBrainDB
DB_PORT=5432                # Changed from 1433
DB_DRIVER=PostgreSQL        # Optional
```

---

##  Docker Commands

### Start PostgreSQL
```bash
cd scalable-brain
docker-compose up -d postgres
```

### Check Status
```bash
docker-compose ps
docker-compose logs postgres | tail -20
```

### Connect to Container
```bash
docker-compose exec postgres psql -U sa -d ForexBrainDB
```

### Stop & Cleanup
```bash
# Stop only
docker-compose stop postgres

# Stop and remove (keeps data)
docker-compose down

# Stop and delete all data ( irreversible)
docker-compose down
docker volume rm scalable-brain_postgres-data
```

---

##  Common Queries

### List All Tables
```sql
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public'
ORDER BY table_name;
```

### Check Table Sizes
```sql
SELECT 
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

### Count Rows in All Tables
```sql
SELECT 
    schemaname,
    tablename,
    n_live_tup AS row_count
FROM pg_stat_user_tables
ORDER BY n_live_tup DESC;
```

### Find Hypertables (TimescaleDB)
```sql
SELECT * FROM timescaledb_information.hypertables;
```

### Check Indexes
```sql
SELECT schemaname, tablename, indexname 
FROM pg_indexes 
WHERE schemaname = 'public';
```

---

##  Performance Tuning

### Enable Query Logging
```sql
-- Show slow queries (> 1 second)
ALTER SYSTEM SET log_min_duration_statement = 1000;
SELECT pg_reload_conf();
```

### Analyze & Explain
```sql
-- Analyze query performance
EXPLAIN ANALYZE
SELECT * FROM Fact_Market_Prices LIMIT 100;
```

### Vacuum & Analyze
```bash
# In psql:
ANALYZE;
VACUUM ANALYZE;
```

---

##  Troubleshooting

### Cannot connect to PostgreSQL
```bash
# Check if Docker is running
docker ps

# Check PostgreSQL status
docker-compose ps postgres

# View logs
docker-compose logs postgres

# Restart
docker-compose restart postgres
```

### Wrong password
```bash
# Check .env doesn't have quotes
cat scalable-brain/.env | grep DB_PASS

# Should be: DB_PASS=password (not DB_PASS="password")
```

### Database doesn't exist
```bash
# Check available databases
psql -h localhost -U sa -c "\l"

# If ForexBrainDB missing, it will auto-create on docker-compose up
docker-compose restart postgres
```

### Permission denied
```bash
# Check user permissions
psql -h localhost -U sa -d ForexBrainDB -c "SELECT current_user;"

# Grant permissions (as superuser)
psql -h localhost -U sa -d postgres -c \
  "ALTER ROLE sa WITH SUPERUSER;"
```

---

##  Migration Steps Reference

| Step | Command | Expected Output |
|------|---------|-----------------|
| 1. Activate venv | `source .venv/bin/activate` | `(.venv) $` prompt |
| 2. Load env | Load from `.env` | `DB_SERVER=postgres` |
| 3. Start Docker | `docker-compose up -d postgres` | `postgres is up-to-date` |
| 4. Wait ready | `docker-compose exec postgres pg_isready -U sa` | `accepting connections` |
| 5. Check schema | `psql -h localhost -U sa -c "\dt"` | Tables listed |
| 6. Test Python | `python test_postgresql_connection.py` | `6/6 tests passed` |

---

##  From SQL Server to PostgreSQL Syntax

| Operation | SQL Server | PostgreSQL |
|-----------|-----------|-----------|
| **Limit** | `SELECT TOP 10 *` | `SELECT * LIMIT 10` |
| **Identity** | `IDENTITY(1,1)` | `SERIAL` |
| **Datetime** | `DATETIME2` | `TIMESTAMPTZ` |
| **String Escape** | `[ColumnName]` | `"ColumnName"` |
| **Case-Insensitive** | By collation | By default (use COLLATE "C" for case-sensitive) |
| **NULL Default** | Default | `NULL` |
| **Transactions** | `BEGIN ... COMMIT` | `BEGIN ... COMMIT` (same) |
| **Indexes** | `ON (column)` | `ON (column)` (same) |

---

##  Verification Checklist

- [ ] PostgreSQL Docker running: `docker-compose ps`
- [ ] Can connect: `psql -h localhost -U sa -d ForexBrainDB`
- [ ] Tables exist: `\dt` (in psql)
- [ ] Python can connect: `python test_postgresql_connection.py`
- [ ] Layer 0 works: `python scalable-brain/src/layer0/...py --dry-run`
- [ ] Layer 5 API works: `python scalable-brain/src/layer5/run.py`

---

##  Getting Help

### 1. Check logs
```bash
docker-compose logs postgres | tail -100
```

### 2. Read documentation
- [POSTGRESQL_MIGRATION_GUIDE.md](scalable-brain/POSTGRESQL_MIGRATION_GUIDE.md)
- [POSTGRESQL_MIGRATION_SUMMARY.md](../POSTGRESQL_MIGRATION_SUMMARY.md)

### 3. Test connection
```bash
python test_postgresql_connection.py --verbose
```

### 4. Manual test
```bash
# Direct SQL test
psql -h localhost -U sa -d ForexBrainDB << 'EOF'
SELECT COUNT(*) FROM Dim_Asset;
SELECT COUNT(*) FROM Fact_Market_Prices;
EOF
```

---

##  File Locations

| File | Purpose |
|------|---------|
| `.env` | Database credentials (root or scalable-brain/) |
| `migrate_to_postgresql.sh` | One-click migration setup |
| `test_postgresql_connection.py` | Verify database |
| `scalable-brain/requirements.txt` | Python dependencies |
| `scalable-brain/docker-compose.yml` | Docker configuration |
| `scalable-brain/init-db/01-create-database.sql` | Database schema |
| `scalable-brain/POSTGRESQL_MIGRATION_GUIDE.md` | Detailed guide |
| `scalable-brain/src/sql/migrate_sqlserver_to_postgresql.py` | Data migration |

---

**Version**: 1.0  
**Last Updated**: April 25, 2026  
**Status**: Ready for Production 
