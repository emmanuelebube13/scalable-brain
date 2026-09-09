import pandas as pd
from src.common.db import get_engine

sql = """
SELECT bar_time_utc, regime, vol_zscore, atr_pct, adx, ema_slow
FROM fact_regime_structural
WHERE labeller_version = 'structural-v2.1.0' AND asset_id = 1 AND granularity = 'D1'
ORDER BY bar_time_utc
LIMIT 510;
"""
df = pd.read_sql(sql, get_engine())
print(df[490:510])
