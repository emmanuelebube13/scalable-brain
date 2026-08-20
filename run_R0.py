import os
import json
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from pathlib import Path
from scipy.stats import bootstrap

from src.layer0.strategies.v2_harness import discover, build_frames, RESULTS_ROOT
from src.layer0.strategies.position_engine import PositionEngine
from src.validation import walk_forward as WF
from src.regime_aware.context import readonly_connection, load_regime_labels, build_trend_labels, UNKNOWN

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("R0")

# --- Monkeypatch PositionEngine to record decision_bar ---
import src.layer0.strategies.position_engine as pe

original_open = pe.PositionEngine._open_position
def patched_open(self, trade_id, intent, fill, fill_bar, checks_from, decision_idx, atr_values, pip, pair, index, stop_rows):
    pos = original_open(self, trade_id, intent, fill, fill_bar, checks_from, decision_idx, atr_values, pip, pair, index, stop_rows)
    pos._decision_bar_hack = intent.decision_bar
    return pos
pe.PositionEngine._open_position = patched_open

original_close = pe.PositionEngine._close_remainder
def patched_close(self, pos, price, exit_reason, exit_kind, exit_bar, gapped, index, leg_rows, trade_rows, slippage_applied=True):
    original_close(self, pos, price, exit_reason, exit_kind, exit_bar, gapped, index, leg_rows, trade_rows, slippage_applied)
    trade_rows[-1]["decision_bar"] = pos._decision_bar_hack
pe.PositionEngine._close_remainder = patched_close
pe.TRADES_COLUMNS.append("decision_bar")
# ---------------------------------------------------------

def get_oos_trades_for_strategy(strategy, pair, gran, frames):
    intents = list(strategy.generate_orders(frames))
    if not intents:
        return pd.DataFrame()
    
    primary = frames[gran]
    folds = WF.default_folds(primary.index[0].to_pydatetime(), primary.index[-1].to_pydatetime())
    if not folds:
        return pd.DataFrame()
        
    engine = PositionEngine()
    # We evaluate natively for simplicity, or we can use H1 if preferred. 
    # The evaluation JSON used H1 resolution for pooled results when available.
    # To keep it simple and match intents directly, we'll use the native frame.
    result = engine.run(
        primary, 
        intents, 
        pair=pair, 
        warmup_bars=strategy.warmup_bars, 
        strategy=strategy, 
        granularity=gran
    )
    
    trades = result.trades
    if trades.empty:
        return trades
        
    trades["entry_time"] = pd.to_datetime(trades["entry_time"], utc=True)
    trades["is_oos"] = False
    
    for fold in folds:
        lo = pd.Timestamp(fold.oos_start).tz_localize("UTC") if fold.oos_start.tzinfo is None else pd.Timestamp(fold.oos_start).tz_convert("UTC")
        hi = pd.Timestamp(fold.oos_end).tz_localize("UTC") if fold.oos_end.tzinfo is None else pd.Timestamp(fold.oos_end).tz_convert("UTC")
        mask = (trades["entry_time"] >= lo) & (trades["entry_time"] < hi)
        trades.loc[mask, "is_oos"] = True
        
    return trades[trades["is_oos"]].copy()

def guess_family(sid):
    sid = sid.lower()
    if any(x in sid for x in ["breakout", "sweep", "grab", "box"]):
        return "breakout"
    if any(x in sid for x in ["reversion", "fade", "range"]):
        return "mean_reversion"
    return "trend_following"

def get_favourable_regimes(family):
    if family == "trend_following":
        return ["Trending-Up", "Trending-Down"]
    elif family == "mean_reversion":
        return ["Ranging", "High-Vol"] # "NOT trending"
    elif family == "breakout":
        return ["High-Vol", "Trending-Up", "Trending-Down"]
    return []

def boot_diff(inside_r, outside_r):
    if len(inside_r) == 0 or len(outside_r) == 0:
        return 0.0, (0.0, 0.0)
    
    # difference in means
    def stat(data1, data2, axis=-1):
        return np.mean(data1, axis=axis) - np.mean(data2, axis=axis)
        
    inside_r = np.array(inside_r)
    outside_r = np.array(outside_r)
    diff = np.mean(inside_r) - np.mean(outside_r)
    
    try:
        res = bootstrap((inside_r, outside_r), stat, vectorized=True, n_resamples=1000)
        return diff, (res.confidence_interval.low, res.confidence_interval.high)
    except Exception:
        return diff, (diff, diff)

def main():
    strategies = discover()
    evaluated = []
    for sid, strat in strategies.items():
        base = RESULTS_ROOT / sid
        if not base.exists():
            continue
        evals = list(base.glob("v2_evaluation_*.json"))
        if evals:
            evaluated.append((sid, strat))
            
    logger.info(f"Found {len(strategies)} total strategies, {len(evaluated)} have evaluations.")
    
    conn = readonly_connection()
    # Cache regime labels
    regime_cache = {}
    for gran in ["H1", "H4", "D1", "W1"]:
        try:
            regime_cache[gran] = load_regime_labels(conn, gran)
        except Exception:
            pass
            
    results_out = []
    
    for sid, strat in evaluated:
        logger.info(f"Processing {sid}...")
        meta = strat.metadata
        gran = meta.primary_granularity
        
        all_oos_trades = []
        for pair in meta.pairs:
            frames = build_frames(pair, gran, meta.context_granularities)
            if frames is None:
                continue
            
            trades = get_oos_trades_for_strategy(strat, pair, gran, frames)
            if not trades.empty:
                all_oos_trades.append(trades)
                
        if not all_oos_trades:
            continue
            
        trades_df = pd.concat(all_oos_trades, ignore_index=True)
        trades_df["decision_bar"] = pd.to_datetime(trades_df.get("decision_bar"), utc=True)
        trades_df = trades_df.dropna(subset=["decision_bar"])
        
        # Attach regime_causal
        trades_df["hmm_causal"] = UNKNOWN
        for pair in trades_df["pair"].unique():
            pair_mask = trades_df["pair"] == pair
            if gran in regime_cache:
                asset_id = None
                with conn.cursor() as cur:
                    cur.execute("SELECT asset_id FROM dim_asset WHERE symbol = %s", (pair,))
                    res = cur.fetchone()
                    if res:
                        asset_id = res[0]
                if asset_id and asset_id in regime_cache[gran]:
                    labels = regime_cache[gran][asset_id].sort_values("bar_time")
                    pair_trades = trades_df[pair_mask].sort_values("decision_bar")
                    merged = pd.merge_asof(
                        pair_trades,
                        labels[["bar_time", "regime"]],
                        left_on="decision_bar",
                        right_on="bar_time",
                        direction="backward"
                    )
                    trades_df.loc[pair_mask, "hmm_causal"] = merged["regime"].fillna(UNKNOWN).values
        
        # Attach d1_trend
        trades_df["d1_trend"] = UNKNOWN
        for pair in trades_df["pair"].unique():
            pair_mask = trades_df["pair"] == pair
            from src.layer0.strategies.research_data import load_ohlcv_readonly
            d1_frame = load_ohlcv_readonly(pair, "D1")
            if d1_frame is not None and not d1_frame.empty:
                d1_labels = build_trend_labels(d1_frame)
                pair_trades = trades_df[pair_mask].sort_values("decision_bar")
                merged = pd.merge_asof(
                    pair_trades,
                    d1_labels.sort_values("bar_time"),
                    left_on="decision_bar",
                    right_on="bar_time",
                    direction="backward"
                )
                trades_df.loc[pair_mask, "d1_trend"] = merged["regime"].fillna(UNKNOWN).values
                
        # Family
        family = getattr(meta, 'strategy_family', None) or guess_family(sid)
        favourable = get_favourable_regimes(family)
        
        # Compute stats
        res = {
            "strategy_id": sid,
            "family": family,
            "favourable_regimes": favourable,
            "n_oos_trades": len(trades_df),
            "omnibus": {},
            "directional": {}
        }
        
        for label_src in ["hmm_causal", "d1_trend"]:
            # Omnibus
            win_rates = trades_df.groupby(label_src)["r_multiple"].apply(lambda x: (x>0).mean())
            counts = trades_df.groupby(label_src).size()
            valid_wr = win_rates[counts >= 10] # Only consider regimes with at least 10 trades for max spread
            spread = valid_wr.max() - valid_wr.min() if len(valid_wr) >= 2 else 0.0
            discriminates_omnibus = spread >= 0.10
            
            res["omnibus"][label_src] = {
                "spread": float(spread),
                "discriminates": bool(discriminates_omnibus),
                "per_regime_wr": win_rates.to_dict()
            }
            
            # Directional
            inside_mask = trades_df[label_src].isin(favourable)
            outside_mask = (~inside_mask) & (trades_df[label_src] != UNKNOWN)
            
            inside_r = trades_df[inside_mask]["r_multiple"].tolist()
            outside_r = trades_df[outside_mask]["r_multiple"].tolist()
            
            diff, ci = boot_diff(inside_r, outside_r)
            discriminates_dir = diff > 0.0 and ci[0] > 0.0 # CI entirely above 0
            
            res["directional"][label_src] = {
                "diff_mean_R": float(diff),
                "ci_low": float(ci[0]),
                "ci_high": float(ci[1]),
                "inside_n": len(inside_r),
                "outside_n": len(outside_r),
                "discriminates": bool(discriminates_dir)
            }
            
            if discriminates_omnibus or discriminates_dir:
                # Concentration check (per pair breakdown of favourable cell)
                if discriminates_dir:
                    fav_df = trades_df[inside_mask]
                else:
                    best_regime = valid_wr.idxmax()
                    fav_df = trades_df[trades_df[label_src] == best_regime]
                    
                pair_breakdown = fav_df["pair"].value_counts().to_dict()
                res["concentration"] = res.get("concentration", {})
                res["concentration"][label_src] = pair_breakdown
                
        results_out.append(res)
        
    out_dir = Path("results/regime_aware/R0")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    with open(out_dir / "r0_results.json", "w") as f:
        json.dump(results_out, f, indent=2)
        
    # Write SUMMARY.md
    n_strats = len(results_out)
    n_omni_hmm = sum(1 for r in results_out if r["omnibus"]["hmm_causal"]["discriminates"])
    n_omni_d1 = sum(1 for r in results_out if r["omnibus"]["d1_trend"]["discriminates"])
    n_dir_hmm = sum(1 for r in results_out if r["directional"]["hmm_causal"]["discriminates"])
    n_dir_d1 = sum(1 for r in results_out if r["directional"]["d1_trend"]["discriminates"])
    
    lines = [
        "# R0 Discrimination Baseline Summary\n",
        f"Evaluated {n_strats} v2 strategies with OOS evaluations.\n",
        "## Omnibus Test (Spread >= 0.10)",
        f"- **hmm_causal**: {n_omni_hmm} discriminating",
        f"- **d1_trend**: {n_omni_d1} discriminating\n",
        "## Directional Test (Hypothesized Regimes Outperform)",
        f"- **hmm_causal**: {n_dir_hmm} discriminating",
        f"- **d1_trend**: {n_dir_d1} discriminating\n",
        "## Concentration Check"
    ]
    
    for r in results_out:
        if "concentration" in r:
            lines.append(f"\n### {r['strategy_id']}")
            for src, breakdown in r["concentration"].items():
                lines.append(f"- **{src}**: {breakdown}")
                
    verdict = "\n## Verdict\n"
    if n_omni_hmm == 0 and n_omni_d1 == 0 and n_dir_hmm == 0 and n_dir_d1 == 0:
        verdict += "Nothing discriminates. The regime labels carry no significant predictive power over these strategies out-of-sample. The week is a plumbing exercise, as we continue the build operationally despite this null result."
    else:
        verdict += f"There is some discrimination. {max(n_omni_hmm, n_omni_d1, n_dir_hmm, n_dir_d1)} strategies showed significant discrimination. However, concentration checks may reveal if this effect is isolated to a single pair like USD_JPY."
        
    lines.append(verdict)
    
    with open(out_dir / "SUMMARY.md", "w") as f:
        f.write("\n".join(lines))
        
if __name__ == "__main__":
    main()
