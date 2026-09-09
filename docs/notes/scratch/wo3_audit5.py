import pandas as pd
from src.common.db import get_engine

sql = """
SELECT asset_id, granularity, SUM(CASE WHEN regime = 'UNKNOWN' THEN 1 ELSE 0 END) as uk
FROM fact_regime_structural
WHERE version = 'structural-v2.1.0'
GROUP BY asset_id, granularity
ORDER BY asset_id, granularity;
"""
try:
    print(pd.read_sql(sql.replace("version", "labeller_version"), get_engine()))
except Exception as e:
    print(e)
