"""Principal-Quant risk audit — stress-test the edge behind the summary scalars.

A pooled Profit Factor is a scalar that hides how it was earned. This tool asks the
questions a scalar cannot answer: was the edge one lucky trade, one lucky six months, or
something structural that repeats? It reads the JSON written by ``v2_harness`` and reports
per strategy.

Checks (mirroring the audit brief):

1. OUTLIER & WINSORIZATION — recompute with the top 2% winners and bottom 1% losers
   removed. PF < 1.10 after that => ``OUTLIER_DEPENDENT``. Mean-R vs median-R divergence
   distinguishes single-event harvesting from a structural edge.
2. TEMPORAL & REGIME CONSISTENCY — share of walk-forward folds with positive net R
   (bar: >= 65%). Any single fold carrying > 40% of gross profit => ``REGIME_CONCENTRATION``.
3. DRAWDOWN & FAT TAILS — longest underwater stretch as a share of the series, and the
   three worst consecutive-loss clusters.
4. INTRABAR PATH FIDELITY — native vs H1-resolved. Sharpe drop > 0.4 or PF drop > 0.3 =>
   ``INTRABAR_EXECUTION_BIAS``. Requires a run WITHOUT ``--no-h1``.
5. VERDICT — ROBUST | MARGINAL | FRAGILE_OUTLIER_DRIVEN | REGIME_CONCENTRATED | REJECT.

**What the stored data cannot support, and is therefore not faked:**

* Per-trade entry timestamps are not persisted — only fold windows. So "60-day calendar
  cluster" concentration is approximated by **fold-level** concentration (each fold is a
  6-month OOS window), and drawdown duration is measured in **trades**, not calendar days.
  Both are labelled as such in the output. Adding ``entry_time`` to the per-trade record in
  ``v2_harness._fold_attribute`` would make the calendar-exact versions possible.

Usage:
    python task/2026-August-week1/wave2/risk_audit.py            # every strategy with a report
    python task/2026-August-week1/wave2/risk_audit.py <id> ...   # named strategies
    python task/2026-August-week1/wave2/risk_audit.py --json     # machine-readable
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

ROOT = Path("/home/emmanuel/Documents/Scalable_Brain/scalable-brain")
sys.path.insert(0, str(ROOT))

from src.attribution import metrics as M  # noqa: E402

RESULTS = ROOT / "results" / "research"

# Thresholds from the audit brief.
WINSOR_TOP_PCT = 0.02
WINSOR_BOT_PCT = 0.01
PF_FLOOR_AFTER_WINSOR = 1.10
FOLD_POSITIVE_SHARE_BAR = 0.65
SINGLE_FOLD_PROFIT_SHARE_BAR = 0.40
UNDERWATER_SHARE_BAR = 0.50
SHARPE_DROP_BAR = 0.4
PF_DROP_BAR = 0.3


def _latest_report(sid: str) -> Optional[Path]:
    files = sorted((RESULTS / sid).glob("v2_evaluation_*.json"))
    return files[-1] if files else None


def _pooled(cells: Sequence[Dict[str, Any]], resolution: str) -> Tuple[List[float], List[Dict]]:
    """Raw OOS r-multiples and folds across cells at one resolution."""
    rs: List[float] = []
    folds: List[Dict] = []
    for cell in cells:
        res = cell["resolutions"].get(resolution)
        if not res:
            continue
        rs.extend(res.get("r_multiples", []))
        folds.extend(res.get("per_fold", []))
    return rs, folds


def _months(folds: Sequence[Dict]) -> float:
    import pandas as pd

    spans = {(f["oos_start"], f["oos_end"]) for f in folds}
    days = sum((pd.Timestamp(e) - pd.Timestamp(s)).days for s, e in spans)
    return days / 30.44


def _metrics(rs: Sequence[float], months: float) -> Dict[str, float]:
    """Recompute the gate metrics exactly as the harness does, so a winsorized
    series is comparable to the reported one rather than to a different formula."""
    n = len(rs)
    if n == 0:
        return {"profit_factor": 0.0, "sharpe": 0.0, "max_drawdown": 1.0, "win_rate": 0.0}
    years = max(months / 12.0, 1e-9)
    sharpe = M.annualized_sharpe(rs, n / years)
    return {
        "profit_factor": float(M.profit_factor(rs)),
        "sharpe": 0.0 if sharpe != sharpe else float(sharpe),
        "max_drawdown": float(M.max_drawdown(rs)),
        "win_rate": float(M.win_rate([1 if r > 0 else 0 for r in rs])),
    }


def _winsorize(rs: Sequence[float]) -> List[float]:
    """Drop the largest winners (top 2%) and the largest losers (bottom 1%).

    Counts are computed on the WHOLE series, per the brief, and at least one trade
    is removed from each tail whenever the series is long enough for that to mean
    anything — otherwise a 40-trade sample would round to zero and the check would
    silently pass."""
    r = np.asarray(rs, dtype="float64")
    n = len(r)
    if n < 20:
        return list(r)
    n_top = max(1, int(round(n * WINSOR_TOP_PCT)))
    n_bot = max(1, int(round(n * WINSOR_BOT_PCT)))
    order = np.argsort(r)  # ascending
    drop = set(order[:n_bot].tolist()) | set(order[-n_top:].tolist())
    return [float(v) for i, v in enumerate(r) if i not in drop]


def _fold_net_r(folds: Sequence[Dict]) -> List[Tuple[str, float, int]]:
    """(label, net R, n_trades) per fold, summed across pairs sharing a fold id."""
    agg: Dict[Any, Dict[str, Any]] = {}
    for f in folds:
        key = (f.get("fold"), f.get("oos_start"))
        slot = agg.setdefault(
            key, {"net": 0.0, "n": 0, "start": str(f.get("oos_start"))[:10]}
        )
        slot["net"] += float(f.get("mean_r", 0.0)) * int(f.get("n_trades", 0))
        slot["n"] += int(f.get("n_trades", 0))
    return [
        (f"F{k[0]}@{v['start']}", v["net"], v["n"])
        for k, v in sorted(agg.items(), key=lambda kv: str(kv[0][1]))
    ]


def _longest_underwater(rs: Sequence[float]) -> Tuple[int, float]:
    """Longest run of trades spent below a prior equity peak, and the share of the
    series spent underwater. Measured in TRADES — timestamps are not persisted."""
    eq = np.cumsum(np.asarray(rs, dtype="float64"))
    peak = np.maximum.accumulate(eq)
    underwater = eq < peak - 1e-12
    longest = cur = 0
    for u in underwater:
        cur = cur + 1 if u else 0
        longest = max(longest, cur)
    return longest, float(underwater.mean()) if len(underwater) else 0.0


def _worst_loss_clusters(rs: Sequence[float], k: int = 3) -> List[Tuple[int, float]]:
    """The k worst runs of consecutive losing trades, as (length, total R)."""
    clusters: List[Tuple[int, float]] = []
    run_len, run_sum = 0, 0.0
    for r in list(rs) + [1.0]:  # sentinel closes a trailing run
        if r < 0:
            run_len += 1
            run_sum += r
        elif run_len:
            clusters.append((run_len, run_sum))
            run_len, run_sum = 0, 0.0
    return sorted(clusters, key=lambda c: c[1])[:k]


def audit(sid: str) -> Dict[str, Any]:
    path = _latest_report(sid)
    if path is None:
        return {"strategy_id": sid, "verdict": "NO_REPORT"}
    report = json.loads(path.read_text())
    cells = report.get("cells", [])

    rs_native, folds_native = _pooled(cells, "native")
    rs_h1, folds_h1 = _pooled(cells, "h1")
    rs = rs_h1 or rs_native  # the harness prefers H1 for the pooled verdict
    folds = folds_h1 or folds_native
    flags: List[str] = []

    out: Dict[str, Any] = {
        "strategy_id": sid,
        "report": path.name,
        "resolution_used": "h1" if rs_h1 else "native",
        "n_oos_trades": len(rs),
    }
    if not rs:
        out["verdict"] = "REJECT"
        out["rationale"] = ["no OOS trades — nothing to audit"]
        return out

    months = _months(folds)
    base = _metrics(rs, months)
    out["pooled"] = {k: round(v, 4) for k, v in base.items()}

    # -- 1. outliers ----------------------------------------------------------
    kept = _winsorize(rs)
    wins = _metrics(kept, months)
    arr = np.asarray(rs, dtype="float64")
    out["outlier"] = {
        "trades_removed": len(rs) - len(kept),
        "pf_full": round(base["profit_factor"], 4),
        "pf_winsorized": round(wins["profit_factor"], 4),
        "pf_delta": round(wins["profit_factor"] - base["profit_factor"], 4),
        "mean_r": round(float(arr.mean()), 4),
        "median_r": round(float(np.median(arr)), 4),
        "mean_minus_median": round(float(arr.mean() - np.median(arr)), 4),
        "largest_win_r": round(float(arr.max()), 4),
        "top1_share_of_gross_profit": round(
            float(arr.max() / arr[arr > 0].sum()) if (arr > 0).any() else 0.0, 4
        ),
    }
    if wins["profit_factor"] < PF_FLOOR_AFTER_WINSOR <= base["profit_factor"]:
        flags.append("OUTLIER_DEPENDENT")

    # -- 2. temporal / regime -------------------------------------------------
    per_fold = _fold_net_r(folds)
    pos = [f for f in per_fold if f[1] > 0]
    gross_pos = sum(f[1] for f in pos)
    top_fold = max(per_fold, key=lambda f: f[1]) if per_fold else ("-", 0.0, 0)
    share = (top_fold[1] / gross_pos) if gross_pos > 0 else 0.0
    out["temporal"] = {
        "n_folds": len(per_fold),
        "n_folds_positive": len(pos),
        "share_folds_positive": round(len(pos) / len(per_fold), 4) if per_fold else 0.0,
        "best_fold": top_fold[0],
        "best_fold_net_r": round(top_fold[1], 4),
        "best_fold_share_of_gross_fold_profit": round(share, 4),
        "note": "fold-level proxy; per-trade timestamps are not persisted, so a "
        "60-day calendar cluster cannot be computed exactly",
    }
    if per_fold and (len(pos) / len(per_fold)) < FOLD_POSITIVE_SHARE_BAR:
        flags.append("FOLD_INCONSISTENT")
    if share > SINGLE_FOLD_PROFIT_SHARE_BAR:
        flags.append("REGIME_CONCENTRATION")

    # -- 3. drawdown / fat tails ---------------------------------------------
    longest, uw_share = _longest_underwater(rs)
    out["drawdown"] = {
        "max_drawdown_pct_equity": round(base["max_drawdown"] * 100, 2),
        "longest_underwater_trades": longest,
        "share_of_series_underwater": round(uw_share, 4),
        "worst_3_loss_clusters": [
            {"consecutive_losses": n, "total_r": round(s, 3)}
            for n, s in _worst_loss_clusters(rs)
        ],
        "note": "underwater measured in trades, not calendar days (no timestamps stored)",
    }
    if uw_share > UNDERWATER_SHARE_BAR:
        flags.append("PERSISTENTLY_UNDERWATER")

    # -- 4. intrabar path fidelity -------------------------------------------
    if rs_h1 and rs_native:
        nat = _metrics(rs_native, _months(folds_native))
        d_sharpe = nat["sharpe"] - base["sharpe"]
        d_pf = nat["profit_factor"] - base["profit_factor"]
        out["intrabar"] = {
            "native_pf": round(nat["profit_factor"], 4),
            "h1_pf": round(base["profit_factor"], 4),
            "pf_drop_native_to_h1": round(d_pf, 4),
            "native_sharpe": round(nat["sharpe"], 4),
            "h1_sharpe": round(base["sharpe"], 4),
            "sharpe_drop_native_to_h1": round(d_sharpe, 4),
        }
        if d_sharpe > SHARPE_DROP_BAR or d_pf > PF_DROP_BAR:
            flags.append("INTRABAR_EXECUTION_BIAS")
    else:
        out["intrabar"] = {
            "status": "NOT_TESTED — report has only one resolution; re-run the "
            "harness without --no-h1 to populate this"
        }

    # -- 5. verdict -----------------------------------------------------------
    pf, sharpe = base["profit_factor"], base["sharpe"]
    rationale: List[str] = []
    if len(rs) < 30:
        verdict = "REJECT"
        rationale.append(f"only {len(rs)} OOS trades — too thin to conclude anything")
    elif pf < 1.0:
        verdict = "REJECT"
        rationale.append(
            f"PF {pf:.2f} < 1.0 — loses money gross of nothing; costs are already included"
        )
    elif "OUTLIER_DEPENDENT" in flags:
        verdict = "FRAGILE_OUTLIER_DRIVEN"
        rationale.append(
            f"PF falls {base['profit_factor']:.2f} -> {wins['profit_factor']:.2f} when "
            f"{len(rs) - len(kept)} tail trades are removed"
        )
    elif "REGIME_CONCENTRATION" in flags:
        verdict = "REGIME_CONCENTRATED"
        rationale.append(
            f"{share:.0%} of all positive-fold profit comes from {top_fold[0]} alone"
        )
    elif pf >= 1.5 and sharpe >= 0.8 and "FOLD_INCONSISTENT" not in flags:
        verdict = "ROBUST"
        rationale.append(f"PF {pf:.2f}, Sharpe {sharpe:.2f}, consistent across folds")
    else:
        verdict = "MARGINAL"
        rationale.append(
            f"PF {pf:.2f} / Sharpe {sharpe:.2f} — positive but under the gate bars"
        )

    rationale.append(
        f"{out['temporal']['n_folds_positive']}/{out['temporal']['n_folds']} folds "
        f"profitable ({out['temporal']['share_folds_positive']:.0%}; bar is 65%)"
    )
    rationale.append(
        f"mean R {out['outlier']['mean_r']:+.3f} vs median R "
        f"{out['outlier']['median_r']:+.3f}; largest single win is "
        f"{out['outlier']['top1_share_of_gross_profit']:.0%} of all gross profit"
    )

    out["flags"] = flags
    out["verdict"] = verdict
    out["rationale"] = rationale
    return out


def main(argv: List[str]) -> int:
    as_json = "--json" in argv
    ids = [a for a in argv if not a.startswith("-")]
    if not ids:
        ids = sorted(p.name for p in RESULTS.iterdir() if p.is_dir())

    rows = [audit(sid) for sid in ids]
    rows = [r for r in rows if r.get("verdict") != "NO_REPORT"]

    if as_json:
        print(json.dumps(rows, indent=2))
    else:
        print(
            f"{'strategy':30} {'res':6} {'trades':>7} {'PF':>6} {'PF_wins':>8} "
            f"{'folds+':>7} {'uw%':>6}  verdict"
        )
        for r in sorted(rows, key=lambda r: -r.get("pooled", {}).get("profit_factor", 0)):
            if "pooled" not in r:
                print(f"{r['strategy_id']:30} {'-':6} {'-':>7}  {r['verdict']}")
                continue
            print(
                f"{r['strategy_id']:30} {r['resolution_used']:6} "
                f"{r['n_oos_trades']:7} "
                f"{r['pooled']['profit_factor']:6.2f} "
                f"{r['outlier']['pf_winsorized']:8.2f} "
                f"{r['temporal']['share_folds_positive']:6.0%} "
                f"{r['drawdown']['share_of_series_underwater']:6.0%}  "
                f"{r['verdict']}"
                + (f"  {','.join(r['flags'])}" if r.get("flags") else "")
            )
        print("\nPer-strategy rationale:")
        for r in sorted(rows, key=lambda r: -r.get("pooled", {}).get("profit_factor", 0)):
            print(f"\n  {r['strategy_id']} — {r['verdict']}")
            for b in r.get("rationale", []):
                print(f"    - {b}")

    out = ROOT / "task" / "2026-W32" / "wave2" / "RISK_AUDIT.json"
    out.write_text(json.dumps(rows, indent=2))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
