"""MODEL-009 — retrain orchestrator: triggers → gated pipeline → atomic promote.

Designed for testability: ``run()`` accepts injectable ``pipeline_fn`` / ``promote_fn``
so deployment-gate / lock / cooldown behaviour can be exercised without the multi-minute
real pipeline. Defaults wire the real System-1 steps (features → regime → attribution →
vetting → serialize/publish via MODEL-007).

Usage: python -m src.system1.scheduler.orchestrator           # evaluate triggers + maybe retrain
       python -m src.system1.scheduler.orchestrator --force   # force a run (ignore triggers)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from src.system1.scheduler import triggers as TR

logger = logging.getLogger("system1.scheduler")

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
STATE_DIR = os.path.join(_REPO_ROOT, "results", "state")
RETRAIN_STATE = os.path.join(STATE_DIR, "retrain_state.json")
LOCK_FILE = os.path.join(STATE_DIR, "retrain.lock")
LATEST_JSON = os.path.join(_REPO_ROOT, "model-artifacts", "latest.json")
REGIME_ACCURACY_FLOOR = 0.70


class SingleFlightLock:
    """Exclusive on-disk lock (O_EXCL). Raises if already held (concurrent run guard)."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or LOCK_FILE  # read module global at call time (test-friendly)
        self.fd = None

    def __enter__(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        try:
            self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as e:
            raise RuntimeError("another retrain run holds the single-flight lock") from e
        os.write(self.fd, datetime.now(timezone.utc).isoformat().encode())
        return self

    def __exit__(self, *exc):
        if self.fd is not None:
            os.close(self.fd)
        if os.path.exists(self.path):
            os.remove(self.path)


def _load_state() -> Dict[str, Any]:
    if os.path.exists(RETRAIN_STATE):
        with open(RETRAIN_STATE, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def _save_state(state: Dict[str, Any]) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = RETRAIN_STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    os.replace(tmp, RETRAIN_STATE)


def _incumbent() -> Dict[str, Any]:
    if not os.path.exists(LATEST_JSON):
        return {}
    with open(LATEST_JSON, encoding="utf-8") as fh:
        latest = json.load(fh)
    meta_path = os.path.join(_REPO_ROOT, "model-artifacts", latest["bundle_version"], "model_metadata.json")
    metrics = {}
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as fh:
            metrics = json.load(fh).get("metrics", {})
    return {"bundle_version": latest.get("bundle_version"), "metrics": metrics}


def deployment_gates(candidate: Dict[str, Any], incumbent: Dict[str, Any]) -> tuple[bool, Dict[str, Any]]:
    """Block promotion unless the candidate clears quality gates AND beats the incumbent."""
    gates: Dict[str, Any] = {}
    acc = candidate.get("regime_accuracy")
    gates["regime_accuracy_ok"] = acc is not None and acc >= REGIME_ACCURACY_FLOOR
    gates["non_empty_map"] = candidate.get("n_qualified_strategies", 0) > 0
    # OOS uplift gate is conditional on MODEL-006 (currently blocked on fact_signals).
    uplift = candidate.get("oos_uplift")
    gates["oos_uplift_ok"] = True if uplift is None else (uplift >= 0)
    # Must beat incumbent on the comparable score (regime accuracy here).
    inc_acc = (incumbent.get("metrics") or {}).get("regime_accuracy")
    gates["beats_incumbent"] = inc_acc is None or (acc is not None and acc >= inc_acc)
    passed = all(gates.values())
    return passed, gates


def _default_pipeline() -> Dict[str, Any]:
    """Run the real System-1 retrain steps and return candidate metrics. Heavy."""
    from src.system1.attribution import attribute as A
    from src.system1.regime import hmm_regime as H
    from src.system1.vetting import vet as V

    regime = H.run(register_mlflow=False)
    accs = [r["holdout_accuracy"] for r in regime["per_granularity"]]
    A.run(register_mlflow=False)
    vet = V.run(live=True, register_mlflow=False)
    return {
        "regime_accuracy": min(accs) if accs else None,
        "n_qualified_strategies": vet["n_qualifying"],
        "oos_uplift": None,  # MODEL-006 blocked on fact_signals
    }


def _default_promote() -> Dict[str, Any]:
    from src.system1.serializer import serialize as S

    return S.publish(register_mlflow=False)


def run(
    now: Optional[datetime] = None,
    metrics: Optional[Dict[str, Any]] = None,
    force: bool = False,
    pipeline_fn: Callable[[], Dict[str, Any]] = _default_pipeline,
    promote_fn: Callable[[], Dict[str, Any]] = _default_promote,
    cooldown_seconds: int = TR.DEFAULT_COOLDOWN_SECONDS,
    register_mlflow: bool = True,
) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    metrics = metrics or {}
    state = _load_state()

    if force:
        should_run, reasons = True, ["forced"]
    else:
        should_run, reasons = TR.decide(now, metrics, state, cooldown_seconds)

    decision: Dict[str, Any] = {
        "evaluated_at_utc": now.isoformat(), "trigger_reasons": reasons,
        "ran": False, "promoted": False,
    }
    if not should_run:
        decision["outcome"] = "no_trigger_or_cooldown"
        _log_run(decision)
        logger.info("No retrain: %s", reasons or "no triggers")
        return decision

    try:
        with SingleFlightLock():
            incumbent = _incumbent()
            candidate = pipeline_fn()
            decision["ran"] = True
            decision["candidate"] = candidate
            decision["incumbent"] = incumbent
            passed, gates = deployment_gates(candidate, incumbent)
            decision["gates"] = gates
            if not passed:
                decision["outcome"] = "skipped_gates_failed"
                logger.warning("Candidate failed deployment gates %s — keeping incumbent", gates)
            else:
                bundle = promote_fn()
                decision["promoted"] = True
                decision["bundle_version"] = bundle.get("bundle_version")
                decision["outcome"] = "promoted"
                logger.info("Promoted candidate bundle %s", bundle.get("bundle_version"))
    except RuntimeError as e:  # single-flight lock held
        decision["outcome"] = f"aborted: {e}"
        _log_run(decision)
        logger.warning("Retrain aborted: %s", e)
        return decision

    state["last_run_utc"] = now.isoformat()
    state["last_decision"] = decision["outcome"]
    if decision.get("bundle_version"):
        state["last_bundle"] = decision["bundle_version"]
    _save_state(state)
    log_path = _log_run(decision)
    decision["log_path"] = log_path
    if register_mlflow:
        _register_mlflow(decision)
    return decision


def _log_run(decision: Dict[str, Any]) -> str:
    os.makedirs(STATE_DIR, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = os.path.join(STATE_DIR, f"retrain_log_{ts}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(decision, fh, indent=2, default=str)
    return path


def _register_mlflow(decision) -> Optional[str]:
    try:
        import mlflow
        from src.system1.features.feature_pipeline import _resolve_mlflow_uri

        mlflow.set_tracking_uri(_resolve_mlflow_uri())
        mlflow.set_experiment("system1-retrain")
        with mlflow.start_run(run_name="retrain") as run_:
            mlflow.log_param("outcome", decision["outcome"])
            mlflow.log_param("trigger_reasons", ",".join(decision["trigger_reasons"])[:250])
            mlflow.log_param("promoted", decision["promoted"])
            return run_.info.run_id
    except Exception as e:  # noqa: BLE001
        logger.error("MLflow registration failed: %s", e)
        return None


def main() -> None:
    p = argparse.ArgumentParser(description="MODEL-009 retrain scheduler")
    p.add_argument("--force", action="store_true")
    p.add_argument("--no-mlflow", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    print(run(force=args.force, register_mlflow=not args.no_mlflow))


if __name__ == "__main__":
    main()
