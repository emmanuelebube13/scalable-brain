#!/usr/bin/env python3
"""
Seed Dim_Asset with OANDA-compatible test symbols.

Adds/updates a small Forex test set using idempotent MERGE logic:
- EUR_USD
- GBP_USD
- USD_JPY
- AUD_USD
- USD_CAD
"""

import os
from pathlib import Path
from typing import Dict, List, Tuple

import psycopg2

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
    if len(value) >= 2 and ((value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'"))):
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

    env["DB_PORT"] = clean_env_value(os.getenv("DB_PORT")) or "5432"

    if missing:
        raise ValueError(f"Missing DB env vars: {', '.join(missing)}")

    return env


def validate_assets_schema_fit(assets: List[Tuple[str, str]]) -> None:
    """Match Dim_Asset schema: Symbol VARCHAR(20), Market_Type VARCHAR(20)."""
    for symbol, market_type in assets:
        if len(symbol) > 20:
            raise ValueError(f"Symbol exceeds VARCHAR(20): {symbol}")
        if len(market_type) > 20:
            raise ValueError(f"Market_Type exceeds VARCHAR(20): {market_type}")


def get_db_connection(env: Dict[str, str]) -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=env['DB_SERVER'],
        dbname=env['DB_NAME'],
        user=env['DB_USER'],
        password=env['DB_PASS'],
        port=env['DB_PORT'],
        connect_timeout=30,
    )


def upsert_assets(conn: psycopg2.extensions.connection, assets: List[Tuple[int, str, str]]) -> None:
    upsert_sql = """
    INSERT INTO Dim_Asset (Asset_ID, Symbol, Market_Type)
    VALUES (%s, %s, %s)
    ON CONFLICT (Asset_ID) DO UPDATE SET
        Symbol = EXCLUDED.Symbol,
        Market_Type = EXCLUDED.Market_Type;
    """

    cursor = conn.cursor()
    for asset_id, symbol, market_type in assets:
        cursor.execute(upsert_sql, (asset_id, symbol, market_type))

    conn.commit()


def print_dim_asset_snapshot(conn: psycopg2.extensions.connection) -> None:
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT Asset_ID, Symbol, Market_Type
        FROM Dim_Asset
        WHERE Symbol IN (%s, %s, %s, %s, %s)
        ORDER BY Asset_ID
        """,
        ("EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"),
    )

    rows = cursor.fetchall()
    print("\nDim_Asset seeded rows:")
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
