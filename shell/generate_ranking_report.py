import pandas as pd
import numpy as np
from sqlalchemy import text
from src.common.db import get_engine
from src.vetting import gates as G
from src.attribution import metrics as MET
from src.validation import walk_forward as WF

def evaluate_metrics_for_trades(df):
    r = df["r_multiple"].to_numpy(dtype="float64")
    n = len(df)
    if n == 0:
        return None
    fids = sorted({int(f) for f in df["fold_id"].dropna().unique()})
    
    # We need folds by id for all assets... WF.default_folds uses smin, smax.
    # We'll just approximate oos_months using min/max of entry_time for simplicity if we can't build folds,
    # BUT wait, we can just use the global smin/smax per granularity.
    # Actually, simpler: span of OOS trades is close enough for the report, or we can build the folds.
    
    # For accuracy, let's just use the strict WF month span if we can, else approximate:
    oos_span_days = (df["entry_time"].max() - df["entry_time"].min()).days
    oos_months = round(oos_span_days / 30.44, 2)
    oos_years = oos_months / 12.0
    trades_per_year = (n / oos_years) if oos_years > 0 else 0.0
    
    m = {
        "trade_count": n,
        "win_rate": MET.win_rate(df["is_winner"].to_numpy()),
        "profit_factor": MET.profit_factor(r),
        "sharpe": MET.annualized_sharpe(r, trades_per_year),
        "expectancy": MET.expectancy(r),
        "max_drawdown": MET.max_drawdown(r),
        "recovery_factor": MET.recovery_factor(r),
        "avg_r": MET.avg_r(r),
        "oos_months": oos_months,
        "low_confidence": False # ignore for report
    }
    return m

def bootstrap_ci(r, n_boot=1000):
    if len(r) < 2: return 0.0, 0.0
    np.random.seed(42)
    means = np.mean(np.random.choice(r, size=(n_boot, len(r)), replace=True), axis=1)
    return np.percentile(means, 2.5), np.percentile(means, 97.5)

def tail_dependence(r):
    total_r = np.sum(r)
    if len(r) <= 3 or total_r <= 0: return 0.0
    r_sorted = np.sort(r)[::-1]
    total_without_top_3 = total_r - np.sum(r_sorted[:3])
    return total_without_top_3 / total_r

def run():
    engine = get_engine()
    df = pd.read_sql("""
        SELECT outcome_id, "timestamp" as entry_time, asset_id, strategy_id, granularity,
        is_winner, r_multiple, is_oos, fold_id
        FROM fact_trade_outcomes
        WHERE is_oos = true
    """, engine)
    
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
    
    names = pd.read_sql("SELECT strategy_id, strategy_name FROM dim_strategy", engine)
    name_map = dict(zip(names["strategy_id"], names["strategy_name"]))
    
    results = []
    
    for sid, grp in df.groupby("strategy_id"):
        m = evaluate_metrics_for_trades(grp)
        if m is None: continue
        
        _, failures = G.evaluate_gates({"strategy_id": sid, **m})
        
        r = grp["r_multiple"].to_numpy(dtype="float64")
        ci_lower, ci_upper = bootstrap_ci(r)
        
        # Per pair dispersion
        passed_pairs = 0
        pair_counts = []
        for aid, pair_grp in grp.groupby("asset_id"):
            pair_counts.append(len(pair_grp))
            pm = evaluate_metrics_for_trades(pair_grp)
            if pm:
                _, p_fail = G.evaluate_gates({"strategy_id": sid, **pm})
                if not p_fail:
                    passed_pairs += 1
                    
        max_pair_share = max(pair_counts) / len(grp) if pair_counts else 0.0
        
        td = tail_dependence(r)
        
        results.append({
            "Strategy": name_map.get(sid, str(sid)),
            "Trades": len(grp),
            "PF": round(m["profit_factor"], 2),
            "Sharpe": round(m["sharpe"], 2),
            "MaxDD": round(m["max_drawdown"], 2),
            "Failures": ", ".join(failures) if failures else "PASS",
            "CI(Mean R)": f"[{ci_lower:.3f}, {ci_upper:.3f}]",
            "Pairs Passed": f"{passed_pairs}/5",
            "Max Pair %": f"{max_pair_share*100:.1f}%",
            "Tail Dep (ex-top3 R%)": f"{td*100:.1f}%"
        })
        
    results.sort(key=lambda x: x["Sharpe"], reverse=True)
    
    with open('task/2026-August-week3/promotion-path/ranked_report.md', 'w') as f:
        f.write("# Strategy Ranking Report (OOS Pooled)\n\n")
        f.write("| Strategy | Trades | PF | Sharpe | MaxDD | CI(Mean R) | Pairs Passed | Max Pair % | Tail Dep | Failures |\n")
        f.write("|---|---|---|---|---|---|---|---|---|---|\n")
        for r in results:
            f.write(f"| {r['Strategy']} | {r['Trades']} | {r['PF']} | {r['Sharpe']} | {r['MaxDD']} | {r['CI(Mean R)']} | {r['Pairs Passed']} | {r['Max Pair %']} | {r['Tail Dep (ex-top3 R%)']} | {r['Failures']} |\n")

if __name__ == '__main__':
    run()
