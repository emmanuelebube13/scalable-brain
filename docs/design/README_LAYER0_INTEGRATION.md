# Layer 0 Integration Guide

Last updated: 2026-04-06

This guide is the current reference for how Layer 0 qualification artifacts are promoted into Layer 2 runtime configuration tables.

Cross-layer context (current):

1. Runtime model is 8 layers (Layer 0 through Layer 7).
2. NLP macro intelligence under `src/nlp/` is now implemented and will be integrated as an auxiliary feature source in upcoming Layer 3/4 iterations.

## What Changed

The `Kimi_Agent_Layer 0 Swing Engine` has been **integrated** into `scalable-brain/src/layer0` without destroying the existing data-ingestion files.

### Existing Files (Preserved)
- `ingest_oanda_prices.py` — OANDA  `Fact_Market_Prices` ETL
- `seed_dim_asset_test.py` — `Dim_Asset` seeding utilities
- `promotion/layer2_strategy_map.txt` — human-readable Layer 2 logic map

### New Files (Migrated)
- `core_engine/strategy_base.py`, `core_engine/backtest_engine.py`, `core_engine/strategy_analyzer.py`
- `core_engine/multi_timeframe.py`, `data_access/indicators.py`, `data_access/utils.py`, `qualification/demo.py`
- `strategies/*.py` — 6 strategy families, 18 variants
- `qualification/qualify_strategies.py` — **updated** to pull from DB and emit Layer 2 SQL

### Integration Files (New)
- `data_access/data_loader.py` — reads `Dim_Asset` + `Fact_Market_Prices` via `pyodbc`
- `promotion/layer2_config_adapter.py` — maps qualified strategies to `Dim_Strategy_Config` JSON and generates T-SQL MERGE scripts
- `README_SWING_ENGINE.md` — original Swing Engine documentation
- `README_LAYER0_INTEGRATION.md` — this file

## How to Run

### 1. Backtest against live DB data
```bash
cd scalable-brain/src/layer0
python qualify_strategies.py --use-db --env-file ../../../.env
```

### 2. Offline mode (CSV / synthetic fallback)
```bash
python qualify_strategies.py --no-use-db --assets EUR_USD GBP_USD --granularities H4
```

### 3. Outputs
All outputs land in `./results/` (or the path you pass with `--output-dir`):
- `qualification_report_YYYYMMDD_HHMMSS.json` — raw metrics
- `qualification_report_YYYYMMDD_HHMMSS.md` — human-readable report
- `layer2_strategies.sql` — **T-SQL seed script** for `Dim_Strategy`, `Dim_Strategy_Config`, `Dim_Strategy_Asset_Mapping`
- `layer2_indicator_extension.sql` — SQL to register `ATR` in `Dim_Indicator_Library`

## Promotion Workflow (Option B)

1. Run qualification:
   ```bash
   python qualify_strategies.py --use-db
   ```
2. Review the Markdown report.
3. Execute the generated SQL in SQL Server Management Studio (or via `pyodbc`):
   ```bash
   # Example
   sqlcmd -S your_server -d ForexBrainDB -i ./results/layer2_strategies.sql
   ```
4. Run Layer 2 signal generation:
   ```bash
   cd ../layer2_signals
   python generate_signals.py
   ```

## Asset ID Alignment

**No hardcoded asset IDs remain in Layer 0.**

`data_loader.py` dynamically queries `Dim_Asset`:

| Asset_ID | Symbol   |
|----------|----------|
| 1        | EUR_USD  |
| 2        | GBP_USD  |
| 3        | USD_JPY  |
| 4        | AUD_USD  |
| 5        | USD_CAD  |

This matches the ground-truth screenshot you provided and the `layer2_signals/settings.py` mapping.

## Critical Issues Addressed During Migration

### 1. Asset ID Mismatch
**Problem:** Source hardcoded `EUR_USD=5, GBP_USD=6, USD_JPY=7`. Old seed scripts also used these IDs.  
**Fix:** `data_loader.py` reads `Dim_Asset` dynamically. `layer2_config_adapter.py` resolves symbols to IDs at generation time.

### 2. No Database Data Loader
**Problem:** Source only loaded CSV or synthetic data.  
**Fix:** `data_loader.py` connects to `Fact_Market_Prices` using the same `.env` pattern as Layer 2.

### 3. Layer 2 Config Incompatibility
**Problem:** Source emitted a simple JSON list of names. Layer 2 needs `Indicator_Configs` + `Signal_Rules` JSON arrays.  
**Fix:** `layer2_config_adapter.py` maintains a full catalog mapping every strategy variant to its exact Layer 2 JSON schema and generates `MERGE` SQL.

### 4. Missing `ATR` in Layer 2 Registry
**Problem:** Layer 2 `IndicatorRegistry` only had EMA, ADX, BB, DONCHIAN, RSI, STOCH.  
**Fix:** Added `ATR` to `signal_engine/indicators/registry.py` and created `layer2_indicator_extension.sql` for the DB side.

### 5. Source Import Bug
**Problem:** `strategies/__init__.py` did not export variant classes (`TrendEMAADX_H1_Only`, etc.), causing `ImportError` in `qualify_strategies.py`.  
**Fix:** Updated `strategies/__init__.py` to export all 18 variants.

### 6. Pandas 3.0 Compatibility
**Problem:** Source used uppercase freq strings (`"H"`, `"4H"`, `"D"`) which pandas 3.0 rejects.  
**Fix:** Normalized to lowercase (`"h"`, `"4h"`, `"d"`) in `qualify_strategies.py` and `utils.py`.

### 7. Backtest Engine Bug
**Problem:** `backtest_engine.py` referenced `trade.strategy.max_bars_hold`, but `trade.strategy` is a `str`.  
**Fix:** Passed the `strategy` object into `_check_exit` and used `strategy.config.max_bars_hold`.

## Strategies That Map 1:1 to Layer 2

These families have complete, executable JSON configs in the generated SQL:
- **Trend_EMA_ADX** (H1, H4, MultiTF)
- **Range_Bollinger** (H1, H4, Aggressive)
- **Trend_Donchian** (H1, H4)
- **Range_Stochastic** (H1, H4)

## Strategies Requiring Manual Review

These use custom indicators not available in the standard `ta` library registry. The adapter still generates `Dim_Strategy` rows and approximate configs, but flags them with `Risk_Filters` notes:
- **Support_Resistance** — uses `detect_swing_points` (swing-high/low clustering)
- **VCP_Breakout** — uses custom volatility-contraction / squeeze logic
- **Range_Stochastic_Divergence** — divergence detection is beyond current rule syntax

To promote these to full Layer 2 execution, you must either:
1. Extend `signal_engine/indicators/registry.py` with custom Python indicator classes, OR
2. Implement the logic as custom rules in `signal_engine/rules/evaluator.py`, OR
3. Keep them as Layer 0-only strategies and feed their signals into Layer 3/4 manually.

## Loose-Coupling Design Decisions

- Layer 0 does **not** import Layer 2 modules. It only shares the `.env` convention.
- The SQL seed files are **idempotent MERGE scripts** — safe to rerun.
- `Config_Hash` is computed with SHA-256 (same algorithm as Layer 2 `StrategyConfig`) for traceability.
- Each strategy variant gets its own `Strategy_Key` in `Dim_Strategy`, preserving granularity-specific parameters.

## Next Steps

1. **Run a real backfill** with `python qualify_strategies.py --use-db`
2. **Review `layer2_strategies.sql`** for any custom-strategy warnings
3. **Apply the SQL** to your SQL Server instance
4. **Run Layer 2** (`generate_signals.py`) to confirm signal generation works
5. **Consider adding unit tests** for `data_loader.py` and `layer2_config_adapter.py`
