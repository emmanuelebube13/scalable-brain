# Prompt: FND-004 Phase 3 — Application Code De-coupling from SQL Server

> Paste everything below the line into a fresh Claude Code session opened at the
> repo root (`/home/emmanuel/Documents/Scalable_Brain/scalable-brain`).

---

You are working on the **Scalable Brain** quantitative trading repo. This is task
**FND-004 Phase 3 — migrate all application code from SQL Server to PostgreSQL +
TimescaleDB**. Read this entire brief before changing anything. This is the largest
and riskiest phase: work incrementally, verify each layer, and do not attempt a
single big-bang rewrite.

## Background (already done — do NOT redo)

- The canonical operational database is the **host system PostgreSQL 16 cluster on
  `localhost:5432`, database `ForexBrainDB`, role `sa`** (password in `.env`
  `DB_PASS`). It is the source of truth.
- **Phase 1 (done):** TimescaleDB 2.26.3 + toolkit enabled; time-series tables are
  hypertables. `fact_market_prices` holds **4,670,963 rows** (~20 yrs, 5 assets) —
  use it for real read tests. Phase 1 SQL: `src/sql/timescaledb/`.
- **Phase 2 (done):** SQL Server containers/volumes removed; `docker-compose.yml`
  no longer stands up SQL Server.
- Migration record lives in **`docs/database/`** (`README.md`, `MIGRATION_LOG.md`).
  You will ex
tend it.

> ⚠️ The live `ForexBrainDB` on :5432 is the only copy of the price data. Read
> freely; for writes, prefer a scratch/dry-run path and never run destructive SQL
> without explicit confirmation. Take a `pg_dump` before any bulk write test.

## The problem

The schema and data are PostgreSQL, but the **code still speaks SQL Server**.
Verified inventory (re-verify with your own grep before trusting it):

**Raw `pyodbc` (16 files):**
`src/layer0/data_loader.py`, `src/layer0/ingest_oanda_prices.py`,
`src/layer0/seed_dim_asset_test.py`, `src/layer1_regime/ingest_regimes.py`,
`src/layer1_regime/exploratory/regime_clustering.py`,
`src/layer1_regime/exploratory/visualize_cluster.py`,
`src/layer2_signals/signal_engine/config/database.py`,
`src/layer2_signals/signal_engine/persistence/repository.py`,
`src/layer3_ml/model_winner_impact_report.py`,
`src/layer3_ml/training/train_ml_gatekeeper.py`,
`src/layer4_executor/live_pipeline.py`, `src/layer5/services/db_client.py`,
`src/layer6_auditor/trade_auditor.py`, `src/nlp/macro_scraper.py`,
`src/research/data_loader.py`, `src/research/layer0_multi_asset_evaluator.py`.

**`pymssql` (1 file):** `src/layer1_regime/Fact_market_regime_v2.py` (the preferred
regime pipeline — uses `pymssql.connect`, `%s` placeholders, raw SQL).

**`mssql+pyodbc://` SQLAlchemy engines (6 sites):** `src/layer3_ml/training/train_ml_gatekeeper.py`,
`src/layer5/app.py`, `src/layer5/services/db_client.py`,
`src/layer4_executor/live_pipeline.py`, `src/nlp/macro_scraper.py`.

**SQL-Server-isms (counts across `src/`, excluding `archieved/`):**
`MERGE`≈37 · `[Close]`/`[Open]`≈25 · `GETDATE()`≈19 / `GETUTCDATE()`≈13 ·
`TOP N`≈19 · `fast_executemany`≈9 · `NVARCHAR`≈7 · `ISNULL(`≈1 · `NEWID()`≈1.

**The only genuine PostgreSQL runtime code today** is `src/research_notes_api.py`
(psycopg2). Use it as the reference for a working PG connection pattern. Do NOT
break it.

**Config inconsistency:** `.env` has `DB_DRIVER=PostgreSQL` (a leftover that is
neither a valid ODBC driver nor used correctly) and ODBC builders are scattered
across ~8 files. Connection logic must be consolidated.

## Target architecture (the decision)

- **Driver/ORM:** SQLAlchemy 2.0 + `psycopg2` with `postgresql+psycopg2://` URLs.
  Much code already uses SQLAlchemy engines (just the wrong `mssql+pyodbc` dialect)
  and `pandas.read_sql`, so this is the lowest-friction target. `psycopg2-binary`
  and `sqlalchemy>=2.0` are already in `requirements.txt`.
- **One canonical connection module.** Create `src/common/db.py` (new `src/common/`
  package) exposing, at minimum:
  - `get_engine() -> sqlalchemy.Engine` — cached, built from a single canonical
    DSN. Reads `.env` once.
  - `get_psycopg2_connection()` — for raw/bulk paths (COPY, `execute_values`).
  - a documented **canonical DSN convention** sourced from `.env`
    (`DB_HOST`/`DB_PORT`/`DB_NAME`/`DB_USER`/`DB_PASS`), e.g.
    `postgresql+psycopg2://{user}:{quote_plus(pass)}@{host}:{port}/{name}`.
  Every layer must import from this module instead of building its own connection.
- **Keep** layer boundaries, granularity (H1/H4/…) contracts, schema-aware optional
  column handling, dry-run modes, rotating logs, and parameterized SQL.

## SQL translation rules (apply consistently)

| SQL Server | PostgreSQL |
|---|---|
| `MERGE ... WHEN MATCHED/NOT MATCHED` | `INSERT ... ON CONFLICT (pk_cols) DO UPDATE SET ...` (or `DO NOTHING`) |
| `[Close]`, `[Open]` | `"Close"`, `"Open"` (these columns are genuinely mixed-case in PG — keep capitalization, double-quote) |
| other `[identifier]` | unquoted lowercase `identifier` (all other columns are lowercase); only double-quote if reserved/mixed-case |
| `GETDATE()` / `GETUTCDATE()` | `now()` / `now() AT TIME ZONE 'utc'` (or `CURRENT_TIMESTAMP`) |
| `TOP N ...` | `... LIMIT N` (move to end of query) |
| `ISNULL(a,b)` | `COALESCE(a,b)` |
| `NEWID()` | `gen_random_uuid()` (pgcrypto/`gen_random_uuid` is built-in on PG16) |
| `NVARCHAR(n)` / `DATETIME2` | `varchar(n)`/`text` / `timestamptz` |
| `fast_executemany=True` (pyodbc) | `psycopg2.extras.execute_values(...)` or `COPY` for bulk inserts |
| `?` placeholders (pyodbc) / `%s` (pymssql) | SQLAlchemy `text()` with `:named` params, or psycopg2 `%s` |
| `mssql+pyodbc:///?odbc_connect=...` | `postgresql+psycopg2://...` via `src/common/db.py` |
| temp `#table` + MERGE upsert pattern | staging via `execute_values` then `INSERT ... ON CONFLICT`, or `INSERT ... ON CONFLICT` directly |

When rewriting an upsert, derive the conflict target from the table's real PRIMARY
KEY (inspect with `\d <table>` against the live DB). Preserve idempotency — re-running
must not duplicate rows.

## Process (work in this order; one layer per commit-sized unit)

1. **Foundation first.** Build and unit-test `src/common/db.py`. Prove it with a
   read against the live DB (e.g. `SELECT count(*) FROM fact_market_prices` →
   expect 4,670,963). Fix `.env`/config to the canonical convention; remove or
   repurpose the misleading `DB_DRIVER` and any hard-coded ODBC driver names.
2. **Migrate layer-by-layer**, in dependency order, validating each before moving on:
   **Layer 0** (data_loader, ingest, seed) → **Layer 1** (`Fact_market_regime_v2.py`
   pymssql→psycopg2/SQLAlchemy, plus `ingest_regimes.py`) → **Layer 2**
   (`signal_engine/config/database.py` + `settings.py` + `persistence/repository.py`,
   incl. MERGE→ON CONFLICT) → **Layer 3** (`train_ml_gatekeeper.py`,
   `model_winner_impact_report.py`) → **Layer 4** (`live_pipeline.py`) → **Layer 5**
   (`services/db_client.py`, `app.py`, legacy apps) → **Layer 6**
   (`trade_auditor.py`) → **Layer 7** (check `src/layer7/` for any DB coupling) →
   **NLP** (`macro_scraper.py`) → **research/** utilities.
3. For each file: replace the connection with `src/common/db.py`, translate SQL per
   the rules, convert placeholders/bulk inserts, and run that layer's dry-run /
   tests against the live PG.
4. **After all layers:** remove `pyodbc` and `pymssql` from `requirements.txt` and
   from imports; confirm `grep -rn "pyodbc\|pymssql\|mssql+pyodbc\|GETDATE\|MERGE \|\[Close\]\|\[Open\]\|ISNULL\| TOP " src --include=*.py | grep -v archieved` returns nothing meaningful.

## Testing & validation (evidence, not claims)

- **Read parity:** representative queries (price ranges, latest regime, signal
  counts) return sane results against the live data; the price-range query meets a
  reasonable latency budget (hypertables + chunk exclusion).
- **Dry-run each layer:** the existing `--dry-run` paths (Layer 3 training, Layer 4
  `live_pipeline.py --dry-run --granularity H1`, etc.) run cleanly end-to-end.
- **Upsert idempotency:** run a write path twice on a small scratch window; row
  counts must not change on the second run (ON CONFLICT works).
- **Parameterization:** no string-interpolated SQL introduced; all params bound.
- **Regression of former SQL-Server-isms:** `[Close]`/`MERGE`/`GETDATE` paths behave
  identically under PostgreSQL.
- Run `pytest` for the layers that have tests (`src/layer0/tests`, `src/layer3_ml/tests`,
  `src/layer7/tests`, `src/layer4_executor/tests`) and `black`/`mypy` per repo
  conventions.

## Docs recording requirement (part of the task)

Extend the existing `docs/database/` folder:
- Add `docs/database/CODE_MIGRATION_PHASE3.md` — the per-layer migration record:
  for each file, what connection/SQL changed, the conflict targets chosen for
  upserts, and the validation evidence (dry-run output, counts, latency).
- Add `docs/database/SQL_TRANSLATION_RULES.md` — the canonical translation table
  above plus any project-specific decisions (column-case rules, the DSN convention,
  bulk-insert helper usage) so future code stays PostgreSQL-native.
- Update `docs/database/MIGRATION_LOG.md` with a dated **Phase 3** section
  summarizing scope, what was migrated, and what (if anything) remains.
- Update `CLAUDE.md`: replace SQL-Server-specific guidance (ODBC auto-detection,
  `[Close]` bracket escaping, `MERGE` upsert pattern, pyodbc dependency) with the
  PostgreSQL+TimescaleDB equivalents and point at `src/common/db.py` and the
  translation-rules doc. Keep edits scoped to what actually changed.

## Constraints

- **Do not** modify the live PostgreSQL schema/data beyond agreed write-path tests;
  `pg_dump` first if a bulk write test is needed.
- **Do not** break `src/research_notes_api.py` (already PG).
- **Do not** reintroduce ODBC/SQL-Server assumptions or per-file connection builders
  — everything routes through `src/common/db.py`.
- Preserve dry-run modes, granularity contracts, schema-aware optional-column
  handling, rotating logs, and parameterized SQL.
- Keep changes additive and reviewable; migrate and validate one layer at a time.
  If a layer's behavior can't be validated against the live data, STOP and report
  rather than guessing.
- Do not commit or push unless the user explicitly asks; summarize the diff per
  layer for review.

## Acceptance criteria

- [ ] `src/common/db.py` exists; all layers connect through it via one canonical
      `postgresql+psycopg2` DSN sourced from `.env`; the misleading `DB_DRIVER` is
      resolved.
- [ ] No runtime code imports `pyodbc`/`pymssql` or builds `mssql+pyodbc` engines
      (verified by grep); they are removed from `requirements.txt`.
- [ ] All `MERGE`/`[Close]`/`[Open]`/`GETDATE`/`GETUTCDATE`/`TOP`/`ISNULL`/`NEWID`/
      `fast_executemany` occurrences translated; grep is clean.
- [ ] Each layer runs its dry-run/tests against the live PostgreSQL successfully;
      upserts are idempotent; read parity demonstrated.
- [ ] `pytest`, `black`, `mypy` pass per repo conventions for touched layers.
- [ ] `docs/database/CODE_MIGRATION_PHASE3.md`, `SQL_TRANSLATION_RULES.md`, an
      updated `MIGRATION_LOG.md`, and an updated `CLAUDE.md` are in place.
- [ ] Final check: `SELECT count(*) FROM fact_market_prices` still returns
      4,670,963 — the data is untouched.
