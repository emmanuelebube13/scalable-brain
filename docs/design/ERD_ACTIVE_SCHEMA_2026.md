# ForexBrain Database ERD Mapping (April 3, 2026)
## Current Active Schema - Complete Analysis

---

## 📊 Database Overview

**Database Name:** `ForexBrainDB`
**Environment:** Production (MSSQL Server)
**Last Updated:** 2026-04-03
**Schema Version:** Layer 2 Normalized (Post-Migration)
**Total Active Tables:** 14 (7 Dimensions, 7 Facts)

---

## 🏗️ Architecture Layers

The database is organized by the 6-Layer Execution Pipeline:

```
Layer 0 (Offline) ─→ Layer 1 (Regime) ─→ Layer 2 (Signals) ─→ Layer 3 (ML) ─→ Layer 4/5 (Execution/Audit)
  [Backtests]          [Clustering]       [Generation]      [Gatekeeper]    [Live Trades]
```

Each layer has its corresponding fact/dimension tables:

| Layer | Purpose | Key Tables |
|-------|---------|-----------|
| **Layer 0** | Strategy Qualification (Backtesting) | `Fact_Trade_Outcomes` |
| **Layer 1** | Market Regime Detection | `Fact_Market_Regime_V2` |
| **Layer 2** | Signal Generation | `Dim_Strategy*`, `Fact_Signals`, `Fact_Indicator_Values` |
| **Layer 3** | ML Meta-Labeling | `train_ml_gatekeeper.py` uses all three: Regime → Signals → Outcomes |
| **Layer 4.5** | Dynamic Risk Mgmt | `Fact_Live_Trades` (pre-risk-check) |
| **Layer 5** | Live Execution | `Fact_Live_Trades` (post-execution) |
| **Layer 6** | Auditing | `Fact_Live_Trades` (updates Actual_Outcome) |

---

## 📋 Complete Table Reference

### DIMENSION TABLES (Reference/Lookup Data)

#### **Dim_Asset** ⭐ (Core Hub)
**Purpose:** Master list of tradeable currency pairs  
**Layer:** Layer 0 (Ingestion)  
**Read By:** All layers  

| Column | Type | PK/FK | Nullable | Description |
|--------|------|-------|----------|-------------|
| Asset_ID | INT | PK | NO | Unique asset identifier |
| Symbol | VARCHAR(20) | - | NO | Currency pair (e.g., EUR_USD, GBP_USD) |
| Market_Type | VARCHAR(20) | - | YES | Market classification (FX, COMMODITIES, etc.) |
| Is_Active | BIT | - | YES | Flag for active/inactive assets |
| Created_Date | DATETIME | - | YES | Record creation timestamp |

**Foreign Key References:**
- Referenced by: `Fact_Market_Prices`, `Fact_Market_Regime_V2`, `Fact_Signals`, `Fact_Trade_Outcomes`, `Fact_Live_Trades`, `Fact_Macro_Events`, `Fact_Indicator_Values`, `Dim_Strategy_Asset_Mapping`

**Disadvantages:**
- ⚠️ No versioning if asset definitions change
- ⚠️ Is_Active flag logic scattered across queries (not enforced at DB level)
- ⚠️ Market_Type is under-utilized (not leveraged for portfolio correlation checks)

**Points of Improvement:**
- ✅ Add CHECK constraint: `Market_Type IN ('FX', 'COMMODITIES', 'INDICES', 'BONDS')`
- ✅ Create indexed view for active assets only
- ✅ Add pip_value and contract_multiplier for P&L calculations
- ✅ Add creation_timestamp and deprecation_timestamp for audit trail

---

#### **Dim_Strategy** 🎯 (NEW - Layer 2 Refactor)
**Purpose:** Strategy identity and versioning hub  
**Layer:** Layer 2 (Signal Generation)  
**Status:** ACTIVE (post-April 2, 2026 migration)

| Column | Type | PK/FK | Nullable | Description |
|--------|------|-------|----------|-------------|
| Strategy_ID | INT | PK | NO | Unique strategy identifier |
| Strategy_Key | VARCHAR(50) | UNQ | NO | Human-readable name (e.g., 'bbands_mean_revert_v1') |
| Strategy_Type | VARCHAR(30) | - | NO | Category (MEAN_REVERSION, TREND_FOLLOWING, MEAN_REVERSION_OSCILLATOR) |
| Is_Active | BIT | - | NO | Enable/disable strategy globally |
| Created_Date | DATETIME | - | NO | Creation timestamp |
| Updated_Date | DATETIME | - | YES | Last modification timestamp |
| Python_Module | VARCHAR(255) | - | YES | Path to Python implementation (e.g., 'strategies.bbands_mean_revert') |

**Foreign Key References:**
- Parent of: `Dim_Strategy_Config`, `Dim_Strategy_Asset_Mapping`
- Referenced by: `Fact_Signals`, `Fact_Trade_Outcomes`, `Fact_Live_Trades`

**Disadvantages:**
- ⚠️ No conflict detection if two strategies generate opposite signals on same asset/timeframe
- ⚠️ Python_Module field is metadata-only (not enforced)

**Points of Improvement:**
- ✅ Add signal_conflict_resolution column (e.g., 'MAJORITY_VOTE', 'WEIGHTED_CONFIDENCE')
- ✅ Add description and documentation fields
- ✅ Track strategy author and revision history

---

#### **Dim_Strategy_Config** ⚙️ (NEW - Layer 2 Refactor)
**Purpose:** Versioned parameter sets for each strategy  
**Layer:** Layer 2 (Signal Generation)  
**Status:** ACTIVE (post-April 2, 2026 migration)

| Column | Type | PK/FK | Nullable | Description |
|--------|------|-------|----------|-------------|
| Config_ID | INT | PK | NO | Unique config identifier |
| Strategy_ID | INT | FK | NO | References Dim_Strategy |
| Config_Version | INT | - | NO | Incremental version number (v1, v2, v3...) |
| Config_Timestamp | DATETIME | - | NO | When this config version was created |
| Config_Hash | VARCHAR(255) | - | NO | SHA256 hash of JSON rules (for deduplication) |
| Indicator_Configs | NVARCHAR(MAX) | - | NO | JSON: `{"rsi_period": 14, "rsi_overbought": 70}` |
| Signal_Rules | NVARCHAR(MAX) | - | NO | JSON: `{"entry_logic": "rsi > 70", "exit_logic": "price < sma_50"}` |
| Is_Active | BIT | - | NO | Whether this config is currently used for signal generation |
| Backtest_Profit_Factor | FLOAT | - | YES | PF from backtesting on historical data |
| Backtest_Expectancy_Per_Trade | FLOAT | - | YES | Expected $ per trade (from backtesting) |
| Live_Trades_Count | INT | - | YES | Number of live trades generated |
| Live_Win_Rate | FLOAT | - | YES | Real P&L win rate (0.0 to 1.0) |

**Foreign Key References:**
- Parent of: `Dim_Strategy_Asset_Mapping`
- Referenced by: `Fact_Signals`, `Fact_Indicator_Values`

**Disadvantages:**
- ⚠️ JSON rules are unvalidated (no schema enforcement at DB layer)
- ⚠️ Backtest metrics can drift from live performance (no real-time sync)
- ⚠️ No rollback mechanism if config introduces drawdown

**Points of Improvement:**
- ✅ Add JSON_VALUE checks in INSERT/UPDATE triggers to validate JSON structure
- ✅ Add audit_trail column to track who approved each config change
- ✅ Add max_consecutive_losses threshold to auto-disable if exceeded
- ✅ Create indexed view for active configs only
- ✅ Add rollback_previous_config_id for quick version revert

---

#### **Dim_Strategy_Asset_Mapping** 🗺️ (NEW - Layer 2 Refactor)
**Purpose:** Maps strategy configs to specific assets and timeframes  
**Layer:** Layer 2 (Signal Generation)  
**Status:** ACTIVE (post-April 2, 2026 migration)

| Column | Type | PK/FK | Nullable | Description |
|--------|------|-------|----------|-------------|
| Mapping_ID | INT | PK | NO | Unique mapping identifier |
| Strategy_ID | INT | FK | NO | References Dim_Strategy |
| Asset_ID | INT | FK | NO | References Dim_Asset |
| Granularity | VARCHAR(10) | - | NO | Timeframe (H1, H4, D1, W1) |
| Config_ID | INT | FK | NO | References Dim_Strategy_Config (active config) |
| Priority | INT | - | NO | Signal priority (1=highest, 99=lowest) for conflict resolution |
| Is_Active | BIT | - | NO | Whether this mapping is enabled |
| Created_Date | DATETIME | - | NO | Creation timestamp |
| Updated_Date | DATETIME | - | YES | Last modification timestamp |

**Foreign Key References:**
- References: `Dim_Strategy`, `Dim_Asset`, `Dim_Strategy_Config`
- Used by: Signal generation engine (Layer 2)

**Disadvantages:**
- ⚠️ No correlation matrix to detect highly-correlated signals (can cause over-leverage)
- ⚠️ Priority is manual (should be AI-weighted based on live performance)

**Points of Improvement:**
- ✅ Add estimated_correlation_to_existing_positions column (updated nightly)
- ✅ Add ai_priority_weight_learned (auto-adjusted based on live PnL)
- ✅ Add max_notional_exposure column for position sizing limits
- ✅ Add session_time_filter (e.g., 'LONDON_08-12_UTC', 'NY_13-17_UTC') for time-zone sensitive trading

---

#### **Dim_Indicator_Library** 📚
**Purpose:** Registry of all available technical indicators  
**Layer:** Layer 2 (Signal Generation)  
**Status:** ACTIVE

| Column | Type | PK/FK | Nullable | Description |
|--------|------|-------|----------|-------------|
| Indicator_ID | INT | PK | NO | Unique indicator identifier |
| Indicator_Key | VARCHAR(50) | UNQ | NO | Code name (e.g., 'RSI', 'SMA_CROSS', 'BOLLINGER_BANDS') |
| Category | VARCHAR(50) | - | NO | Type (MOMENTUM, TREND, VOLATILITY, VOLUME) |
| Required_Price_Fields | VARCHAR(255) | - | NO | CSV: 'OHLCV', 'HLC', 'C' |
| Default_Parameters | NVARCHAR(MAX) | - | YES | JSON: `{"period": 14, "overbought": 70, "oversold": 30}` |
| Python_Class | VARCHAR(255) | - | YES | Import path (e.g., 'ta_lib.RSI', 'indicators.BollingerBands') |
| Calculation_Time_ms | INT | - | YES | Typical calculation time (for optimization) |
| Min_Lookback_Bars | INT | - | NO | Minimum historical bars needed |
| Is_Cacheable | BIT | - | NO | Can results be cached? (true/false) |

**Foreign Key References:**
- Referenced by: `Fact_Indicator_Values`

**Disadvantages:**
- ⚠️ No performance metrics (which indicators are most profitable)
- ⚠️ Default parameters may not be optimal for all assets

**Points of Improvement:**
- ✅ Add profitability_score (win rate when used in signals)
- ✅ Add optimal_parameter_set for each asset (from hyperparameter optimization)
- ✅ Add update_frequency (e.g., 'on_every_candle', 'on_london_open') for partial updates
- ✅ Add supported_granularities (some indicators are only valid on H4+)

---

#### **Dim_Market_Regime** (LEGACY - Reference Only)
**Purpose:** Lookup table for regime labels  
**Layer:** Layer 1 (Regime Detection)  
**Status:** LEGACY (kept for SQL VIEW compatibility)

| Column | Type | PK/FK | Nullable | Description |
|--------|------|-------|----------|-------------|
| Regime_ID | INT | PK | NO | Regime identifier |
| Regime_Name | VARCHAR(50) | - | NO | Label (e.g., 'Trending_HighVol') |
| Volatility_Index | FLOAT | - | YES | VIX-equivalent threshold |

**Note:** This table is kept for backward compatibility but is not actively populated. `Fact_Market_Regime_V2.Regime_Label` is a direct VARCHAR instead.

---

### FACT TABLES (Transactional Data)

#### **Fact_Market_Prices** 💰 (Core OHLCV)
**Purpose:** High-frequency price data ingested from OANDA  
**Layer:** Layer 0 (Data Ingestion)  
**Status:** ACTIVE
**Ingestion Rate:** Continuous (1H candles)
**Data Retention:** 18+ years

| Column | Type | PK/FK | Nullable | Description |
|--------|------|-------|----------|-------------|
| Price_ID | BIGINT | PK | NO | Unique row identifier |
| Timestamp | DATETIME | - | NO | Candle close time (UTC) |
| Asset_ID | INT | FK | NO | References Dim_Asset |
| Open | FLOAT | - | NO | Opening price |
| High | FLOAT | - | NO | Highest price in candle |
| Low | FLOAT | - | NO | Lowest price in candle |
| Close | FLOAT | - | NO | Closing price |
| Volume | BIGINT | - | YES | Tick volume or transaction count |
| Granularity | VARCHAR(10) | - | YES | Timeframe (H1, H4, D1, W1) |

**Indexes:**
- `PK: Price_ID`
- `UK: (Asset_ID, Timestamp, Granularity)` for single-candle lookup
- `IX: Timestamp DESC` (for resume mechanism in ingest)

**Foreign Key References:**
- References: `Dim_Asset`
- Referenced by: `Fact_Market_Regime_V2`, `Fact_Indicator_Values` (join on Timestamp)

**Disadvantages:**
- ⚠️ Single `Granularity` column (H1 prices mixed with potentially H4, D1 data)
- ⚠️ No bid/ask spread data (only mid-prices)
- ⚠️ Volume is tick volume (not contract volume) - reduces PnL accuracy
- ⚠️ No liquidity metadata (bid-ask width changes over time)

**Points of Improvement:**
- ✅ Separate into `Fact_Market_Prices_H1`, `Fact_Market_Prices_H4`, `Fact_Market_Prices_D1` (DONE for H4, D1)
- ✅ Add Bid_Price, Ask_Price, Bid_Volume, Ask_Volume columns for order execution accuracy
- ✅ Add Session field (TOKYO, LONDON, NY, SYDNEY) for session-based strategies
- ✅ Add Data_Quality_Flag (e.g., 'NORMAL', 'SPARSE', 'GAPPED') for gap detection
- ✅ Create rolling hourly average of Bid_Ask spread for slippage simulation

---

#### **Fact_Market_Prices_H4 & Fact_Market_Prices_D1**
**Purpose:** Pre-aggregated 4-hour and daily OHLCV data  
**Layer:** Layer 0 (Ingestion)  
**Status:** ACTIVE
**Data Retention:** 18+ years

Same schema as `Fact_Market_Prices` but granularity-specific (no Granularity column needed).

**Disadvantages:**
- ⚠️ Three separate tables create redundancy (UPDATE one = UPDATE three)
- ⚠️ Denormalization increases storage footprint

**Points of Improvement:**
- ✅ Create indexed view `v_Market_Prices_Unified` that UNION ALL's all three
- ✅ Migrate to single partitioned table by granularity

---

#### **Fact_Market_Regime_V2** 🌦️ (Regime Detection Output)
**Purpose:** Dynamically detected market regime for each asset/timeframe  
**Layer:** Layer 1 (Market Regime Detection)  
**Status:** ACTIVE
**Updated By:** `ingest_regimes.py` and `Fact_market_regime_v2.py` (Layer 1 pipeline)
**Read By:** `train_ml_gatekeeper.py` (Layer 3 ML training)

| Column | Type | PK/FK | Nullable | Description |
|--------|------|-------|----------|-------------|
| Timestamp | DATETIME | PK | NO | Candle close time (UTC) |
| Asset_ID | INT | FK, PK | NO | References Dim_Asset |
| Granularity | VARCHAR(10) | PK | NO | Timeframe (H1, H4, D1) |
| Regime_Label | VARCHAR(50) | - | NO | Classification tag (e.g., 'Trending_HighVol', 'Sideways_LowVol') |
| ATR_Value | FLOAT | - | YES | Average True Range (volatility metric) |
| ADX_Value | FLOAT | - | YES | Average Directional Index (trend strength 0-100) |
| Session_Volume_Z | FLOAT | - | YES | Z-score of current volume vs session average |
| Regime_Model_Version | VARCHAR(20) | - | YES | Which clustering model was used (v1.0, v2.1, etc.) |
| Clustering_Confidence | FLOAT | - | YES | Confidence score of regime assignment (0.0-1.0) |

**Indexes:**
- `PK: (Timestamp, Asset_ID, Granularity)`
- `IX: (Asset_ID, Timestamp DESC)` for regime history lookups

**Foreign Key References:**
- References: `Dim_Asset`
- Referenced by: `train_ml_gatekeeper.py` (left table of 3-way join)

**Disadvantages:**
- ⚠️ Regime labels are arbitrary strings (no enum/domain table enforcing valid values)
- ⚠️ Calculation of regime is deterministic clustering (may not reflect human discretionary regimes)
- ⚠️ No confidence intervals (only point estimate with single confidence score)
- ⚠️ Regime_Model_Version is text (should be FK to model metadata table)

**Points of Improvement:**
- ✅ Create `Dim_Regime_Catalog` table: Regime_Label, Description, ATR_Range, ADX_Range
- ✅ Add regime_transition_probability (vs previous hour's regime)
- ✅ Add regime_duration_hours (how long in current regime)
- ✅ Add model_update_date for explainability
- ✅ Create materialized view for latest regimes only
- ✅ Track regime change events in separate audit table

---

#### **Fact_Signals** 📡 (Trading Signals Output)
**Purpose:** Raw signals generated by strategies before ML gating  
**Layer:** Layer 2 (Signal Generation)  
**Status:** ACTIVE
**Updated By:** Signal engine (Layer 2 `generate_signals.py`)
**Read By:** `train_ml_gatekeeper.py` (Layer 3)

| Column | Type | PK/FK | Nullable | Description |
|--------|------|-------|----------|-------------|
| Timestamp | DATETIME | PK | NO | Signal generation time (UTC) |
| Asset_ID | INT | FK, PK | NO | References Dim_Asset |
| Granularity | VARCHAR(10) | PK | NO | Timeframe (H1, H4, D1) |
| Strategy_ID | INT | FK, PK | NO | References Dim_Strategy |
| Signal_Value | INT | - | NO | -1 (SELL), 0 (HOLD), 1 (BUY) |
| Strategy_Version | VARCHAR(20) | - | NO | Config version used (v1, v2.1, etc.) |
| Config_Hash | VARCHAR(255) | - | YES | Reproducibility: hash of exact JSON rules used |
| Signal_Reason | VARCHAR(500) | - | YES | Human-readable explanation (e.g., "RSI > 70 and Price > SMA50") |
| Rule_ID | VARCHAR(100) | - | YES | Specific rule triggered (for audit trail) |
| Indicator_Snapshot | NVARCHAR(MAX) | - | YES | JSON of all indicator values at signal time |
| Confidence_Score | FLOAT | - | YES | Strategy's internal confidence (0.0-1.0), later overridden by ML |

**Indexes:**
- `PK: (Timestamp, Asset_ID, Granularity, Strategy_ID)`
- `IX: (Strategy_ID, Timestamp DESC)` for strategy signal history
- `IX: (Signal_Value)` for filtering SELL vs BUY

**Foreign Key References:**
- References: `Dim_Asset`, `Dim_Strategy`
- Referenced by: `train_ml_gatekeeper.py` (middle table of 3-way join)

**Disadvantages:**
- ⚠️ No deduplication if same strategy/rule fires multiple times in same candle (may double-count signals)
- ⚠️ Signal_Reason and Rule_ID are free-form text (impossible to aggregate or search)
- ⚠️ Indicator_Snapshot is large JSON (increases I/O for 3-way joins)
- ⚠️ No expiration time (signals older than N bars should be invalidated)

**Points of Improvement:**
- ✅ Add signal_ttl_hours (time-to-live: auto-expire stale signals)
- ✅ Create `Dim_Signal_Rules` table: Rule_ID, Strategy_ID, Description, Trigger_Logic
- ✅ Add is_filtered_by_ml boolean (whether ML gatekeeper was applied)
- ✅ Add ml_approval_score post-facto (after Layer 3 runs)
- ✅ Create unique constraint (Asset_ID, Timestamp, Granularity, Strategy_ID, Rule_ID) to prevent duplicates
- ✅ Compress Indicator_Snapshot as VARBINARY instead of plain JSON

---

#### **Fact_Trade_Outcomes** 🎯 (Backtest Results)
**Purpose:** Win/loss labeling for signals during backtesting  
**Layer:** Layer 0 (Strategy Qualification - Backtesting)  
**Status:** ACTIVE
**Updated By:** `evaluate_trades_atr.py` (post-processing)
**Read By:** `train_ml_gatekeeper.py` (right table of 3-way join)

| Column | Type | PK/FK | Nullable | Description |
|--------|------|-------|----------|-------------|
| Timestamp | DATETIME | PK | NO | Signal timestamp |
| Asset_ID | INT | FK, PK | NO | References Dim_Asset |
| Strategy_ID | INT | FK, PK | NO | References Dim_Strategy |
| Signal_Value | INT | - | NO | -1 (SELL), 1 (BUY) from original signal |
| Forward_Return | FLOAT | - | YES | Pct return N bars after signal (e.g., 0.015 = +1.5%) |
| Is_Winner | BIT | - | YES | Whether Forward_Return > 0 (1=PROFIT, 0=LOSS) |
| Stop_Loss_Hit | BIT | - | YES | Was position stopped out? (1=yes, 0=no/reached TP or expired) |
| Take_Profit_Hit | BIT | - | YES | Was take profit reached? (1=yes, 0=no) |
| Bars_Held | INT | - | YES | How many bars before exit |
| Exit_Price | FLOAT | - | YES | Price at which position was exited |

**Indexes:**
- `PK: (Timestamp, Asset_ID, Strategy_ID)`
- `IX: (Is_Winner)` for win rate calculations

**Foreign Key References:**
- References: `Dim_Asset`, `Dim_Strategy`
- Referenced by: `train_ml_gatekeeper.py` (right table of 3-way join)

**Disadvantages:**
- ⚠️ Forward_Return is realized return (static, no mark-to-market during hold period)
- ⚠️ Stop loss distance is hard-coded (doesn't adapt to regime changes)
- ⚠️ Only binary winner/loser (no labeling of "breakeven" or "small profit"
- ⚠️ No transaction costs or slippage modeling

**Points of Improvement:**
- ✅ Add scenario_return (mark-to-market at each candle during hold)
- ✅ Add transaction_cost_pips and slippage_pips
- ✅ Add atr_multiple_at_entry (how many ATRs was SL away)
- ✅ Create ternary outcome: LOSS, BREAKEVEN, WIN (instead of binary)
- ✅ Track regime_at_entry so ML can learn "BUY signals work best in Trending_HighVol"

---

#### **Fact_Live_Trades** 🚀 (Live Execution Log)
**Purpose:** All trades approved and sent to broker  
**Layer:** Layer 4.5/5/6 (Execution and Audit)  
**Status:** ACTIVE
**Updated By:** `live_pipeline.py` (Layer 4 - execution), `trade_auditor.py` (Layer 6 - outcomes)

| Column | Type | PK/FK | Nullable | Description |
|--------|------|-------|----------|-------------|
| Timestamp | DATETIME | - | NO | Signal approval time (when ML green-lighted trade) |
| Asset_ID | INT | FK | NO | References Dim_Asset |
| Strategy_ID | INT | FK | NO | References Dim_Strategy |
| Signal_Value | INT | - | NO | -1 (SELL), 1 (BUY) |
| Entry_Price | FLOAT | - | YES | Execution fill price |
| Stop_Loss | FLOAT | - | YES | Dynamic ATR-based stop loss |
| Take_Profit | FLOAT | - | YES | Dynamic take profit |
| Confidence_Score | FLOAT | - | YES | ML model confidence (0.0-1.0) |
| Is_Approved | BIT | - | NO | 1 = ML approved, 0 = ML vetoed |
| Order_ID | VARCHAR(50) | - | YES | Broker order ID (OANDA ID) |
| Execution_Time | DATETIME | - | YES | When broker confirmed execution |
| Actual_Outcome | INT | - | YES | Realized P&L in pips (or NULL if still open) |
| Close_Time | DATETIME | - | YES | When position was closed |
| Close_Reason | VARCHAR(50) | - | YES | 'STOP_LOSS', 'TAKE_PROFIT', 'TIME_DECAY', 'VOL_SHOCK' |
| Correlation_Score | FLOAT | - | YES | Portfolio correlation check (0.0-1.0, lower is better) |

**Foreign Key References:**
- References: `Dim_Asset`, `Dim_Strategy`

**Disadvantages:**
- ⚠️ Order_ID is text (not referenced to any broker table, no audit trail to OANDA)
- ⚠️ Single Actual_Outcome field (doesn't distinguish profit/loss reason)
- ⚠️ No Position_Size column (can't calculate $ P&L)
- ⚠️ Close_Reason is free text (should be FK to enum table)

**Points of Improvement:**
- ✅ Add position_size_units and notional_exposure columns
- ✅ Add realized_pnl_dollars and realized_pnl_percent
- ✅ Create `Dim_Trade_Exit_Reason` table with ID + Description
- ✅ Add Execution_Slippage (difference between Entry_Price and filled price)
- ✅ Add post_execution_correlation_check_result (passed/failed)
- ✅ Add link_to_oanda_trade_id (for reconciliation with broker)

---

#### **Fact_Indicator_Values** 📊 (Cached Indicators)
**Purpose:** Pre-calculated technical indicator values (RSI, SMA, etc.)  
**Layer:** Layer 2 (Signal Generation)  
**Status:** ACTIVE
**Updated By:** Indicator calculation engine (Layer 2)
**Read By:** `generate_signals.py` (Layer 2)

| Column | Type | PK/FK | Nullable | Description |
|--------|------|-------|----------|-------------|
| Timestamp | DATETIME | PK | NO | Candle close time (UTC) |
| Asset_ID | INT | FK, PK | NO | References Dim_Asset |
| Granularity | VARCHAR(10) | PK | NO | Timeframe (H1, H4, D1) |
| Indicator_Instance | VARCHAR(100) | PK | NO | Unique name (e.g., 'RSI_14', 'SMA_50', 'BBANDS_20_2') |
| Indicator_ID | INT | FK | NO | References Dim_Indicator_Library |
| Indicator_Value | FLOAT | - | YES | Current value (e.g., 75.5 for RSI) |
| Indicator_Value_Upper_Band | FLOAT | - | YES | For bands/envelopes (e.g., Bollinger upper band) |
| Indicator_Value_Lower_Band | FLOAT | - | YES | For bands/envelopes (e.g., Bollinger lower band) |
| Config_Hash | VARCHAR(255) | - | NO | Hash of indicator parameters (for reproducibility) |
| Calculation_Timestamp | DATETIME | - | NO | When this value was computed |
| Data_Quality_Flag | VARCHAR(20) | - | YES | 'NORMAL', 'INSUFFICIENT_DATA', 'STALE' |

**Indexes:**
- `PK: (Timestamp, Asset_ID, Granularity, Indicator_Instance)`
- `IX: (Indicator_ID, Timestamp DESC)` for indicator history

**Foreign Key References:**
- References: `Dim_Asset`, `Dim_Indicator_Library`

**Disadvantages:**
- ⚠️ Separates indicator values from price data (requires JOIN to get full context)
- ⚠️ One row per indicator per candle (can have 50+ indicators, creating wide tables)
- ⚠️ No versioning if indicator calculation algorithm changes

**Points of Improvement:**
- ✅ Pivot/normalize: Separate columns for each indicator (one row = all indicators)
- ✅ Add previous_value column (for momentum-of-indicator calculations)
- ✅ Add calculation_duration_ms (which indicators are slow?)
- ✅ Create `Dim_Indicator_Version` table to track algo changes
- ✅ Add expiration flag (older than lookback window = invalid)

---

#### **Fact_Macro_Events** 🌍 (Macroeconomic News - NEW)
**Purpose:** Standardized macro economic event surprises (extracted via NLP)  
**Layer:** Layer 2 (Context/Signal Filtering)  
**Status:** ACTIVE
**Updated By:** `macro_scraper.py` (NLP pipeline, not yet fully integrated)

| Column | Type | PK/FK | Nullable | Description |
|--------|------|-------|----------|-------------|
| id | BIGINT | PK | NO | Unique event identifier |
| timestamp | DATETIME | - | NO | Event release time (UTC) |
| asset_id | INT | FK | NO | References Dim_Asset (e.g., USD-sensitive events) |
| event_title | VARCHAR(255) | - | NO | Event name (e.g., 'US Non-Farm Payroll') |
| source | VARCHAR(100) | - | YES | Data source (e.g., 'FRED', 'TRADINGECONOMICS', 'ECBDATAWAREHOUSE') |
| expected_value | FLOAT | - | YES | Consensus forecast (e.g., 200k jobs) |
| actual_value | FLOAT | - | YES | Released value (e.g., 187k jobs) |
| prior_value | FLOAT | - | YES | Previous period's value |
| standardized_surprise_score | FLOAT | - | YES | (actual - expected) / std_dev (z-score, -3.0 to +3.0) |
| finbert_sentiment | FLOAT | - | YES | News sentiment (-1.0 to +1.0) from FinBERT NLP |
| finbert_dispersion | FLOAT | - | YES | Dispersion of sentiments across news sources (0.0-1.0) |
| cyclical_features | NVARCHAR(MAX) | - | YES | JSON: `{"economic_cycle": "expansion", "inflation_trend": "rising"}` |
| inserted_timestamp | DATETIME | - | NO | When this record was created |

**Foreign Key References:**
- References: `Dim_Asset`

**Disadvantages:**
- ⚠️ NLP sentiment is experimental (FinBERT can be noisy)
- ⚠️ Event-to-asset mapping is crude (same event affects many currency pairs differently)
- ⚠️ No confidence scores for how "surprising" the event is from market perspective

**Points of Improvement:**
- ✅ Add event_category ('EMPLOYMENT', 'INFLATION', 'GDPFCAST', 'CENTRAL_BANK')
- ✅ Add impacted_assets (JSON array: which currency pairs are affected)
- ✅ Add market_reaction_5min, market_reaction_1hour (realized market move post-event)
- ✅ Add is_consensus_beat (true if actual > expected for positive indicators)
- ✅ Create embargo tracking (when event was locked/released)

---

### Deprecated Tables (Marked for Deletion)

#### **Fact_Market_Regime** ❌
**Purpose:** Original market regime (replaced by `Fact_Market_Regime_V2`)  
**Status:** DEPRECATED (April 2, 2026)
**Reason:** Schema refinement - V2 adds Granularity, Clustering_Confidence, Regime_Model_Version

#### **Fact_Daily_Regime** ❌
**Purpose:** Daily regime classification (legacy)  
**Status:** DEPRECATED
**Reason:** Replaced by more granular `Fact_Market_Regime_V2` with hourly updates

#### **Dim_Strategy_Registry** ❌
**Purpose:** Legacy strategy registry  
**Status:** DEPRECATED (April 2, 2026)  
**Reason:** Replaced by 3-table design: `Dim_Strategy` + `Dim_Strategy_Config` + `Dim_Strategy_Asset_Mapping`

---

## 🔗 Foreign Key Relationship Map

```
┌─────────────────────────────────────────────────────────┐
│                     HUB: Dim_Asset                      │
│  (Master list of assets: EUR_USD, GBP_USD, etc.)       │
└────────┬────────────────────────┬──────────────────────┘
         │                        │
         ├────→ Fact_Market_Prices               ────────┐
         │       (OHLCV: Layer 0 Ingestion)               │
         │                                                │
         ├────→ Fact_Market_Regime_V2            ←───────┤
         │       (Regime detection: Layer 1)     Reads FM│
         │       ↓ (Uses this data)                       │
         │       │                                        │
         │       └────────────────────────────────────┐   │
         │                                            │   │
         │                                     ┌──────┴───┴──────┐
         │                                     │ Layer 3 ML      │
         │                                     │ (3-way JOIN)    │
         │                                     └──────┬──────────┘
         │                                            │
         ├────→ Dim_Strategy_Asset_Mapping           │
         │       (Maps strategies to assets)          │
         │       │                                    │
         │       └────→ Dim_Strategy_Config           │
         │               (Strategy parameters)        │
         │               │                            │
         │               └────→ Dim_Strategy           │
         │                       (Strategy hub)       │
         │                            │                │
         │                            └────→ Fact_Signals  ←─┤
         │                                   (Signals)       │
         │                                                   │
         ├────→ Fact_Indicator_Values                       │
         │       (Cached calculations)                       │
         │                                                  │
         ├────→ Fact_Trade_Outcomes                        │
         │       (Backtest labels for ML training) ────────┘
         │
         ├────→ Fact_Live_Trades
         │       (Live execution to broker)
         │
         ├────→ Fact_Macro_Events
         │       (Economic news context)
         │
         └────→ Dim_Strategy_Asset_Mapping → Dim_Indicator_Library

```

---

## 📈 Data Flow by Layer

### **Layer 0: Strategy Qualification (Backtesting)**
```
Fact_Market_Prices 
    → [Backtest Engine] 
        → Fact_Signals (theoretical, using strategy rules)
        → Fact_Trade_Outcomes (win/loss labels for historical data)
```

### **Layer 1: Regime Detection**
```
Fact_Market_Prices 
    → [Clustering Algorithm (ATR, ADX, Volume)]
        → Fact_Market_Regime_V2 (regime labels + metrics)
```

### **Layer 2: Signal Generation**
```
Dim_Strategy_Asset_Mapping → Config→Parameters
Fact_Market_Prices, Fact_Indicator_Values
    → [Signal Engine]
        → Fact_Signals (real-time signal generation)
```

### **Layer 3: ML Meta-Labeling (Gatekeeper)**
```
Fact_Market_Regime_V2 (regime context)
Fact_Signals (strategy signals)
Fact_Trade_Outcomes (backtest labels)
    → [3-Way JOIN]
        → [ML Model Training]
            → Confidence Scores for new signals
            (Approval if confidence > 0.75)
```

### **Layer 4.5: Risk Management**
```
Fact_Live_Trades (pending)
    → [ATR-based SL/TP Calculation]
    → [Correlation Matrix Check]
        → Accept or Reject trade
```

### **Layer 5: Live Execution**
```
Fact_Live_Trades (approved)
    → [OANDA Broker API]
        → (Fill price, order ID recorded)
```

### **Layer 6: Audit & Telemetry**
```
Fact_Live_Trades (with fills)
    → [Trade Auditor]
        → Update Actual_Outcome
        → Create audit log
```

---

## 🔍 Query Patterns (Most Common)

### Q1: Get regime for asset (hourly)
```sql
SELECT TOP 1 * FROM Fact_Market_Regime_V2
WHERE Asset_ID = 5 AND Granularity = 'H1'
ORDER BY Timestamp DESC
```

### Q2: Train ML model (3-way join)
```sql
SELECT 
    fmr.Regime_Label, fmr.ATR_Value, fmr.ADX_Value,
    fs.Signal_Value, fs.Confidence_Score,
    fto.Is_Winner, fto.Forward_Return
FROM Fact_Market_Regime_V2 fmr
    INNER JOIN Fact_Signals fs ON fmr.Timestamp = fs.Timestamp 
        AND fmr.Asset_ID = fs.Asset_ID 
        AND fmr.Granularity = fs.Granularity
    INNER JOIN Fact_Trade_Outcomes fto ON fs.Timestamp = fto.Timestamp 
        AND fs.Asset_ID = fto.Asset_ID 
        AND fs.Strategy_ID = fto.Strategy_ID
WHERE fmr.Timestamp >= '2008-01-01'
```

### Q3: Get signal history for strategy
```sql
SELECT Timestamp, Asset_ID, Signal_Value, Confidence_Score
FROM Fact_Signals
WHERE Strategy_ID = 3 AND Timestamp > DATEADD(DAY, -30, GETDATE())
ORDER BY Timestamp DESC
```

### Q4: Calculate win rate by regime
```sql
SELECT 
    fmr.Regime_Label,
    COUNT(*) as Total_Signals,
    SUM(CAST(fto.Is_Winner AS INT)) as Winners,
    CAST(SUM(CAST(fto.Is_Winner AS INT)) AS FLOAT) / COUNT(*) as Win_Rate
FROM Fact_Market_Regime_V2 fmr
    INNER JOIN Fact_Signals fs ON fmr.Timestamp = fs.Timestamp ...
    INNER JOIN Fact_Trade_Outcomes fto ON ...
GROUP BY fmr.Regime_Label
```

---

## 📋 Summary Table: What Changed

| Aspect | Before (v1) | After (v2 - April 3, 2026) |
|--------|-------------|---------------------------|
| **Strategy Definition** | Single `Dim_Strategy_Registry` | 3-table design: `Dim_Strategy` + `Dim_Strategy_Config` + `Dim_Strategy_Asset_Mapping` |
| **Regime Tables** | `Fact_Market_Regime`, `Fact_Daily_Regime` | Single `Fact_Market_Regime_V2` with Granularity |
| **Price Granularity** | Mixed in single table | Separated: `Fact_Market_Prices_H1`, `H4`, `D1` |
| **Total Tables** | 11 | 14 (active) |
| **Deprecated** | 0 | 3 |
| **Unused** | 0 | 1 (Dim_Model_Metadata) |

---

## 🎯 Next Steps for Improvement

### Phase 1: Validation (W/C April 3, 2026)
- [ ] Run `cleanup_deprecated_tables.sql` to drop 4 unused tables
- [ ] Verify all Python scripts still work post-cleanup
- [ ] Create indexed views for common query patterns

### Phase 2: Schema Normalization (W/C April 10, 2026)
- [ ] Add missing enum tables (`Dim_Regime_Catalog`, `Dim_Signal_Rules`, `Dim_Trade_Exit_Reason`)
- [ ] Add missing metadata columns (confidence intervals, tracking fields)
- [ ] Split `Fact_Market_Prices` into separate granularity tables (already done for H4, D1)

### Phase 3: Performance Optimization (W/C April 17, 2026)
- [ ] Add missing indexes (highlighted in each table section)
- [ ] Create materialized views for slow queries
- [ ] Implement partitioning strategy for large fact tables

### Phase 4: Data Quality & Governance (W/C April 24, 2026)
- [ ] Add CHECK constraints for data validation
- [ ] Create audit triggers for sensitive table updates
- [ ] Implement soft-delete pattern for dimension tables

---

**Generated:** April 3, 2026 | **Version:** 2.0 | **Stability:** PRODUCTION-READY
