"""R3 steps 5-6 — the blind-vs-aware comparison report.

Reads `fact_regime_trial_outcomes` for one run and reports, per strategy and per
label source, what the regime gate did to the outcome distribution.

Three things this module deliberately does:

* **It reuses the metrics.** ``system1.attribution.metrics`` is imported rather than
  reimplemented — a fresh drawdown implementation once reported 1650% in this repo.
* **It reports intervals, not point estimates.** With cells of 30-300 trades the
  interval on a difference in mean R is wide enough to change the decision, so a
  bare "aware is better by 0.04R" is not a finding.
* **It states how many comparisons were run.** Roughly 48 strategies x 2 label
  sources means several will look good by chance; a reader cannot weigh a p-value
  without the denominator.

    python -m src.regime_aware.v2.report            # latest run
    python -m src.regime_aware.v2.report <run_id>
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence

import numpy as np
import pandas as pd
from sqlalchemy import text

from src.common.db import get_engine
from src.attribution import metrics as M

RESULTS_DIR = Path(__file__).resolve().parents[3] / "results" / "regime_aware" / "R3"

#: Below this many OOS trades a cell is reported as unmeasurable rather than scored.
#: Gating is *expected* to cut trade counts — that is the intervention working — but a
#: profit factor computed from six trades is noise wearing a number's clothes.
TRADE_FLOOR = 30

#: Trades per year assumed when annualising Sharpe, by primary granularity.
_TPY = {"H1": 1500.0, "H4": 400.0, "D1": 120.0, "W1": 30.0}


def load_run(run_id: str | None = None) -> pd.DataFrame:
    eng = get_engine()
    with eng.connect() as conn:
        if run_id is None:
            run_id = conn.execute(
                text(
                    "SELECT run_id FROM fact_regime_trial_outcomes "
                    'ORDER BY "timestamp" DESC LIMIT 1'
                )
            ).scalar()
            if run_id is None:
                raise SystemExit("fact_regime_trial_outcomes is empty — run the runner first")
        df = pd.read_sql(
            text(
                # OOS trades only. Every gate in this system is defined on out-of-sample
                # trades (FIX-S1-002); pooling in-sample with out-of-sample inflates the
                # result and is not comparable with any other number we publish. An
                # earlier version of this query omitted the filter.
                "SELECT o.*, a.symbol AS pair FROM fact_regime_trial_outcomes o "
                "JOIN dim_asset a ON a.asset_id = o.asset_id "
                "WHERE o.run_id = :rid AND o.is_oos = true"
            ),
            conn,
            params={"rid": run_id},
        )
    df.attrs["run_id"] = run_id
    return df


def score(r: Sequence[float], granularity: str) -> Dict[str, Any]:
    r = [float(x) for x in r]
    if not r:
        return {"n": 0}
    return {
        "n": len(r),
        # NOT M.avg_r — that returns avg_win/avg_loss, a RATIO, not the mean of the
        # series. Reporting it as "mean R" produced implausible values like +1.89 in the
        # first run of this report. The delta and its CI were always computed from raw
        # numpy means and so were unaffected; only these display columns were wrong.
        "mean_r": float(np.mean(r)),
        "win_rate": M.win_rate([1 if x > 0 else 0 for x in r]),
        "profit_factor": M.profit_factor(r),
        "sharpe": M.annualized_sharpe(r, _TPY.get(granularity, 400.0)),
        "max_drawdown": M.max_drawdown_absolute(r),
    }


def diff_ci(
    blind: Sequence[float],
    aware: Sequence[float],
    n_boot: int = 2000,
    seed: int = 42,
) -> Dict[str, float] | None:
    """Percentile bootstrap interval on (mean R aware - mean R blind).

    The two arms are resampled independently because they are not paired: the gate
    removes trades, so there is no one-to-one correspondence to preserve.
    """
    if len(blind) < 10 or len(aware) < 10:
        return None
    rng = np.random.default_rng(seed)
    b = np.asarray(blind, dtype=float)
    a = np.asarray(aware, dtype=float)
    draws = np.empty(n_boot, dtype=float)
    for i in range(n_boot):
        draws[i] = rng.choice(a, a.size, replace=True).mean() - rng.choice(
            b, b.size, replace=True
        ).mean()
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return {"delta_mean_r": float(a.mean() - b.mean()), "lo": float(lo), "hi": float(hi)}


def build(df: pd.DataFrame) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "run_id": df.attrs.get("run_id"),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "trade_floor": TRADE_FLOOR,
        "strategies": [],
    }
    n_comparisons = 0
    n_unmeasurable = 0
    favourable: List[Dict[str, Any]] = []

    for (sid, source), grp in df.groupby(["strategy_key", "regime_source"]):
        gran = str(grp["granularity"].iloc[0])
        blind = grp.loc[grp["arm"] == "blind", "r_multiple"].tolist()
        aware = grp.loc[grp["arm"] == "aware", "r_multiple"].tolist()
        n_comparisons += 1

        rec: Dict[str, Any] = {
            "strategy_key": sid,
            "regime_source": source,
            "granularity": gran,
            "blind": score(blind, gran),
            "aware": score(aware, gran),
            "delta": diff_ci(blind, aware),
        }

        if len(aware) < TRADE_FLOOR:
            rec["verdict"] = "unmeasurable"
            rec["reason"] = f"aware arm has {len(aware)} OOS trades < floor {TRADE_FLOOR}"
            n_unmeasurable += 1
        else:
            better = rec["delta"] is not None and rec["delta"]["delta_mean_r"] > 0
            rec["verdict"] = "aware_better" if better else "aware_not_better"
            if better:
                # Per-pair breakdown is mandatory for anything that looks favourable:
                # an effect that lives in one pair is the concentration artifact, not an edge.
                per_pair = {}
                for pair, sub in grp.groupby("pair"):
                    pb = sub.loc[sub["arm"] == "blind", "r_multiple"].tolist()
                    pa = sub.loc[sub["arm"] == "aware", "r_multiple"].tolist()
                    per_pair[str(pair)] = {
                        "blind_n": len(pb),
                        "aware_n": len(pa),
                        "blind_mean_r": float(np.mean(pb)) if pb else None,
                        "aware_mean_r": float(np.mean(pa)) if pa else None,
                    }
                rec["per_pair"] = per_pair
                shares = {p: v["aware_n"] for p, v in per_pair.items()}
                total = sum(shares.values()) or 1
                top_pair, top_n = max(shares.items(), key=lambda kv: kv[1])
                rec["concentration"] = {
                    "top_pair": top_pair,
                    "share": round(top_n / total, 3),
                    "flag": (top_n / total) > 0.8,
                }
                favourable.append(rec)

        out["strategies"].append(rec)

    ci_clear = [
        r for r in favourable
        if r["delta"] is not None and r["delta"]["lo"] > 0
    ]
    out["summary"] = {
        "n_comparisons": n_comparisons,
        "n_unmeasurable": n_unmeasurable,
        "n_aware_better_point_estimate": len(favourable),
        "n_aware_better_ci_excludes_zero": len(ci_clear),
        "n_concentration_flagged": sum(
            1 for r in favourable if r.get("concentration", {}).get("flag")
        ),
    }
    return out


def render(rep: Dict[str, Any]) -> str:
    s = rep["summary"]
    lines = [
        "# R3 — blind vs aware comparison",
        "",
        f"**run_id** `{rep['run_id']}` · generated {rep['generated_at_utc']}",
        "",
        f"- comparisons run: **{s['n_comparisons']}** (strategy x label source)",
        f"- unmeasurable (aware arm under the {rep['trade_floor']}-trade floor): "
        f"**{s['n_unmeasurable']}**",
        f"- aware better on the point estimate: **{s['n_aware_better_point_estimate']}**",
        f"- aware better with a 95% CI clear of zero: "
        f"**{s['n_aware_better_ci_excludes_zero']}**",
        f"- of the favourable, concentration-flagged (>80% of aware trades in one pair): "
        f"**{s['n_concentration_flagged']}**",
        "",
        "With this many comparisons, several will look favourable by chance. The column "
        "that matters is the CI-clear-of-zero count, and then only after the per-pair "
        "breakdown has been read.",
        "",
        "| strategy | source | gran | blind n | aware n | blind meanR | aware meanR | "
        "delta [95% CI] | verdict |",
        "|---|---|---|--:|--:|--:|--:|---|---|",
    ]
    for r in sorted(rep["strategies"], key=lambda x: x["strategy_key"]):
        d = r["delta"]
        dtxt = (
            f"{d['delta_mean_r']:+.4f} [{d['lo']:+.4f}, {d['hi']:+.4f}]" if d else "n/a"
        )
        bm = r["blind"].get("mean_r")
        am = r["aware"].get("mean_r")
        lines.append(
            f"| {r['strategy_key']} | {r['regime_source']} | {r['granularity']} | "
            f"{r['blind'].get('n', 0)} | {r['aware'].get('n', 0)} | "
            f"{bm:+.4f} | {am:+.4f} | {dtxt} | {r['verdict']} |"
            if bm is not None and am is not None
            else f"| {r['strategy_key']} | {r['regime_source']} | {r['granularity']} | "
            f"{r['blind'].get('n', 0)} | {r['aware'].get('n', 0)} | — | — | {dtxt} | "
            f"{r['verdict']} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    run_id = argv[0] if argv else None
    df = load_run(run_id)
    rep = build(df)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "comparison.json").write_text(json.dumps(rep, indent=2, default=str))
    (RESULTS_DIR / "COMPARISON.md").write_text(render(rep))
    print(render(rep))
    print(f"-> {RESULTS_DIR}/COMPARISON.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
