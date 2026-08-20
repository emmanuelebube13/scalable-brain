import pandas as pd
from src.common.db import get_engine

def run():
    engine = get_engine()
    df = pd.read_sql("""
        SELECT 
            s.strategy_id, 
            s.strategy_key,
            COUNT(f.outcome_id) as trades_written,
            SUM(CASE WHEN f.is_oos THEN 1 ELSE 0 END) as oos_trades,
            MIN(f.timestamp) as date_min,
            MAX(f.timestamp) as date_max
        FROM dim_strategy s
        JOIN fact_trade_outcomes f ON s.strategy_id = f.strategy_id
        GROUP BY s.strategy_id, s.strategy_key
        ORDER BY s.strategy_id
    """, engine)
    
    # Calculate OOS months roughly (each fold is 6 months typically, or date diff)
    df['oos_months'] = (pd.to_datetime(df['date_max']) - pd.to_datetime(df['date_min'])).dt.days / 30.44
    
    with open('task/2026-August-week3/promotion-path/report.md', 'w') as f:
        f.write("| strategy_id | strategy_key | trades | OOS trades | date_min | date_max |\n")
        f.write("|---|---|---|---|---|---|\n")
        for _, row in df.iterrows():
            f.write(f"| {row['strategy_id']} | {row['strategy_key']} | {row['trades_written']} | {row['oos_trades']} | {row['date_min'].strftime('%Y-%m-%d')} | {row['date_max'].strftime('%Y-%m-%d')} |\n")

if __name__ == "__main__":
    run()
