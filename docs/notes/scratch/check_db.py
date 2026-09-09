import psycopg2
import pandas as pd
import os

conn_str = "postgresql://sa:~Js^qAI*N2XS3=UQkk#O{WQ?]Lv7@localhost:5432/ForexBrainDB"
conn = psycopg2.connect(conn_str)

query = """
SELECT 
    EXTRACT(hour FROM bar_time_utc) AS h,
    COUNT(CASE WHEN regime = 'High-Vol' THEN 1 END) AS high_vol_count,
    COUNT(*) AS total_count,
    COUNT(CASE WHEN regime = 'High-Vol' THEN 1 END)::float / NULLIF(COUNT(*), 0) * 100 AS pct
FROM fact_regime_structural
WHERE granularity = 'H1' 
  AND asset_id = (SELECT asset_id FROM dim_asset WHERE symbol = 'EUR_USD')
  AND regime IN ('High-Vol', 'Ranging')
GROUP BY EXTRACT(hour FROM bar_time_utc)
ORDER BY pct DESC
"""
df = pd.read_sql_query(query, conn)
print("H1 spread:")
print(df)
