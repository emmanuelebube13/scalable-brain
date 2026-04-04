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
from typing import Dict, List, Tuple

import pyodbc

# Legacy core trio + two additional liquid OANDA FX pairs
TEST_ASSETS: List[Tuple[str, str]] = [
    ("EUR_USD", "Forex"),
    ("GBP_USD", "Forex"),
    ("USD_JPY", "Forex"),
    ("AUD_USD", "Forex"),
    ("USD_CAD", "Forex"),
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
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(script_dir, "..", ".."))
    env_path = os.path.join(repo_root, ".env")

    if not os.path.exists(env_path):
        return

    with open(env_path, "r", encoding="utf-8") as env_file:
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

    env["DB_PORT"] = clean_env_value(os.getenv("DB_PORT")) or "1433"

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


def get_db_connection(env: Dict[str, str]) -> pyodbc.Connection:
    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={env['DB_SERVER']},{env['DB_PORT']};"
        f"DATABASE={env['DB_NAME']};"
        f"UID={env['DB_USER']};"
        f"PWD={env['DB_PASS']};"
        f"Encrypt=yes;"
        f"TrustServerCertificate=yes;"
        f"Connection Timeout=30;"
    )
    return pyodbc.connect(conn_str, timeout=30)


def upsert_assets(conn: pyodbc.Connection, assets: List[Tuple[str, str]]) -> None:
    merge_sql = """
    MERGE dbo.Dim_Asset AS target
    USING (SELECT ? AS Symbol, ? AS Market_Type) AS source
    ON target.Symbol = source.Symbol
    WHEN MATCHED AND ISNULL(target.Market_Type, '') <> source.Market_Type THEN
        UPDATE SET target.Market_Type = source.Market_Type
    WHEN NOT MATCHED THEN
        INSERT (Symbol, Market_Type)
        VALUES (source.Symbol, source.Market_Type);
    """

    cursor = conn.cursor()
    for symbol, market_type in assets:
        cursor.execute(merge_sql, (symbol, market_type))

    conn.commit()


def print_dim_asset_snapshot(conn: pyodbc.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT Asset_ID, Symbol, Market_Type
        FROM dbo.Dim_Asset
        WHERE Symbol IN (?, ?, ?, ?, ?)
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
