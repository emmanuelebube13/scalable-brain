# System 1 — Dependencies & Prerequisites

Everything below must be **provisioned and verified before any MODEL-XXX task starts**. Where a dependency is owned by the Foundational track, the FND ID is cited; System 1 consumes it but does not build it.

## 1. Object Storage — Artifact Registry (FND-001)

**What:** An S3-compatible object store (AWS S3, or MinIO for local/on-prem on Computer 1) holding the versioned model bundles that Computer 2 pulls. Buckets/prefixes: `model-artifacts/` (timestamped versions), `model-artifacts/latest.json` (pointer), `feature-store/` (versioned Parquet feature sets).

**Why:** MODEL-007 packages and uploads `hmm_model.joblib + strategy_weights.json + regime_strategy_map.json + model_metadata.json + latest.json` with SHA256 checksums. The store is the decoupling boundary between Computer 1 (producer) and Computer 2 (consumer). MODEL-002 also persists the feature store here (or on a shared volume).

**Required capabilities:** versioned/immutable object keys, **server-side encryption at rest**, **TLS for transfer (encryption in transit)**, IAM/scoped credentials (write for Computer 1, read-only for Computer 2), lifecycle policy to retain N recent versions.

> **Provisioning status (locked):** no object store is provisioned yet. MODEL-007 codes against a **pluggable `StorageBackend` interface** (`orchestration/STORAGE_AND_QUEUE_ABSTRACTION.md`) whose **default is a local-filesystem backend** that reproduces the immutable-version + `latest.json` + SHA256 + encryption-flag semantics on disk. A **Google Cloud Storage** adapter is attached later via `STORAGE_PROVIDER=gcs` with **no code change**. The capabilities above are the contract the GCS adapter must satisfy when wired.

## 2. Message Queue (FND-002)

**What:** A durable message broker hosting `Scored_Signal_Queue` (e.g., RabbitMQ, Redis Streams, or a cloud queue). Must support max-queue-size / bounded depth, acknowledgements, and dead-letter handling.

**Why:** MODEL-008 publishes scored signals here for System 3 to consume, replacing the direct Layer 3 → Layer 4 call. Backpressure and DLQ semantics are required to avoid unbounded growth when consumers lag.

## 3. Database — `ForexBrainDB` (FND-004)

**What:** **PostgreSQL 16 + TimescaleDB 2.26.3** — the host system cluster on `localhost:5432`, database `ForexBrainDB` (role `sa`), FND-004 (Phase 3 complete). Must support the **multi-granularity extension** to `Fact_Market_Prices` (D1/H4/W1 in addition to existing H1/H4), plus existing fact/dim tables (`Fact_Market_Regime_V2`, `Fact_Signals`, `Fact_Trade_Outcomes`, `Fact_Macro_Events`, `Dim_*`).

> **DB = PostgreSQL 16 + TimescaleDB; any historical SQL-Server mention in this roadmap is obsolete.** All code connects via `src/common/db.py` (SQLAlchemy 2.0 + `psycopg2`, `postgresql+psycopg2`, UTC session). Idempotent writes use `INSERT … ON CONFLICT`. Only `"Open"`/`"Close"`/`"timestamp"` are double-quoted; all other columns are lowercase.

**Why:** MODEL-001 ingests prices here; MODEL-002 reads prices; MODEL-003 writes regime labels; MODEL-004/005 read trade outcomes and write attribution; MODEL-010 reads `Fact_Macro_Events`. Idempotent upserts use the `INSERT … ON CONFLICT` pattern already standard in Layers 1–2.

**Note:** The active runtime DB is **PostgreSQL 16 + TimescaleDB** (FND-004 complete). New code connects through `src/common/db.py` and double-quotes reserved words (e.g. `"Close"`); never build a connection string inline.

## 4. OANDA v20 API (practice)

**What:** OANDA v20 REST API access (`OANDA_API_KEY`, `OANDA_ACCOUNT_ID_DEMO`, `OANDA_ENV=practice`, `OANDA_URL=https://api-fxpractice.oanda.com`) via `oandapyV20`.

**Why:** MODEL-001 is the only task that calls OANDA, pulling D1/H4/W1 candles (500 per request) for the 2005→present backfill and incremental updates. Practice environment is sufficient since System 1 never executes trades. Confirm the practice account exposes the required instruments and that historical depth reaches 2005 for each (some instruments may have shorter history — document per-instrument earliest date).

## 5. Training Compute (Computer 1)

**What:** A dedicated training host/cluster with sufficient CPU/RAM for: deep-history backfill (I/O bound), Parquet feature builds (memory bound), HMM EM training (CPU), XGBoost/LightGBM training (CPU, optional GPU), and FinBERT inference (GPU strongly preferred for `torch`/`transformers`, CPU acceptable for batch). Scratch disk for Parquet feature store and model artifacts.

**Why:** All MODEL tasks run here. Establish **resource and latency budgets** up front: full backfill (one-time, hours acceptable); incremental ingest + feature build (< minutes); full retrain (MODEL-009) must complete within the weekly window (target < a few hours) so a Sunday 00:00 UTC job finishes before markets reopen.

## 6. Python ML Stack

**What:** Python 3.12 venv (`/home/emmanuel/Documents/Scalable_Brain/.venv`) extended with existing deps (`pandas`, `numpy`, `scikit-learn`, `xgboost`, `lightgbm`, `optuna`, `oandapyV20`, `psycopg2-binary`, `sqlalchemy`, `joblib`, `torch`, `transformers`) **plus new additions**: `hmmlearn` (Gaussian HMM), `pyarrow` (Parquet + compression), `mlflow` (experiment tracking), `python-docx` (stakeholder report), and the pluggable storage/queue clients per FND-001/FND-002 (local-filesystem + local-durable-queue by default; a Google Cloud Storage client `google-cloud-storage` and a real broker client are attached later by config only).

**Why:** MODEL-003 needs `hmmlearn`; MODEL-002/007 need `pyarrow`; experiment tracking needs `mlflow`. All new deps must be added to `requirements.txt` (per repo rule: check before adding) — but **do not modify source code or requirements as part of writing these docs**; the additions are specified here for the implementation tasks.

## 7. Experiment Tracking & Model Versioning (recommend MLflow) (supports FND-007)

**What:** An MLflow tracking server (local file store acceptable initially, backed by object storage for artifacts) recording params, metrics (PF, Sharpe, MaxDD, regime accuracy, OOS uplift), feature-set version, data lineage, and model versions.

**Why:** MODEL-002 through MODEL-009 must be reproducible and comparable across retrains. MLflow provides the experiment lineage and the model-version registry that the deployment gates (MODEL-009) and artifact registry (MODEL-007) reference. The `model_metadata.json` should carry the MLflow run ID.

## 8. CI / Test Harness (FND-007)

**What:** The shared CI pipeline running `pytest`, `black`, `mypy`, plus data-quality and statistical-validation checks (walk-forward, OOS≥60mo, significance).

**Why:** Every MODEL task's Testing & Validation section runs under this harness; deployment gates depend on green CI. Backtesting and statistical-validation utilities live here so all tasks share one validation contract.

## Provisioning Checklist (do before MODEL-001)

- [ ] Pluggable `StorageBackend` resolves (default **local-filesystem**; GCS adapter attachable later) — atomic pointer + SHA256 + encryption-flag semantics verified locally (FND-001)
- [ ] Pluggable `QueueBackend` resolves (default **local durable queue**; real broker attachable later) with bounded-depth + DLQ semantics (FND-002)
- [ ] `ForexBrainDB` (PostgreSQL 16 + TimescaleDB) reachable via `src/common/db.py`; multi-granularity `Fact_Market_Prices` extension approved (FND-004)
- [ ] OANDA practice credentials validated; per-instrument earliest history documented
- [ ] Computer 1 compute sized; resource/latency budgets recorded
- [ ] Python venv updated (`hmmlearn`, `pyarrow`, `mlflow`, `python-docx`; storage/queue clients are local-default, GCS/broker later)
- [ ] MLflow tracking server reachable; artifact store wired to object storage
- [ ] CI harness runs `pytest`/`black`/`mypy` + DQ/statistical checks (FND-007)
