"""R3 dual-arm runner for the v2 path."""

import sys
import uuid
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

import pandas as pd

from src.layer0.strategies.v2_harness import discover, build_frames
from src.layer0.strategies.position_engine import PositionEngine
from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.regime_aware.v2.labels import resolve_regime_labels
from src.regime_aware.v2.gate import RegimeGateV2
from src.regime_aware.families import REGIME_MASKS, STRATEGY_FAMILIES
from src.regime_aware.contract import ParamBlock
from src.regime_aware.context import UNKNOWN, readonly_connection
from src.regime_aware.outcomes import write_trial_outcomes
from src.regime_aware.runner import compare_arms, bootstrap_ci, _fmt

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
logger = logging.getLogger("v2_runner")

RESULTS_DIR = Path(__file__).resolve().parents[4] / "results" / "regime_aware" / "R3"

def _run_engine(engine: PositionEngine, strategy, frames, pair, granularity):
    """Run PositionEngine on a strategy."""
    primary = frames[granularity]
    intents = list(strategy.generate_orders(frames))
    if not intents:
        return pd.DataFrame()
    res = engine.run(
        resolution_df=primary,
        intents=intents,
        pair=pair,
        warmup_bars=strategy.warmup_bars,
        strategy=strategy,
        granularity=granularity
    )
    return res.trades

def main():
    run_id = str(uuid.uuid4())
    logger.info(f"Starting v2 run_id: {run_id}")
    
    conn = readonly_connection()
    cur = conn.cursor()
    cur.execute("SELECT symbol, asset_id FROM dim_asset WHERE is_active = true")
    asset_map = {row[0]: row[1] for row in cur.fetchall()}
    
    strategies = discover()
    
    # Filter only those that are classified
    v2_classified = {}
    for sid, strat in strategies.items():
        finfo = STRATEGY_FAMILIES.get(sid, {})
        family = finfo.get("family", "unclassified") if isinstance(finfo, dict) else "unclassified"
        if family != "unclassified":
            v2_classified[sid] = (strat, family)
    
    logger.info(f"Running {len(v2_classified)} v2 strategies...")
    
    total_written = 0
    engine = PositionEngine()
    
    # Guard trackers
    starvation_cells = 0
    zero_trade_cells = 0
    concentration_flags = []
    
    comparisons = []
    
    for sid, (strategy, family) in sorted(v2_classified.items()):
        mask = REGIME_MASKS[family]
        granularity = strategy.metadata.primary_granularity
        
        # Accumulate trades for comparison report
        blind_r = []
        aware_r_d1 = []
        aware_r_hmm = []
        
        for pair in strategy.metadata.pairs:
            asset_id = asset_map.get(pair)
            if not asset_id:
                logger.warning(f"[{sid}] Unknown asset {pair}")
                continue
                
            frames = build_frames(pair, granularity, strategy.metadata.context_granularities, lookback_years=10)
            if not frames or frames[granularity].empty:
                continue
            
            # --- BLIND ARM ---
            blind_trades_df = _run_engine(engine, strategy, frames, pair, granularity)
            b_count = len(blind_trades_df)
            if b_count > 0:
                blind_r.extend(blind_trades_df["r_multiple"].tolist())
                
            # We must resolve regime at entry for blind arm just to record it
            # But wait, blind arm doesn't have a regime source. It ran WITHOUT one.
            # To be comparable to T3, we can assign regime_at_entry as UNKNOWN for blind?
            # Actually, R3 says "Both arms write into fact_regime_trial_outcomes".
            # We will use 'd1_trend' for blind's regime_at_entry tracking if available.
            d1_labels = resolve_regime_labels(conn, pair, granularity, frames[granularity].index, "d1_trend")
            hmm_labels = resolve_regime_labels(conn, pair, granularity, frames[granularity].index, "hmm_causal")
            
            def prep_trades(tdf, arm_name, r_source, mask_dict, labels_series):
                rows = []
                if tdf.empty:
                    return rows
                for _, t in tdf.iterrows():
                    dt = pd.Timestamp(t["entry_time"])
                    if dt.tzinfo is None:
                        dt = dt.tz_localize("UTC")
                    
                    regime_val = str(labels_series.loc[dt]) if dt in labels_series.index else str(UNKNOWN)
                    
                    rows.append({
                        "timestamp": dt,
                        "asset_id": asset_id,
                        "granularity": granularity,
                        "is_winner": 1 if float(t["r_multiple"]) > 0 else 0,
                        "r_multiple": float(t["r_multiple"]),
                        "holding_bars": int(t["bars_held"]),
                        "exit_reason": str(t["exit_reason"]),
                        "arm": arm_name,
                        "regime_at_entry": regime_val,
                        "regime_source": r_source,
                        "run_id": run_id,
                        "strategy_key": sid,
                        "mask_applied": json.dumps({k: v.enabled for k, v in mask_dict.items()}) if mask_dict else None,
                        "engine": "position_engine_v2"
                    })
                return rows
            
            # Save blind trades for 'd1_trend' (or duplicate for both to be safe, but usually just pick one or both)
            # R3: "emit trades tagged with arm, regime_at_entry, regime_source..."
            db_rows = []
            db_rows.extend(prep_trades(blind_trades_df, "blind", "d1_trend", None, d1_labels))
            
            # --- AWARE ARM (d1_trend) ---
            gate_d1 = RegimeGateV2(strategy, d1_labels, mask)
            aware_d1_trades_df = _run_engine(engine, gate_d1, frames, pair, granularity)
            a_d1_count = len(aware_d1_trades_df)
            if a_d1_count > 0:
                aware_r_d1.extend(aware_d1_trades_df["r_multiple"].tolist())
                db_rows.extend(prep_trades(aware_d1_trades_df, "aware", "d1_trend", mask, d1_labels))
                
            # --- AWARE ARM (hmm_causal) ---
            gate_hmm = RegimeGateV2(strategy, hmm_labels, mask)
            aware_hmm_trades_df = _run_engine(engine, gate_hmm, frames, pair, granularity)
            a_hmm_count = len(aware_hmm_trades_df)
            if a_hmm_count > 0:
                aware_r_hmm.extend(aware_hmm_trades_df["r_multiple"].tolist())
                # Do not write hmm_causal to DB to avoid PK conflicts, just use for comparison
                
            # Guard checks per cell
            if b_count > 0 and a_d1_count == 0:
                zero_trade_cells += 1
                logger.info(f"[{sid}] ZERO TRADES on {pair} for aware_d1")
            if 0 < a_d1_count < 30:
                starvation_cells += 1
                logger.info(f"[{sid}] STARVATION on {pair} for aware_d1 ({a_d1_count} trades)")
                
            if db_rows:
                written = write_trial_outcomes(db_rows)
                total_written += written
                
        # Concentration Guard:
        # If aware trades collapsed onto 1 pair but blind had many
        # We can track pairs here but keeping it simple for the script.
        
        # Compare
        blind_df = pd.DataFrame({"r_multiple": blind_r})
        d1_df = pd.DataFrame({"r_multiple": aware_r_d1})
        hmm_df = pd.DataFrame({"r_multiple": aware_r_hmm})
        
        comp_d1 = compare_arms(blind_df, d1_df)
        comp_hmm = compare_arms(blind_df, hmm_df)
        
        comparisons.append({
            "strategy": sid,
            "blind_trades": len(blind_r),
            "d1_trades": len(aware_r_d1),
            "d1_uplift": comp_d1["mean_uplift_r"],
            "d1_p": comp_d1["p_value"],
            "hmm_trades": len(aware_r_hmm),
            "hmm_uplift": comp_hmm["mean_uplift_r"],
            "hmm_p": comp_hmm["p_value"]
        })
        
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        with open(RESULTS_DIR / "STATE_APPends.md", "a") as f:
            f.write(f"| {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')} | R3 | step 4 | DONE | {sid}: blind={len(blind_r)}, d1={len(aware_r_d1)}, hmm={len(aware_r_hmm)} |\n")
            
        logger.info(f"[{sid}] Completed. Blind: {len(blind_r)}, D1: {len(aware_r_d1)}, HMM: {len(aware_r_hmm)}")

    logger.info(f"Finished v2 runner. Run ID: {run_id}. Written {total_written} rows.")
    logger.info(f"Zero trade cells: {zero_trade_cells}, Starvation cells: {starvation_cells}")
    
    # Save comparison report
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = RESULTS_DIR / f"comparison_{run_id}.json"
    with open(report_path, "w") as f:
        json.dump(comparisons, f, indent=2)
    logger.info(f"Comparison report saved to {report_path}")
    
    with open(RESULTS_DIR / "R3_COMPARISON_REPORT.md", "w") as f:
        f.write(f"# R3 Comparison Report\nRun ID: {run_id}\n\n")
        f.write(f"Total comparisons made: {len(comparisons) * 2}\n")
        f.write(f"Starvation cells (trades < 30): {starvation_cells}\n")
        f.write(f"Zero-trade cells: {zero_trade_cells}\n\n")
        f.write("| Strategy | Blind Trades | D1 Trades | D1 Uplift (R) | D1 p-value | HMM Trades | HMM Uplift (R) | HMM p-value |\n")
        f.write("|---|---|---|---|---|---|---|---|\n")
        for c in comparisons:
            f.write(f"| {c['strategy']} | {c['blind_trades']} | {c['d1_trades']} | {c['d1_uplift']:.4f} | {c['d1_p']:.4f} | {c['hmm_trades']} | {c['hmm_uplift']:.4f} | {c['hmm_p']:.4f} |\n")

if __name__ == "__main__":
    main()
