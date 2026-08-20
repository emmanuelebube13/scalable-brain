"""MODEL-001 — additive, idempotent schema migration for multi-timeframe ingestion.

Adds lineage columns to ``fact_market_prices`` and creates the
``fact_market_prices_quarantine`` table. Everything here is ``IF NOT EXISTS`` /
``ADD COLUMN IF NOT EXISTS`` so it is safe to run on every ingestion run and never
destroys or rewrites existing data (rollback = drop the added columns / table).

Connect ONLY via ``src/common/db.py`` (canonical engine). Reserved/mixed-case columns
(``"Open"``/``"Close"``/``"timestamp"``) are double-quoted; everything else lowercase.
"""
from __future__ import annotations

import logging
from typing import List

from sqlalchemy import text

from src.common.db import get_engine

logger = logging.getLogger("system1.ingestion.schema")

FACT_TABLE = "fact_market_prices"
QUARANTINE_TABLE = "fact_market_prices_quarantine"

# Lineage columns added to fact_market_prices (additive; legacy rows get NULL/defaults).
LINEAGE_COLUMNS: List[tuple] = [
    ("complete", "boolean"),
    ("source", "varchar(16)"),
    ("ingest_run_id", "uuid"),
    ("ingested_at_utc", "timestamptz"),
]


def ensure_lineage_columns() -> List[str]:
    """Add lineage columns to fact_market_prices if absent. Returns columns added."""
    added: List[str] = []
    engine = get_engine()
    with engine.begin() as conn:
        existing = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = :t"
                ),
                {"t": FACT_TABLE},
            )
        }
        for col, coltype in LINEAGE_COLUMNS:
            if col not in existing:
                # Identifiers cannot be bound parameters; col/coltype come from the
                # hard-coded LINEAGE_COLUMNS list above (no user input) — safe.
                conn.execute(
                    text(f'ALTER TABLE {FACT_TABLE} ADD COLUMN IF NOT EXISTS {col} {coltype}')
                )
                added.append(col)
                logger.info("Added lineage column %s.%s (%s)", FACT_TABLE, col, coltype)
    if not added:
        logger.info("Lineage columns already present on %s", FACT_TABLE)
    return added


def ensure_quarantine_table() -> bool:
    """Create fact_market_prices_quarantine if absent. Returns True if created."""
    engine = get_engine()
    with engine.begin() as conn:
        exists = conn.execute(
            text("SELECT to_regclass(:q)"), {"q": f"public.{QUARANTINE_TABLE}"}
        ).scalar()
        if exists:
            logger.info("Quarantine table %s already exists", QUARANTINE_TABLE)
            return False
        conn.execute(
            text(
                f"""
                CREATE TABLE {QUARANTINE_TABLE} (
                    quarantine_id        bigserial PRIMARY KEY,
                    asset_id             integer NOT NULL,
                    granularity          varchar(8) NOT NULL,
                    "timestamp"          timestamptz,
                    "Open"               double precision,
                    high                 double precision,
                    low                  double precision,
                    "Close"              double precision,
                    volume               integer,
                    complete             boolean,
                    source               varchar(16),
                    ingest_run_id        uuid,
                    quarantine_reason_code varchar(32) NOT NULL,
                    quarantine_detail    text,
                    quarantined_at_utc   timestamptz NOT NULL DEFAULT now()
                )
                """
            )
        )
        # Helpful index for triage by run / reason.
        conn.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS ix_{QUARANTINE_TABLE}_run "
                f"ON {QUARANTINE_TABLE} (ingest_run_id, quarantine_reason_code)"
            )
        )
        logger.info("Created quarantine table %s", QUARANTINE_TABLE)
        return True


def migrate() -> dict:
    """Run the full additive migration. Idempotent. Returns a summary dict."""
    added_cols = ensure_lineage_columns()
    created_q = ensure_quarantine_table()
    return {"lineage_columns_added": added_cols, "quarantine_table_created": created_q}


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )
    print(migrate())
