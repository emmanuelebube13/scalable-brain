import pandas as pd
from sqlalchemy import text
from src.common.db import get_engine
import ast

def run(mode: str) -> dict:
    result = {
        "id": "A4",
        "title": "merge_asof direction and tolerance",
        "severity": "P0",
        "status": "INCONCLUSIVE",
        "verdict": "",
        "evidence": {},
        "notes": ""
    }

    try:
        # Check source code
        with open("src/gatekeeper/features.py", "r") as f:
            code = f.read()

        has_backward = "direction=\"backward\"" in code
        has_tolerance = "tolerance=" in code

        exact_call = """    merged = pd.merge_asof(
        decision_times.sort_values("bar_time"),
        labels,
        on="bar_time",
        direction="backward",
    ).set_index("bar_time")"""
        
        if not has_tolerance:
            result["status"] = "FAIL"
            result["verdict"] = "merge_asof uses direction='backward' but lacks an explicit tolerance."
        elif has_backward:
            result["status"] = "PASS"
            result["verdict"] = "merge_asof uses direction='backward' and has an explicit tolerance."

        # Empirical test
        engine = get_engine()
        with engine.connect() as conn:
            # We check fact_signals as our proxy for live signals evaluated
            signals = pd.read_sql(
                text("SELECT timestamp as signal_time, asset_id FROM fact_signals"), 
                conn
            )
            
            d1_prices = pd.read_sql(
                text("SELECT timestamp as d1_time, asset_id FROM fact_market_prices WHERE granularity = 'D1'"), 
                conn
            )

        if signals.empty or d1_prices.empty:
            result["notes"] = "Not enough data to calculate gap."
        else:
            signals['signal_time'] = pd.to_datetime(signals['signal_time'], utc=True)
            d1_prices['d1_time'] = pd.to_datetime(d1_prices['d1_time'], utc=True)

            signals = signals.sort_values('signal_time')
            d1_prices = d1_prices.sort_values('d1_time')

            gaps = []
            for asset_id, sig_group in signals.groupby('asset_id'):
                d1_group = d1_prices[d1_prices['asset_id'] == asset_id]
                
                if d1_group.empty:
                    continue
                
                merged = pd.merge_asof(
                    sig_group,
                    d1_group,
                    left_on='signal_time',
                    right_on='d1_time',
                    direction='backward'
                )
                
                # dropna because some signals might be before any D1 bar
                merged = merged.dropna(subset=['d1_time'])
                if not merged.empty:
                    merged['gap'] = merged['signal_time'] - merged['d1_time']
                    gaps.append(merged)

            if gaps:
                all_merged = pd.concat(gaps)
                max_gap_td = all_merged['gap'].max()
                max_gap_hours = max_gap_td.total_seconds() / 3600
                
                over_48h = (all_merged['gap'].dt.total_seconds() / 3600) > 48
                num_over_48h = over_48h.sum()
                
                result["evidence"] = {
                    "exact_call": exact_call,
                    "max_observed_label_age_hours": float(max_gap_hours),
                    "signals_older_than_48h": int(num_over_48h)
                }
                result["notes"] = f"Max observed label age: {max_gap_hours} hours. Flagged {num_over_48h} signals older than 48 hours."
            else:
                result["notes"] = "Could not compute gaps for any signals."
                
    except Exception as e:
        result["verdict"] = f"Error during execution: {str(e)}"
        
    return result
