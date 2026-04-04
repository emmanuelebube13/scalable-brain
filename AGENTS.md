# AGENTS.md

This file is the authoritative operational context for coding agents working in this repository.

Last verified snapshot: 2026-04-04
Repository root: /home/emmanuel/Documents/Scalable_Brain/scalable-brain

## 1) Mission And Scope

Scalable Brain is an instrument-agnostic quantitative trading platform built as a layered decision pipeline.

Core idea:
- Deterministic strategies generate opportunities.
- Regime context explains market state.
- ML gatekeeper filters low-quality setups.
- Risk and correlation controls protect portfolio exposure.
- Execution and audit close the loop.

Agent goal in this repo:
- Preserve pipeline contracts and backward compatibility.
- Prefer minimal, targeted changes.
- Treat schema and runtime contracts as first-class.

## 2) Current Repository State (Verified)

Top-level active structure currently includes:
- AGENTS.md
- archieved/
- assets/
- design/
- docs/
- frontend/
- init-db/
- logs/
- models/
- results/
- shell/
- src/
- testing/
- v1-legacy-object/
- path_map.json

Important notes:
- The project currently uses archieved (typo retained for compatibility) as the active archive folder.
- docs/ is active and contains migrated documentation from legacy doc/.
- results/ has been reorganized into reports/, sql/, and state/ with compatibility symlinks at results root.
- logs/ is now a real directory (not a broken symlink).

## 3) Layered System Status

### Layer 0 (Qualification)
Primary code:
- src/layer0/qualify_strategies.py
- src/layer0/layer2_config_adapter.py

Observed outputs:
- results/sql/layer2_strategies.sql
- results/sql/layer2_indicator_extension.sql
- results/reports/qualification_report_*.json|md
- results/state/qualification_progress.json

Current status:
- Functional and producing Layer 2 seed artifacts.

### Layer 1 (Regime)
Primary code:
- src/layer1_regime/Fact_market_regime_v2.py
- src/layer1_regime/ingest_regimes.py

Current status:
- V2 ingestion pipeline exists and is preferred.
- Writes regime labels for H1/H4 and includes lineage fields.

### Layer 2 (Signals)
Primary code:
- src/layer2_signals/generate_signals.py
- src/layer2_signals/signal_engine/*

Current status:
- Data-driven signal engine is in place.
- Depends on Layer 0 promotion SQL being applied.

### Layer 3 (ML Gatekeeper)
Primary code:
- src/layer3_ml/train_ml_gatekeeper.py

Current status (after recent fixes):
- Supports strict/fallback selection modes.
- Includes threshold diagnostics for validation and test.
- Enforces configurable min/max turnover and min expectancy gates.
- Expands feature query with optional context columns when present.
- Refuses degenerate promotion unless explicitly overridden.

Model artifacts currently present in models/:
- best_ml_gatekeeper_sklearn.pkl
- best_ml_gatekeeper_preprocessor.pkl
- ml_gatekeeper_run_*.json

Champion contract artifacts currently absent:
- models/champion_model.pkl
- models/champion_preprocessor.pkl
- models/champion_manifest.json

### Layer 4 (Execution / Risk / Correlation)
Primary code:
- src/layer4_executor/live_pipeline.py

Current status (verified runtime):
- Starts successfully.
- Loads legacy Layer 3 model artifacts if champion artifacts are missing.
- Auto-detects installed SQL Server ODBC driver (18/17/env override).
- Handles Fact_Signals schema variants (with/without Is_Active column).
- Uses SQLAlchemy-safe parameter binding for SQL Server.
- Returns exit code 0 when no eligible signals are found (valid operational state).

### Layer 5 (Telemetry)
Primary code:
- src/layer5/run.py
- src/layer5/api/*
- src/layer5/services/*
- src/layer5/frontend/*

Current status:
- FastAPI + frontend structure exists.
- Designed to consume outputs from Layers 1-4.

### Layer 6 (Auditor)
Primary code:
- src/layer6_auditor/trade_auditor.py
- src/layer6_auditor/tools/patch_actual_outcome.py

Current status:
- Auditor pipeline exists and is used to close unresolved outcomes.

### Layer 7 (Execution Extensions)
Primary code:
- src/layer7/oanda_executor.py
- src/layer7/exploratory/monte_carlo_dashboard.py

Current status:
- Executor integration present and imported by Layer 4.

## 4) Data And Contract Expectations

Primary DB: ForexBrainDB (SQL Server)

Critical cross-layer tables:
- Dim_Asset
- Dim_Strategy
- Dim_Strategy_Config
- Dim_Strategy_Asset_Mapping
- Dim_Indicator_Library
- Fact_Market_Prices
- Fact_Market_Regime_V2 (preferred)
- Fact_Signals
- Fact_Trade_Outcomes
- Fact_Live_Trades

Contract rules that must not be broken:
- Granularity alignment across regime/signals/outcomes (Layer 3 supervised event contract).
- Layer 3 supports H1/H4 only unless explicitly extended.
- Layer 4 must not recompute Layer 1/Layer 2 outputs internally.

## 5) Runtime Verification Snapshot (2026-04-04)

Verified behavior:
- python src/layer4_executor/live_pipeline.py runs without startup crash.
- Layer 4 reports legacy model fallback when champion artifacts are absent.
- Layer 4 currently reports no H1 signals and exits cleanly (code 0).

This is expected in quiet windows or when Fact_Signals has no recent qualifying rows.

## 6) Active Output Layout

results/ structure:
- results/sql/
  - layer2_strategies.sql
  - layer2_indicator_extension.sql
  - diagnose_price_duplication.sql
- results/reports/
  - qualification_report_*.json
  - qualification_report_*.md
- results/state/
  - qualification_progress.json

Compatibility at results root:
- symlinks exist for legacy direct file paths (do not remove without migration update).

## 7) Documentation Layout

docs/ currently organized as:
- docs/design/
- docs/research/
- docs/notes/content/
- docs/reference/

Notable files:
- docs/design/SYSTEM_ARCHITECTURE.md
- docs/design/ERD_ACTIVE_SCHEMA_2026.md
- docs/design/ICE1_ForexBrain_DDL.sql

## 8) Known Gaps And Risks

- Champion model contract not yet materialized in models/ (Layer 4 using legacy fallback).
- Repository is currently in a heavy in-flight migration state (many staged/unstaged changes).
- Naming drift remains between archieved and archived in planning artifacts; active filesystem still uses archieved.

## 9) Agent Rules (Project-Specific)

Do:
- Preserve existing layer boundaries and contracts.
- Prefer additive compatibility fixes over breaking refactors.
- Keep SQL/schema changes paired with docs updates.
- Use schema-aware code where tables vary across migration states.

Do not:
- Remove compatibility symlinks blindly.
- Assume optional columns exist (for example Fact_Signals.Is_Active).
- Force champion-only loading in Layer 4 unless Layer 3 promotion is guaranteed.

## 10) Canonical Run Order (Operational)

Post Layer 0 qualification sequence:
1. Apply results/sql/layer2_indicator_extension.sql
2. Apply results/sql/layer2_strategies.sql
3. Run Layer 1 regime ingestion
4. Run Layer 2 signal generation
5. Train Layer 3 (dry-run first), then promote champion when non-degenerate
6. Run Layer 4 execution pipeline
7. Run Layer 6 auditor
8. Run Layer 5 telemetry services as needed

## 11) Layer 3 Recommended Command Patterns

Dry-run strict:
- python src/layer3_ml/train_ml_gatekeeper.py --dry-run --selection-mode strict --min-turnover 0.01 --max-turnover 0.35 --min-expectancy 0.0

Fallback diagnostic run:
- python src/layer3_ml/train_ml_gatekeeper.py --dry-run --selection-mode fallback

Promotion run (guarded):
- python src/layer3_ml/train_ml_gatekeeper.py --selection-mode strict --promote-as-champion

## 12) Security And Safety

- Never commit .env or credentials.
- Treat broker/API keys and DB secrets as sensitive.
- Avoid destructive SQL without explicit confirmation and dependency checks.
- Preserve auditability: update docs when behavior changes at layer boundaries.

## 13) Quick Troubleshooting Map

If Layer 4 fails at startup:
- Check logs directory path validity.
- Check model artifacts in models/.
- Check installed ODBC drivers.

If Layer 4 runs but executes nothing:
- Verify Fact_Signals has recent rows for target granularity.
- Verify signal freshness window and gating thresholds.

If Layer 3 fails to produce deployable model:
- Review threshold diagnostics output.
- Confirm turnover/expectancy gates are realistic for current data window.
- Check granularity contract and outcome table coverage.

---

If this file conflicts with implementation behavior, implementation wins. Update this file in the same change set that updates behavior.
