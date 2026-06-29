"""MODEL-005 — strategy vetting + regime→strategy map / weights emitter.

Reads MODEL-004 attribution (latest qualification_run_id), applies the strict per-regime
gates, ranks qualifiers by composite score, and emits:
  * results/state/regime_strategy_map.json   (ranked qualifying strategies per regime)
  * results/state/strategy_weights.json      (per-regime weights, sum to 1)
  * results/reports/vetting_report_*.json     (gate pass/fail + rejection detail)
Both JSON artifacts validate against contracts/{regime-map,weights}-contract.json.

Log-only mode (VETTING_LOG_ONLY=true) writes to results/reports/proposed_* instead and
does not update the registry. Usage: python -m src.system1.vetting.vet [--live]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy import text

from src.common.db import get_engine
from src.system1.vetting import gates as G

logger = logging.getLogger("system1.vetting")

SCHEMA_VERSION = "1.0.0"
REGIME_MODEL_VERSION = "hmm-v1.0.0"
REGIMES = ["Trending-Up", "Trending-Down", "Ranging", "High-Vol"]
CAP = 100.0  # cap unbounded ratios (inf PF/recovery, huge Sharpe) for ranking/JSON
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
STATE_DIR = os.path.join(_REPO_ROOT, "results", "state")
REPORTS_DIR = os.path.join(_REPO_ROOT, "results", "reports")
CONTRACTS = os.path.join(_REPO_ROOT, "contracts")


def _cap(v: float) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    if v != v:  # NaN
        return 0.0
    return min(v, CAP) if v > 0 else max(v, -CAP)


def _load_cells() -> tuple[List[Dict], str]:
    engine = get_engine()
    with engine.connect() as conn:
        run_id = conn.execute(
            text(
                "SELECT qualification_run_id FROM fact_strategy_regime_attribution "
                "ORDER BY created_at DESC LIMIT 1"
            )
        ).scalar()
        rows = (
            conn.execute(
                text(
                    "SELECT a.strategy_id, s.strategy_name, a.regime, a.granularity, a.trade_count, "
                    "a.win_rate, a.profit_factor, a.sharpe, a.max_drawdown, a.recovery_factor, "
                    "a.oos_months, a.low_confidence "
                    "FROM fact_strategy_regime_attribution a "
                    "JOIN dim_strategy s ON s.strategy_id = a.strategy_id "
                    "WHERE a.qualification_run_id = :rid"
                ),
                {"rid": run_id},
            )
            .mappings()
            .all()
        )
    cells = []
    for r in rows:
        cells.append(
            {
                "strategy_id": int(r["strategy_id"]),
                "variant": f"{r['strategy_name']}@{r['granularity']}",
                "regime": r["regime"],
                "granularity": r["granularity"],
                "trade_count": int(r["trade_count"]),
                "win_rate": float(r["win_rate"]),
                "profit_factor": _cap(r["profit_factor"]),
                "sharpe": _cap(r["sharpe"]),
                "max_drawdown": float(r["max_drawdown"]),
                "recovery_factor": _cap(r["recovery_factor"]),
                "oos_months": float(r["oos_months"] or 0.0),
                "low_confidence": bool(r["low_confidence"]),
            }
        )
    return cells, str(run_id)


class WeightsNotNormalized(ValueError):
    """Raised by the build post-condition when a non-empty regime's weights do not
    sum to 1.0 (FIX-S1-004 guard). Failing the run is intentional: a collapsed/degenerate
    weight map (e.g. the shipped ``Ranging = {'10': 5e-08}``) must never be published.
    """


def _assert_weights_normalized(weights_out: Dict[str, Dict[str, float]]) -> None:
    """Hard post-condition: every NON-EMPTY regime's weights must sum to 1.0 (±1e-6).

    This guard CAN fire — it inspects already-computed weight dicts, so a bug upstream
    (a key collision, a dropped variant, a bad renormalization) that breaks the
    sum-to-1 invariant trips it and fails the run, rather than silently shipping a
    corrupt position-sizing artifact to Computer 2.
    """
    for regime, weights in weights_out.items():
        if not weights:
            continue
        total = sum(weights.values())
        if abs(total - 1.0) >= 1e-6:
            raise WeightsNotNormalized(
                f"Regime '{regime}' weights sum to {total!r}, not 1.0 "
                f"(keys={list(weights)}). Refusing to publish a degenerate weight map."
            )


def _metrics_block(c: Dict) -> Dict[str, float]:
    return {
        "profit_factor": round(c["profit_factor"], 4),
        "sharpe": round(c["sharpe"], 4),
        "win_rate": round(c["win_rate"], 4),
        "max_drawdown": round(c["max_drawdown"], 4),
        "recovery_factor": round(c["recovery_factor"], 4),
        "trade_count": c["trade_count"],
        "oos_months": round(c["oos_months"], 2),
    }


def build(cells: List[Dict], run_id: str) -> Dict[str, Any]:
    rejection = {
        k: 0
        for k in [
            "pf_fail",
            "sharpe_fail",
            "maxdd_fail",
            "winrate_fail",
            "recovery_fail",
            "oos_fail",
            "low_confidence_fail",
        ]
    }
    rejection_detail: List[Dict] = []
    by_regime: Dict[str, List[Dict]] = {r: [] for r in REGIMES}

    for c in cells:
        passed, failures = G.evaluate_gates(c)
        if passed:
            by_regime[c["regime"]].append(c)
        else:
            for f in failures:
                if f == "LOW_CONFIDENCE":
                    rejection["low_confidence_fail"] += 1
                elif f.startswith("PF"):
                    rejection["pf_fail"] += 1
                elif f.startswith("Sharpe"):
                    rejection["sharpe_fail"] += 1
                elif f.startswith("MaxDD"):
                    rejection["maxdd_fail"] += 1
                elif f.startswith("WinRate"):
                    rejection["winrate_fail"] += 1
                elif f.startswith("Recovery"):
                    rejection["recovery_fail"] += 1
                elif f.startswith("OOS"):
                    rejection["oos_fail"] += 1
            rejection_detail.append(
                {
                    "strategy_id": c["strategy_id"],
                    "variant": c["variant"],
                    "regime": c["regime"],
                    "failed_gates": failures,
                }
            )

    regimes_out: Dict[str, List[Dict]] = {}
    weights_out: Dict[str, Dict[str, float]] = {}
    empty_regimes: List[str] = []
    for regime in REGIMES:
        ranked = G.rank_cells(by_regime[regime])
        if not ranked:
            empty_regimes.append(regime)
            logger.warning(
                "STARVATION: no qualifying strategies for regime '%s'", regime
            )
            continue
        regimes_out[regime] = [
            {
                "strategy_id": c["strategy_id"],
                "variant": c["variant"],
                "rank": c["rank"],
                "composite_score": round(c["composite_score"], 6),
                "metrics": _metrics_block(c),
            }
            for c in ranked
        ]
        weights_out[regime] = {
            k: round(v, 8) for k, v in G.normalized_weights(ranked).items()
        }

    # FIX-S1-004 post-condition: fail the run before emitting if any non-empty regime's
    # weights don't sum to 1.0 (e.g. a duplicate-strategy key collision). Runs on the
    # rounded values that are actually written, so the published artifact is the one checked.
    _assert_weights_normalized(weights_out)

    now = datetime.now(timezone.utc).isoformat()
    regime_map = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now,
        "regime_model_version": REGIME_MODEL_VERSION,
        "qualification_run_id": run_id,
        "ranking_rule": G.RANKING_RULE,
        "gates": G.GATES,
        "regimes": regimes_out,
        "empty_regimes": empty_regimes,
        "rejection_summary": rejection,
    }
    weights = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now,
        "regime_model_version": REGIME_MODEL_VERSION,
        "qualification_run_id": run_id,
        "weights": weights_out,
    }
    return {"map": regime_map, "weights": weights, "rejection_detail": rejection_detail}


def _validate(artifact: Dict, contract_name: str) -> None:
    import jsonschema

    with open(os.path.join(CONTRACTS, contract_name), encoding="utf-8") as fh:
        schema = json.load(fh)
    jsonschema.validate(artifact, schema)


def _write_json(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    os.replace(tmp, path)


def _update_registry(regime_map: Dict) -> None:
    qualified_ids = {
        s["strategy_id"] for entries in regime_map["regimes"].values() for s in entries
    }
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE dim_strategy_registry ADD COLUMN IF NOT EXISTS is_qualified boolean"
            )
        )
        conn.execute(text("UPDATE dim_strategy_registry SET is_qualified = false"))
        if qualified_ids:
            conn.execute(
                text(
                    "UPDATE dim_strategy_registry SET is_qualified = true WHERE strategy_id = ANY(:ids)"
                ),
                {"ids": list(qualified_ids)},
            )
    logger.info("Registry: %d strategies marked qualified", len(qualified_ids))


def run(live: bool = False, register_mlflow: bool = True) -> Dict[str, Any]:
    cells, run_id = _load_cells()
    logger.info("Loaded %d attribution cells (run %s)", len(cells), run_id)
    out = build(cells, run_id)

    _validate(out["map"], "regime-map-contract.json")
    _validate(out["weights"], "weights-contract.json")

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if live:
        _write_json(os.path.join(STATE_DIR, "regime_strategy_map.json"), out["map"])
        _write_json(os.path.join(STATE_DIR, "strategy_weights.json"), out["weights"])
        _update_registry(out["map"])
        map_path = os.path.join(STATE_DIR, "regime_strategy_map.json")
    else:
        _write_json(
            os.path.join(REPORTS_DIR, "proposed_regime_strategy_map.json"), out["map"]
        )
        _write_json(
            os.path.join(REPORTS_DIR, "proposed_strategy_weights.json"), out["weights"]
        )
        map_path = os.path.join(REPORTS_DIR, "proposed_regime_strategy_map.json")

    report = {
        "qualification_run_id": run_id,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "live" if live else "log_only",
        "n_cells": len(cells),
        "n_qualifying": sum(len(v) for v in out["map"]["regimes"].values()),
        "empty_regimes": out["map"]["empty_regimes"],
        "rejection_summary": out["map"]["rejection_summary"],
        "rejection_detail": out["rejection_detail"],
    }
    _write_json(os.path.join(REPORTS_DIR, f"vetting_report_{ts}.json"), report)

    summary = {
        k: report[k] for k in ("n_cells", "n_qualifying", "empty_regimes", "mode")
    }
    summary["map_path"] = map_path
    if register_mlflow:
        summary["mlflow_run_id"] = _register_mlflow(report)
    logger.info("MODEL-005 complete: %s", summary)
    return summary


def _register_mlflow(report) -> str:
    try:
        import mlflow
        from src.system1.features.feature_pipeline import _resolve_mlflow_uri

        mlflow.set_tracking_uri(_resolve_mlflow_uri())
        mlflow.set_experiment("system1-vetting")
        with mlflow.start_run(run_name="vetting") as run:
            mlflow.log_param("mode", report["mode"])
            mlflow.log_metric("n_cells", report["n_cells"])
            mlflow.log_metric("n_qualifying", report["n_qualifying"])
            for k, v in report["rejection_summary"].items():
                mlflow.log_metric(k, v)
            return run.info.run_id
    except Exception as e:  # noqa: BLE001
        logger.error("MLflow registration failed: %s", e)
        return None


def main() -> None:
    p = argparse.ArgumentParser(description="MODEL-005 vetting + regime map")
    p.add_argument(
        "--live",
        action="store_true",
        help="write to results/state/ and update registry",
    )
    p.add_argument("--no-mlflow", action="store_true")
    args = p.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    live = args.live or os.environ.get("VETTING_LOG_ONLY", "true").lower() == "false"
    print(run(live=live, register_mlflow=not args.no_mlflow))


if __name__ == "__main__":
    main()
