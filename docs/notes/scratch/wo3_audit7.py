import pandas as pd
from src.common.db import get_engine

sql = """
SELECT EXTRACT(HOUR FROM bar_time_utc) as h, COUNT(*) as c
FROM fact_regime_structural
WHERE labeller_version = 'structural-v2.1.0' AND asset_id = 1 AND granularity = 'D1'
GROUP BY h;
"""
print(pd.read_sql(sql, get_engine()))
