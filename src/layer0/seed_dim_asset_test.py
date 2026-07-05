"""Backward-compatible wrapper for the grouped Dim_Asset seeding script."""

try:
    from .qualification.seed_dim_asset_test import *  # noqa: F401,F403
    from .qualification.seed_dim_asset_test import main as _main
except ImportError:
    from qualification.seed_dim_asset_test import *  # type: ignore # noqa: F401,F403
    from qualification.seed_dim_asset_test import main as _main  # type: ignore

if __name__ == "__main__":
    _main()
#!/usr/bin/env python3
"""
Seed dim_asset with OANDA-compatible test symbols.

Adds/updates a small Forex test set using idempotent upsert logic (PostgreSQL
``UPDATE`` then conditional ``INSERT``; FND-004 Phase 3 — migrated off SQL
Server ``MERGE``/pyodbc):
- EUR_USD
- GBP_USD
- USD_JPY
- AUD_USD
- USD_CAD

Note: ``dim_asset.symbol`` has no UNIQUE constraint (the PK is ``asset_id``),
so ``INSERT ... ON CONFLICT (symbol)`` is not available. The MERGE-on-Symbol
semantics are reproduced with a guarded UPDATE + INSERT ... WHERE NOT EXISTS,
which is idempotent (re-running does not duplicate rows).
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Ensure the repo root is importable so ``src.common`` resolves.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.common.db import get_psycopg2_connection  # noqa: E402

# Legacy core trio + two additional liquid OANDA FX pairs
TEST_ASSETS: List[Tuple[int, str, str]] = [
    (1, "EUR_USD", "Forex"),
    (2, "GBP_USD", "Forex"),
    (3, "USD_JPY", "Forex"),
    (4, "AUD_USD", "Forex"),
    (5, "USD_CAD", "Forex"),
]


def clean_env_value(value: str | None) -> str:
    if value is None:
        return ""
    value = value.strip()
    if len(value) >= 2 and (
        (value.startswith('"') and value.endswith('"'))
        or (value.startswith("'") and value.endswith("'"))
    ):
        value = value[1:-1]
    return value.strip()


def load_repo_env_file() -> None:
    """Load repo-root .env, filling only missing or empty env vars."""
    script_path = Path(__file__).resolve()
    env_path = None

    for candidate_root in script_path.parents:
        candidate_env = candidate_root / ".env"
        if candidate_env.exists():
            env_path = candidate_env
            break

    if env_path is None:
        return

    with env_path.open("r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, raw_value = line.split("=", 1)
            key = key.strip()
            if not key:
                continue

            cleaned = clean_env_value(raw_value)
            current = clean_env_value(os.getenv(key))
            if not current:
                os.environ[key] = cleaned


def read_db_env() -> Dict[str, str]:
    load_repo_env_file()

    required = ["DB_SERVER", "DB_USER", "DB_PASS", "DB_NAME"]
    env: Dict[str, str] = {}
    missing: List[str] = []

    for name in required:
        value = clean_env_value(os.getenv(name))
        if not value:
            missing.append(name)
        env[name] = value

    # PostgreSQL default port (was 1433 under SQL Server).
    env["DB_PORT"] = clean_env_value(os.getenv("DB_PORT")) or "5432"

    if missing:
        raise ValueError(f"Missing DB env vars: {', '.join(missing)}")

    return env


def validate_assets_schema_fit(assets: List[Tuple[str, str]]) -> None:
    """Match dim_asset schema: symbol VARCHAR(20), market_type VARCHAR(50)."""
    for symbol, market_type in assets:
        if len(symbol) > 20:
            raise ValueError(f"Symbol exceeds VARCHAR(20): {symbol}")
        if len(market_type) > 50:
            raise ValueError(f"Market_Type exceeds VARCHAR(50): {market_type}")


def get_db_connection(env: Dict[str, str]):
    """Return a raw psycopg2 connection (routes through src.common.db).

    ``env`` is read by :func:`read_db_env` into ``os.environ``; the canonical
    connection module sources the same variables.
    """
    return get_psycopg2_connection()


def upsert_assets(conn, assets: List[Tuple[str, str]]) -> None:
    """Idempotently upsert (symbol, market_type) pairs into dim_asset.

    Reproduces the former MERGE-on-Symbol behaviour without a UNIQUE constraint:
    update market_type when it differs, otherwise insert when the symbol is new.
    """
    update_sql = """
        UPDATE dim_asset
        SET market_type = %(market_type)s
        WHERE symbol = %(symbol)s
          AND COALESCE(market_type, '') <> %(market_type)s
    """
    insert_sql = """
        INSERT INTO dim_asset (symbol, market_type)
        SELECT %(symbol)s, %(market_type)s
        WHERE NOT EXISTS (
            SELECT 1 FROM dim_asset WHERE symbol = %(symbol)s
        )
    """

    cursor = conn.cursor()
    for symbol, market_type in assets:
        params = {"symbol": symbol, "market_type": market_type}
        cursor.execute(update_sql, params)
        cursor.execute(insert_sql, params)

    conn.commit()


def print_dim_asset_snapshot(conn) -> None:
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT asset_id, symbol, market_type
        FROM dim_asset
        WHERE symbol IN (%s, %s, %s, %s, %s)
        ORDER BY asset_id
        """,
        ("EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"),
    )

    rows = cursor.fetchall()
    print("\ndim_asset seeded rows:")
    for row in rows:
        print(f"  Asset_ID={row[0]} | Symbol={row[1]} | Market_Type={row[2]}")


def main() -> None:
    validate_assets_schema_fit(TEST_ASSETS)
    env = read_db_env()

    conn = get_db_connection(env)
    try:
        upsert_assets(conn, TEST_ASSETS)
        print_dim_asset_snapshot(conn)
        print("\nSeed completed successfully.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
