"""Shared query composition helpers for Layer 5 services.

Keeps SQL fragments reusable and granularity-aware across all layer clients.
"""

from datetime import datetime
from typing import Optional
import sqlalchemy as sa


def build_date_filter(
    column: str = "flt.Timestamp",
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> str:
    clauses = []
    if start_date:
        clauses.append(f"{column} >= :start_date")
    if end_date:
        clauses.append(f"{column} < DATEADD(day, 1, CAST(:end_date AS DATE))")
    return " AND ".join(clauses) if clauses else "1=1"


def build_granularity_filter(column: str = "flt.Granularity") -> str:
    return f"({column} IS NULL OR {column} IN (:granularity))"


def build_pagination(limit: int = 50, offset: int = 0) -> str:
    return f"OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY"
