# Scalable Brain

Scalable Brain is a layered quantitative trading system that separates research, signal generation, ML filtering, execution, telemetry, and audit into explicit contracts.

Last updated: 2026-04-06

This repository currently runs an 8-layer runtime structure:

1. Layer 0: Strategy qualification and promotion artifacts
2. Layer 1: Market regime detection and ingestion
3. Layer 2: Rule-based signal generation engine
4. Layer 3: ML gatekeeper training and feature alignment
5. Layer 4: Live execution orchestration and risk gating
6. Layer 5: API + dashboard telemetry surface
7. Layer 6: Post-trade outcome auditing
8. Layer 7: Broker execution adapter

NLP macro intelligence is implemented under src/nlp as an auxiliary data service that writes Fact_Macro_Events and is planned for tighter Layer 3/4 feature integration.

## Repository Structure

```
src/
  layer0/            # Offline qualification + Layer 2 config generation
  layer1_regime/     # Regime tables and clustering pipelines
  layer2_signals/    # Signal engine, indicator registry, persistence
  layer3_ml/         # Training + feature engineering/alignment contract
  layer4_executor/   # Live pipeline (consumes L1/L2/L3 outputs)
  layer5/            # FastAPI telemetry backend
  layer6_auditor/    # Outcome reconciliation
  layer7/            # Oanda trade executor
docs/
  design/            # Architecture and schema references
  reference/         # Operational references and indexes
frontend/            # Human-readable HTML architecture/docs portal
src/nlp/             # FinBERT + macro ingestion (auxiliary feature source)
```

## Core Data Flow

1. Layer 0 backtests and qualifies strategy variants.
2. Layer 1 writes market regime context to `Fact_Market_Regime_V2`.
3. Layer 2 writes raw trade candidates to `Fact_Signals`.
4. Layer 3 trains model artifacts using `Fact_Signals` + regime + outcomes.
5. Layer 4 loads latest signals, applies ML threshold/risk/correlation checks, and executes through Layer 7.
6. Layer 5 exposes observability endpoints for frontend and operations.
7. Layer 6 updates unresolved outcomes in `Fact_Live_Trades`.
8. `src/nlp/macro_scraper.py` ingests macro events and sentiment into `Fact_Macro_Events` for upcoming model/context usage.

## Current System State (Apr 6, 2026)

1. Layer 4 execution path is running with schema-aligned SQL writes and escaped SQL Server reserved words.
2. Layer 4 logging now uses rotating logs to prevent oversized single-day files.
3. Layer 1 regime pipeline return-shape mismatch has been fixed in clustering flow.
4. Layer 5 remains read-oriented and should not own signal/execution logic.
5. NLP/FinBERT pipeline is implemented and writing macro intelligence, but is not yet a mandatory gate in Layer 4 decisions.

## Upcoming Improvements

1. Integrate `Fact_Macro_Events` features into Layer 3 training sets and Layer 4 pre-trade context checks.
2. Add explicit schema health checks before Layer 4 starts (fail fast on drift).
3. Add source-of-truth synchronization checks so HTML docs reflect canonical markdown contracts automatically.
4. Expand telemetry to show macro sentiment snapshots, event surprise, and sentiment dispersion trends.

## Local Runbook

### Python environment

Use the project virtual environment:

```bash
source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate
```

### Layer 5 backend

```bash
cd scalable-brain
python src/layer5/run.py
```

### Layer 5 frontend

```bash
cd scalable-brain/src/layer5/frontend
npm install
npm run dev
```

### Layer 4 scheduled execution

The cron wrapper is in `shell/cron_layer4_pipeline.sh` and runs `src/layer4_executor/live_pipeline.py` with configurable flags.

## Current Source-of-Truth Docs

- `docs/design/SYSTEM_ARCHITECTURE.md`
- `docs/design/ERD_ACTIVE_SCHEMA_2026.md`
- `docs/reference/DOCUMENTATION_INDEX_2026_04_05.md`
- `src/layer0/README_LAYER0_INTEGRATION.md`
- `src/layer5/README_LAYER5.md`
- `src/layer5/frontend/README.md`

Historical reports under `results/` remain immutable run artifacts and are not architecture source-of-truth.
