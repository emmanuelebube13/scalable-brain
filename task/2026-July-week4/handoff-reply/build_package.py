"""Build the S1 → Computer-2 handoff reply package (2026-08-01).

Produces, into this directory:
  gatekeeper-feature-contract.json   exact column order, dtypes, categorical vocabularies
  gatekeeper-golden-vectors.json     real training rows + the score the champion MUST return
  gatekeeper-score-distribution.json what correct inference looks like on 134,407 rows
  oos-r-multiples-strat10-td-h1.json the backtest series System 2 asked for (ask #2)
"""
from __future__ import annotations

import json
import os

import joblib
import numpy as np
import pandas as pd

from src.gatekeeper import train as T

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))


def out(name: str, obj) -> None:
    p = os.path.join(HERE, name)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, sort_keys=False)
    print(f"wrote {name}")


model = joblib.load(os.path.join(ROOT, "models", "champion_model.pkl"))
pre = joblib.load(os.path.join(ROOT, "models", "champion_preprocessor.pkl"))
man = json.load(open(os.path.join(ROOT, "models", "champion_manifest.json")))
cols = man["features"]
th = man["dynamic_thresholds"]

frame = T._derive_features(T.build_frame())
X = frame[cols]
scores = model.predict_proba(pre.transform(X))[:, 1]
thr = frame["regime_causal"].map(lambda r: th.get(r, th["fallback"])).to_numpy()

# ---------------------------------------------------------------- contract
oh = pre.named_transformers_["cat"]
sc = pre.named_transformers_["num"]

contract = {
    "artifact": "system1-gatekeeper-feature-contract",
    "champion_bundle": "models/gatekeeper/2026-07-05T17-43-09Z-656f09e2/",
    "champion_model_sha256": "250fab25865fb4325c19ecfa8c5b7caa291fccaf1102163f8c2a7dde95ed1b48",
    "champion_preprocessor_sha256": "a50f5ac770477124d993635eb245823cff1b8d75ecd058984b926407304db9fb",
    "schema_version": man["schema_version"],
    "feature_set_version": man["feature_set_version"],
    "regime_model_version": man["regime_model_version"],
    "how_to_score": [
        "Build a pandas DataFrame with EXACTLY the 12 columns in `column_order`.",
        "Pass the DataFrame (NOT a numpy array) to champion_preprocessor.pkl .transform().",
        "ColumnTransformer selects by COLUMN NAME, so a DataFrame is required; a bare",
        "array is selected positionally and will silently mis-map the one-hot block.",
        "Score = champion_model.predict_proba(Xt)[:, 1]  -- column 1, not column 0.",
        "Approve if score >= dynamic_thresholds[regime_causal], else the 'fallback' key.",
    ],
    "column_order": cols,
    "numeric_columns": T.NUMERIC_DERIVED,
    "categorical_columns": T.CATEGORICAL,
    "dtypes": {
        **{c: "float64" for c in T.NUMERIC_DERIVED},
        **{c: "str (python string, NOT int/enum)" for c in T.CATEGORICAL},
    },
    "derived_feature_formulas": {
        "volatility_regime": "float(prob_causal_high_vol > 0.3)",
        "trending_strength": "prob_causal_trending_up + prob_causal_trending_down",
        "adx_over_atr": "adx_value / atr_value  if atr_value > 1e-8 else 0.0",
    },
    "units": {
        "atr_value": "PRICE units of the instrument, NOT pips. EUR_USD ATR ~ 0.0008.",
        "adx_value": "conventional ADX, 0-100 scale.",
        "prob_causal_*": "probabilities in [0,1], NOT percentages. They sum to ~1.0.",
    },
    "categorical_vocabularies": {
        c: sorted(v.tolist()) for c, v in zip(T.CATEGORICAL, oh.categories_)
    },
    "unknown_category_behaviour": (
        "OneHotEncoder(handle_unknown='ignore'): a value outside the vocabulary above "
        "encodes as ALL ZEROS and raises NO error. strategy_id must be the STRING '10', "
        "not the integer 10. regime_causal must be exactly 'Trending-Down' (hyphen, "
        "title case), not 'TRENDING_DOWN'."
    ),
    "dynamic_thresholds": th,
    "scaler_reference": {
        "note": "StandardScaler means/scales the champion was fitted with, in "
                "numeric_columns order. Use these to sanity-check your live feature "
                "magnitudes: a live value many sigma from `mean` indicates unit skew.",
        "mean": [float(x) for x in sc.mean_],
        "scale": [float(x) for x in sc.scale_],
    },
}
out("gatekeeper-feature-contract.json", contract)

# ---------------------------------------------------------------- golden vectors
# Pick real rows spanning the regimes, biased to what System 2 actually trades.
rng = np.random.default_rng(42)
picks: list[int] = []
for regime in ["Trending-Down", "Ranging", "Trending-Up", "High-Vol"]:
    idx = frame.index[
        (frame["regime_causal"] == regime) & (frame["strategy_id"] == "10")
    ].to_numpy()
    if len(idx) == 0:
        idx = frame.index[frame["regime_causal"] == regime].to_numpy()
    picks += list(rng.choice(idx, size=min(3, len(idx)), replace=False))

vectors = []
for i in picks:
    row = frame.loc[i]
    vectors.append(
        {
            "input": {
                **{c: float(row[c]) for c in T.NUMERIC_DERIVED},
                **{c: str(row[c]) for c in T.CATEGORICAL},
            },
            "expected_model_score": round(float(scores[frame.index.get_loc(i)]), 10),
            "threshold_applied": float(th.get(row["regime_causal"], th["fallback"])),
            "expected_approved": bool(
                scores[frame.index.get_loc(i)]
                >= th.get(row["regime_causal"], th["fallback"])
            ),
        }
    )

out(
    "gatekeeper-golden-vectors.json",
    {
        "artifact": "system1-gatekeeper-golden-vectors",
        "purpose": (
            "Feed each `input` through YOUR live inference path. If your pipeline is "
            "correct you MUST reproduce `expected_model_score` to ~1e-9. Any deviation "
            "localises the skew before you ever look at market data."
        ),
        "champion_model_sha256": contract["champion_model_sha256"],
        "column_order": cols,
        "vectors": vectors,
    },
)

# ---------------------------------------------------------------- distribution
per_regime = {}
for r, g in frame.groupby("regime_causal"):
    pos = [frame.index.get_loc(i) for i in g.index]
    s = scores[pos]
    t = th.get(r, th["fallback"])
    per_regime[r] = {
        "n": int(len(g)),
        "threshold": float(t),
        "mean_score": round(float(s.mean()), 6),
        "approval_rate": round(float((s >= t).mean()), 6),
    }

dist = {
    "artifact": "system1-gatekeeper-score-distribution",
    "measured_on": "System-1's own 134,407-row training frame, 2026-08-01",
    "using": "the byte-identical champion System 2 has (sha256 250fab25...)",
    "n": int(len(frame)),
    "mean_score": round(float(scores.mean()), 6),
    "median_score": round(float(np.median(scores)), 6),
    "min_score": round(float(scores.min()), 6),
    "max_score": round(float(scores.max()), 6),
    "overall_approval_rate": round(float((scores >= thr).mean()), 6),
    "percentiles": {
        f"p{p}": round(float(np.percentile(scores, p)), 6)
        for p in [1, 5, 25, 50, 75, 90, 95, 99, 99.9]
    },
    "fraction_at_or_above_live_mean_0_759": round(float((scores >= 0.759).mean()), 8),
    "count_at_or_above_live_mean_0_759": int((scores >= 0.759).sum()),
    "per_regime": per_regime,
    "interpretation": (
        "This model's scores are centred on 0.495 and CAP at 0.8114 across 134,407 rows. "
        "A live mean of 0.759 sits at our 99.63rd percentile. No input corruption we "
        "could inject (unit skew, unknown categories, unscaled numerics, permuted "
        "columns, NaNs, zeros, probs on 0-100) moved the mean outside 0.48-0.51 -- every "
        "one LOWERED approval. A mean of 0.759 is not reachable from this artifact."
    ),
}
out("gatekeeper-score-distribution.json", dist)

# ---------------------------------------------------------------- ask #2
tr = json.load(
    open(os.path.join(ROOT, "results", "state", "analytics_staging", "trade_returns.json"))
)
cells = [
    c
    for c in tr["cells"]
    if c["strategy_id"] == "10"
    and c["regime"] == "Trending-Down"
    and c["granularity"] == "H1"
]
enriched = []
for c in cells:
    r = np.array(c["r_multiples"], dtype=float)
    enriched.append(
        {
            **c,
            "stats": {
                "n": int(len(r)),
                "mean_r": round(float(r.mean()), 6),
                "median_r": round(float(np.median(r)), 6),
                "win_rate": round(float((r > 0).mean()), 6),
                "sum_r": round(float(r.sum()), 6),
                "min_r": round(float(r.min()), 6),
                "max_r": round(float(r.max()), 6),
            },
        }
    )
out(
    "oos-r-multiples-strat10-td-h1.json",
    {
        "artifact": "system1-oos-r-multiples",
        "answers": "Computer-2 handoff ask #2",
        "source_bundle": "system1/analytics/2026-07-29T11-46-49Z-f3014649/",
        "oos_only": tr["oos_only"],
        "definition": (
            "r_multiple = realised return / initial risk, measured on OOS walk-forward "
            "trades only. Risk denominator is the backtest's own 1.0x-ATR stop, so these "
            "are directly comparable to your live R AFTER your 1.5x sizing correction."
        ),
        "cells": enriched,
    },
)
print("\ndone")
