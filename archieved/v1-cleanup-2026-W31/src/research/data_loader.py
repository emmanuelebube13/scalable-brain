# data_loader.py
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from dotenv import load_dotenv

# Ensure the repo root is importable so ``src.common`` resolves.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.common.db import get_engine  # noqa: E402

load_dotenv()


def fetch_real_data():
    print("Connecting to PostgreSQL...")
    engine = get_engine()
    asset_map = {5: "EUR_USD", 6: "GBP_USD", 7: "USD_JPY"}
    data = {}
    for asset_id, symbol in asset_map.items():
        print(f"→ Downloading {symbol}...")
        query = text("""
            SELECT "timestamp" AS "Timestamp", "Open", high AS "High",
                   low AS "Low", "Close", volume AS "Volume"
            FROM fact_market_prices
            WHERE asset_id = :asset_id
            ORDER BY "timestamp" ASC
            """)
        with engine.connect() as conn:
            df = pd.read_sql(
                query,
                conn,
                params={"asset_id": asset_id},
                index_col="Timestamp",
                parse_dates=True,
            )
        data[symbol] = df
    return data
