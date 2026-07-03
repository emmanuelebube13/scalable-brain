# CLAUDE.md

This file provides comprehensive guidance to Claude Code (claude.ai) for working in this repository.

Last updated: 2026-06-20
Repository root: `/home/emmanuel/Documents/Scalable_Brain/scalable-brain`

---

## PROJECT OVERVIEW

**Scalable Brain** is an institutional-grade quantitative trading pipeline for automated Forex trading. It separates concerns across **8 distinct processing layers** with the philosophy: *"No strategy touches live data until it proves a mathematical edge. Every trade is traceable, auditable, and risk-managed."*

- **Language:** Python 3.12
- **Primary DB:** PostgreSQL 16 + TimescaleDB 2.26.3 (host system cluster on `localhost:5432`) — database `ForexBrainDB`, role `sa`. Canonical operational store (FND-004). *SQL Server has been removed.*
- **Secondary DB:** PostgreSQL (research notes)
- > **DB migration status (FND-004): COMPLETE.** Phase 1 (TimescaleDB +
  hypertables), Phase 2 (SQL Server scaffolding removed), and **Phase 3
  (2026-06-23): all runtime code migrated to PostgreSQL** are done. Every layer
  connects via the canonical **`src/common/db.py`** (SQLAlchemy 2.0 + `psycopg2`,
  `postgresql+psycopg2`, UTC session); `MERGE`→`INSERT … ON CONFLICT`; `[Close]`/
  `[Open]` are double-quoted mixed-case columns; `pyodbc`/`pymssql` removed. See
  `docs/database/CODE_MIGRATION_PHASE3.md` and `SQL_TRANSLATION_RULES.md`. The one
  remaining SQL-Server artifact is the **T-SQL generator**
  `src/layer0/layer2_config_adapter.py` (writes `.sql` files; needs schema
  reconciliation — tracked as follow-up).
- **Broker:** OANDA (v20 REST API, practice environment)
- **ML:** XGBoost + LightGBM gatekeeper with scikit-learn preprocessing
- **NLP:** FinBERT (HuggingFace transformers) for macro sentiment
- **Frontend:** React 19 + TypeScript + Vite + shadcn/ui (Layer 5 dashboard)
- **Backend API:** FastAPI (Layer 5 telemetry) + Flask (research notes)
- **Hyperparameter Tuning:** Optuna
- **Dev Tools:** pytest, black, mypy

---

## 8-LAYER RUNTIME ARCHITECTURE

Each layer produces artifacts consumed by downstream layers. No downstream layer recomputes upstream logic. Granularity (`H1`, `H4`) must be preserved across all layers.

### Layer 0 — Strategy Qualification (`src/layer0/`)

**Purpose:** Backtest and validate trading strategies against historical data. Only strategies with a proven mathematical edge get promoted.

**Key files:**
- `src/layer0/qualify_strategies.py` — Main entry point (1105 lines)
- `src/layer0/strategy_base.py` — Base class and config for all strategies
- `src/layer0/backtest_engine.py` — Backtest configuration and result classes
- `src/layer0/indicators.py` — Technical indicators (ATR, ADX, RSI, Bollinger, etc.)
- `src/layer0/strategy_analyzer.py` — Performance metrics analysis
- `src/layer0/multi_timeframe.py` — Multi-timeframe backtest engine
- `src/layer0/layer2_config_adapter.py` — Qualified strategies → Layer 2 SQL config

**Strategy families (6 families, 18 variants):**
- Trend EMA/ADX (`strategies/trend_ema_adx.py`)
- Trend Donchian (`strategies/trend_donchian.py`)
- Range Bollinger (`strategies/range_bollinger.py`)
- Range Stochastic (`strategies/range_stochastic.py`)
- Support/Resistance (`strategies/support_resistance.py`)
- VCP Breakout (`strategies/vcp_breakout.py`)

**Outputs:**
- `results/reports/qualification_report_*.json` and `*.md`
- `results/sql/layer2_strategies.sql`
- `results/sql/layer2_indicator_extension.sql`
- `results/state/qualification_progress.json`

**Run:**
```bash
python src/layer0/qualify_strategies.py --use-db
```

---

### Layer 1 — Market Regime Detection (`src/layer1_regime/`)

**Purpose:** K-Means clustering on volatility/trend features (ATR + ADX + derived features) to classify market state. Writes hourly regime labels with lineage metadata.

**Key files:**
- `src/layer1_regime/Fact_market_regime_v2.py` — Main pipeline (715 lines, preferred)
- `src/layer1_regime/ingest_regimes.py` — Legacy regime ingestion
- `src/layer1_regime/exploratory/regime_clustering.py` — Exploratory clustering
- `src/layer1_regime/exploratory/visualize_cluster.py` — Cluster visualization

**Output:** `Fact_Market_Regime_V2` table (granularity-aware: H1, H4)
**Pattern:** Schema-aware `INSERT … ON CONFLICT` upsert for idempotent writes
**Features:** Silhouette validation, deterministic label mapping

**Run:**
```bash
python src/layer1_regime/Fact_market_regime_v2.py
```

---

### Layer 2 — Signal Generation (`src/layer2_signals/`)

**Purpose:** Data-driven, modular, vectorized signal engine. Evaluates active strategy configs against market prices using indicator/rule pipeline.

**Key files:**
- `src/layer2_signals/generate_signals.py` — Main entry point (187 lines)
- `src/layer2_signals/signal_engine/config/database.py` — DB connection config
- `src/layer2_signals/signal_engine/config/settings.py` — Engine settings
- `src/layer2_signals/signal_engine/core/engine.py` — Core signal engine
- `src/layer2_signals/signal_engine/core/models.py` — Data models
- `src/layer2_signals/signal_engine/indicators/calculator.py` — Indicator computation
- `src/layer2_signals/signal_engine/indicators/registry.py` — Indicator registry
- `src/layer2_signals/signal_engine/indicators/dependency_graph.py` — Dependency resolution
- `src/layer2_signals/signal_engine/rules/evaluator.py` — Rule evaluation
- `src/layer2_signals/signal_engine/persistence/` — DB persistence (`INSERT … ON CONFLICT`)

**Output:** `Fact_Signals` table (915K+ signals)
**Depends on:** Layer 0 promotion SQL being applied first

**Run:**
```bash
python src/layer2_signals/generate_signals.py
```

---

### Layer 3 — ML Gatekeeper (`src/layer3_ml/`)

**Purpose:** Train XGBoost/LightGBM models to filter low-quality signals. Produces champion model artifacts that Layer 4 consumes for inference.

**Key files:**
- `src/layer3_ml/training/train_ml_gatekeeper.py` — Main training script (1755 lines)
- `src/layer3_ml/__init__.py` — Exports for Layer 4 inference
- `src/layer3_ml/feature_alignment.py` — Train/inference column alignment
- `src/layer3_ml/train_ml_gatekeeper.py` — Feature engineering + training (270 lines)
- `src/layer3_ml/model_winner_impact_report.py` — Winner impact analysis

**Features:**
- ColumnTransformer preprocessing with feature alignment
- Strict/fallback selection modes
- Configurable min/max turnover and min expectancy gates
- Tournament selection with Sha256 hashing for artifact integrity
- Threshold diagnostics for validation and test sets

**Artifact contract (what Layer 4 expects in `models/`):**
- `champion_model.pkl` — Trained model
- `champion_preprocessor.pkl` — Fitted ColumnTransformer
- `champion_manifest.json` — Metadata (features, thresholds, hash)
- Legacy fallback: `best_ml_gatekeeper_sklearn.pkl`, `best_ml_gatekeeper_preprocessor.pkl`

**Recommended commands:**
```bash
# Dry-run strict mode
python src/layer3_ml/training/train_ml_gatekeeper.py --dry-run --selection-mode strict --min-turnover 0.01 --max-turnover 0.35 --min-expectancy 0.0

# Fallback diagnostic
python src/layer3_ml/training/train_ml_gatekeeper.py --dry-run --selection-mode fallback

# Promotion (guarded — refuses degenerate models)
python src/layer3_ml/training/train_ml_gatekeeper.py --selection-mode strict --promote-as-champion
```

---

### Layer 4 — Live Execution Pipeline (`src/layer4_executor/`)

**Purpose:** Deterministic trade execution with risk management, correlation guards, and ML gatekeeping. The main orchestrator.

**Key file:**
- `src/layer4_executor/live_pipeline.py` — Main orchestrator (1400+ lines)

**8 execution stages:**
1. Load signals with full features from `Fact_Signals`
2. Load current market regime from `Fact_Market_Regime_V2`
3. Load Layer 3 model artifact (champion → legacy fallback)
4. Compute ATR-based risk parameters (1.0x ATR SL, 3.0x ATR TP, 3.0 RR ratio)
5. Evaluate portfolio correlation gate (max 0.85 correlation, max 25% exposure)
6. Apply ML gatekeeper threshold (`LAYER3_APPROVAL_THRESHOLD=0.20` from `.env`)
7. Execute trades via Layer 7 broker adapter
8. Log results to `Fact_Live_Trades` and `Fact_Execution_Log`

**Key classes:** `ExecutionPipeline`, `TradeDecision`, `SignalContext`, `RegimeContext`, `ModelArtifact`, `RiskParameters`, `CorrelationResult`, `ExecutionResult`

**Runtime behavior:**
- Connects via `src/common/db.py` `get_engine()` (PostgreSQL; no ODBC)
- Schema-aware: handles `Fact_Signals.Is_Active` and the narrowed
  `fact_live_trades` (writes only existing columns via `INSERT … ON CONFLICT`)
- SQLAlchemy `:named` parameter binding — `"Close"`/`"Open"` double-quoted
- Rotating file logs: 10MB max per file, 14 backups
- Returns exit code 0 when no eligible signals found (valid operational state)

**Run:**
```bash
python src/layer4_executor/live_pipeline.py --granularity H1
python src/layer4_executor/live_pipeline.py --dry-run --granularity H1
```

**Cron:**
```bash
bash shell/cron_layer4_pipeline.sh  # hourly via crontab
```

---

### Layer 5 — Telemetry API + Dashboard (`src/layer5/`)

**Purpose:** Read-only observability layer serving KPI, trades, risk, regimes, model, strategy, and asset data. No duplicate decision logic.

**Backend (FastAPI):**
- `src/layer5/run.py` — Uvicorn launcher (port 8001)
- `src/layer5/api/main.py` — FastAPI app with 7 route modules
- `src/layer5/api/routes/kpi.py`, `trades.py`, `risk.py`, `regimes.py`, `model.py`, `strategies.py`, `assets.py`
- `src/layer5/api/config.py` — Env-driven config
- `src/layer5/api/dependencies.py` — FastAPI dependency injection
- `src/layer5/services/db_client.py` — Database client
- `src/layer5/services/query_builder.py` — SQL query construction

**Frontend (React + Vite):**
- `src/layer5/frontend/src/App.tsx` — Main app component
- `src/layer5/frontend/src/services/api.ts` — API integration service
- `src/layer5/frontend/src/components/views/` — Dashboard views
- `src/layer5/frontend/src/components/charts/` — Recharts visualizations
- `src/layer5/frontend/src/components/ui/` — shadcn/ui (Radix) components

**Run backend:**
```bash
python src/layer5/run.py  # FastAPI at http://localhost:8001
```

**Run frontend:**
```bash
cd src/layer5/frontend && npm install && npm run dev  # Vite at http://localhost:5173
```

**Also in this layer:**
- `src/layer5/app.py` — Legacy Dash standalone dashboard
- `src/research_notes_api.py` — Flask API for research notes CRUD (412 lines)

---

### Layer 6 — Trade Auditor (`src/layer6_auditor/`)

**Purpose:** Post-trade outcome reconciliation. Reads unresolved rows from `Fact_Live_Trades` and patches `Actual_Outcome` based on market path.

**Key files:**
- `src/layer6_auditor/trade_auditor.py` — Main auditor (183 lines)
- `src/layer6_auditor/tools/patch_actual_outcome.py` — Outcome patching utility

**Run:**
```bash
python src/layer6_auditor/trade_auditor.py
```

---

### Layer 7 — Broker Executor (`src/layer7/`)

**Purpose:** OANDA order placement with Fractional Kelly position sizing. Called by Layer 4.

**Key files:**
- `src/layer7/oanda_executor.py` — Main executor (643 lines)
- `src/layer7/tests/` — Executor tests

**Position sizing:** Quarter-Kelly with 2% risk cap

---

### Auxiliary — NLP Macro Intelligence (`src/nlp/`)

**Purpose:** FinBERT sentiment analysis on macro events. Implemented but not yet enforced as a hard gate in Layer 3/4.

**Key files:**
- `src/nlp/finbert.py` — FinBERT sentiment analysis
- `src/nlp/macro_scraper.py` — ECB/Fed RSS + calendar event scraping

**Output:** `Fact_Macro_Events` table
**Planned:** Integration into Layer 3 feature contracts, Layer 4 veto/downweight

---

## COMPLETE DIRECTORY STRUCTURE

```
scalable-brain/
├── .env                          # Credentials, API keys, DB config
├── .gitignore                    # 181 lines, comprehensive
├── docker-compose.yml            # Optional dev-only TimescaleDB (profile `dev`, port 5433); canonical store is host PostgreSQL :5432
├── requirements.txt              # Python dependencies
├── path_map.json                 # Standardized directory paths manifest
├── plotly-cloud.toml             # Plotly Cloud deployment config
├── README.md                     # Main project README (393 lines)
├── AGENTS.md                     # Operational context for AI agents
├── CLAUDE.md                     # This file
├── LICENSE                       # MIT License (Mbachu Emmanuel, 2026)
├── DATABASE_MIGRATION.md         # Migration guide
│
├── docs/                         # Project documentation
│   ├── design/                   # ERD diagrams, DFD, data dictionary, UX architecture
│   ├── notes/content/            # Historical fix logs
│   ├── reference/                # Database migration, other reference
│   └── research/                 # Research notes
├── frontend/                     # Static HTML documentation portal
│   ├── assets/                   # Logo, theme CSS
│   ├── index.html                # Main landing page hub
│   ├── architecture.html         # Architecture narrative
│   ├── overview.html             # Project overview
│   ├── data_dictionary*.html     # Data dictionary
│   ├── erd_interactive.html      # Interactive ERD explorer
│   ├── strategies.html           # Strategy reference
│   └── design-system.css         # Enterprise CSS framework
├── init-db/
│   └── 01-init-timescaledb.sql   # PostgreSQL init for the dev-only TimescaleDB (Phase 2; replaced SQL Server T-SQL)
├── logs/                         # Rotating runtime logs
├── models/                       # ML model artifacts
│   ├── best_ml_gatekeeper_sklearn.pkl
│   ├── best_ml_gatekeeper_preprocessor.pkl
│   ├── champion_model.pkl        # (Champion contract — may be absent)
│   ├── champion_preprocessor.pkl
│   ├── champion_manifest.json
│   └── ml_gatekeeper_run_*.json  # Versioned run metadata
├── results/                      # Immutable run artifacts
│   ├── reports/                  # Qualification reports (JSON + MD pairs)
│   ├── sql/                      # Layer 2 SQL, diagnostics
│   └── state/                    # qualification_progress.json
├── shell/                        # Cron & utility scripts
│   ├── cron_layer4_pipeline.sh   # Hourly Layer 4 cron
│   ├── cron_oanda_ingest_saturday.sh
│   ├── retrain_tournament.sh     # ML model retraining
│   ├── execute_migration.sh
│   ├── setup_research_api.sh
│   ├── start_research_api.sh
│   └── run_cleanup.py
├── src/
│   ├── layer0/                   # Strategy qualification (17 .py files)
│   ├── layer1_regime/            # Market regime detection (2 .py files)
│   ├── layer2_signals/           # Signal generation engine
│   ├── layer3_ml/                # ML gatekeeper
│   ├── layer4_executor/          # Live execution pipeline
│   ├── layer5/                   # Telemetry API + React dashboard
│   ├── layer6_auditor/           # Post-trade auditor
│   ├── layer7/                   # Broker executor adapter
│   ├── nlp/                      # FinBERT macro intelligence
│   ├── research/                 # Research utilities, backtesting
│   └── sql/                      # SQL migrations & cleanup
├── testing/                      # Testing notes
└── archieved/                    # Archive (typo retained for compatibility)
```

---

## DATABASE SCHEMA

**Database:** `ForexBrainDB` — PostgreSQL 16 + TimescaleDB 2.26.3, host system cluster on `localhost:5432` (role `sa`). Time-series fact tables are TimescaleDB hypertables (`fact_market_prices`: 4,670,963 rows across 248 chunks; compression policies active). All code is PostgreSQL-native (FND-004 Phase 3 done) — connect via `src/common/db.py`; see `docs/database/SQL_TRANSLATION_RULES.md`.

### Core Fact Tables

| Table | Producer | Consumers |
|-------|----------|-----------|
| `Fact_Market_Prices` | OANDA ingest / external | Layers 1, 2, 6 |
| `Fact_Market_Regime_V2` | Layer 1 | Layers 3, 4, 5 |
| `Fact_Signals` | Layer 2 | Layers 3, 4, 5 |
| `Fact_Trade_Outcomes` | Historical / Layer 0 | Layer 3 |
| `Fact_Live_Trades` | Layer 4 | Layers 5, 6 |
| `Fact_Execution_Log` | Layer 4 | Layer 5 |
| `Fact_Macro_Events` | NLP (auxiliary) | Planned: Layers 3, 4 |

### Core Dimension Tables

| Table | Purpose |
|-------|---------|
| `Dim_Asset` | Common asset hub across all runtime layers |
| `Dim_Strategy` | Strategy metadata |
| `Dim_Strategy_Config` | Strategy configuration parameters |
| `Dim_Strategy_Asset_Mapping` | Strategy-to-asset assignments |
| `Dim_Strategy_Registry` | Qualification status and metadata |
| `Dim_Indicator_Library` | Indicator definitions |

### Critical Schema Notes

- **Schema has drifted** from the original design — code is schema-aware and only
  reads/writes columns that exist. `fact_live_trades` is narrow (`trade_id,
  timestamp, asset_id, strategy_id, signal_value, entry_price, stop_loss,
  take_profit, confidence_score, is_approved, actual_outcome, created_at,
  updated_at`); it lacks `order_id`, `granularity`, `symbol`, `model_decision`,
  `atr_value`, `adx_value`, `veto_reason`, `execution_status`. `fact_market_regime_v2`
  lacks the lineage/audit JSON columns; `dim_strategy` lacks `strategy_key`;
  `dim_strategy_asset_mapping` lacks `priority`.
- **Column case:** only `"Open"`/`"Close"` are mixed-case (double-quote them);
  `"timestamp"` is reserved (quote it); all other columns are lowercase. Alias
  outputs to mixed-case (`asset_id AS "Asset_ID"`) when callers expect it.
- `Fact_Signals` may or may not have `Is_Active` column — use schema-aware code.
- Idempotent writes use `INSERT … ON CONFLICT (<pk>)` (see translation-rules doc).
- Layers use `src/common/db.py` + SQLAlchemy `:named` / psycopg2 `%s` binding (no
  string interpolation).

---

## ENVIRONMENT SETUP

### Virtual Environment
```bash
source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate
pip install -r scalable-brain/requirements.txt
```

### Database
The canonical `ForexBrainDB` is the **host system PostgreSQL 16 + TimescaleDB cluster on `localhost:5432`** — it is already running as a system service; there is nothing to `docker-compose up` for normal operation.
```bash
# Verify the live canonical store (do NOT bind anything to host :5432):
psql -h localhost -p 5432 -U sa -d ForexBrainDB -c "SELECT count(*) FROM fact_market_prices;"

# OPTIONAL throwaway dev DB only (ephemeral, host port 5433, NOT canonical):
docker-compose --profile dev up -d timescaledb-dev
```

### Environment Variables (`.env`)
```
DB_SERVER=localhost
DB_USER=sa
DB_PASS=Emm5$manuel
DB_NAME=ForexBrainDB
DB_PORT=5432
DB_DRIVER=PostgreSQL   # deprecated no-op (no ODBC driver); src/common/db.py ignores it
OANDA_API_KEY=...
OANDA_ACCOUNT_ID_DEMO=101-002-38449021-001
OANDA_ENV=practice
OANDA_URL=https://api-fxpractice.oanda.com
LAYER3_APPROVAL_THRESHOLD=0.20
```

---

## CANONICAL RUN ORDER

After Layer 0 qualification completes:

1. Apply `results/sql/layer2_indicator_extension.sql` to DB
2. Apply `results/sql/layer2_strategies.sql` to DB
3. Run Layer 1 regime ingestion: `python src/layer1_regime/Fact_market_regime_v2.py`
4. Run Layer 2 signal generation: `python src/layer2_signals/generate_signals.py`
5. Train Layer 3 (dry-run first): `python src/layer3_ml/training/train_ml_gatekeeper.py --dry-run --selection-mode strict`
6. Promote champion: `python src/layer3_ml/training/train_ml_gatekeeper.py --selection-mode strict --promote-as-champion`
7. Run Layer 4 execution: `python src/layer4_executor/live_pipeline.py`
8. Run Layer 6 auditor: `python src/layer6_auditor/trade_auditor.py`
9. Start Layer 5 telemetry: `python src/layer5/run.py`

---

## CODING CONVENTIONS

- **Type hints** on all functions (mypy compliant)
- **Docstrings** for all public functions
- **Parameterized SQL** — never use string interpolation for queries
- **No hardcoded secrets** — use environment variables from `.env`
- **Logging format:** `%(asctime)s | %(levelname)-8s | %(name)s | %(message)s`
- **Rotating logs** — prevent unbounded disk usage (10MB max, 14 backups)
- **`INSERT … ON CONFLICT`** for idempotent DB writes (all layers); connect via
  `src/common/db.py` — never build a connection string or `create_engine` inline
- **SHA256 hashing** for model artifact integrity verification
- **Dry-run modes** on all pipeline stages for safe testing
- **Schema-aware code** — detect optional columns at runtime, don't assume they exist

### Naming Conventions

- Fact tables: `Fact_*` (e.g., `Fact_Signals`, `Fact_Market_Regime_V2`, `Fact_Live_Trades`)
- Dimension tables: `Dim_*` (e.g., `Dim_Asset`, `Dim_Strategy_Registry`)
- Layer directories: `layer{N}` or `layer{N}_{descriptor}` (e.g., `layer0`, `layer1_regime`, `layer2_signals`)
- Legacy folder typo: `archieved` (retained for compatibility, symlinked from `archived`)

---

## TESTING

```bash
# Layer 0 strategy qualification tests
pytest src/layer0/tests/ -v

# Layer 3 ML model validation
pytest src/layer3_ml/tests/ -v

# Layer 4 live execution simulation
pytest src/layer4_executor/tests/ --live-sim

# Layer 7 executor tests
pytest src/layer7/tests/ -v

# Full coverage report
pytest --cov=src --cov-report=html
```

Code quality:
```bash
black src/           # Formatting
mypy src/            # Type checking
```

---

## AGENT RULES (Claude-Specific)

### DO:

- Preserve existing layer boundaries and contracts — each layer produces artifacts for the next
- Prefer additive, minimal changes over breaking refactors
- Use schema-aware code where tables vary across migration states (e.g., `Fact_Signals.Is_Active` may be absent)
- Keep SQL/schema changes paired with documentation updates
- Use parameterized SQL (SQLAlchemy `:named` / psycopg2 `%s`) — never string interpolation
- Connect through `src/common/db.py`; double-quote `"Open"`/`"Close"`/`"timestamp"`, lowercase everything else
- Support both champion and legacy model artifact paths in Layer 4
- Use rotating log handlers for any new logging
- Preserve granularity contracts (H1/H4) across all layers
- Verify dry-run modes work before live execution changes

### DO NOT:

- Remove compatibility symlinks (`archieved` → `archived`, `doc` → `docs`) blindly
- Assume optional columns exist — always check dynamically
- Force champion-only loading in Layer 4 unless Layer 3 promotion is guaranteed
- Recompute upstream layer outputs in downstream layers
- Use destructive SQL without explicit confirmation and dependency checks
- Commit `.env` files or credentials
- Hardcode broker/API keys or DB secrets
- Introduce new dependencies without checking `requirements.txt` first

---

## LAYER CONTRACTS (Must Not Be Broken)

1. **Granularity alignment** — H1/H4 must be preserved across regime/signals/outcomes. Layer 3 supports H1/H4 only unless explicitly extended.
2. **Artifact-based handoff** — Layer 3 produces model artifacts; Layer 4 consumes them. Layer 4 must NOT recompute Layer 1 or Layer 2 outputs internally.
3. **Table contracts** — `Fact_Signals` → Layer 3 training → champion artifacts → Layer 4 inference. `Fact_Market_Regime_V2` is the preferred regime source.
4. **Execution determinism** — Given the same signal + regime + model artifact, the execution decision must be deterministic.

---

## TROUBLESHOOTING

| Symptom | Check |
|---------|-------|
| Layer 4 fails at startup | Logs directory path validity; model artifacts in `models/`; `.env` DB credentials; `src/common/db.py` connectivity |
| Layer 4 runs but executes nothing | `Fact_Signals` has recent rows for target granularity; signal freshness window; gating thresholds |
| Layer 3 fails to produce deployable model | Threshold diagnostics output; turnover/expectancy gates realistic for data window; granularity contract; outcome table coverage |
| Layer 1 clustering fails | Return signature consistency for all failure paths — must return consistent tuple shapes |
| DB connection issues | Host PostgreSQL on `:5432` is running; `.env` credentials; `src/common/db.py` `test_connection()` |
| Reserved word / column-case errors | Double-quote `"Open"`/`"Close"`/`"timestamp"`; all other columns are lowercase (see `docs/database/SQL_TRANSLATION_RULES.md`) |

---

## KEY DEPENDENCIES

| Dependency | Purpose |
|-----------|---------|
| `psycopg2-binary` | PostgreSQL connectivity (all layers, via `src/common/db.py`) |
| `sqlalchemy` | Database abstraction across all layers (`postgresql+psycopg2`) |
| `pandas`, `numpy` | Core data manipulation |
| `ta` | Technical indicators (ATR, ADX, RSI, Bollinger) |
| `scikit-learn` | K-Means clustering (Layer 1), preprocessing (Layer 3) |
| `xgboost`, `lightgbm` | ML gatekeeper models (Layer 3) |
| `torch`, `transformers` | FinBERT NLP (auxiliary) |
| `optuna` | Hyperparameter tuning |
| `oandapyV20` | OANDA broker API (Layers 4, 7) |
| `fastapi`, `uvicorn` | Layer 5 telemetry backend |
| `flask` | Research notes API |
| `joblib` | Model serialization |
| `numba` | JIT compilation for performance |
| `pytest`, `black`, `mypy` | Test, format, type-check |
| `dash`, `plotly` | Legacy dashboard & visualization |

---

## KNOWN GAPS

- Champion model contract (`champion_model.pkl`, `champion_preprocessor.pkl`, `champion_manifest.json`) may not be materialized — Layer 4 falls back to legacy artifacts
- `Fact_Macro_Events` is populated but not yet integrated into Layer 3/4 as a feature or gate
- Naming drift between `archieved` (filesystem) and `archived` (planning artifacts) — both must be maintained
- Some layers (5, 6, 7) are described as "Planned" in README but have working code — status labels may lag implementation
- The active DB is PostgreSQL 16 + TimescaleDB for **all** layers (FND-004 done)
- Several tables have drifted from the original schema (see Critical Schema Notes);
  code is schema-aware. `fact_signals`/`fact_trade_outcomes` are currently empty,
  so Layers 2–3 need upstream data populated before a full end-to-end run
- `src/layer0/layer2_config_adapter.py` still generates SQL Server T-SQL — pending

---

## DOCUMENTATION MAP

| File | Content |
|------|---------|
| `docs/design/SYSTEM_ARCHITECTURE.md` | Current 8-layer architecture and layer contracts |
| `docs/design/ERD_ACTIVE_SCHEMA_2026.md` | Active schema reference by layer contract |
| `docs/design/ICE1_ForexBrain_DDL.sql` | Core DDL schema definition |
| `docs/reference/DOCUMENTATION_INDEX_2026_04_05.md` | Canonical documentation index |
| `docs/RESEARCH_NOTES_POSTGRESQL.md` | Research notes system docs (365 lines) |
| `src/layer0/README_LAYER0_INTEGRATION.md` | Layer 0 → Layer 2 promotion guide |
| `src/layer0/README_SWING_ENGINE.md` | Original Swing Engine docs |
| `src/layer5/README_LAYER5.md` | Layer 5 telemetry API docs |
| `docs/reference/DATABASE_MIGRATION.md` | Migration guide for Fact_Live_Trades fix |
| `docs/notes/content/FIXES_APPLIED_2026_04_05.md` | Historical fix log (480 lines) |
| `docs/design/DESIGN_SYSTEM_SPECIFICATION.md` | Material Design 3 CSS spec (1456 lines) |
| `docs/design/UX_ARCHITECTURE.md` | Enterprise UX flows and IA (1890 lines) |

---

*If this file conflicts with implementation behavior, implementation wins. Update this file in the same change set that updates behavior.*
