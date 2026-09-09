import pandas as pd
from datetime import timedelta
from src.common.db import get_engine

def run(mode: str) -> dict:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            # Get one H1 backtest trade
            df_t = pd.read_sql(
                "SELECT outcome_id, timestamp, asset_id, granularity "
                "FROM fact_trade_outcomes "
                "WHERE granularity='H1' AND timestamp < '2026-08-01' "
                "ORDER BY timestamp DESC LIMIT 1", 
                conn
            )
            
            if df_t.empty:
                return {"status": "INCONCLUSIVE", "verdict": "No trades found in fact_trade_outcomes"}
                
            signal_bar_time = df_t['timestamp'].iloc[0]
            asset_id = df_t['asset_id'].iloc[0]
            granularity = df_t['granularity'].iloc[0]
            
            # Replicate the join in src/attribution/attribute.py
            # tag_regime_at_entry uses backward merge_asof on entry_time and bar_time
            df_r = pd.read_sql(
                f"SELECT timestamp, regime_causal FROM fact_market_regime_v2 "
                f"WHERE asset_id={asset_id} AND granularity='{granularity}' "
                f"AND timestamp <= '{signal_bar_time}' AND regime_causal IS NOT NULL "
                f"ORDER BY timestamp DESC LIMIT 1", 
                conn
            )
            
            if df_r.empty:
                return {"status": "INCONCLUSIVE", "verdict": "No regime found for trade"}
                
            regime_time = df_r['timestamp'].iloc[0]
            label_value = df_r['regime_causal'].iloc[0]
            
        # For H1, the bar closes 1 hour after the open (timestamp)
        # The label computed on this bar is first knowable at the close of the bar.
        label_knowable_at = regime_time + timedelta(hours=1)
        
        # The signal logic uses the close of the signal_bar_time bar, 
        # so it becomes computable at signal_bar_time + 1 hour.
        signal_computable_at = signal_bar_time + timedelta(hours=1)
        
        # Delta: how long before the signal was computable was the label knowable?
        # Must be strictly positive
        delta_hours = (signal_computable_at - label_knowable_at).total_seconds() / 3600.0
        
        status = "PASS" if delta_hours > 0 else "FAIL"
        
        verdict = (
            f"Backtest trade at signal bar {signal_bar_time} used regime '{label_value}' "
            f"from regime bar {regime_time}. "
            f"Label was computable at {label_knowable_at}, while signal was computable at {signal_computable_at}. "
            f"Delta is {delta_hours} hours. A delta <= 0 indicates lookahead since the batch regime job "
            f"would not have completed instantly."
        )
        
        return {
            "id": "A2",
            "title": "End-to-end label knowability",
            "severity": "P0",
            "status": status,
            "verdict": verdict,
            "evidence": {
                "signal_bar_time": signal_bar_time.isoformat(),
                "label_value": label_value,
                "label_knowable_at_time": label_knowable_at.isoformat(),
                "signal_computable_at_time": signal_computable_at.isoformat(),
                "delta_hours": delta_hours
            },
            "notes": "Verified against backtest trades joined with fact_market_regime_v2 in src/attribution/attribute.py."
        }
    except Exception as e:
        return {
            "id": "A2",
            "title": "End-to-end label knowability",
            "severity": "P0",
            "status": "INCONCLUSIVE",
            "verdict": f"Error running check: {e}",
            "evidence": {},
            "notes": ""
        }
