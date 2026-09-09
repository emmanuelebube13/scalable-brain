import pandas as pd
from src.common.db import get_engine

engine = get_engine()

def check_unknown():
    sql = """
    SELECT granularity,
           SUM(CASE WHEN regime = 'UNKNOWN' THEN 1 ELSE 0 END) as unknown_count,
           COUNT(*) as total_count,
           (SUM(CASE WHEN regime = 'UNKNOWN' THEN 1 ELSE 0 END) * 100.0 / COUNT(*)) as unknown_pct
    FROM fact_regime_structural
    WHERE labeller_version = 'structural-v2.1.0'
    GROUP BY granularity
    ORDER BY granularity;
    """
    df = pd.read_sql(sql, engine)
    print("=== UNKNOWN SHARE ===")
    print(df)

def check_labels():
    sql = """
    SELECT granularity, regime, COUNT(*) as cnt
    FROM fact_regime_structural
    WHERE labeller_version = 'structural-v2.1.0'
    GROUP BY granularity, regime
    ORDER BY granularity, regime;
    """
    df = pd.read_sql(sql, engine)
    print("=== LABEL DISTRIBUTION ===")
    print(df)

def check_diurnal():
    sql = """
    SELECT EXTRACT(HOUR FROM bar_time_utc) as h,
           SUM(CASE WHEN regime = 'High-Vol' THEN 1 ELSE 0 END) as high_vol_count,
           SUM(CASE WHEN regime IN ('High-Vol', 'Ranging') THEN 1 ELSE 0 END) as denom_count,
           (SUM(CASE WHEN regime = 'High-Vol' THEN 1.0 ELSE 0.0 END) * 100.0 / 
            NULLIF(SUM(CASE WHEN regime IN ('High-Vol', 'Ranging') THEN 1 ELSE 0 END), 0)) as pct
    FROM fact_regime_structural
    WHERE labeller_version = 'structural-v2.1.0' AND granularity = 'H1' AND asset_id = 1
    GROUP BY h
    ORDER BY pct DESC;
    """
    df = pd.read_sql(sql, engine)
    print("=== DIURNAL H1 ===")
    print(df.head(2))
    print(df.tail(2))
    print(f"Spread: {df['pct'].max() - df['pct'].min():.2f}pp")

check_unknown()
check_labels()
check_diurnal()
