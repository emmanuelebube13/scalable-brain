"""MODEL-003 — additive, idempotent HMM columns on fact_market_regime_v2."""

from __future__ import annotations

import logging

from sqlalchemy import text

from src.common.db import get_engine

logger = logging.getLogger("system1.regime.schema")

TABLE = "fact_market_regime_v2"
HMM_COLUMNS = [
    ("regime_model", "varchar(10)"),
    ("regime_raw", "varchar(20)"),
    ("regime_smoothed", "varchar(20)"),
    ("prob_trending_up", "double precision"),
    ("prob_trending_down", "double precision"),
    ("prob_ranging", "double precision"),
    ("prob_high_vol", "double precision"),
    ("model_version", "varchar(50)"),
    # FIX-S1-005: causal (walk-forward, filtered forward-only) regime label + probs.
    # These are the ML/attribution-consumed columns; the smoothed columns above are
    # now reporting-only (full-history forward-backward fit — non-causal, leaks future).
    ("regime_causal", "varchar(20)"),
    ("prob_causal_trending_up", "double precision"),
    ("prob_causal_trending_down", "double precision"),
    ("prob_causal_ranging", "double precision"),
    ("prob_causal_high_vol", "double precision"),
    ("causal_label_method", "varchar(20)"),
    ("causal_fold_id", "integer"),
]


def ensure_regime_columns() -> list:
    added = []
    engine = get_engine()
    with engine.begin() as conn:
        existing = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name=:t"
                ),
                {"t": TABLE},
            )
        }
        for col, typ in HMM_COLUMNS:
            if col not in existing:
                conn.execute(
                    text(f"ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS {col} {typ}")
                )
                added.append(col)
                logger.info("Added %s.%s (%s)", TABLE, col, typ)
    if not added:
        logger.info("HMM columns already present on %s", TABLE)
    return added


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s"
    )
    print({"added": ensure_regime_columns()})
