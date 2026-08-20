"""Build the 2026-08-02 diagnosis artifacts.

Two independent findings, both measured:

  A. The gatekeeper is a strategy-identity lookup, not a signal gate.
     strategy_id one-hot carries ~97% of gain importance; regime_causal ~0.2%.
     Per (strategy x regime x H1) approval is bimodal 0%/100%. Strategy 10 --
     the only strategy carrying live weight -- sits in the 100% group, which is
     exactly the 0.9995 live approval Computer 2 measured.

  B. Live entry direction does not come from the strategy. In the backtest,
     strategy 10 @H1 takes LONGs 41% of the time in Trending-Down; live took
     13/13 shorts. Under the backtest's own direction mix that is p=0.001.
"""
from __future__ import annotations

import json
import os

import joblib
import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy import text

from src.common.db import get_engine
from src.gatekeeper import train as T

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
COMMS = "/home/emmanuel/Documents/Scalable_Brain/OtherSystems/comms"

model = joblib.load(os.path.join(ROOT, "models", "champion_model.pkl"))
pre = joblib.load(os.path.join(ROOT, "models", "champion_preprocessor.pkl"))
man = json.load(open(os.path.join(ROOT, "models", "champion_manifest.json")))
th, cols = man["dynamic_thresholds"], man["features"]

# ---------------------------------------------------- A. importance + per-cell
names = list(pre.get_feature_names_out())
imp = model.feature_importances_
tot = float(imp.sum())


def group(prefix: str) -> float:
    return float(sum(imp[i] for i, n in enumerate(names) if prefix in n) / tot)


frame = T._derive_features(T.build_frame())
gran = "granularity_x" if "granularity_x" in frame.columns else "granularity"
frame["_score"] = model.predict_proba(pre.transform(frame[cols]))[:, 1]
frame["_thr"] = frame["regime_causal"].map(lambda r: th.get(r, th["fallback"]))
frame["_app"] = frame["_score"] >= frame["_thr"]
h1 = frame[frame[gran] == "H1"]

cells = []
for (sid, reg), g in h1.groupby(["strategy_id", "regime_causal"]):
    cells.append(
        {
            "strategy_id": sid,
            "regime": reg,
            "n": int(len(g)),
            "mean_score": round(float(g["_score"].mean()), 4),
            "threshold": float(g["_thr"].iloc[0]),
            "approval": round(float(g["_app"].mean()), 4),
            "backtest_win_rate": round(float(g["is_winner"].mean()), 4),
        }
    )
ap = np.array([c["approval"] for c in cells])

finding_a = {
    "finding": "the gatekeeper is a strategy-identity lookup, not a signal gate",
    "feature_importance_share": {
        "strategy_id_onehot": round(group("cat__strategy_id"), 4),
        "regime_causal_onehot": round(group("cat__regime_causal"), 4),
        "entry_signal_type_onehot": round(group("cat__entry_signal_type"), 4),
        "all_numeric_features": round(group("num__"), 4),
    },
    "per_cell_approval_H1": {
        "n_cells": len(cells),
        "cells_at_or_above_0.95": int((ap >= 0.95).sum()),
        "cells_at_or_below_0.05": int((ap <= 0.05).sum()),
        "median": round(float(np.median(ap)), 4),
    },
    "strategy_10_cells": [c for c in cells if c["strategy_id"] == "10"],
    "aggregate_approval_all_rows": round(float(frame["_app"].mean()), 4),
    "manifest_turnover_band": man["turnover_band"],
    "why_the_band_passed": (
        "the band is enforced on the AGGREGATE approval rate only. A policy that "
        "approves 0% of 23 cells and 100% of 12 cells averages to 0.17 and passes "
        "cleanly. FIX-S1-010 added per-REGIME enforcement but not per "
        "(strategy x regime), so it cannot see this."
    ),
    "all_cells_H1": sorted(cells, key=lambda c: (c["strategy_id"], c["regime"])),
}

# ---------------------------------------------------- B. direction provenance
sql = """
SELECT r.regime_causal, t.entry_signal_type, count(*) n,
       avg(t.is_winner::int::float8) win_rate, avg(t.r_multiple) mean_r
FROM fact_trade_outcomes t
JOIN LATERAL (
  SELECT regime_causal FROM fact_market_regime_v2 g
  WHERE g.asset_id=t.asset_id AND g.granularity=t.granularity
    AND g.regime_causal IS NOT NULL AND g."timestamp" <= t."timestamp"
  ORDER BY g."timestamp" DESC LIMIT 1) r ON true
WHERE t.strategy_id=10 AND t.granularity='H1'
GROUP BY 1,2 ORDER BY 1,2
"""
with get_engine().connect() as conn:
    bt = pd.read_sql(text(sql), conn)

td = bt[bt["regime_causal"] == "Trending-Down"]
n_short = int(td[td["entry_signal_type"] == "short"]["n"].iloc[0])
n_long = int(td[td["entry_signal_type"] == "long"]["n"].iloc[0])
p_short = n_short / (n_short + n_long)

trades = json.load(open(os.path.join(COMMS, "s1-section9-trades.json")))
live_td = [t for t in trades if t["regime_at_entry"] == "Trending-Down"]
live_short = sum(1 for t in live_td if t["direction"] == "short")
pv = stats.binomtest(live_short, len(live_td), p_short, alternative="greater").pvalue

clusters = {}
for t in trades:
    clusters.setdefault(t["entry_time"][:16], []).append(t["pair"])

finding_b = {
    "finding": (
        "live entry direction is derived from the regime label, not from the "
        "strategy. Range_Stochastic_Divergence is a mean-reversion oscillator: its "
        "qualified edge requires taking LONGs in a downtrend 41% of the time."
    ),
    "backtest_direction_mix_strategy10_H1": bt.round(4).to_dict("records"),
    "trending_down": {
        "backtest_short": n_short,
        "backtest_long": n_long,
        "backtest_p_short": round(p_short, 4),
        "live_short": live_short,
        "live_long": len(live_td) - live_short,
        "binomial_p_value": round(float(pv), 6),
        "odds": f"about 1 in {round(1 / pv):,}",
    },
    "entry_time_clustering": {
        k: v for k, v in sorted(clusters.items()) if len(v) > 1
    },
    "clustering_note": (
        "3-4 instruments entering on the identical H1 bar is what a regime/batch "
        "trigger looks like. Independent per-instrument stochastic crossings do not "
        "synchronise across EUR_USD, GBP_USD and AUD_USD on the same bar."
    ),
    "bears_on": (
        "Computer 2 withdrew F-405 (the bridge discards ScoredSignal.direction) "
        "BECAUSE direction was consistent with the regime label. For this strategy "
        "that consistency is the defect, not the disproof: something downstream is "
        "reconstructing direction from the label after the bridge drops it."
    ),
}

json.dump(
    {
        "artifact": "system1-diagnosis-2026-08-02",
        "supersedes": "the root-cause section of S1-REPLY-2026-08-01",
        "finding_A_gatekeeper": finding_a,
        "finding_B_direction": finding_b,
    },
    open(os.path.join(HERE, "diagnosis-2026-08-02.json"), "w"),
    indent=2,
)

print("FINDING A — importance share")
for k, v in finding_a["feature_importance_share"].items():
    print(f"  {k:<28} {v:>7.2%}")
print(f"  per-cell H1: {finding_a['per_cell_approval_H1']}")
print("\nFINDING B — direction")
print(f"  backtest Trending-Down: {n_short} short / {n_long} long (P_short={p_short:.3f})")
print(f"  live Trending-Down    : {live_short} short / {len(live_td)-live_short} long")
print(f"  binomial p            : {pv:.6f}  (1 in {round(1/pv):,})")
print("\nwrote diagnosis-2026-08-02.json")
