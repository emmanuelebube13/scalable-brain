"""FIX-S1-013 — audit every qualified strategy for look-ahead.

Method (the repo's own, from src/layer0/strategies/contract.py::assert_no_lookahead):
a trailing-only strategy's signal at bar t is identical whether or not bars after t
exist. Compute signals on the full frame, then recompute from a prefix truncated at t.
Same start, different end -- so any disagreement isolates look-ahead exactly.

CRITICAL: probe bars where the strategy ACTUALLY FIRES. These strategies are rare
(strategy 10 fires 352 times in 130,299 bars); a quiet window agrees trivially and is
not evidence of absence. An earlier probe of a quiet window nearly produced a false
"clean" verdict.
"""

from __future__ import annotations

import json
import os
import sys
import traceback

import numpy as np
import pandas as pd
from sqlalchemy import text

from src.common.db import get_engine
from src.layer0.strategies import (
    RangeBollinger_Aggressive,
    RangeBollinger_H1_Only,
    RangeBollinger_H4_Only,
    RangeStochastic_Divergence,
    TrendDonchian_H1_Only,
    TrendDonchian_H4_Only,
    TrendDonchian_VCP,
    TrendEMAADX_H1_Only,
    TrendEMAADX_H4_Only,
    TrendEMAADX_MultiTF,
)

HERE = os.path.dirname(os.path.abspath(__file__))

# dim_strategy id -> (name, class, granularity it was qualified on)
STRATEGIES = [
    (1, "Trend_EMA_ADX_H1", TrendEMAADX_H1_Only, "H1"),
    (2, "Trend_EMA_ADX_H4", TrendEMAADX_H4_Only, "H4"),
    (3, "Trend_EMA_ADX_MultiTF", TrendEMAADX_MultiTF, "H1"),
    (4, "Trend_Donchian_H1", TrendDonchian_H1_Only, "H1"),
    (5, "Trend_Donchian_H4", TrendDonchian_H4_Only, "H4"),
    (6, "Trend_Donchian_VCP", TrendDonchian_VCP, "H1"),
    (7, "Range_Bollinger_H1", RangeBollinger_H1_Only, "H1"),
    (8, "Range_Bollinger_H4", RangeBollinger_H4_Only, "H4"),
    (9, "Range_Bollinger_Aggressive", RangeBollinger_Aggressive, "H1"),
    (10, "Range_Stochastic_Divergence", RangeStochastic_Divergence, "H1"),
]

N_BARS = 20000
N_PROBE = 20
ASSET_ID, ASSET = 1, "EUR_USD"


def load(gran: str) -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql(
            text(
                'SELECT "timestamp", "Open", high AS "High", low AS "Low", "Close" '
                "FROM fact_market_prices WHERE asset_id=:a AND granularity=:g "
                'ORDER BY "timestamp" ASC LIMIT :lim'
            ),
            conn,
            params={"a": ASSET_ID, "g": gran, "lim": N_BARS},
        )


def signals(strat, df: pd.DataFrame, gran: str) -> pd.Series:
    return strat.generate_signals(
        strat.calculate_indicators(df.copy(), ASSET, gran), ASSET, gran
    )


frames = {g: load(g) for g in ("H1", "H4")}
results = []

for sid, name, cls, gran in STRATEGIES:
    rec = {"strategy_id": sid, "name": name, "granularity": gran}
    try:
        df = frames[gran]
        strat = cls()
        full = signals(strat, df, gran)
        fire = [int(i) for i in full[full != 0].index if i > 300]
        rec["total_signals_full_series"] = int(len(full[full != 0]))
        if not fire:
            rec["verdict"] = "NO SIGNALS — cannot test"
            results.append(rec)
            print(f"{sid:>2} {name:<28} NO SIGNALS on {gran}")
            continue

        # sample evenly across history rather than taking the first N
        idx = np.linspace(0, len(fire) - 1, min(N_PROBE, len(fire))).astype(int)
        probe = [fire[i] for i in sorted(set(idx))]

        differ, examples = 0, []
        for t in probe:
            live = signals(strat, df.iloc[: t + 1], gran)
            a, b = int(full.iloc[t]), int(live.iloc[t])
            if a != b:
                differ += 1
                if len(examples) < 3:
                    examples.append(
                        {
                            "timestamp": str(df["timestamp"].iloc[t]),
                            "with_future": a,
                            "live": b,
                        }
                    )
        rec.update(
            {
                "signal_bars_probed": len(probe),
                "signal_bars_that_differ": differ,
                "pct_differ": round(differ / len(probe), 4),
                "examples": examples,
                "verdict": (
                    "LOOK-AHEAD — emits NO signals live"
                    if differ == len(probe)
                    else ("LOOK-AHEAD" if differ else "clean")
                ),
            }
        )
        flag = "🚨" if differ else "✅"
        print(
            f"{sid:>2} {name:<28} {gran}  probed {len(probe):>2}  "
            f"differ {differ:>2}  {flag} {rec['verdict']}"
        )
    except Exception as e:  # noqa: BLE001
        rec.update({"verdict": "ERROR", "error": f"{type(e).__name__}: {e}"})
        print(f"{sid:>2} {name:<28} ERROR {type(e).__name__}: {e}")
        traceback.print_exc(file=sys.stderr)
    results.append(rec)

contaminated = [
    r for r in results if str(r.get("verdict", "")).startswith("LOOK-AHEAD")
]
clean = [r for r in results if r.get("verdict") == "clean"]

print(f"\n{'='*70}")
print(
    f"CONTAMINATED : {len(contaminated)} of {len(results)}  "
    f"-> {[r['strategy_id'] for r in contaminated]}"
)
print(
    f"CLEAN        : {len(clean)} of {len(results)}  "
    f"-> {[r['strategy_id'] for r in clean]}"
)
other = [r for r in results if r not in contaminated and r not in clean]
if other:
    print(f"UNTESTED     : {[(r['strategy_id'], r['verdict']) for r in other]}")

json.dump(
    {
        "artifact": "system1-lookahead-audit-all-strategies",
        "fix": "FIX-S1-013",
        "method": (
            "signal at bar t recomputed from a prefix truncated at t, compared against "
            "the full-series value. Probes only bars where the strategy fires, sampled "
            "evenly across history."
        ),
        "instrument": f"{ASSET} (first {N_BARS} bars per granularity)",
        "contaminated_strategy_ids": [r["strategy_id"] for r in contaminated],
        "clean_strategy_ids": [r["strategy_id"] for r in clean],
        "results": results,
    },
    open(os.path.join(HERE, "lookahead-audit.json"), "w"),
    indent=2,
)
print("\nwrote lookahead-audit.json")
