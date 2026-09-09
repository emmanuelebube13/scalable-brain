import sys
import logging
import random
from pathlib import Path
from datetime import timedelta
import pandas as pd

# Ensure we can import from src
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.layer0.data_access.data_loader import load_assets, load_market_prices

logger = logging.getLogger(__name__)

def run(mode: str) -> dict:
    result = {
        "id": "A1",
        "title": "D1 bar timestamp semantics",
        "severity": "P0",
        "status": "INCONCLUSIVE",
        "verdict": "",
        "evidence": {},
        "notes": ""
    }
    try:
        df_assets = load_assets()
        if df_assets.empty:
            result["verdict"] = "No assets found."
            return result
        
        # We need 5 instruments
        asset_ids = df_assets["Asset_ID"].dropna().unique().tolist()
        random.seed(42)
        if len(asset_ids) > 5:
            asset_ids = random.sample(asset_ids, 5)
        
        total_bars_checked = 0
        matches_prev_window = 0
        matches_next_window = 0
        evidence_records = []

        for aid in asset_ids:
            df_d1 = load_market_prices(aid, 'D1')
            df_h1 = load_market_prices(aid, 'H1')
            
            if df_d1.empty or df_h1.empty:
                continue
            
            # Pick ~20 random bars for this instrument
            d1_timestamps = df_d1.index.tolist()
            if len(d1_timestamps) > 20:
                selected_timestamps = random.sample(d1_timestamps, 20)
            else:
                selected_timestamps = d1_timestamps
            
            for t in selected_timestamps:
                d1_bar = df_d1.loc[t]
                
                # H1 bars in [T-24h, T)
                t_prev_start = t - timedelta(hours=24)
                h1_prev = df_h1.loc[(df_h1.index >= t_prev_start) & (df_h1.index < t)]
                
                # H1 bars in [T, T+24h)
                t_next_end = t + timedelta(hours=24)
                h1_next = df_h1.loc[(df_h1.index >= t) & (df_h1.index < t_next_end)]
                
                def compute_ohlc(df_sub):
                    if df_sub.empty:
                        return None
                    df_sub = df_sub.sort_index()
                    return {
                        "Open": float(df_sub["Open"].iloc[0]),
                        "High": float(df_sub["High"].max()),
                        "Low": float(df_sub["Low"].min()),
                        "Close": float(df_sub["Close"].iloc[-1])
                    }
                
                prev_ohlc = compute_ohlc(h1_prev)
                next_ohlc = compute_ohlc(h1_next)
                
                def ohlc_match(o1, o2):
                    if o1 is None or o2 is None:
                        return False
                    return bool((abs(o1["Open"] - o2["Open"]) < 1e-5 and
                            abs(o1["High"] - o2["High"]) < 1e-5 and
                            abs(o1["Low"] - o2["Low"]) < 1e-5 and
                            abs(o1["Close"] - o2["Close"]) < 1e-5))
                
                d1_ohlc = {
                    "Open": float(d1_bar["Open"]),
                    "High": float(d1_bar["High"]),
                    "Low": float(d1_bar["Low"]),
                    "Close": float(d1_bar["Close"])
                }
                
                match_prev = ohlc_match(d1_ohlc, prev_ohlc)
                match_next = ohlc_match(d1_ohlc, next_ohlc)
                
                total_bars_checked += 1
                if match_prev:
                    matches_prev_window += 1
                if match_next:
                    matches_next_window += 1
                
                if total_bars_checked <= 10:
                    evidence_records.append({
                        "asset_id": aid,
                        "timestamp": str(t),
                        "d1_ohlc": d1_ohlc,
                        "prev_window_ohlc": prev_ohlc,
                        "next_window_ohlc": next_ohlc,
                        "match_prev": match_prev,
                        "match_next": match_next
                    })
                    
        result["evidence"] = {
            "total_bars_checked": total_bars_checked,
            "matches_prev_window": matches_prev_window,
            "matches_next_window": matches_next_window,
            "sample_records": evidence_records
        }
        
        if total_bars_checked == 0:
            result["verdict"] = "No H1/D1 overlapping data found to compare."
            return result
            
        if matches_next_window > 0 and matches_prev_window == 0:
            result["status"] = "FAIL"
            result["verdict"] = "D1 bars are reproduced by [T, T+24h) meaning the timestamp marks the open. This confirms a P0 lookahead if D1 timestamp is treated as close."
        elif matches_prev_window > 0 and matches_next_window == 0:
            result["status"] = "PASS"
            result["verdict"] = "D1 bars are reproduced by [T-24h, T) meaning the timestamp marks the close. shift(1) is correct."
        else:
            result["status"] = "INCONCLUSIVE"
            result["verdict"] = f"Mixed or no clear matches. Prev matched {matches_prev_window}, Next matched {matches_next_window} out of {total_bars_checked}."

    except Exception as e:
        logger.exception("Failed to run check A1")
        result["status"] = "INCONCLUSIVE"
        result["verdict"] = f"Exception: {str(e)}"
        
    return result

if __name__ == "__main__":
    print(run("live"))
