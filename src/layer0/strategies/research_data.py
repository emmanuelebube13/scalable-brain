"""T6 — read-only data access for the sandbox.

The single door research strategies get to market data. It is deliberately
narrow and deliberately read-only.

**Research must never write to a `fact_*` table.** The sandbox exists to test
ideas, and an idea under test that can mutate the tables the live pipeline
trains on is a contamination path. This module opens a connection, SELECTs, and
returns a frame — there is no write helper here, and
``test_no_side_door.py::test_research_data_module_has_no_write_path`` asserts at
source level that none appears later.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
from sqlalchemy import text

_ALLOWED_GRANULARITIES = {"H1", "H4", "D1"}


def load_ohlcv_readonly(
    pair: str, granularity: str, *, lookback_years: int = 10
) -> Optional[pd.DataFrame]:
    """Load OHLCV for one (pair, granularity). Returns None if unavailable.

    Read-only by construction: a single parameterised SELECT, no transaction, no
    write path.
    """
    if granularity not in _ALLOWED_GRANULARITIES:
        raise ValueError(f"granularity {granularity!r} not in {_ALLOWED_GRANULARITIES}")

    from src.common.db import get_engine

    sql = text(
        '''
        SELECT p."timestamp", p."Open", p.high, p.low, p."Close", p.volume
        FROM fact_market_prices p
        JOIN dim_asset a ON a.asset_id = p.asset_id
        WHERE a.symbol = :pair
          AND p.granularity = :gran
          AND p."timestamp" >= NOW() - (:years || ' years')::interval
        ORDER BY p."timestamp"
        '''
    )
    with get_engine().connect() as conn:
        df = pd.read_sql(
            sql, conn, params={"pair": pair, "gran": granularity, "years": lookback_years}
        )
    if df.empty:
        return None

    df = df.rename(columns={"high": "High", "low": "Low", "volume": "Volume"})
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.set_index("timestamp")
