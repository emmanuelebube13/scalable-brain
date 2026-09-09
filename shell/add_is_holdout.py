import psycopg2
from src.common.db import get_psycopg2_connection

with get_psycopg2_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("ALTER TABLE fact_trade_outcomes ADD COLUMN IF NOT EXISTS is_holdout boolean DEFAULT FALSE;")
    conn.commit()
    print("Column is_holdout added to fact_trade_outcomes.")
