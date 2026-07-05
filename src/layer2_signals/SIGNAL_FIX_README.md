# Layer 2 Signal Generation - Data Integrity Fixes

## Problem Summary

The Layer 2 signal generation system had serious data integrity issues:

1. **Excessive Signal Counts**: 5098+ total signals for 5 currency pairs with hourly processing
2. **Duplicate Signals**: No deduplication was being performed before insertion
3. **Historical Data Re-processing**: Each cron job run re-processed ALL historical data
4. **Missing Primary Key**: The `Fact_Signals` table primary key didn't include `Granularity`
5. **No Incremental Processing**: No tracking of what had already been processed

## Root Causes

### 1. Full Historical Data Fetch
The `_fetch_price_data()` method in `engine.py` fetched ALL historical data for each asset on every run:
```python
df = self._fetch_price_data(asset_id=asset_id, granularity=granularity)
```
This meant processing thousands of bars every hour.

### 2. No Deduplication Before Insert
While the MERGE operation prevented duplicate rows in the database, the engine still:
- Calculated indicators for all historical bars
- Evaluated rules for all historical bars
- Attempted to insert all signals

### 3. Missing Granularity in Primary Key
The `Fact_Signals` table PK was `(Timestamp, Asset_ID, Strategy_ID)`, missing `Granularity`.
This meant H1 and H4 signals for the same timestamp would conflict.

### 4. No Processing State Tracking
There was no mechanism to track what data had already been processed.

## Solutions Implemented

### 1. New Processing Tracker (`processing_tracker.py`)

Created a new `ProcessingTracker` class that:
- Tracks `last_processed_timestamp` per `(Asset_ID, Granularity, Strategy_ID)`
- Calculates appropriate start dates for incremental processing
- Provides batch update capabilities

Key methods:
```python
def get_last_processed_timestamp(asset_id, granularity, strategy_id) -> Optional[datetime]
def update_last_processed(asset_id, granularity, strategy_id, timestamp, batch_id, records_processed) -> bool
def calculate_start_date(asset_id, granularity, strategy_id, lookback_bars=5) -> Optional[datetime]
```

### 2. Updated Signal Engine (`engine.py`)

Modified the engine to:
- Use `ProcessingTracker` for incremental processing
- Only fetch data since last processed timestamp (plus lookback for indicator warmup)
- Filter signals to current hour only (prevents historical signal accumulation)
- Track processing state after successful persistence

New parameters:
```python
def run(self, ..., incremental: bool = True, current_hour_only: bool = True)
```

### 3. Enhanced Repository (`repository.py`)

Added deduplication and validation:
- `_filter_existing_signals()`: Filters out signals that already exist in database
- `_filter_to_current_hour()`: Only processes signals for current hour
- `check_existing_signal()`: Checks if a specific signal exists
- `get_existing_timestamps()`: Batch check for existing timestamps

Updated `save_signals()` signature:
```python
def save_signals(
    self,
    signals_df: pd.DataFrame,
    strategy_version: str,
    config_hash: str,
    batch_id: Optional[str] = None,
    asset_id: Optional[int] = None,
    granularity: Optional[str] = None,
    strategy_id: Optional[int] = None,
    validate_current_hour_only: bool = True
) -> int
```

### 4. New CLI Options (`generate_signals.py`)

Added command-line options:
```bash
python generate_signals.py --full-backfill  # Process all historical data
python generate_signals.py --all-hours      # Process all hours, not just current
```

Default behavior (incremental, current hour only):
```bash
python generate_signals.py  # Only processes new data for current hour
```

### 5. Database Migration (`add_signal_processing_tracking.sql`)

SQL migration that:
- Creates `Fact_Signal_Processing_Log` table for tracking processing state
- Adds `Granularity` column to `Fact_Signals` if missing
- Adds additional traceability columns (Strategy_Version, Config_Hash, Signal_Reason, Rule_ID, Indicator_Snapshot, Confidence_Score, Batch_ID, Created_At)
- Updates primary key to include `Granularity`
- Creates indexes for performance
- Cleans up any existing duplicate signals

### 6. Verification Script (`verify_signals.py`)

New script to verify signal integrity:
```bash
# Check signal counts and duplicates
python verify_signals.py

# Remove duplicates
python verify_signals.py --fix-duplicates

# Filter by specific criteria
python verify_signals.py --asset-id 5 --granularity H1
```

## Expected Behavior After Fixes

### For Hourly Cron Job
- Each run processes only the **current hour's data**
- Maximum signals per run: ~5 pairs × 2 granularities × ~2 strategies = ~20 signals
- No duplicate signals
- Fast execution (seconds, not minutes)

### For Initial Backfill
```bash
python generate_signals.py --full-backfill --all-hours
```
This will process all historical data once, then future runs use incremental mode.

## Deployment Steps

1. **Run Database Migration**:
   ```bash
   sqlcmd -S your_server -d ForexBrainDB -i scalable-brain/src/sql/migrations/add_signal_processing_tracking.sql
   ```

2. **Verify Current State**:
   ```bash
   cd scalable-brain/src/layer2_signals
   python verify_signals.py
   ```

3. **Clean Up Duplicates** (if any):
   ```bash
   python verify_signals.py --fix-duplicates
   ```

4. **Test Incremental Run**:
   ```bash
   python generate_signals.py --dry-run
   ```

5. **Production Run**:
   ```bash
   python generate_signals.py
   ```

## Monitoring

### Normal Operation
```
Layer 2: Signal Generation Pipeline
====================================
Batch ID: abc12345
Dry run: False
Incremental: True
Current hour only: True

Processing granularity: H1
Found 10 active strategy configurations

  Processing EURUSD (Asset_ID: 5) with 2 strategies
    Loaded 5 price bars (from 2026-04-06 14:00:00)
    Persisted 1 signals for Strategy A
    Persisted 0 signals for Strategy B

Execution Summary
====================================
Batch ID:          abc12345
Strategies:        10
Assets:            5
Signals Generated: 5
Execution Time:    1250.50ms
```

### Warning Signs
- Signal count > 50 per hour: Check incremental mode is working
- Duplicate warnings: Run verify_signals.py --fix-duplicates
- High execution time: Check if full backfill is happening

## Rollback Plan

If issues occur:

1. Revert to original code (git checkout)
2. The database schema changes are backward-compatible
3. The new columns in Fact_Signals are nullable
4. The Processing_Log table can be ignored by old code

## Future Enhancements

1. **Retry Logic**: Add automatic retry for failed processing attempts
2. **Metrics**: Export processing metrics (signals/hour, processing time)
3. **Alerting**: Alert on abnormal signal counts or processing failures
4. **Archival**: Archive old signals to prevent table bloat
