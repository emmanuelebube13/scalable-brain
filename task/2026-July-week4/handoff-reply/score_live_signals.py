"""Score Computer 2's 14 live signals through OUR champion gatekeeper.

They sent per-trade `sig_model_score` (the score their live system used). We hold the
regime/feature bar those signals were generated from. Reconstructing the true feature row
and scoring it with the shipped champion tells us, per signal, what the gatekeeper System 1
published would ACTUALLY have said -- and therefore whether their live scores came from it.

Output: live-signal-rescore.json + a printed table.
"""
from __future__ import annotations

import json
import os

import joblib
import pandas as pd
from sqlalchemy import text

from src.common.db import get_engine
from src.gatekeeper import train as T

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
COMMS = "/home/emmanuel/Documents/Scalable_Brain/OtherSystems/comms"

SYMBOL_TO_ID = {"EUR_USD": 1, "GBP_USD": 2, "USD_JPY": 3, "AUD_USD": 4, "USD_CAD": 5}

model = joblib.load(os.path.join(ROOT, "models", "champion_model.pkl"))
pre = joblib.load(os.path.join(ROOT, "models", "champion_preprocessor.pkl"))
man = json.load(open(os.path.join(ROOT, "models", "champion_manifest.json")))
th, cols = man["dynamic_thresholds"], man["features"]

trades = json.load(open(os.path.join(COMMS, "s1-section9-trades.json")))

engine = get_engine()
rows = []
with engine.connect() as conn:
    for i, t in enumerate(trades, 1):
        aid = SYMBOL_TO_ID[t["pair"]]
        entry = pd.to_datetime(t["entry_time"], utc=True)
        # point-in-time: the last CAUSAL regime bar at or before entry (same join rule
        # build_frame() uses -- merge_asof direction="backward")
        r = conn.execute(
            text(
                'SELECT "timestamp", regime_causal, atr_value, adx_value, '
                "prob_causal_trending_up, prob_causal_trending_down, "
                "prob_causal_ranging, prob_causal_high_vol "
                "FROM fact_market_regime_v2 "
                "WHERE asset_id=:a AND granularity='H1' AND regime_causal IS NOT NULL "
                'AND "timestamp" <= :ts ORDER BY "timestamp" DESC LIMIT 1'
            ),
            {"a": aid, "ts": entry.to_pydatetime()},
        ).fetchone()

        rec = {
            "n": i,
            "pair": t["pair"],
            "entry_time": t["entry_time"],
            "direction": t["direction"],
            "regime_live": t["regime_at_entry"],
            "live_score": round(float(t["sig_model_score"]), 6),
            "live_atr": float(t["sig_atr"]),
            "R_live": round(float(t["R"]), 4),
            "exit": t["exit_reason"].split("[")[0],
        }
        if r is None:
            rec["status"] = "no_regime_bar_in_S1_db"
            rows.append(rec)
            continue

        bar_time = pd.to_datetime(r[0], utc=True)
        age_h = (entry - bar_time).total_seconds() / 3600.0
        if age_h > 24:
            rec["status"] = f"stale_bar_{age_h:.0f}h (S1 data ends 2026-07-24)"
            rec["s1_bar"] = str(bar_time)
            rows.append(rec)
            continue

        feat = {
            "atr_value": float(r[2]),
            "adx_value": float(r[3]),
            "prob_causal_trending_up": float(r[4]),
            "prob_causal_trending_down": float(r[5]),
            "prob_causal_ranging": float(r[6]),
            "prob_causal_high_vol": float(r[7]),
            "regime_causal": str(r[1]),
            "strategy_id": str(t["strategy_id"]),
            "entry_signal_type": t["direction"],
        }
        df = T._derive_features(pd.DataFrame([feat]))
        score = float(model.predict_proba(pre.transform(df[cols]))[:, 1][0])
        thr = float(th.get(feat["regime_causal"], th["fallback"]))

        rec.update(
            {
                "status": "scored",
                "s1_bar": str(bar_time),
                "bar_age_h": round(age_h, 2),
                "s1_regime": feat["regime_causal"],
                "s1_atr": round(feat["atr_value"], 6),
                "s1_adx": round(feat["adx_value"], 2),
                "s1_score": round(score, 6),
                "threshold": thr,
                "s1_would_approve": bool(score >= thr),
                "score_delta_live_minus_s1": round(rec["live_score"] - score, 6),
                "regime_agrees": feat["regime_causal"] == t["regime_at_entry"],
                "atr_ratio_live_over_s1": round(
                    rec["live_atr"] / feat["atr_value"], 4
                ),
            }
        )
        rows.append(rec)

scored = [r for r in rows if r.get("status") == "scored"]

print(
    f"{'#':>2} {'pair':<8} {'entry(UTC)':<17} {'live':>6} {'S1':>6} {'thr':>5} "
    f"{'S1 approve?':<11} {'regime(live/S1)':<28} {'ATRratio':>8} {'R':>6}"
)
for r in rows:
    if r.get("status") != "scored":
        print(f"{r['n']:>2} {r['pair']:<8} {r['entry_time'][:16]:<17} "
              f"{r['live_score']:>6.3f} {'--':>6} {'--':>5} {r['status']}")
        continue
    reg = f"{r['regime_live']}/{r['s1_regime']}"
    print(
        f"{r['n']:>2} {r['pair']:<8} {r['entry_time'][:16]:<17} {r['live_score']:>6.3f} "
        f"{r['s1_score']:>6.3f} {r['threshold']:>5.2f} "
        f"{('APPROVE' if r['s1_would_approve'] else 'REJECT'):<11} {reg:<28} "
        f"{r['atr_ratio_live_over_s1']:>8.3f} {r['R_live']:>6.2f}"
    )

if scored:
    n_app = sum(r["s1_would_approve"] for r in scored)
    print(f"\nscored {len(scored)} of {len(rows)} (S1 price/regime data ends 2026-07-24 20:00)")
    print(f"S1 champion would APPROVE {n_app} of {len(scored)}  "
          f"({n_app / len(scored):.1%})   -- live approved 100%")
    print(f"mean live score {sum(r['live_score'] for r in scored) / len(scored):.4f}  "
          f"vs  mean S1 score {sum(r['s1_score'] for r in scored) / len(scored):.4f}")
    agree = sum(r["regime_agrees"] for r in scored)
    print(f"regime label agrees on {agree} of {len(scored)}")

json.dump(
    {
        "artifact": "system1-rescore-of-computer2-live-signals",
        "champion_model_sha256": "250fab25865fb4325c19ecfa8c5b7caa291fccaf1102163f8c2a7dde95ed1b48",
        "note": (
            "Each live signal re-scored through the shipped champion using the "
            "point-in-time causal regime bar from System 1's own fact_market_regime_v2 "
            "(same backward-asof join rule as training). S1 market data ends "
            "2026-07-24 20:00 UTC, so later trades cannot be scored."
        ),
        "trades": rows,
    },
    open(os.path.join(HERE, "live-signal-rescore.json"), "w"),
    indent=2,
)
print("\nwrote live-signal-rescore.json")
