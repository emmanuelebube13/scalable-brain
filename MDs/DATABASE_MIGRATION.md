#  DATABASE MIGRATION REQUIRED: Fact_Live_Trades Schema Fix

> **SWING TRADING SYSTEM** | Schema correction essential for swing trade execution logging

##  Overview

The `Fact_Live_Trades` table is missing the critical `Trade_ID` primary key column. This prevents Layer 4 (swing trade executor) from properly logging live trade executions to the database.

**Status:** Not applied | **Severity:** HIGH | **Downtime:** ~1-2 minutes | **Data Loss:** None (full backup created)

---

##  Check Current Status

### Option 1: Quick Check in SQL Server

```sql
USE ForexBrainDB;
GO

SELECT COLUMN_NAME 
FROM INFORMATION_SCHEMA.COLUMNS 
WHERE TABLE_NAME = 'Fact_Live_Trades'
ORDER BY ORDINAL_POSITION;
```

**Expected Output (after migration):**
```
Trade_ID           PRIMARY KEY, IDENTITY(1,1) 
Timestamp
Asset_ID
Strategy_ID
Signal_Value
Entry_Price
Stop_Loss
Take_Profit
Confidence_Score
Is_Approved
Actual_Outcome
Created_At         NEW
Updated_At         NEW
```

### Option 2: Use Verification Script

```bash
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain

# Run pre-migration check
sqlcmd -S (your_server),1433 -U (your_user) -P (your_password) -d ForexBrainDB \
  -i src/sql/migrations/00_verify_schema_before_migration.sql
```

---

##  Apply Migration

### Method 1: Automated Script (RECOMMENDED)

Make the script executable:
```bash
chmod +x shell/execute_migration.sh
```

Run with interactive prompts:
```bash
cd /home/emmanuel/Documents/Scalable_Brain
./scalable-brain/shell/execute_migration.sh
```

Or run non-interactively:
```bash
./scalable-brain/shell/execute_migration.sh --force
```

### Method 2: SQL Server Management Studio (SSMS)

1. Open **SQL Server Management Studio**
2. Connect to your instance
3. Open file: `scalable-brain/src/sql/migrations/fix_schema_trade_id_2026_04_05.sql`
4. Execute the script (F5 or Ctrl+E)
5. Check output for success message

### Method 3: sqlcmd Command Line

```bash
sqlcmd -S (your_server),1433 -U (your_user) -P (your_password) -d ForexBrainDB \
  -i scalable-brain/src/sql/migrations/fix_schema_trade_id_2026_04_05.sql
```

Replace:
- `(your_server)` - SQL Server hostname/IP
- `(your_user)` - Database user (e.g., `sa`)
- `(your_password)` - Password
- Add `-S (your_server),(port)` if using non-default port 1433

### Method 4: Load from .env Automatically

Ensure your `.env` has correct credentials:
```bash
DB_SERVER=your_server
DB_USER=your_user
DB_PASS=your_password
DB_NAME=ForexBrainDB
DB_PORT=1433
```

Then:
```bash
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain
sqlcmd -S ${DB_SERVER},${DB_PORT} -U ${DB_USER} -P ${DB_PASS} -d ${DB_NAME} \
  -i src/sql/migrations/fix_schema_trade_id_2026_04_05.sql
```

---

##  Verify Migration Success

After migration, run post-verification:

```bash
sqlcmd -S (your_server),1433 -U (your_user) -P (your_password) -d ForexBrainDB \
  -i scalable-brain/src/sql/migrations/01_verify_schema_after_migration.sql
```

Expected output:
```
 Table exists: Fact_Live_Trades
 Trade_ID column exists
 Trade_ID is configured as IDENTITY primary key
 Backup table exists: Fact_Live_Trades_Backup (0 records)
 Insert successful (Trade_ID: 1)
 Test record cleaned up
```

---

##  Migration Details

| Aspect | Details |
|--------|---------|
| **Type** | Schema restructuring with data preservation |
| **Downtime** | ~1-2 minutes |
| **Data Loss** | None (automatic backup created) |
| **Rollback** | Manual: restore from `Fact_Live_Trades_Backup` |
| **Idempotent** | Yes - safe to re-run |
| **Testing** | Post-migration script includes insert test |

### What the Migration Does

1.  Creates backup table `Fact_Live_Trades_Backup`
2.  Drops old foreign keys
3.  Renames old table to `Fact_Live_Trades_Old`
4.  Creates new table with `Trade_ID` as identity primary key
5.  Migrates all existing records (if any)
6.  Creates performance indexes:
   - `IX_LiveTrades_Timestamp` - for time-range queries
   - `IX_LiveTrades_Asset` - for asset-specific trades
   - `IX_LiveTrades_Strategy` - for strategy analysis
   - `IX_LiveTrades_Approval` - for approval status filtering
7.  Drops old staging table
8.  Adds audit columns: `Created_At`, `Updated_At`

---

##  Rollback (if needed)

If something goes wrong, the backup is preserved:

```sql
USE ForexBrainDB;
GO

-- See backup table
SELECT * FROM Fact_Live_Trades_Backup;

-- IF NEEDED: Restore from backup
DROP TABLE Fact_Live_Trades;
EXEC sp_rename 'Fact_Live_Trades_Backup', 'Fact_Live_Trades';
```

---

##  Next Steps After Migration

Once migration succeeds:

1. **Verify Layer 4 readiness:**
   ```bash
   cd scalable-brain
   python src/layer4_executor/live_pipeline.py --dry-run --all-signals --max-signals 5
   ```

2. **Ensure OANDA credentials in `.env`:**
   ```bash
   OANDA_API_KEY=your_live_or_practice_key
   OANDA_ACCOUNT_ID_DEMO=demo_account_id
   OANDA_ACCOUNT_ID=live_account_id
   OANDA_ENV=practice  # or "live" for real trading
   ```

3. **Run Layer 4 live pipeline:**
   ```bash
   python src/layer4_executor/live_pipeline.py
   ```

4. **Monitor execution logs:**
   ```bash
   tail -f logs/layer4_execution.log
   ```

---

##  Troubleshooting

### Error: "Invalid column name 'Trade_ID'"
**Cause:** Migration not applied yet  
**Fix:** Run one of the migration methods above

### Error: "Could not connect to database"
**Cause:** DB credentials in .env are incorrect  
**Fix:** Verify `DB_SERVER`, `DB_USER`, `DB_PASS`, `DB_NAME`, `DB_PORT` in `.env`

### Error: "Backup table already exists"
**Cause:** Migration was partially run before  
**Fix:** The script is idempotent; re-run it (it will skip if already applied)

### Error: "Foreign key constraint violations"
**Cause:** References to deleted/modified data  
**Fix:** This is rare; the script handles this automatically

---

##  Migration Files

- **Main migration:** `scalable-brain/src/sql/migrations/fix_schema_trade_id_2026_04_05.sql`
- **Pre-check:** `scalable-brain/src/sql/migrations/00_verify_schema_before_migration.sql`
- **Post-check:** `scalable-brain/src/sql/migrations/01_verify_schema_after_migration.sql`
- **Execution script:** `scalable-brain/shell/execute_migration.sh`

---

**Status:** Ready to apply | **Impact:** High | **Risk:** Low (fully reversible)
