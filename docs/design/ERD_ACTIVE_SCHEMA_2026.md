# Scalable Brain Active Schema Reference - Swing Trading

> **SWING TRADING SYSTEM** | Database schema for swing trade signal generation, ML filtering, and execution tracking

**Last updated:** 2026-04-06 | **Trading Methodology:** Swing Trading | **Data Velocity:** Real-time market prices + historical context

This document is the active schema map used by the current code paths.

## Core Tables by Layer Contract

### Layer 1 Contract

- `Fact_Market_Regime_V2`
  - Produced by: `src/layer1_regime/Fact_market_regime_v2.py`
  - Consumed by: Layer 3 training, Layer 4 live pipeline, Layer 5 regime/model APIs
  - Typical fields: `Timestamp`, `Asset_ID`, `Granularity`, `Regime_Label`, `ATR_Value`, `ADX_Value`, context columns

### Layer 2 Contract

- `Dim_Strategy`
- `Dim_Strategy_Config`
- `Dim_Strategy_Asset_Mapping`
- `Fact_Signals`
  - Produced by: `src/layer2_signals/signal_engine/core/engine.py`
  - Persisted via: `src/layer2_signals/signal_engine/persistence/repository.py` (MERGE)
  - Key fields used downstream: `Timestamp`, `Asset_ID`, `Strategy_ID`, `Granularity`, `Signal_Value`, `Indicator_Snapshot`, `Confidence_Score`

### Layer 3 Training Contract

- Reads joined data from:
  - regime table (`Fact_Market_Regime_V2` or fallback)
  - `Fact_Signals`
  - `Fact_Trade_Outcomes`
- Training script: `src/layer3_ml/training/train_ml_gatekeeper.py`
- Artifact outputs in `models/`:
  - champion model
  - preprocessor
  - champion manifest

### Layer 4 Execution Contract

- Reads:
  - `Fact_Signals`
  - `Fact_Market_Regime_V2`
  - model artifacts/manifests from `models/`
- Writes:
  - `Fact_Live_Trades`
  - `Fact_Execution_Log`
- Orchestrator: `src/layer4_executor/live_pipeline.py`

Important current-state note:

`Fact_Live_Trades` currently includes `Order_ID` and does not include historical columns such as `Broker_Order_ID`, `Fill_Price`, `Fill_Time`, `Slippage_Pips`, `Model_Threshold`, `Regime_Label`, `Correlation_Score`, `Correlation_Passed`, `Updated_At`.
Layer 4 writes must remain aligned to the active column set.

### Layer 5 Telemetry Read Model

- FastAPI routes consume read models from:
  - Layer 1 tables (regime)
  - Layer 2 tables (signals)
  - Layer 4 tables (live trades/risk)
  - Layer 3 artifact metadata (manifest/files)
- API entrypoint: `src/layer5/api/main.py`

### NLP Macro Intelligence Contract (Auxiliary)

- Reads:
  - ECB/Fed RSS content and macro calendar event feeds
- Writes:
  - `Fact_Macro_Events`
- Producer:
  - `src/nlp/macro_scraper.py`
- FinBERT inference:
  - `src/nlp/finbert.py`

Current usage status:

1. Persisted and available for analytics.
2. Planned for Layer 3/4 feature integration in upcoming iterations.

### Layer 6 Audit Contract

- Reads unresolved rows from `Fact_Live_Trades`.
- Updates `Actual_Outcome` when outcome can be resolved.
- Auditor: `src/layer6_auditor/trade_auditor.py`

## Shared Dimension/Reference Tables

- `Dim_Asset` is the common asset hub across all runtime layers.
- Strategy dimensions are shared between Layer 0 promotion outputs and Layer 2 runtime engine.

## Granularity Contract

1. Layer 2 runtime defaults to `H1`/`H4`.
2. Layer 3 gatekeeper supports `H1`/`H4` (explicitly validates supported set).
3. Layer 4 enforces granularity-aware joins and model compatibility.

## Current Runtime State Highlights (Apr 6, 2026)

1. Layer 4 SQL Server reserved keyword handling uses `[Close]` in correlation/price-history query paths.
2. Layer 4 logging uses rotation to cap single-file growth.
3. Layer 1 clustering failure paths now return consistent tuple shape for ingestion stability.

## Notes on Historical Artifacts

Generated reports in `results/` are run artifacts and not schema authority.
Use this file plus `docs/design/SYSTEM_ARCHITECTURE.md` as authoritative system references.
