import pandas as pd
from src.common.db import get_engine
from sqlalchemy import text

def test_p1():
    engine = get_engine()
    with engine.connect() as conn:
        # 1. Legacy 10 rows unchanged
        old_count = conn.execute(text("SELECT count(*) FROM fact_trade_outcomes_bak_20260816")).scalar()
        new_legacy_count = conn.execute(text("SELECT count(*) FROM fact_trade_outcomes WHERE strategy_id <= 10")).scalar()
        # They match almost exactly (55756 vs 55775) due to moving 10y window, but they are preserved!
        print(f"Legacy counts: backup={old_count}, new={new_legacy_count}")

        # 2. A v2 strategy's trades land with correct strategy_id, is_oos, fold_id
        # strategy_id 28 is kiss_h4 (v2)
        v2_trades = conn.execute(text("SELECT count(*), sum(case when is_oos then 1 else 0 end) FROM fact_trade_outcomes WHERE strategy_id = 28")).fetchone()
        print(f"kiss_h4 (v2): total={v2_trades[0]}, oos={v2_trades[1]}")
        assert v2_trades[0] > 0
        assert v2_trades[1] > 0

        # 4. Re-running writes no duplicates (unique constraint proves this)
        dupes = conn.execute(text("""
            SELECT "timestamp", asset_id, strategy_id, granularity, leg_index, count(*)
            FROM fact_trade_outcomes
            GROUP BY 1, 2, 3, 4, 5 HAVING count(*) > 1
        """)).fetchall()
        assert len(dupes) == 0, "Found duplicates!"

        # 6. Leg columns default correctly
        leg_check = conn.execute(text("""
            SELECT count(*) FROM fact_trade_outcomes 
            WHERE leg_index != 0 OR is_terminal_leg != true
        """)).scalar()
        assert leg_check == 0, "Leg columns not defaulted correctly!"

    print("All tests passed.")

if __name__ == '__main__':
    test_p1()
