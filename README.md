# Scalable Brain
## Institutional-Grade Quantitative Trading Pipeline

Transparent, auditable trade execution backed by rigorous mathematical qualification, with portfolio-level risk management and machine-learning signal filtering.

[![Status](https://img.shields.io/badge/status-production-brightgreen?style=flat-square)](https://github.com)
[![Layer Stack](https://img.shields.io/badge/layer%20stack-8%2F8-orange?style=flat-square)](https://github.com)
[![PostgreSQL](https://img.shields.io/badge/database-PostgreSQL%2016-336791?style=flat-square&logo=postgresql)](https://postgresql.org)
[![Python](https://img.shields.io/badge/python-3.12-brightgreen?style=flat-square&logo=python)](https://python.org)

---

## Overview

Scalable Brain is a quantitative trading architecture that separates concerns across eight distinct processing layers:

- **Research and Qualification** — Rigorous backtesting and statistical validation.
- **Market Intelligence** — Dynamic regime detection and feature engineering.
- **Signal Generation** — Rule-based algorithmic trading strategy engine.
- **ML Gatekeeping** — Machine-learning confidence filtering and contextual decision making.
- **Execution and Risk** — Trade execution with portfolio-level correlation guards.
- **Telemetry and Audit** — Real-time observability and post-trade reconciliation.
- **NLP Intelligence** — Macro sentiment and event-driven feature enrichment.

**Core philosophy:** No strategy touches live data until it proves a mathematical edge. Every trade is traceable, auditable, and risk-managed.

---

## 8-Layer Runtime Architecture

| Layer | Component | Purpose | Status |
|-------|-----------|---------|--------|
| 0 | Qualification Engine | Backtest and validate trading strategies | Complete |
| 1 | Market Regimes | K-Means clustering on volatility/trend | Complete |
| 2 | Signal Generation | Rule-based strategy signal bank | Complete |
| 3 | ML Gatekeeper | XGBoost confidence filtering and feature alignment | Complete |
| 4 | Live Executor | Trade execution with risk management | In Progress |
| 5 | API Telemetry | FastAPI observability backend and dashboard | Planned |
| 6 | Auditor | Post-trade outcome reconciliation | Planned |
| 7 | Broker Adapter | OANDA execution integration | Planned |

**Auxiliary systems:**
- **NLP Intelligence** — FinBERT macro event ingestion into the `Fact_Macro_Events` table.
- **Telemetry Surface** — Dashboard with regime tracking, ML veto rates, and confidence scores.

---

## Repository Structure

```
scalable-brain/
├── src/
│   ├── layer0/                 # Strategy qualification and promotion
│   ├── layer1_regime/          # Market regime clustering pipeline
│   ├── layer2_signals/         # Signal generation engine and indicators
│   ├── layer3_ml/              # XGBoost training and feature alignment
│   ├── layer4_executor/        # Live trading execution and risk gating
│   ├── layer5/                 # FastAPI telemetry backend
│   │   └── frontend/           # React dashboard
│   ├── layer6_auditor/         # Post-trade outcome reconciliation
│   ├── layer7/                 # OANDA broker executor adapter
│   ├── system1/                # System-1 gatekeeper: causal regimes, walk-forward, governed promote
│   └── nlp/                    # FinBERT macro intelligence
│
├── docs/
│   ├── design/                 # System architecture and ERD
│   ├── reference/              # Operational runbooks
│   ├── proposed-fixes/         # Prioritized fix register
│   └── research/               # Quantitative research notes
│
├── frontend/                   # Static HTML documentation portal
├── results/                    # Immutable run artifacts and reports
├── models/                     # ML model artifacts (git-ignored)
├── shell/                      # Cron schedulers and utilities
└── init-db/                    # Database initialization scripts
```

---

## Core Data Flow

```
Historical Market Data
        |
        v
Layer 0  — Strategy Qualification
           Backtests all strategies; only promoted strategies advance.
        |
        v
Layer 1  — Market Regime Detection
           K-Means clustering (ATR + ADX) -> Fact_Market_Regime_V2.
        |
        v
Layer 2  — Signal Generation
           Runs promoted strategies on live candles -> Fact_Signals.
        |
        v
Layer 3  — ML Gatekeeper (XGBoost)
           Scores trades with regime and session context; low-confidence signals are filtered out.
        |
        v
Layer 4  — Live Execution and Risk Management
           ATR-based stops/targets and portfolio correlation guard; executes via Layer 7.
        |
        v
Layer 5  — Telemetry and Observability
           FastAPI endpoints for the dashboard and real-time monitoring.
        |
        v
Layer 6  — Post-Trade Auditing
           Reconciles outcomes and detects decay in strategy performance.
```

**Auxiliary enrichment:** FinBERT macro ingestion writes to `Fact_Macro_Events` (planned for Layer 3/4 context integration).

---

## Current System State

| Component | Status | Details |
|-----------|--------|---------|
| Layer 0 | Stable | Strategy qualification with a 20-trade minimum, positive expectancy, and a 1.15+ profit factor. |
| Layer 1 | Stable | K-Means regime clustering with silhouette validation and hourly updates. |
| Layer 2 | Stable | 915,000+ signals processed; ATR-based risk stops operating correctly. |
| Layer 3 | Stable | XGBoost training with walk-forward, causal regime labels and a governed promote path. |
| Layer 4 | Running | Live execution on PostgreSQL with rotating logs and active correlation guards. |
| Layer 5 | Designed | FastAPI backend ready; dashboard architecture documented. |
| Layer 6 | Planned | Post-trade reconciliation framework ready for implementation. |
| Layer 7 | Planned | OANDA adapter ready for live broker integration testing. |

### Recent Improvements
- Layer 4 execution path migrated to PostgreSQL with correct reserved-word and mixed-case column handling.
- Layer 4 logging uses rotating handlers to prevent oversized single-day files.
- Layer 1 regime pipeline return-shape mismatch resolved.
- System-1 gatekeeper hardened: leakage closed, deployment gates armed, and a single governed champion writer enforced.

---

## Roadmap

### Phase 1: Model Enhancement
- Integrate `Fact_Macro_Events` features into Layer 3 training sets.
- Add macro sentiment snapshots to Layer 4 pre-trade context checks.
- Extend Optuna hyperparameter tuning across candidate model families.

### Phase 2: System Robustness
- Add schema health checks before Layer 4 starts (fail-fast on drift).
- Synchronize source-of-truth documentation (HTML docs and canonical markdown).
- Expand error handling and recovery mechanisms.

### Phase 3: Observability
- Expand telemetry with macro sentiment snapshots.
- Add event-surprise and sentiment-dispersion trend metrics.
- Build a real-time decay-detection dashboard for strategy performance.

### Phase 4: Production Hardening
- Load-test Layer 4 with concurrent signal volumes.
- Define disaster-recovery procedures and automated failover.
- Complete broker integration certification and audit-trail validation.

---

## Quick Start

### Prerequisites
- Python 3.12 with a virtual environment.
- PostgreSQL 16 with TimescaleDB and the `ForexBrainDB` database.
- Node.js 16+ (for Layer 5 frontend development).
- Git.

### Python Environment Setup

```bash
cd /home/emmanuel/Documents/Scalable_Brain
source .venv/bin/activate
pip install -r scalable-brain/requirements.txt
```

### Layer 5 Backend (FastAPI Telemetry)

```bash
cd scalable-brain
python src/layer5/run.py
# Serves the telemetry API; see src/layer5/run.py for the configured port.
```

### Layer 5 Frontend (React Dashboard)

```bash
cd scalable-brain/src/layer5/frontend
npm install
npm run dev
```

### Layer 4 Live Execution (Scheduled)

```bash
# Manual trigger:
bash shell/cron_layer4_pipeline.sh

# Example crontab entry (hourly):
# 0 * * * * /home/emmanuel/Documents/Scalable_Brain/shell/cron_layer4_pipeline.sh >> /var/log/scalable-brain.log 2>&1
```

### Layer 0 Strategy Qualification

```bash
python src/layer0/qualify_strategies.py --use-db
```

---

## Documentation Index

### Core Architecture
- [`docs/design/SYSTEM_ARCHITECTURE.md`](docs/design/SYSTEM_ARCHITECTURE.md) — System design and layer contracts.
- [`docs/design/ERD_ACTIVE_SCHEMA_2026.md`](docs/design/ERD_ACTIVE_SCHEMA_2026.md) — Database schema and tables.
- [`docs/reference/DOCUMENTATION_INDEX_2026_04_05.md`](docs/reference/DOCUMENTATION_INDEX_2026_04_05.md) — Complete documentation index.

### Layer-Specific Guides
- [`src/layer0/README_LAYER0_INTEGRATION.md`](src/layer0/README_LAYER0_INTEGRATION.md) — Strategy qualification framework.
- [`src/layer5/README_LAYER5.md`](src/layer5/README_LAYER5.md) — API backend and telemetry.

### Documentation Portal
- [`frontend/index.html`](frontend/index.html) — Landing page.
- [`frontend/overview.html`](frontend/overview.html) — Project architecture overview.

---

## Database Schema Highlights

**Core fact tables:**
- `Fact_Signals` — Raw trading signals from Layer 2.
- `Fact_Market_Regime_V2` — Hourly regime classifications.
- `Fact_Live_Trades` — Active and completed trades with outcomes.
- `Fact_Macro_Events` — NLP-extracted macro events and sentiment.

**Dimension tables:**
- `Dim_Strategy_Registry` — Strategy metadata and qualification status.
- `Dim_Asset` — Instruments and trading metadata.

---

## Security and Risk Controls

**Data integrity**
- PostgreSQL ACID transactions.
- Credentials sourced from environment variables, never committed.
- Audit trail for trade-related decisions.

**Risk management**
- Portfolio-level correlation guards to prevent correlated position stacking.
- ATR-based dynamic stop losses rather than fixed-pip stops.
- Enforced risk-reward ratio on every position.

**Operational security**
- Role-based access control for database users.
- Token authentication for telemetry endpoints.
- Rotating log files to bound disk usage.

---

## Contributing and Development

### Development Workflow
1. Create feature branches: `git checkout -b feature/layer-X-enhancement`.
2. Run layer-specific tests with `pytest`.
3. Update `docs/` and the relevant layer README.
4. Open a pull request describing the change and requesting review.
5. Merge to `main`.

### Code Quality Standards
- Type hints on all functions (`mypy` compliant).
- Docstrings for all public functions.
- Parameterized SQL queries (no string interpolation).
- Environment variables for all sensitive configuration.

### Testing

```bash
# Layer 0: strategy qualification tests
pytest src/layer0/tests/ -v

# Layer 3: ML model validation
pytest src/layer3_ml/tests/ -v

# System-1 gatekeeper suite
PYTHONPATH=. pytest src/system1/ -q

# Full coverage report
pytest --cov=src --cov-report=html
```

---

## License

See the [LICENSE](LICENSE) file for details.
