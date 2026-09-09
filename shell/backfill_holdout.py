import psycopg2
from src.common.db import get_psycopg2_connection
from src.validation.walk_forward import HOLDOUT_CUT_DATE

with get_psycopg2_connection() as conn:
    with conn.cursor() as cur:
        # 1. Set is_holdout = TRUE for trades >= cut
        cur.execute("""
            UPDATE fact_trade_outcomes 
            SET is_holdout = TRUE, is_oos = FALSE
            WHERE timestamp >= %s
        """, (HOLDOUT_CUT_DATE,))
        print(f"Updated {cur.rowcount} holdout trades.")
    conn.commit()
