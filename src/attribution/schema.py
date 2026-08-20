"""MODEL-004 — idempotent creation of fact_strategy_regime_attribution."""
from __future__ import annotations

import logging

from sqlalchemy import text

from src.common.db import get_engine

logger = logging.getLogger("system1.attribution.schema")

TABLE = "fact_strategy_regime_attribution"


def ensure_attribution_table() -> bool:
    engine = get_engine()
    with engine.begin() as conn:
        if conn.execute(text("SELECT to_regclass(:q)"), {"q": f"public.{TABLE}"}).scalar():
            # Additive: ensure later-added metric columns exist.
            for col in ("recovery_factor", "oos_months"):
                conn.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS {col} double precision"))
            logger.info("%s already exists (ensured recovery_factor/oos_months)", TABLE)
            return False
        conn.execute(
            text(
                f"""
                CREATE TABLE {TABLE} (
                    attribution_id     bigserial PRIMARY KEY,
                    strategy_id        integer NOT NULL,
                    regime             varchar(20) NOT NULL,
                    granularity        varchar(8) NOT NULL,
                    scope              varchar(20) NOT NULL DEFAULT 'PORTFOLIO',
                    trade_count        integer NOT NULL,
                    win_rate           double precision,
                    profit_factor      double precision,
                    sharpe             double precision,
                    expectancy         double precision,
                    max_drawdown       double precision,
                    recovery_factor    double precision,
                    oos_months         double precision,
                    avg_r              double precision,
                    win_rate_shrunk    double precision,
                    profit_factor_shrunk double precision,
                    sharpe_shrunk      double precision,
                    low_confidence     boolean NOT NULL,
                    model_version      varchar(50),
                    qualification_run_id varchar(64),
                    created_at         timestamptz NOT NULL DEFAULT now(),
                    UNIQUE (strategy_id, regime, granularity, scope, qualification_run_id)
                )
                """
            )
        )
        logger.info("Created %s", TABLE)
        return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    print({"created": ensure_attribution_table()})
