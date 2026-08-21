"""T6 — the promotion pipeline: research → staged → qualified.

    python -m src.layer0.strategies.promote --list
    python -m src.layer0.strategies.promote <strategy_id> --to staged
    python -m src.layer0.strategies.promote <strategy_id> --to qualified

Guarantees, all enforced in code rather than by convention:

* **One step at a time.** research → staged → qualified. No skipping, no jumping
  straight to qualified.
* **staged→qualified reuses the LIVE gates.** It imports
  ``src.vetting.gates`` and calls ``evaluate_gates``. The thresholds are
  not copied here — if the live bar moves, the sandbox bar moves with it, and
  there is no second qualification path to drift.
* **OOS folds only.** Metrics come from ``src.validation.walk_forward``
  folds, so a research backtest is leak-free by construction rather than by care.
* **No look-ahead.** ``assert_no_lookahead`` runs before any promotion.
* **Every promotion is auditable and reversible** — a `git mv` plus a JSON report
  under ``results/research/<strategy_id>/``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .contract import Stage, assert_no_lookahead
from .registry import RegisteredStrategy, StrategyRegistry, get_registry

REPO = Path(__file__).resolve().parents[3]
REPORT_ROOT = REPO / "results" / "research"

_NEXT_STAGE = {Stage.RESEARCH: Stage.STAGED, Stage.STAGED: Stage.QUALIFIED}


class PromotionRefused(RuntimeError):
    """A gate said no. This is a successful outcome of the pipeline, not an error."""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _report_path(strategy_id: str, kind: str) -> Path:
    d = REPORT_ROOT / strategy_id
    d.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return d / f"{kind}_{stamp}.json"


def _write_report(strategy_id: str, kind: str, payload: Dict[str, Any]) -> Path:
    path = _report_path(strategy_id, kind)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    return path


# --- evidence gathering -------------------------------------------------------


def evaluate_walk_forward(reg: RegisteredStrategy) -> Dict[str, Any]:
    """Run the strategy over walk-forward OOS folds with the standard cost model.

    Uses the SAME fold generator as MODEL-003/004/006
    (``validation/walk_forward.py``: min_train 36mo, step 6mo, OOS 6mo, anchored),
    so a research backtest cannot accidentally be more generous than the live path.

    Returns per-fold OOS metrics plus the aggregate cell that the vetting gates
    consume. Data access is READ-ONLY: prices come through the shared loader; the
    sandbox never writes to any ``fact_*`` table.
    """
    from src.layer0.core_engine.backtest_engine import BacktestConfig, BacktestEngine
    from src.validation import walk_forward as WF

    strategy = reg.instantiate()
    meta = reg.metadata

    from src.layer0.strategies.contract_v2 import StrategyV2

    if isinstance(strategy, StrategyV2):
        from src.layer0.strategies.v2_harness import evaluate_strategy

        report = evaluate_strategy(strategy, lookback_years=5)
        return {
            "strategy_id": reg.strategy_id,
            "evaluated_at_utc": report["evaluated_at_utc"],
            "fold_design": report["fold_design"],
            "cost_model": {"spread_pips": 1.0, "slippage_pips": 0.5, "commission": 0.0},
            "per_fold": [],
            "n_oos_trades": report["pooled"]["n_oos_trades"],
            "cell": report["pooled"]["cell"],
        }

    from .engine_adapter import ContractStrategyAdapter
    from .research_data import (
        load_ohlcv_readonly,
    )  # local import: keeps I/O at the edge

    # The contract is the promotion surface; the engine needs the execution
    # surface. The adapter supplies uniform ATR stops so no research strategy can
    # flatter itself with bespoke exit logic.
    runnable = ContractStrategyAdapter(strategy)
    engine = BacktestEngine(BacktestConfig())
    per_fold: List[Dict[str, Any]] = []
    all_r: List[float] = []

    for pair in meta.pairs:
        for gran in meta.granularities:
            df = load_ohlcv_readonly(pair, gran)
            if df is None or len(df) < strategy.warmup_bars * 2:
                continue

            assert_no_lookahead(strategy, df)

            start, end = df.index[0].to_pydatetime(), df.index[-1].to_pydatetime()
            folds = WF.default_folds(start, end)
            for i, fold in enumerate(folds, start=1):
                oos = df[(df.index >= fold.oos_start) & (df.index < fold.oos_end)]
                if len(oos) < strategy.warmup_bars:
                    continue
                result = engine.run_backtest(
                    runnable,
                    df.loc[: oos.index[-1]],
                    pair,
                    gran,
                    warmup_bars=runnable.get_required_warmup_bars(),
                )
                trades = (
                    [
                        t
                        for t in result.trades
                        if fold.oos_start <= t.entry_time.to_pydatetime() < fold.oos_end
                    ]
                    if hasattr(result, "trades")
                    else []
                )
                if not trades:
                    continue
                rs = [float(t.r_multiple or 0.0) for t in trades]
                all_r.extend(rs)
                per_fold.append(
                    {
                        "fold": i,
                        "pair": pair,
                        "granularity": gran,
                        "oos_start": fold.oos_start,
                        "oos_end": fold.oos_end,
                        "n_trades": len(rs),
                        "mean_r": sum(rs) / len(rs),
                        "win_rate": sum(1 for r in rs if r > 0) / len(rs),
                    }
                )

    return {
        "strategy_id": reg.strategy_id,
        "evaluated_at_utc": _utcnow(),
        "fold_design": {
            "min_train_months": WF.MIN_TRAIN_MONTHS,
            "step_months": WF.STEP_MONTHS,
            "oos_window_months": WF.OOS_WINDOW_MONTHS,
            "mode": "anchored",
        },
        "cost_model": {"spread_pips": 1.0, "slippage_pips": 0.5, "commission": 0.0},
        "per_fold": per_fold,
        "n_oos_trades": len(all_r),
        "cell": _aggregate_cell(all_r, per_fold),
    }


def _aggregate_cell(
    r_multiples: List[float], per_fold: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Build the metric dict that ``vetting.gates.evaluate_gates`` consumes.

    Every metric is computed by ``src.attribution.metrics`` — the SAME
    functions the live attribution path uses. They are imported, never
    reimplemented, for exactly the reason the thresholds are imported: a second
    implementation is a second definition of "good" waiting to drift.

    (The first draft of this function did reimplement them, and got max drawdown
    wrong by dividing by a near-zero early peak — it reported 1650%. The live
    `max_drawdown` compounds a fixed-fractional equity curve from 1.0, which is
    bounded in [0,1) by construction.)

    Metrics are computed on OOS trades only. Thin samples are flagged
    ``low_confidence``, which the live gates treat as an unconditional rejection —
    the sandbox does not get a softer standard for having less data.
    """
    from src.attribution import metrics as M

    n = len(r_multiples)
    if n == 0:
        return {
            "profit_factor": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 1.0,
            "win_rate": 0.0,
            "recovery_factor": 0.0,
            "oos_months": 0,
            "trade_count": 0,
            "low_confidence": True,
        }

    months = 0.0
    if per_fold:
        spans = {(f["oos_start"], f["oos_end"]) for f in per_fold}
        months = sum((e - s).days for s, e in spans) / 30.44
    years = max(months / 12.0, 1e-9)
    trades_per_year = n / years

    is_winner = [1 if r > 0 else 0 for r in r_multiples]
    sharpe = M.annualized_sharpe(r_multiples, trades_per_year)
    recovery = M.recovery_factor(r_multiples)

    cell = {
        "profit_factor": round(M.profit_factor(r_multiples), 4),
        "sharpe": 0.0 if sharpe != sharpe else round(sharpe, 4),  # NaN -> 0.0
        "max_drawdown": round(M.max_drawdown(r_multiples), 4),
        "win_rate": round(M.win_rate(is_winner), 4),
        "recovery_factor": 0.0 if recovery == float("inf") else round(recovery, 4),
        "oos_months": round(months, 2),
        "trade_count": n,
        "low_confidence": n < 20,
    }
    # The live sanity bounds (FIX-S1-001) apply to sandbox metrics too.
    violations = M.validate_metrics(cell)
    if violations:
        cell["low_confidence"] = True
        cell["metric_violations"] = violations
    return cell


# --- promotion ----------------------------------------------------------------


def _git_mv(src: Path, dst: Path) -> None:
    """Move a strategy between stage packages, preserving git history when possible.

    A freshly-authored research strategy is normally *untracked* — that is the
    common case for the sandbox, not an error — and `git mv` refuses untracked
    sources. Fall back to a filesystem move plus `git add` so the promotion still
    lands and the result is staged for the audit commit either way.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    tracked = (
        subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(src)],
            cwd=REPO,
            capture_output=True,
            text=True,
        ).returncode
        == 0
    )

    if tracked:
        subprocess.run(
            ["git", "mv", str(src), str(dst)],
            cwd=REPO,
            check=True,
            capture_output=True,
            text=True,
        )
    else:
        shutil.move(str(src), str(dst))
        subprocess.run(
            ["git", "add", str(dst)], cwd=REPO, capture_output=True, text=True
        )


def promote(
    strategy_id: str,
    to: Stage,
    *,
    registry: StrategyRegistry | None = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    reg_obj = registry or get_registry(refresh=True)
    entry = reg_obj.get(strategy_id)
    current = entry.stage

    expected = _NEXT_STAGE.get(current)
    if expected is None:
        raise PromotionRefused(
            f"{strategy_id} is already {current.value}; nothing above it"
        )
    if to is not expected:
        raise PromotionRefused(
            f"{strategy_id} is {current.value}; the only legal next stage is "
            f"{expected.value}, not {to.value}. Stages cannot be skipped — that is "
            "the side door the gates exist to close."
        )

    evidence = evaluate_walk_forward(entry)
    cell = evidence["cell"]

    verdict: Dict[str, Any] = {
        "strategy_id": strategy_id,
        "from_stage": current.value,
        "to_stage": to.value,
        "decided_at_utc": _utcnow(),
        "evidence": evidence,
    }

    if to is Stage.QUALIFIED:
        # Import the LIVE gates. Thresholds are never copied into this module.
        from src.vetting.gates import GATES, evaluate_gates

        passed, failures = evaluate_gates(cell)
        verdict.update({"gates": GATES, "passed": passed, "failures": failures})
        if not passed:
            verdict["outcome"] = "REFUSED"
            path = _write_report(strategy_id, "qualification_refused", verdict)
            verdict["report"] = str(path)
            raise PromotionRefused(
                f"{strategy_id} refused promotion to qualified:\n  "
                + "\n  ".join(failures)
                + f"\nreport: {path}"
            )
    else:
        # research -> staged: contract compliance + a real OOS backtest existing at all.
        verdict["passed"] = evidence["n_oos_trades"] > 0
        if not verdict["passed"]:
            verdict["outcome"] = "REFUSED"
            path = _write_report(strategy_id, "staging_refused", verdict)
            raise PromotionRefused(
                f"{strategy_id} produced no OOS trades across the walk-forward folds — "
                f"nothing to evaluate. report: {path}"
            )

    verdict["outcome"] = "PROMOTED"
    if not dry_run:
        module_file = REPO / (entry.module.replace(".", "/") + ".py")
        _git_mv(module_file, reg_obj.stage_dir(to) / module_file.name)
        reg_obj.refresh()
    path = _write_report(strategy_id, f"promoted_to_{to.value}", verdict)
    verdict["report"] = str(path)
    return verdict


def main() -> None:
    p = argparse.ArgumentParser(description="T6 research strategy promotion pipeline")
    p.add_argument("strategy_id", nargs="?")
    p.add_argument("--to", choices=[s.value for s in Stage])
    p.add_argument("--list", action="store_true", help="list the registry")
    p.add_argument(
        "--dry-run", action="store_true", help="evaluate without moving files"
    )
    args = p.parse_args()

    reg = get_registry(refresh=True)

    if args.list or not args.strategy_id:
        print(f"{'stage':<11}{'strategy_id':<32}{'version':<10}name")
        for r in reg.list():
            print(
                f"{r.stage.value:<11}{r.strategy_id:<32}{r.metadata.version:<10}{r.metadata.name}"
            )
        print(
            f"\n{len(reg)} strategies. Only {len(reg.qualified())} qualified "
            "(the live path sees these and nothing else)."
        )
        return

    if not args.to:
        p.error("--to is required when promoting")

    try:
        verdict = promote(
            args.strategy_id, Stage(args.to), registry=reg, dry_run=args.dry_run
        )
    except PromotionRefused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        sys.exit(2)
    print(
        json.dumps(
            {k: v for k, v in verdict.items() if k != "evidence"}, indent=2, default=str
        )
    )
    print(f"report: {verdict['report']}")


if __name__ == "__main__":
    main()
