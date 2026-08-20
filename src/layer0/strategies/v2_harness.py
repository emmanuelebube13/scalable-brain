"""Wave 1, agent E — the walk-forward harness for the v2 (faithful) path.

Runs a :class:`StrategyV2` over the standard walk-forward folds and produces the
report shape the spec asks for (§8):

1. **per-cell verdicts** — one gate evaluation per (pair × granularity)
2. **the pooled verdict** — continuity with T6, and the only thing promotion
   may ever consider
3. **dispersion** — best and worst cell, so a strategy that qualifies pooled
   while failing most cells is visible rather than flattering

and, per spec §5, every cell is evaluated **twice** — resolved on its native
bars and resolved on H1 bars — with the delta published. That delta is the
measurement of what the intrabar-path assumption was worth. Publishing it is
what makes the fidelity claim honest instead of asserted.

Three things this module deliberately does NOT do:

- **It does not reimplement metrics.** ``promote._aggregate_cell`` is imported
  and reused. It already computes every metric through
  ``src.attribution.metrics``, and rewriting that is the exact mistake
  the T6 failure log records (a fresh drawdown implementation reported 1650%).
- **It does not restate thresholds.** ``vetting.gates.evaluate_gates`` is
  imported. There is one definition of "good".
- **It does not promote.** It reports. Promotion remains ``promote.py``'s
  single door, and per-cell results are reporting only — never a second
  qualification path.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from src.validation import walk_forward as WF
from src.vetting.gates import evaluate_gates

from .contract_v2 import (
    GRANULARITY_INTERVAL,
    OrderIntent,
    StrategyV2,
    assert_no_lookahead_v2,
    closed_context_frame,
)
from .position_engine import PositionEngine
from .promote import _aggregate_cell

RESULTS_ROOT = Path(__file__).resolve().parents[3] / "results" / "research"


# ---------------------------------------------------------------------------
# Frame assembly
# ---------------------------------------------------------------------------


def build_frames(
    pair: str,
    primary_granularity: str,
    context_granularities: Sequence[str],
    *,
    loader: Any = None,
    lookback_years: int = 10,
) -> Optional[Dict[str, pd.DataFrame]]:
    """Load the primary frame plus any context frames for one pair.

    Returns ``None`` if the primary frame is unavailable — a pair with no
    history is skipped, not failed, so a strategy declaring pairs whose backfill
    has not finished still produces a verdict on the pairs that do exist.
    """
    if loader is None:
        from .research_data import (
            load_ohlcv_readonly as loader,
        )  # local: I/O at the edge

    primary = loader(pair, primary_granularity, lookback_years=lookback_years)
    if primary is None or primary.empty:
        return None

    frames: Dict[str, pd.DataFrame] = {primary_granularity: primary}
    for gran in context_granularities:
        if gran == primary_granularity:
            continue
        ctx = loader(pair, gran, lookback_years=lookback_years)
        if ctx is None or ctx.empty:
            return None  # a declared context frame is not optional
        frames[gran] = ctx
    return frames


def _h1_eligibility(native_granularity: str):
    """Spec §5: an order decided on a native bar may fill only once that bar has
    closed, even though fills resolve on H1. Without this the H1 resolution
    would let a D1 decision fill inside the very bar that produced it."""
    interval = GRANULARITY_INTERVAL[native_granularity]

    def _fn(intent: OrderIntent) -> pd.Timestamp:
        return intent.decision_bar + interval

    return _fn


# ---------------------------------------------------------------------------
# One cell
# ---------------------------------------------------------------------------


def evaluate_cell(
    strategy: StrategyV2,
    frames: Mapping[str, pd.DataFrame],
    *,
    pair: str,
    granularity: str,
    h1_frame: Optional[pd.DataFrame] = None,
) -> Optional[Dict[str, Any]]:
    """Evaluate one (pair × granularity) cell, native and (if given) on H1.

    The strategy's orders are generated **once** over the full frame rather than
    re-generated per fold. That is sound precisely because
    ``assert_no_lookahead_v2`` has already proved the order at bar *t* does not
    depend on bars after *t* — so the full-frame order set restricted to a fold
    is identical to the order set the strategy would have emitted inside that
    fold. Trades are then attributed to folds by entry time, which is how
    ``promote.evaluate_walk_forward`` attributes them too.
    """
    primary = frames[granularity]
    if len(primary) < strategy.warmup_bars * 2:
        return None

    assert_no_lookahead_v2(strategy, frames)

    intents = list(strategy.generate_orders(frames))
    if not intents:
        return None

    folds = WF.default_folds(
        primary.index[0].to_pydatetime(), primary.index[-1].to_pydatetime()
    )
    if not folds:
        return None

    engine = PositionEngine()
    runs: Dict[str, Any] = {}

    for label, resolution_df, eligibility in (
        ("native", primary, None),
        (
            "h1",
            h1_frame,
            _h1_eligibility(granularity) if h1_frame is not None else None,
        ),
    ):
        if resolution_df is None:
            continue
        result = (
            engine.run(
                resolution_df,
                intents,
                pair=pair,
                warmup_bars=strategy.warmup_bars,
                strategy=strategy,
                granularity=granularity,
            )
            if eligibility is None
            else engine.run(
                resolution_df,
                intents,
                pair=pair,
                warmup_bars=0,
                strategy=strategy,
                eligibility_fn=eligibility,
                granularity=granularity,
            )
        )
        runs[label] = _fold_attribute(result.trades, folds, pair, granularity)

    if "native" not in runs:
        return None

    cell: Dict[str, Any] = {
        "pair": pair,
        "granularity": granularity,
        "resolutions": {},
    }
    for label, (per_fold, r_multiples) in runs.items():
        metrics = _aggregate_cell(r_multiples, per_fold)
        passed, failures = evaluate_gates(metrics)
        cell["resolutions"][label] = {
            "per_fold": per_fold,
            "n_oos_trades": len(r_multiples),
            # Raw OOS r-multiples are kept so the pooled verdict is computed from
            # trades, never from an average of fold averages (which would weight
            # a 3-trade fold like a 300-trade one).
            "r_multiples": r_multiples,
            "cell": metrics,
            "passed": passed,
            "failures": failures,
        }

    _attach_resolution_delta(cell)
    return cell


def _as_utc(value: Any) -> pd.Timestamp:
    """Fold boundaries arrive tz-aware or naive depending on the caller; both
    must compare against UTC-indexed trades."""
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def _fold_attribute(
    trades: pd.DataFrame,
    folds: Sequence[WF.Fold],
    pair: str,
    granularity: str,
) -> Tuple[List[Dict[str, Any]], List[float]]:
    """Split trades into OOS folds by entry time. OOS trades only."""
    per_fold: List[Dict[str, Any]] = []
    all_r: List[float] = []
    if trades.empty:
        return per_fold, all_r

    entry = pd.to_datetime(trades["entry_time"], utc=True)
    for i, fold in enumerate(folds, start=1):
        lo = _as_utc(fold.oos_start)
        hi = _as_utc(fold.oos_end)
        sel = trades[(entry >= lo) & (entry < hi)]
        if sel.empty:
            continue
        rs = [float(r) for r in sel["r_multiple"].tolist()]
        all_r.extend(rs)
        per_fold.append(
            {
                "fold": i,
                "pair": pair,
                "granularity": granularity,
                "oos_start": fold.oos_start,
                "oos_end": fold.oos_end,
                "n_trades": len(rs),
                "mean_r": sum(rs) / len(rs),
                "win_rate": sum(1 for r in rs if r > 0) / len(rs),
            }
        )
    return per_fold, all_r


def _attach_resolution_delta(cell: Dict[str, Any]) -> None:
    """Spec §5: publish what the bar-path assumption was worth."""
    res = cell["resolutions"]
    if "native" not in res or "h1" not in res:
        cell["resolution_delta"] = None
        return
    nat, h1 = res["native"]["cell"], res["h1"]["cell"]
    cell["resolution_delta"] = {
        key: round(float(h1.get(key, 0.0)) - float(nat.get(key, 0.0)), 4)
        for key in (
            "profit_factor",
            "sharpe",
            "max_drawdown",
            "win_rate",
            "recovery_factor",
        )
    }
    cell["resolution_delta"]["n_trades"] = int(
        res["h1"]["n_oos_trades"] - res["native"]["n_oos_trades"]
    )


# ---------------------------------------------------------------------------
# Whole strategy
# ---------------------------------------------------------------------------


def evaluate_strategy(
    strategy: StrategyV2,
    *,
    loader: Any = None,
    resolve_on_h1: bool = True,
    lookback_years: int = 10,
) -> Dict[str, Any]:
    """Evaluate a v2 strategy across every declared (pair × granularity).

    Produces per-cell verdicts, the pooled verdict, and dispersion (spec §8).
    """
    meta = strategy.metadata
    cells: List[Dict[str, Any]] = []
    pooled_r: List[float] = []
    pooled_folds: List[Dict[str, Any]] = []
    skipped: List[Dict[str, str]] = []

    for pair in meta.pairs:
        frames = build_frames(
            pair,
            meta.primary_granularity,
            meta.context_granularities,
            loader=loader,
            lookback_years=lookback_years,
        )
        if frames is None:
            skipped.append(
                {"pair": pair, "reason": "no data for primary or context frame"}
            )
            continue

        h1 = None
        if resolve_on_h1 and meta.primary_granularity != "H1":
            if loader is None:
                from .research_data import load_ohlcv_readonly as _ld
            else:
                _ld = loader
            h1 = _ld(pair, "H1", lookback_years=lookback_years)

        cell = evaluate_cell(
            strategy,
            frames,
            pair=pair,
            granularity=meta.primary_granularity,
            h1_frame=h1,
        )
        if cell is None:
            skipped.append(
                {"pair": pair, "reason": "insufficient history or no orders emitted"}
            )
            continue

        cells.append(cell)
        primary_res = cell["resolutions"].get("h1") or cell["resolutions"]["native"]
        pooled_folds.extend(primary_res["per_fold"])

    pooled_r = _pooled_r_multiples(cells)

    pooled_metrics = _aggregate_cell(pooled_r, pooled_folds)
    pooled_passed, pooled_failures = evaluate_gates(pooled_metrics)

    return {
        "strategy_id": meta.strategy_id,
        "version": meta.version,
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "fold_design": {
            "min_train_months": WF.MIN_TRAIN_MONTHS,
            "step_months": WF.STEP_MONTHS,
            "oos_window_months": WF.OOS_WINDOW_MONTHS,
            "mode": "anchored",
        },
        "resolution": {
            "native_granularity": meta.primary_granularity,
            "resolved_on_h1": bool(resolve_on_h1 and meta.primary_granularity != "H1"),
            "note": (
                "Cells are evaluated twice; the pooled verdict uses the H1-resolved "
                "series where available, because it resolves intrabar sequence that "
                "native bars cannot. resolution_delta reports what that was worth."
            ),
        },
        "cells": cells,
        "skipped": skipped,
        "pooled": {
            "n_oos_trades": len(pooled_r),
            "cell": pooled_metrics,
            "passed": pooled_passed,
            "failures": pooled_failures,
        },
        "dispersion": _dispersion(cells),
    }


def _pooled_r_multiples(cells: Sequence[Mapping[str, Any]]) -> List[float]:
    """Raw OOS r-multiples across cells, preferring the H1-resolved series."""
    out: List[float] = []
    for cell in cells:
        res = cell["resolutions"].get("h1") or cell["resolutions"]["native"]
        out.extend(res.get("r_multiples", []))
    return out


def _dispersion(cells: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Best and worst cell, and how many passed.

    A strategy that clears the pooled gates while failing most of its cells is a
    concentration risk — this system's finding C, arrived at the hard way.
    """
    scored: List[Tuple[float, Mapping[str, Any]]] = []
    n_passed = 0
    for cell in cells:
        res = cell["resolutions"].get("h1") or cell["resolutions"]["native"]
        if res["passed"]:
            n_passed += 1
        scored.append((float(res["cell"].get("sharpe", 0.0)), cell))

    if not scored:
        return {"n_cells": 0, "n_passed": 0, "best": None, "worst": None}

    scored.sort(key=lambda t: t[0])

    def _label(c: Mapping[str, Any]) -> Dict[str, Any]:
        res = c["resolutions"].get("h1") or c["resolutions"]["native"]
        return {
            "pair": c["pair"],
            "granularity": c["granularity"],
            "sharpe": res["cell"].get("sharpe"),
            "profit_factor": res["cell"].get("profit_factor"),
            "trade_count": res["cell"].get("trade_count"),
            "passed": res["passed"],
        }

    return {
        "n_cells": len(scored),
        "n_passed": n_passed,
        "best": _label(scored[-1][1]),
        "worst": _label(scored[0][1]),
        "warning": (
            "pooled verdict passes but a minority of cells do — concentration risk"
            if n_passed and n_passed < len(scored) / 2
            else None
        ),
    }


def write_report(report: Mapping[str, Any], *, root: Optional[Path] = None) -> Path:
    """Persist a report under ``results/research/<strategy_id>/``."""
    base = (root or RESULTS_ROOT) / str(report["strategy_id"])
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = base / f"v2_evaluation_{stamp}.json"
    path.write_text(json.dumps(report, indent=2, default=str))
    return path


# ---------------------------------------------------------------------------
# Discovery + CLI
# ---------------------------------------------------------------------------


def discover() -> Dict[str, StrategyV2]:
    """Find every contract-v2 strategy across the three stage packages.

    The v1 ``registry`` discovers ``Strategy`` subclasses and therefore does not
    see v2 strategies — they are a parallel path, deliberately. This is the v2
    equivalent, and like the registry it rejects duplicate ``strategy_id``
    loudly (FIX-S1-004: a duplicate id silently collapsed weights once already).
    """
    import importlib
    import inspect
    import pkgutil

    found: Dict[str, StrategyV2] = {}
    origin: Dict[str, str] = {}
    package_root = Path(__file__).resolve().parent

    for stage in ("research", "staged", "qualified"):
        stage_dir = package_root / stage
        if not stage_dir.is_dir():
            continue
        for mod in pkgutil.iter_modules([str(stage_dir)]):
            if mod.name.startswith("_") or mod.ispkg:
                continue
            dotted = f"src.layer0.strategies.{stage}.{mod.name}"
            module = importlib.import_module(dotted)
            for _, obj in inspect.getmembers(module, inspect.isclass):
                if not issubclass(obj, StrategyV2) or obj is StrategyV2:
                    continue
                if inspect.isabstract(obj) or obj.__module__ != dotted:
                    continue
                instance = obj()
                sid = instance.metadata.strategy_id
                if sid in found:
                    raise ValueError(
                        f"duplicate strategy_id {sid!r}: {origin[sid]} and {dotted}"
                    )
                found[sid] = instance
                origin[sid] = dotted
    return found


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m src.layer0.strategies.v2_harness",
        description="Evaluate contract-v2 strategies over walk-forward folds.",
    )
    parser.add_argument("strategy_id", nargs="?", help="omit with --list, or use --all")
    parser.add_argument(
        "--list", action="store_true", help="list discovered v2 strategies"
    )
    parser.add_argument(
        "--all", action="store_true", help="evaluate every discovered strategy"
    )
    parser.add_argument(
        "--no-h1",
        action="store_true",
        help="skip H1 fill resolution (much faster, less faithful)",
    )
    args = parser.parse_args(argv)

    strategies = discover()

    if args.list or (not args.strategy_id and not args.all):
        if not strategies:
            print("no contract-v2 strategies found in research/, staged/ or qualified/")
            return 0
        print(f"{'strategy_id':<40} {'gran':<5} pairs")
        for sid, s in sorted(strategies.items()):
            meta = s.metadata
            print(f"{sid:<40} {meta.primary_granularity:<5} {','.join(meta.pairs)}")
        print(
            f"\n{len(strategies)} strategies. Reports land in results/research/<id>/."
        )
        return 0

    targets = (
        sorted(strategies) if args.all else [args.strategy_id]  # type: ignore[list-item]
    )
    missing = [t for t in targets if t not in strategies]
    if missing:
        print(f"unknown strategy_id: {', '.join(missing)}")
        return 2

    for sid in targets:
        print(f"evaluating {sid} …")
        report = evaluate_strategy(strategies[sid], resolve_on_h1=not args.no_h1)
        path = write_report(report)
        pooled = report["pooled"]
        verdict = "PASS" if pooled["passed"] else "FAIL"
        print(
            f"  {verdict}  {pooled['n_oos_trades']} OOS trades  "
            f"PF={pooled['cell'].get('profit_factor')} "
            f"Sharpe={pooled['cell'].get('sharpe')}"
        )
        for reason in pooled["failures"]:
            print(f"    - {reason}")
        disp = report["dispersion"]
        print(f"  cells: {disp['n_passed']}/{disp['n_cells']} passed  -> {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
