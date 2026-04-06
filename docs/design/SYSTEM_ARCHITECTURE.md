# Scalable Brain System Architecture (Current)

Last updated: 2026-04-06

## Principles

1. Layer contracts are explicit and table/artifact based.
2. No downstream layer recomputes upstream logic.
3. Granularity (`H1`, `H4`) is preserved across training and inference.
4. Execution decisions are deterministic given signal + regime + model artifact.

## 8-Layer Runtime Model

### Layer 0: Strategy Qualification

- Code: `src/layer0/`
- Purpose: Backtest and qualify strategy variants, then emit Layer 2 configuration artifacts.
- Key outputs: qualification reports + SQL promotion scripts for strategy/config mapping.

### Layer 1: Regime Detection

- Code: `src/layer1_regime/`
- Purpose: Generate market state labels and regime context features.
- Key outputs: `Fact_Market_Regime_V2` (with ATR/ADX and context features).

### Layer 2: Signal Generation

- Code: `src/layer2_signals/`
- Purpose: Evaluate active strategy configs against market prices using indicator/rule pipeline.
- Key outputs: `Fact_Signals` via temp-table + MERGE upsert pattern.

### Layer 3: ML Gatekeeper

- Code: `src/layer3_ml/`
- Purpose: Train and package champion model artifacts that score Layer 2 signals in Layer 1 context.
- Key outputs: model artifact, preprocessor artifact, champion manifest, run metadata.

### Layer 4: Live Execution Orchestrator

- Code: `src/layer4_executor/live_pipeline.py`
- Purpose: Load signals/regimes/model artifact, run gate checks, compute ATR risk, apply correlation gate, execute trade.
- Key outputs: `Fact_Live_Trades`, `Fact_Execution_Log`.

### Layer 5: Telemetry API + Frontend

- Code: `src/layer5/`
- Purpose: Serve read-side observability for KPI, trades, risk, regimes, model, strategies, assets.
- Key outputs: FastAPI routes (`/api/v1/*`) and React dashboard views.

### Layer 6: Trade Auditor

- Code: `src/layer6_auditor/trade_auditor.py`
- Purpose: Reconcile unresolved live trades and patch `Actual_Outcome` based on market path.

### Layer 7: Broker Executor

- Code: `src/layer7/oanda_executor.py`
- Purpose: Position sizing + Oanda order placement adapter used by Layer 4.

## Auxiliary Intelligence Service (Upcoming Integration)

### NLP Macro Intelligence (Pre-Feature Layer)

- Code: `src/nlp/finbert.py`, `src/nlp/macro_scraper.py`
- Purpose: Ingest macro event text and score sentiment/uncertainty using FinBERT.
- Table output: `Fact_Macro_Events`
- Current state: implemented and ingest-capable, but not yet enforced as a hard gate in Layer 4.

Planned integration targets:

1. Layer 3: include macro sentiment, dispersion, and surprise features in training/inference feature contracts.
2. Layer 4: optionally veto or downweight trades during high-impact macro windows with adverse sentiment context.
3. Layer 5: add macro observability endpoints and dashboard cards.

## Layer Relationship Focus: Layer 2 -> Layer 3

Layer 2 and Layer 3 are tightly coupled by supervised-event contract.

1. Layer 2 writes `Fact_Signals` with `Signal_Value`, strategy identifiers, granularity, and indicator snapshots.
2. Layer 3 training query joins:
	- regime table (`Fact_Market_Regime_V2` or fallback),
	- `Fact_Signals`,
	- `Fact_Trade_Outcomes`.
3. Layer 3 learns whether Layer 2 candidates become winners (`Is_Winner`) and exports thresholded artifacts.
4. Layer 4 applies those Layer 3 artifacts to new Layer 2 signals.

## Operational Entry Points

- Layer 2 run: `src/layer2_signals/generate_signals.py`
- Layer 3 training: `src/layer3_ml/training/train_ml_gatekeeper.py`
- Layer 4 run: `src/layer4_executor/live_pipeline.py`
- Layer 5 API run: `src/layer5/run.py`
- Layer 6 audit run: `src/layer6_auditor/trade_auditor.py`
- NLP macro run: `src/nlp/macro_scraper.py`

## Current Runtime Health Snapshot (Apr 6, 2026)

1. Layer 4 schema write path has been aligned with current `Fact_Live_Trades` columns.
2. SQL reserved keyword issue for `Close` has been fixed via escaped `[Close]` usage.
3. Layer 1 clustering return signatures are now consistent for all failure paths.
4. Layer 4 log file handling now uses rotation (size + backups).

## Deprecated Narrative

Any previous references to a 6-layer model or Streamlit-only Layer 5 are deprecated in favor of this document and the current code contracts.
