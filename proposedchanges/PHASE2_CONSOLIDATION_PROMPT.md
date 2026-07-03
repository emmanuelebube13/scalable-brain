# Prompt: FND-004 Phase 2 — Database Consolidation

> Paste everything below the line into a fresh Claude Code session opened at the
> repo root (`/home/emmanuel/Documents/Scalable_Brain/scalable-brain`).

---

You are working on the **Scalable Brain** quantitative trading repo. This is task
**FND-004 Phase 2 — Database Consolidation**. Read this whole brief before acting.

## Background (already done — do NOT redo)

The canonical operational database has been settled: it is the **host system
PostgreSQL 16 cluster on `localhost:5432`, database `ForexBrainDB`, role `sa`**
(credentials in `.env`: `DB_PASS`). Phase 1 already enabled **TimescaleDB 2.26.3 +
timescaledb_toolkit 1.22.0** on it and converted the time-series tables to
hypertables. `fact_market_prices` holds **4,670,963 rows** (~20 years, 5 assets)
across 248 chunks; compression policies are active. The Phase 1 SQL lives in
`src/sql/timescaledb/` and a pre-migration backup is in `backups/` (gitignored).

> ⚠️ **NEVER touch the live system PostgreSQL on :5432 or its `ForexBrainDB`.** It
> is the source of truth and the only copy of the 4.67M price rows. This task only
> removes *leftover duplicate Docker volumes and SQL Server scaffolding*.

Note: `CLAUDE.md` still describes SQL Server as the "Primary DB" — that is stale
and you will correct it as part of this task.

## What Phase 2 must accomplish

The repo still carries dead SQL Server scaffolding and empty duplicate DB volumes
from before the consolidation. Remove them, fix the port-collision hazard, and
record the work in docs.

### Current state to clean up (verify each before deleting)

1. **`docker-compose.yml`** defines a `sqlserver` (mcr.microsoft.com/mssql/server:2022)
   and `sql-init` service. It binds `"${DB_PORT}:1433"` and `DB_PORT=5432`, so
   starting it would **collide with the live system PostgreSQL on :5432** — a real
   hazard. SQL Server is not used anywhere at runtime anymore.
2. **`init-db/01-create-database.sql`** is SQL Server T-SQL (`sys.databases`, `GO`) —
   obsolete.
3. **Docker volumes** (all duplicates/empty — confirm before removing):
   - `scalable-brain_postgres-data` — an empty TimescaleDB *mirror* (only
     `dim_asset`=5 rows, no prices). Mounted by an **exited** container named
     `postgres` (image `timescale/timescaledb:latest-pg16`, stopped ~2 months).
   - `sqlserver-data` — old standalone SQL Server volume.
   - `scalable-brain_sqlserver-data` — SQL Server volume from the compose project.

### Required steps (in order, with safety gates)

1. **Verify before destroying.** Run and reason about:
   - `docker ps -a` and `docker volume ls` — confirm no *running* container uses the
     three volumes (only the exited `postgres` container should reference
     `scalable-brain_postgres-data`).
   - For each volume, confirm it is the duplicate/empty one and not the live data.
     The live data is NOT in Docker — it is the host system PostgreSQL. If any
     volume unexpectedly appears to hold real price data, **STOP and report** before
     deleting anything.

2. **Safety backup of the Docker volumes before deletion** (cheap insurance even
   though they are believed empty). For each volume, tar its contents to
   `backups/phase2/<volume>.tar.gz` using a throwaway alpine container, e.g.:
   ```bash
   mkdir -p backups/phase2
   docker run --rm -v <volume>:/data -v "$PWD/backups/phase2":/backup alpine \
     tar czf /backup/<volume>.tar.gz -C /data .
   ```
   Ensure `backups/` is gitignored (it already should be).

3. **Remove the dead Docker objects:**
   - `docker rm postgres` (the exited timescale mirror container).
   - `docker volume rm scalable-brain_postgres-data sqlserver-data scalable-brain_sqlserver-data`.

4. **Fix `docker-compose.yml`.** SQL Server must go. Recommended approach
   (pick and justify): replace the `sqlserver`/`sql-init` services with **either**
   (a) no DB service at all plus a top comment stating the canonical store is the
   host's system PostgreSQL+TimescaleDB on :5432 (simplest, matches reality), **or**
   (b) an *optional, dev-only* `timescaledb` service using
   `timescale/timescaledb:latest-pg16` bound to a **non-conflicting host port
   (e.g. 5433)**, clearly commented as not the canonical store. Do not leave
   anything that binds host :5432. Remove the now-unused `sqlserver-data` volume
   declaration.

5. **Handle `init-db/01-create-database.sql`.** It is SQL Server-specific. Either
   delete it, or replace it with a short PostgreSQL note/DDL consistent with the
   chosen compose direction. Update any references to it.

6. **Correct stale docs.** Update `CLAUDE.md` so the database section reflects
   reality: canonical store is **PostgreSQL 16 + TimescaleDB on :5432
   (`ForexBrainDB`)**, SQL Server removed. Keep edits minimal and additive; note
   that code-level de-coupling from SQL Server (pyodbc/MERGE/`[Close]`) is Phase 3
   and still pending. Do NOT rewrite unrelated sections.

### Docs recording requirement (do this — it is part of the task)

Create a **dedicated docs folder `docs/database/`** as the home for the database
strategy/migration record, with this structure:

- `docs/database/README.md` — index of the database consolidation effort; links to
  the FND-004 roadmap task
  (`docs/implementation-roadmap/00-foundational-and-cross-cutting/tasks/04-database-strategy-and-consolidation.md`),
  the Phase 1 SQL (`src/sql/timescaledb/`), and the files below. State the current
  canonical topology in a short table.
- `docs/database/MIGRATION_LOG.md` — chronological, dated log. Seed it with:
  - **Phase 1 (done, 2026-06-22):** TimescaleDB enabled on live `ForexBrainDB`;
    6 hypertables; `fact_market_prices` 4,670,963 rows in 248 chunks; compression
    policies (prices @90d, signals @180d). Reference `src/sql/timescaledb/`.
  - **Phase 2 (this task):** exactly what you removed/changed, with the commands
    run, volumes deleted (and their backup tarball paths), the `docker-compose.yml`
    decision and rationale, and `init-db` disposition.
  - **Phase 3 (pending):** code de-coupling from SQL Server (16 `pyodbc` files,
    12 `MERGE`, ~422 SQL-Server-isms) → PostgreSQL driver + `INSERT … ON CONFLICT`,
    single canonical DSN per FND-003.
- `docs/database/CONSOLIDATION_PHASE2.md` — the detailed before/after for Phase 2:
  the inventory of what existed, what each volume contained, why each was safe to
  remove, the verification evidence, and rollback notes (the backup tarballs + the
  Phase 1 `backups/*.dump`).

Keep the docs factual and concise. Use real command output as evidence, not claims.

## Constraints

- **Do not** start the old SQL Server compose, and **do not** bind anything to host
  port 5432.
- **Do not** modify the live system PostgreSQL, its data, or `src/sql/timescaledb/`.
- **Do not** commit `.env`, secrets, or anything under `backups/`.
- Treat volume deletion as irreversible: back up first, verify first, and STOP +
  ask the user if anything looks unexpected (e.g. a "duplicate" volume that turns
  out to contain real data).
- Application code changes are **out of scope** (that is Phase 3) — but if you
  notice code that hard-codes SQL Server connection assumptions, note it in the
  MIGRATION_LOG under Phase 3, don't fix it here.
- Do not commit or push unless the user explicitly asks; summarize the diff for
  review when done.

## Acceptance criteria

- [ ] The three duplicate volumes and the exited `postgres` container are gone;
      `docker volume ls` / `docker ps -a` confirm it; backup tarballs exist under
      `backups/phase2/`.
- [ ] `docker-compose.yml` no longer references SQL Server and nothing binds host
      :5432; rationale recorded.
- [ ] `init-db/01-create-database.sql` resolved (removed or PostgreSQL-appropriate).
- [ ] `CLAUDE.md` database section reflects PostgreSQL+TimescaleDB reality.
- [ ] `docs/database/` exists with `README.md`, `MIGRATION_LOG.md`, and
      `CONSOLIDATION_PHASE2.md` populated as specified.
- [ ] The live `ForexBrainDB` on :5432 is untouched — `fact_market_prices` still
      returns 4,670,963 rows (verify with a count as the final check).
