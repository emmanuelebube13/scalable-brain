"""Rank every registered strategy on pooled OOS trades — the selection report.

This is what a human reads before designating a strategy. It exists because the
composite score alone has twice pointed at something that was not real:

* `demark_fractal_breakout` looked like the fleet's only passing cell until the
  pip size turned out to be hardcoded to EUR_USD (100x too small on USD_JPY).
* `nnfx_backtrader` passes pooled while passing 0 of 5 cells, on 113 trades whose
  best cell holds 16.

So alongside the gate metrics this reports the three things that caught those:

1. **A bootstrap CI on mean R** — a point estimate over ~100 trades decides nothing.
2. **Dispersion** — how many pairs, and what share of trades sits in the largest.
   A pooled pass concentrated in one pair is a concentration artifact.
3. **Tail dependence** — total R with the top 3 winners removed. If an edge
   evaporates when three trades go, it is a lottery ticket, not an edge.

Metrics come from ``system1.attribution.metrics`` and thresholds from
``vetting.gates`` — imported, never restated, so this cannot drift into a softer
notion of "good" than the live path uses.

    python -m src.vetting.rank_all
    python -m src.vetting.rank_all --min-trades 50
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from sqlalchemy import text

from src.common.db import get_engine
from src.attribution import attribute as attr
from src.attribution import metrics as M
from src.vetting.gates import GATES, composite_score, evaluate_gates
from src.vetting.vet import INTEGRITY_DISQUALIFIED

OUT_DIR = Path(__file__).resolve().parents[2] / "results" / "reports"


def load() -> pd.DataFrame:
    """All trades via the governed loader, plus pair and strategy names.

    Uses ``attribute._load_trades`` rather than a bespoke query so the is_oos/fold_id
    semantics are the ones the live path uses, including its fail-safe behaviour on an
    un-migrated database.
    """
    eng = get_engine()
    trades = attr._load_trades(eng)
    with eng.connect() as c:
        dims = pd.read_sql(
            text(
                "SELECT s.strategy_id, s.strategy_name, s.strategy_key FROM dim_strategy s"
            ),
            c,
        )
        assets = pd.read_sql(text("SELECT asset_id, symbol AS pair FROM dim_asset"), c)
    return trades.merge(dims, on="strategy_id", how="left").merge(
        assets, on="asset_id", how="left"
    )


def bootstrap_mean_ci(r: np.ndarray, n_boot: int = 4000, seed: int = 17):
    if r.size < 20:
        return None
    rng = np.random.default_rng(seed)
    means = np.array(
        [rng.choice(r, r.size, replace=True).mean() for _ in range(n_boot)]
    )
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def score_strategy(g: pd.DataFrame) -> Dict[str, Any]:
    # Metrics come from the GOVERNED function, not a local reimplementation.
    #
    # A hand-rolled version of this computed oos_months as the calendar span
    # (max - min), which is NOT the definition. FIX-S1-002 defines it as the union
    # span of the walk-forward OOS windows the cell actually traded in. The calendar
    # span inflated nnfx_backtrader from 46.35 to 82.4 months and made it appear to
    # clear the 60-month gate when it does not. Two implementations of an OOS
    # measure is how OOS stops meaning anything.
    oos = g[g["is_oos"] == True]  # noqa: E712 - pandas mask
    if oos.empty:
        return None
    gran = str(oos["granularity"].mode().iat[0])
    folds = attr._folds_by_granularity(oos).get(gran, {})
    cell = attr._oos_cell_metrics(oos, folds)
    r = oos["r_multiple"].to_numpy(dtype=float)
    g = oos
    try:
        passed, failures = evaluate_gates(cell)
    except Exception as exc:  # a metric the gates need is missing
        passed, failures = False, [f"gate evaluation failed: {exc}"]

    ci = bootstrap_mean_ci(r)
    per_pair = g.groupby("pair")["r_multiple"].agg(["count", "mean"])
    top_share = float(per_pair["count"].max() / per_pair["count"].sum())

    srt = np.sort(r)
    total = float(r.sum())
    without_top3 = float(srt[:-3].sum()) if r.size > 3 else 0.0

    return {
        **cell,
        "mean_r": float(r.mean()),
        "max_drawdown_r": M.max_drawdown_absolute(r),  # reporting only, in R
        "total_r": total,
        "total_r_minus_top3": without_top3,
        "tail_dependence": (
            round(1.0 - without_top3 / total, 3) if total > 0 else None
        ),
        "ci_lo": ci[0] if ci else None,
        "ci_hi": ci[1] if ci else None,
        "ci_excludes_zero": bool(ci and ci[0] > 0),
        "n_pairs": int(per_pair.shape[0]),
        "largest_pair_share": round(top_share, 3),
        "passed": passed,
        "failures": failures,
        "composite": composite_score(cell),
    }


def build(min_trades: int) -> Dict[str, Any]:
    df = load()
    rows: List[Dict[str, Any]] = []
    for (sid, name, key), g in df.groupby(
        ["strategy_id", "strategy_name", "strategy_key"], dropna=False
    ):
        scored = score_strategy(g)
        if scored is None:
            continue  # no OOS trades — nothing the gates can be evaluated on
        rec = {"strategy_id": int(sid), "strategy_name": name, "strategy_key": key}
        rec.update(scored)
        rec["integrity_disqualified"] = int(sid) in INTEGRITY_DISQUALIFIED
        rec["eligible"] = (
            rec["trade_count"] >= min_trades and not rec["integrity_disqualified"]
        )
        rows.append(rec)

    rows.sort(key=lambda x: (-x["composite"], -x["trade_count"]))
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "gates": GATES,
        "min_trades": min_trades,
        "n_strategies": len(rows),
        "n_passed": sum(1 for r in rows if r["passed"]),
        "n_ci_clear": sum(1 for r in rows if r["ci_excludes_zero"]),
        "strategies": rows,
    }


def render(rep: Dict[str, Any]) -> str:
    L = [
        "# Strategy ranking — pooled OOS trades",
        "",
        f"Generated {rep['generated_at_utc']} · {rep['n_strategies']} strategies with OOS trades",
        f"· **{rep['n_passed']} pass every gate** · {rep['n_ci_clear']} have a mean-R CI clear of zero",
        "",
        "`tail` = share of total R that disappears when the top 3 winners are removed. "
        "`maxPair` = share of trades in the largest pair. Both are here because the "
        "composite score alone has twice pointed at something that was not real.",
        "",
        "| # | strategy | n | meanR | 95% CI | PF | Sharpe | MaxDD | tail | maxPair | pairs | gates |",
        "|--:|---|--:|--:|---|--:|--:|--:|--:|--:|--:|---|",
    ]
    for i, r in enumerate(rep["strategies"], 1):
        ci = (
            f"[{r['ci_lo']:+.3f}, {r['ci_hi']:+.3f}]"
            if r["ci_lo"] is not None
            else "n/a"
        )
        tail = (
            f"{r['tail_dependence']:.0%}" if r["tail_dependence"] is not None else "—"
        )
        gates = "**PASS**" if r["passed"] else f"{len(r['failures'])} fail"
        if r["integrity_disqualified"]:
            gates = "DISQUALIFIED"
        L.append(
            f"| {i} | {r['strategy_key'] or r['strategy_name']} | {r['trade_count']} | "
            f"{r['mean_r']:+.4f} | {ci} | {r['profit_factor']:.2f} | {r['sharpe']:.2f} | "
            f"{r['max_drawdown']:.1%} | {tail} | {r['largest_pair_share']:.0%} | "
            f"{r['n_pairs']} | {gates} |"
        )
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-trades", type=int, default=30)
    args = ap.parse_args(argv)
    rep = build(args.min_trades)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (OUT_DIR / f"strategy_ranking_{stamp}.json").write_text(
        json.dumps(rep, indent=2, default=str)
    )
    (OUT_DIR / "STRATEGY_RANKING.md").write_text(render(rep))
    print(render(rep))
    print(f"-> {OUT_DIR}/STRATEGY_RANKING.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
