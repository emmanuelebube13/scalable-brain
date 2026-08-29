# src/common/ — the shared abstractions

`db.py`, `storage/`, `queue/`. Everything in `src/` goes through these. Adding a bypass is a
design change, not a shortcut. Review with the `db-guardian` agent.

## Database — `db.py` is the only door

PostgreSQL 16 + TimescaleDB, `localhost:5432`, database `ForexBrainDB`, role `sa`.
SQLAlchemy 2.0 + psycopg2, UTC session. SQL Server is gone.

- Use `get_engine()`, `get_psycopg2_connection()`, `bulk_upsert()`.
- **Never build a connection string inline.** No `psycopg2.connect(` or `create_engine(`
  outside this file.
- **Parameterised SQL only.** No f-strings or `%` formatting into SQL, including table names.
- **Idempotent writes:** `INSERT … ON CONFLICT (<pk>)`. Every stage must be safely
  re-runnable — the orchestrator retries and cron runs overlap. A `DELETE`-then-`INSERT` is
  worse than a bare insert: it opens a window where the table is wrong.

## Case and reserved words

The most common runtime SQL failure here:

- Only `"Open"` and `"Close"` are mixed-case — **double-quote them**.
- `"timestamp"` is reserved — **quote it**.
- Everything else is lowercase and unquoted.
- Alias out to mixed-case when a caller expects it; do not rename the column.

Reference: `docs/database/SQL_TRANSLATION_RULES.md`.

## Schema drift is real

The live schema has **drifted from the original design**. Write schema-aware code — never
assume an optional column exists, and do not treat the ERD or data dictionary as ground truth
for what is in the database today.

## Timezones

UTC everywhere. A naive timestamp crossing this boundary is a defect — market-close logic
depends on it, and the ingest ETL has already died once from a timezone bug.

## Storage and queue

`storage/README.md` is the publish/determinism contract — read it before changing the backend
abstraction. Queue is Pub/Sub (`QUEUE_PROVIDER=pubsub`, project `scalable-brain`); the
`scored-signals.heartbeat` topic does not exist and every hourly run logs a 404 on it. Known.
