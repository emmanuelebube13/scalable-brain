"""R2.1 / R2.2 — the two structural-regime tables, and why there are two of them.

``fact_regime_structural`` — the canonical label
------------------------------------------------
One row per (asset, granularity, bar). **THE** source for selection, attribution,
training and routing. The structural rule is deterministic and causal, so recomputing bar
*t* from history reproduces exactly what was computable at *t* — which is why this table
is safe to backfill and safe to rebuild.

It stores the indicator values alongside the label so any label can be re-derived and
disputed without re-running the pipeline. A label you cannot audit is a label you have to
take on trust, and the whole reason this pass exists is that a label was taken on trust.

``fact_regime_structural_live`` — what was actually believed at decision time
-----------------------------------------------------------------------------
Append-only. Written by the live signal path, at the moment the label is used to route.

It exists because the canonical table answers "what *is* the label for that bar?" while
the only question that matters after a bad trade is "what did we *think* the label was
when we placed it?" Those two can differ — through a partial final bar, a different
lookback window, a code change between then and now — and nothing in the system could
previously tell them apart, because the live label left no durable record at all
(``system1/regime_status/latest.json`` is overwritten every run).

**Never UPDATE, never DELETE, never backfill.** A backfilled row here is a fabricated
record: it claims something was believed at a time when nothing was believed. The unique
constraint deliberately includes ``computed_at_utc``, so the same bar labelled twice at
different wall-clock times with different answers keeps **both** rows. That divergence is
the single most valuable thing this table can tell you, and deduplicating it would destroy
exactly the evidence it was built to capture.
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from src.common.db import get_engine

logger = logging.getLogger("system1.regime.structural_schema")

CANONICAL_TABLE = "fact_regime_structural"
LIVE_TABLE = "fact_regime_structural_live"

CANONICAL_DDL = f"""
CREATE TABLE IF NOT EXISTS {CANONICAL_TABLE} (
    asset_id            INTEGER      NOT NULL,
    granularity         TEXT         NOT NULL,
    bar_time_utc        TIMESTAMPTZ  NOT NULL,
    regime              TEXT         NOT NULL,
    source_bar_time_utc TIMESTAMPTZ,
    adx                 DOUBLE PRECISION,
    ema_fast            DOUBLE PRECISION,
    ema_slow            DOUBLE PRECISION,
    atr_pct             DOUBLE PRECISION,
    vol_zscore          DOUBLE PRECISION,
    labeller_version    TEXT         NOT NULL,
    computed_at_utc     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, granularity, bar_time_utc)
)
"""

CANONICAL_COMMENT = f"""
COMMENT ON TABLE {CANONICAL_TABLE} IS
  'Canonical structural regime label. THE single source for vetting, attribution, '
  'training and routing. Deterministic and causal, so safe to recompute over full '
  'history. Always computed from the instrument''s FULL history from a fixed anchor - '
  'never from a truncated window (see labeller lookback sensitivity). Indicator columns '
  'are stored so any label can be re-derived and disputed without re-running the pipeline.'
"""

# R2.2 — identical in shape to REMEDIATION_R1 §R1.1, as the spec requires.
LIVE_DDL = f"""
CREATE TABLE IF NOT EXISTS {LIVE_TABLE} (
    id                      BIGSERIAL PRIMARY KEY,
    asset_id                INTEGER      NOT NULL,
    granularity             TEXT         NOT NULL,
    -- The bar the label is ATTACHED to (the bar being traded/evaluated).
    bar_time_utc            TIMESTAMPTZ  NOT NULL,
    regime                  TEXT         NOT NULL,
    -- The bar the label was DERIVED from, i.e. bar_time_utc shifted back one.
    -- Makes the shift auditable from the data rather than from the code.
    source_bar_time_utc     TIMESTAMPTZ,
    -- Provenance of the D1 frame the label was computed from. These three columns
    -- exist specifically to make the partial-bar question answerable after the fact.
    frame_last_bar_time_utc TIMESTAMPTZ,
    frame_last_bar_complete BOOLEAN,
    frame_row_count         INTEGER,
    -- When this row was written, in wall-clock terms. Not the bar time.
    computed_at_utc         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    code_git_sha            TEXT,
    labeller_version        TEXT         NOT NULL,
    -- adx, ema_fast, ema_slow, atr_pct, vol_zscore at the source bar. Stored so a label
    -- can be re-derived and disputed without re-running the pipeline.
    indicator_snapshot      JSONB,
    CONSTRAINT uq_regime_structural_live
        UNIQUE (asset_id, granularity, bar_time_utc, computed_at_utc)
)
"""

LIVE_COMMENT = f"""
COMMENT ON TABLE {LIVE_TABLE} IS
  'APPEND-ONLY record of the structural regime label as it was known at decision time. '
  'Never UPDATE, never DELETE, never backfill. Rows written by the live signal path. '
  'Multiple rows may exist for the same bar if the label was recomputed at different '
  'wall-clock times; that divergence is itself the signal this table exists to capture.'
"""

INDEXES = [
    f"CREATE INDEX IF NOT EXISTS ix_rsl_asset_bar ON {LIVE_TABLE} "
    "(asset_id, granularity, bar_time_utc)",
    f"CREATE INDEX IF NOT EXISTS ix_rsl_computed_at ON {LIVE_TABLE} (computed_at_utc)",
    f"CREATE INDEX IF NOT EXISTS ix_rs_bar_time ON {CANONICAL_TABLE} (bar_time_utc)",
    f"CREATE INDEX IF NOT EXISTS ix_rs_regime ON {CANONICAL_TABLE} "
    "(granularity, regime)",
]


def ensure_tables() -> None:
    """Create both tables and their indexes. Idempotent; safe to call on every run."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(CANONICAL_DDL))
        conn.execute(text(CANONICAL_COMMENT))
        conn.execute(text(LIVE_DDL))
        conn.execute(text(LIVE_COMMENT))
        for stmt in INDEXES:
            conn.execute(text(stmt))
    logger.info("Ensured %s and %s", CANONICAL_TABLE, LIVE_TABLE)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ensure_tables()
    print({"ensured": [CANONICAL_TABLE, LIVE_TABLE]})
