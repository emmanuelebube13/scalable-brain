import psycopg2
import pandas as pd

conn_str = "postgresql://sa:~Js^qAI*N2XS3=UQkk#O{WQ?]Lv7@localhost:5432/ForexBrainDB"
conn = psycopg2.connect(conn_str)

q = "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'fact_regime_structural'"
df = pd.read_sql_query(q, conn)
print(df)
