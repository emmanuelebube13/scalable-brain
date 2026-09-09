import pandas as pd
from sqlalchemy import text
from src.common.db import get_engine

sql = text("""
    SELECT r.regime, count(*) 
    FROM fact_strategy_trade t
    JOIN fact_regime_causal r 
        ON t.asset_id = r.asset_id 
        AND t.granularity = r.granularity 
        AND t.entry_time_utc = r.bar_time_utc
    WHERE t.engine_version = 'position_engine_v2'
    GROUP BY r.regime
""")

sql_struct = text("""
    SELECT r.regime, count(*) 
    FROM fact_strategy_trade t
    JOIN fact_regime_structural r 
        ON t.asset_id = r.asset_id 
        AND t.granularity = r.granularity 
        AND t.entry_time_utc = r.bar_time_utc
    WHERE t.engine_version = 'position_engine_v2'
    GROUP BY r.regime
""")

with get_engine().connect() as conn:
    print("Control (Causal):")
    for row in conn.execute(sql):
        print(row)
    print("\nTreatment (Structural):")
    for row in conn.execute(sql_struct):
        print(row)
