import psycopg2
import pandas as pd

conn_str = "postgresql://sa:~Js^qAI*N2XS3=UQkk#O{WQ?]Lv7@localhost:5432/ForexBrainDB"
conn = psycopg2.connect(conn_str)

q = """
SELECT 
    granularity, labeller_version, regime, count(*) as cnt
FROM fact_regime_structural
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3
"""
df = pd.read_sql_query(q, conn)
print(df)
