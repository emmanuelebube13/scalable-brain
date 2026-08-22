# Scalable Brain

## Institutional-Grade Quantitative Trading Platform

A layered, deterministic trading pipeline that separates model building, risk governance, and order execution into independently deployable systems. No strategy reaches live capital without demonstrating a mathematical edge, passing ML gatekeeping, and clearing a 10-layer risk gate.

[![Phase](https://img.shields.io/badge/phase-migration%2Frearchitecture-9cf?style=flat-square)](https://github.com)
[![PostgreSQL](https://img.shields.io/badge/database-PostgreSQL%2016-336791?style=flat-square&logo=postgresql)](https://postgresql.org)
[![Python](https://img.shields.io/badge/python-3.12-brightgreen?style=flat-square&logo=python)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](LICENSE)

---

## Current Phase: Migration to Three-System Distributed Architecture

The platform is being reorganized from a single-host, monolithic 8-layer pipeline into **three independently deployable systems across three computers**, connected by cloud object storage and message queues. The original monolith (this repository) becomes **System 1 — The Brain**, while System 2 and System 3 are built as separate modules.

---

## Three-System Topology

```
                            GCS (models, reference data, journals)
                                          |
                    ┌─────────────────────+──────────────────────┐
                    |                                            |
                    ▼                                            ▼
┌─────────────────────────────────┐    ┌──────────────────────────────────┐
│ SYSTEM 1 — The Brain (Comp 1)   │    │ SYSTEM 2 — The Hand (Comp 2)     │
│ INTERMITTENT (training only)    │    │ ACTIVE MARKET HOURS              │
│                                 │    │ (Sun 22:00 – Fri 20:00 UTC)     │
│ Layers 0–3 + NLP               │    │                                  │
│ • Strategy qualification        │    │ Layers 4, 7, 5                   │
│ • Regime detection (HMM +       │    │ • Artifact downloader + verifier │
│   K-Means fallback)             │    │ • Live regime detector           │
│ • Signal generation             │    │ • Execution-only pipeline        │
│ • ML gatekeeper (XGBoost/       │    │ • Queue consumer (approved       │
│   LightGBM tournament)          │    │   orders from System 3)          │
│ • FinBERT macro intelligence    │    │ • OANDA broker adapter           │
│ • Model serialization to GCS    │    │ • Fill confirmation producer     │
│ • Scored signal queue producer  │    │ • Active position management     │
│ • Weekly retraining scheduler   │    │ • Safety mode + emergency STOP   │
└──────────────┬──────────────────┘    │ • Telemetry API + React dashboard│
               │                       └───────────┬──────────────────────┘
               │ Scored_Signal_Queue               │ AMS_Outbound_Queue (orders)
               │ (Pub/Sub)                         │ AMS_Inbound_Queue (fills)
               ▼                                   │
┌──────────────────────────────────────────────────+────────────────────────┐
│ SYSTEM 3 — The Guardian (Comp 3)                                            │
│ ALWAYS-ON (24/7)                                                            │
│                                                                            │
│ 10-Layer Decision Gate (A–J)                                               │
│ • A–C: Account state, daily budget, drawdown                               │
│ • D–G: Kelly sizing, exposure caps, correlation, volatility adjust          │
│ • H–J: Duration gates, weekend/holiday, macro-event windows                │
│                                                                            │
│ Account state machine (DEMO→ACTIVE→CAUTION→PAUSED→CIRCUIT_BROKEN→RECOVERY) │
│ 8-layer circuit breakers + graduated deployment (Paper→Micro→Small→Full)   │
│ Performance tracker + strategy-decay auditor                               │
│ Post-trade processor + journal export                                      │
│ Telegram + SMTP notifications with urgency routing                         │
│ Local PostgreSQL — zero runtime dependency on Computer 1                   │
└────────────────────────────────────────────────────────────────────────────┘
```

**Connective tissue (cloud):**
- **GCS** — model artifacts, reference data, journal exports; `latest.json` pointer with SHA256 verification.
- **Google Cloud Pub/Sub** — `Scored_Signal_Queue` (S1→S3 today, **S2→S3 after ADR-001**), `AMS_Outbound_Queue` (S3→S2), `AMS_Inbound_Queue` (S2→S3).
- **Secrets** — SOPS+age encrypted, least-privilege per host; no credential leaves its owning system.

### Inviolable Principles

1. **Preservation over profit.** Capital survival outranks every return target. When a rule and a profit opportunity conflict, the rule wins.
2. **No downstream recomputation.** System 3 never re-scores a signal. System 2 never re-sizes an order. System 1 never knows if it's live.
3. **Default-safe posture.** Missing data, stale input, or internal error → REJECT, never approve. If System 3 is down, System 2 pauses.
4. **Deterministic, idempotent, auditable.** Every decision is logged with full context, forever.

---

## System Status

| System | Host | Profile | Status |
|--------|------|---------|--------|
| System 1 — The Brain | Computer 1 (training cluster) | Intermittent, heavy training loads | **Operational** — Legacy 8-layer monolith functional; migrating to new topology |
| System 2 — The Hand | Computer 2 (execution host) | Active market hours only | **Phase 0 complete** — Architecture ratified, early EXEC tasks underway |
| System 3 — The Guardian | Computer 3 (always-on, lightweight) | 24/7, <100 ms median decision latency | **Design ratified** — Consolidated architecture published; AMS schema + skeleton pending |
| Foundational | Cloud (GCS + Pub/Sub) | Always available | **Provisioning** — Storage + queue contracts defined; GCP service accounts in progress |

---

## System 1 Detailed Status (The Brain — This Repository)

System 1 is the offline intelligence factory. Its output is a versioned, checksummed model artifact bundle pushed to GCS — never a direct order.

> ⚠️ **Inference location is under review — `docs/design/ADR-001-where-inference-runs.md`.**
> System 1 today *also* runs a continuous signal producer that emits scored signals during
> market hours. That contradicts this document's own System 2 specification below ("live
> regime detector — HMM inference on live candles", "no dependency on Computer 1's
> database"), and it makes all trading depend on Computer 1, whose networking is
> unreliable. ADR-001 proposes returning to the design described here. **Pending approval
> from Systems 2 and 3.** Treat the System 1 producer as a temporary bridge.

### Legacy 8-Layer Pipeline (Operational)

| Layer | Component | Purpose | Status |
|-------|-----------|---------|--------|
| 0 | Qualification Engine | Backtest and validate 6 strategy families (18 variants); emit Layer 2 seed artifacts | Stable |
| 1 | Regime Detection | K-Means clustering (ATR/ADX/silhouette) → `Fact_Market_Regime_V2`; HMM upgrade planned | Stable |
| 2 | Signal Generation | Data-driven, vectorized engine evaluating active configs against live candles → `Fact_Signals` (915K+ signals) | Stable |
| 3 | ML Gatekeeper | XGBoost/LightGBM tournament with walk-forward validation, causal regime labels, governed champion promotion | Stable |
| 4 | Live Executor | ATR-based risk, portfolio correlation guard, ML confidence threshold → `Fact_Live_Trades` | Running |
| 5 | Telemetry API | FastAPI backend + React 19 dashboard (read-only KPI, trades, risk, regimes) | Designed |
| 6 | Trade Auditor | Reconciles unresolved outcomes against market path | Planned |
| 7 | Broker Adapter | OANDA v20 REST, Quarter-Kelly sizing, stop/take-profit confirmation | Running |
| — | NLP Intelligence | FinBERT macro sentiment ingestion → `Fact_Macro_Events` (not yet enforced as gate) | Implemented |

### System-1 Gatekeeper Hardening (Complete)

- Causal regime labeling eliminates look-ahead bias.
- Single governed champion writer with SHA256 integrity hashes.
- Walk-forward OOS validation with deployment gates (non-degenerate, beats incumbent).
- Leakage unit tests and point-in-time feature construction enforced.

### Upcoming System-1 Upgrades (Planned)

| Task | Description |
|------|-------------|
| MODEL-003 | Replace K-Means with 4-state Gaussian HMM (persistence smoothing, min 3 bars) |
| MODEL-004 | Per-regime strategy attribution (win rate, PF, Sharpe per regime) |
| MODEL-007 | Model serializer → GCS artifact registry with `latest.json` + SHA256 |
| MODEL-008 | Scored signal queue producer → Pub/Sub |
| MODEL-009 | Weekly retraining scheduler with performance-triggered retraining |

---

## System 2 in Brief (The Hand)

**Location:** `../system-2-execution-engine/` (separate module)

Pulls verified model artifacts from GCS, polls `AMS_Outbound_Queue` for pre-sized approved orders from System 3, executes deterministically via OANDA, and pushes fill confirmations back on `AMS_Inbound_Queue`. Never makes an autonomous risk decision.

- **Artifact sync** — polls `latest.json` (~15 min), SHA256 verify, atomic swap of model cache.
- **Live regime detector** — HMM inference on live candles with persistence smoothing.
- **Safety** — staleness pause (>5 min queue age → PAUSED); emergency STOP (SIGUSR1 or authenticated API) flattens positions without queue dependency.
- **Idempotency** — `idempotency_key` → OANDA client request ID; replays are no-ops.
- **Slippage budget** — 2 pips tolerance; flag/reject beyond.
- **Local PostgreSQL** — own datastore; no dependency on Computer 1's database.

---

## System 3 in Brief (The Guardian)

**Location:** `../system-3-account-management/` (separate module)

New always-on risk middleware. Every signal that Layer 3 approves must pass through System 3's 10-layer sequential Decision Gate before reaching the broker. Does math, not ML.

### Gate Layers (A–J)

| Layer | Check | Outcome |
|-------|-------|---------|
| A | Account state | Reject unless ACTIVE |
| B | Daily loss budget | Soft stop ≥2%, hard stop ≥3% (pause 24h) |
| C | Drawdown guard | ≥20% max DD → CIRCUIT_BROKEN, close all |
| D | Consecutive losses | 5 consecutive → 24h cooling |
| E | Max concurrent trades | Cap at 5 open |
| F | Per-pair exposure | Max 6% of equity |
| G | Correlated exposure | Max 10% of equity |
| H | Kelly sizing | Quarter-Kelly (cap 2%, floor 0.1%) × multipliers |
| I | Duration, weekend, macro windows | Reject outside session; park during gap windows |
| J | Approve + size + publish | → `AMS_Outbound_Queue` |

### Inviolable Defaults

| Threshold | Value |
|-----------|-------|
| Max risk per trade | 2.0% |
| Min risk per trade (floor) | 0.1% |
| Kelly fraction | 0.25 (Quarter-Kelly) |
| Daily loss soft stop | ≥2% (−50% size, 30m pause) |
| Daily loss hard stop | ≥3% (24h halt) |
| Weekly loss stop | ≥6% (0.5% next week) |
| Max drawdown circuit break | ≥20% (RECOVERY mode) |
| Stage risk multipliers | Demo 0.5 / Micro 0.5 / Small 0.75 / Full 1.0 |

---

## Repository Structure (This Repository)

```
scalable-brain/
│
├── src/
│   ├── layer0/                     Strategy qualification (6 families, 18 variants)
│   ├── layer1_regime/              Market regime clustering (K-Means, V2 pipeline)
│   ├── layer2_signals/             Signal generation engine (vectorized, modular)
│   ├── layer3_ml/                  ML gatekeeper (XGBoost/LightGBM tournament)
│   ├── layer4_executor/            Live execution pipeline (1400+ lines)
│   ├── layer5/                     FastAPI telemetry backend + React dashboard
│   ├── layer6_auditor/             Post-trade outcome reconciliation
│   ├── layer7/                     OANDA broker executor adapter
│   ├── system1/                    System-1 gatekeeper hardening suite
│   ├── nlp/                        FinBERT macro sentiment ingestion
│   └── common/                     Shared utilities (db.py, storage, logging)
│
├── docs/
│   ├── design/                     System architecture, ERD, DDL
│   ├── implementation-roadmap/     Three-system migration plan (00-foundational, S1, S2, S3)
│   ├── proposed-fixes/             Prioritized fix register (FIX-S3 for risk engine)
│   └── research/                   Quantitative research notes
│
├── frontend/                       Static HTML documentation portal
├── results/                        Immutable run artifacts (reports, SQL, state)
├── models/                         ML model artifacts (git-ignored)
├── shell/                          Cron scripts and utilities
├── testing/                        Test suites and fixtures
├── archieved/                      Legacy archive (typo retained for compatibility)
│
├── AGENTS.md                       Operational context for AI coding agents
├── CLAUDE.md                       Comprehensive Claude Code guidance
├── requirements.txt                Python dependencies
├── docker-compose.yml              Optional dev-only TimescaleDB (port 5433)
└── LICENSE
```

---

## Technology Stack

| Concern | Choice |
|---------|--------|
| Language | Python 3.12 |
| Database | PostgreSQL 16 + TimescaleDB 2.26.3 (host cluster `localhost:5432`) |
| ML Models | XGBoost, LightGBM, scikit-learn |
| Hyperparameter Tuning | Optuna |
| NLP | FinBERT (HuggingFace transformers) |
| Backend API | FastAPI (Uvicorn, port 8001) |
| Frontend | React 19 + TypeScript + Vite + shadcn/ui |
| Broker API | OANDA v20 REST (practice environment) |
| Cloud Infrastructure | Google Cloud Storage + Pub/Sub |
| Secrets | SOPS+age (environment-injected, never in git) |
| Testing | pytest, black, mypy |

---

## Canonical Operational Run Order

Post Layer 0 qualification, execute in sequence:

```bash
# 1. Apply Layer 0 promotion artifacts
psql -h localhost -p 5432 -U sa -d ForexBrainDB -f results/sql/layer2_indicator_extension.sql
psql -h localhost -p 5432 -U sa -d ForexBrainDB -f results/sql/layer2_strategies.sql

# 2. Regime ingestion
python src/layer1_regime/Fact_market_regime_v2.py

# 3. Signal generation
python src/layer2_signals/generate_signals.py

# 4. ML training (dry-run first, then promote)
python src/layer3_ml/training/train_ml_gatekeeper.py --dry-run --selection-mode strict
python src/layer3_ml/training/train_ml_gatekeeper.py --selection-mode strict --promote-as-champion

# 5. Live execution
python src/layer4_executor/live_pipeline.py --granularity H1

# 6. Post-trade audit
python src/layer6_auditor/trade_auditor.py

# 7. Telemetry (optional)
python src/layer5/run.py
```

---

## Database Schema (System 1 — ForexBrainDB)

### Core Fact Tables

| Table | Producer | Consumers |
|-------|----------|-----------|
| `Fact_Market_Prices` | OANDA ingest | Layers 1, 2, 6 |
| `Fact_Market_Regime_V2` | Layer 1 | Layers 3, 4, 5 |
| `Fact_Signals` | Layer 2 | Layers 3, 4, 5 |
| `Fact_Trade_Outcomes` | Historical / Layer 0 | Layer 3 |
| `Fact_Live_Trades` | Layer 4 | Layers 5, 6 |
| `Fact_Execution_Log` | Layer 4 | Layer 5 |
| `Fact_Macro_Events` | NLP (auxiliary) | Planned: Layers 3, 4 |

### Core Dimension Tables

| Table | Purpose |
|-------|---------|
| `Dim_Asset` | Common instrument hub across all layers |
| `Dim_Strategy` | Strategy metadata and configuration |
| `Dim_Strategy_Config` | Strategy parameter variant definitions |
| `Dim_Strategy_Asset_Mapping` | Strategy-to-instrument assignments |
| `Dim_Indicator_Library` | Indicator definitions and metadata |

---

## Layer Contracts (Must Not Be Broken)

1. **Granularity alignment** — H1/H4 preserved across regime, signals, and outcomes. Canonical System-1 set: D1 primary (modeling/regime), H4 entry, W1 macro context (additive; H1/H4 legacy contracts kept working).
2. **Artifact-based handoff** — Layer 3 produces model artifacts; Layer 4 consumes them. No recomputation of upstream outputs.
3. **Table contracts** — `Fact_Signals` → Layer 3 training → champion artifacts → Layer 4 inference. `Fact_Market_Regime_V2` is the preferred regime source.
4. **Execution determinism** — Given the same signal, regime, and model artifact, the execution decision must be identical.
5. **Idempotent writes** — All layers use `INSERT … ON CONFLICT` via `src/common/db.py`; no string interpolation.

---

## Environment Setup

### Prerequisites

- Python 3.12 with virtual environment at `../.venv`.
- PostgreSQL 16 + TimescaleDB running on `localhost:5432` with database `ForexBrainDB` and role `sa`.
- Node.js 16+ (for Layer 5 frontend).
- Git.

### Quick Start

```bash
cd /home/emmanuel/Documents/Scalable_Brain
source .venv/bin/activate
pip install -r scalable-brain/requirements.txt

# Verify database connectivity
python scalable-brain/src/common/db.py
```

---

## Security and Risk Controls

**Data integrity**
- PostgreSQL ACID transactions with TimescaleDB hypertable compression.
- All credentials sourced from environment variables via SOPS+age; zero secrets in git.
- Full audit trail for every trade-related decision with immutable logging.

**Risk management**
- Portfolio-level correlation guards prevent correlated position stacking.
- ATR-based dynamic stop losses (not fixed-pip).
- Quarter-Kelly position sizing with drawdown, consecutive-loss, and deployment-stage multipliers.
- Eight-layer circuit breaker system (soft stop, daily, weekly, max-drawdown, consecutive-loss, margin, correlation, volatility).

**Operational security**
- Least-privilege credentials per host; System 3 never holds the OANDA key.
- All inter-system traffic over TLS (GCS HTTPS + Pub/Sub); no public ingress.
- Rotating log files (10 MB max, 14 backups); no secrets or PII in logs.
- NTP on all hosts; all day/week boundaries computed in UTC.

---

## Documentation Index

### Core Architecture
- [`docs/design/SYSTEM_ARCHITECTURE.md`](docs/design/SYSTEM_ARCHITECTURE.md) — Legacy 8-layer architecture and layer contracts.
- [`docs/design/ERD_ACTIVE_SCHEMA_2026.md`](docs/design/ERD_ACTIVE_SCHEMA_2026.md) — Active schema reference.

### Implementation Roadmap (Migration Plan)
- [`docs/implementation-roadmap/00-foundational-and-cross-cutting/README.md`](docs/implementation-roadmap/00-foundational-and-cross-cutting/README.md) — Cloud infrastructure, secrets, CI/CD.
- [`docs/implementation-roadmap/system-1-model-building/README.md`](docs/implementation-roadmap/system-1-model-building/README.md) — System 1 task index (MODEL-001..010).
- [`docs/implementation-roadmap/system-2-execution-engine/README.md`](docs/implementation-roadmap/system-2-execution-engine/README.md) — System 2 task index (EXEC-001..009).
- [`docs/implementation-roadmap/system-3-account-management/README.md`](docs/implementation-roadmap/system-3-account-management/README.md) — System 3 task index (AMS-001..014).

### System 2 (Separate Module)
- [`../system-2-execution-engine/ARCHITECTURE.md`](../system-2-execution-engine/ARCHITECTURE.md) — System 2 component map, data flow, isolation model.
- [`../system-2-execution-engine/orchestration/`](../system-2-execution-engine/orchestration/) — Decision logs, agent fleet topology, progress ledger.

### System 3 (Separate Module)
- [`../system-3-account-management/docs/ARCHITECTURE_OVERVIEW.md`](../system-3-account-management/docs/ARCHITECTURE_OVERVIEW.md) — Consolidated System 3 architecture.
- [`../system-3-account-management/tasks/`](../system-3-account-management/tasks/) — Per-task READMEs (AMS-001..020).

### Layer-Specific Guides
- [`src/layer0/README_LAYER0_INTEGRATION.md`](src/layer0/README_LAYER0_INTEGRATION.md) — Strategy qualification framework.
- [`src/layer0/README_SWING_ENGINE.md`](src/layer0/README_SWING_ENGINE.md) — Original Swing Engine documentation.

### Operational
- [`AGENTS.md`](AGENTS.md) — Operational context for AI coding agents.
- [`CLAUDE.md`](CLAUDE.md) — Comprehensive Claude Code guidance with canonical run order.

### Documentation Portal
- [`frontend/index.html`](frontend/index.html) — Static HTML portal landing page.
- [`frontend/overview.html`](frontend/overview.html) — Project architecture overview.

---

## License

MIT. See [LICENSE](LICENSE).

---

*Last updated: 2026-07-05. This README reflects the current migration phase from an 8-layer monolith to a three-system distributed architecture. Implementation status supersedes documentation where they conflict.*
