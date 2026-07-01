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
# FIX-S1-006: the gatekeeper's OOS uplift (MODEL-006) must clear this absolute floor AND be
# bootstrap-significant for the candidate to promote. 0.0 keeps the historical "non-negative
# uplift" threshold but now *also* requires statistical significance (a positive-but-noisy
# uplift no longer passes). Bump this above 0.0 to demand a minimum measured edge.
MIN_UPLIFT = 0.0


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
            raise RuntimeError(
                "another retrain run holds the single-flight lock"
            ) from e
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
    meta_path = os.path.join(
        _REPO_ROOT, "model-artifacts", latest["bundle_version"], "model_metadata.json"
    )
    metrics = {}
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as fh:
            metrics = json.load(fh).get("metrics", {})
    return {"bundle_version": latest.get("bundle_version"), "metrics": metrics}


def deployment_gates(
    candidate: Dict[str, Any],
    incumbent: Dict[str, Any],
    allow_missing_uplift: bool = False,
) -> tuple[bool, Dict[str, Any]]:
    """Block promotion unless the candidate clears quality gates AND beats the incumbent.

    Four gates, all of which must pass:

    * ``regime_accuracy_ok`` — absolute floor (``REGIME_ACCURACY_FLOOR``).
    * ``non_empty_map`` — at least one qualifying strategy.
    * ``oos_uplift_ok`` — the gatekeeper's measured OOS uplift (MODEL-006) is
      ``>= MIN_UPLIFT`` **and** bootstrap-significant. **FIX-S1-006**: the old
      ``None ⇒ True`` convenience branch made this gate structurally inert (the
      pipeline always passed ``oos_uplift=None``). It now **FAILS CLOSED** when the
      gatekeeper result is genuinely missing — ``oos_uplift is None`` blocks
      promotion unless the operator passes ``allow_missing_uplift=True``
      (CLI ``--allow-missing-uplift``). There is no silent ``None ⇒ pass``.
    * ``beats_incumbent`` — the candidate's ``regime_accuracy`` is ``>=`` the
      incumbent's persisted ``metrics["regime_accuracy"]`` (the serializer now
      writes that key; see ``serialize.publish``).

    First-ever comparison policy (no incumbent metric yet): the *relative*
    ``beats_incumbent`` gate **FAILS OPEN** — there is nothing to beat, so a
    candidate that clears the *absolute* floors (accuracy, non-empty map, and a
    significant OOS uplift) is allowed to become the first incumbent. The absolute
    quality gates (including ``oos_uplift_ok``) still apply, so the bootstrap model
    must still demonstrate edge; only the head-to-head comparison is waived.
    """
    gates: Dict[str, Any] = {}
    acc = candidate.get("regime_accuracy")
    gates["regime_accuracy_ok"] = acc is not None and acc >= REGIME_ACCURACY_FLOOR
    gates["non_empty_map"] = candidate.get("n_qualified_strategies", 0) > 0
    # OOS uplift gate (MODEL-006): require a non-negative, bootstrap-significant uplift.
    # Missing gatekeeper result => fail closed unless explicitly overridden (never a silent pass).
    uplift = candidate.get("oos_uplift")
    significant = candidate.get("oos_uplift_significant")
    if uplift is None:
        gates["oos_uplift_ok"] = bool(allow_missing_uplift)
    else:
        gates["oos_uplift_ok"] = uplift >= MIN_UPLIFT and bool(significant)
    # Must beat incumbent on the comparable score (regime accuracy here). No incumbent
    # metric (first-ever comparison) => fail open; the absolute gates above still bind.
    inc_acc = (incumbent.get("metrics") or {}).get("regime_accuracy")
    gates["beats_incumbent"] = inc_acc is None or (acc is not None and acc >= inc_acc)
    passed = all(gates.values())
    return passed, gates


def _gatekeeper_metrics() -> Dict[str, Any]:
    """Run MODEL-006 (gatekeeper) LOG-ONLY (dry_run) and surface its OOS uplift + significance.

    FIX-S1-006: this threads the gatekeeper result into the candidate so ``oos_uplift_ok`` is a
    real gate. The dry-run writes ``models/proposed_champion_*`` only and never overwrites the live
    champion (global rule #1). Returns ``{}`` when the gatekeeper is genuinely unavailable (e.g.
    ``fact_signals`` empty / training raises) — the caller then leaves ``oos_uplift=None``, which
    fails the gate **closed** unless ``--allow-missing-uplift`` is set.
    """
    try:
        from src.system1.gatekeeper import train as G

        res = G.run(register_mlflow=False, dry_run=True)
        return {
            "oos_uplift": res.get("oos_uplift"),
            "significant": res.get("significant"),
        }
    except (
        Exception
    ) as e:  # noqa: BLE001 — any gatekeeper failure => uplift unavailable
        logger.warning(
            "Gatekeeper (MODEL-006) unavailable; oos_uplift gate will fail closed: %s",
            e,
        )
        return {}


def _default_pipeline() -> Dict[str, Any]:
    """Run the real System-1 retrain steps and return candidate metrics. Heavy."""
    from src.system1.attribution import attribute as A
    from src.system1.regime import hmm_regime as H
    from src.system1.vetting import vet as V

    regime = H.run(register_mlflow=False)
    accs = [r["holdout_accuracy"] for r in regime["per_granularity"]]
    A.run(register_mlflow=False)
    vet = V.run(live=True, register_mlflow=False)
    gk = _gatekeeper_metrics()
    return {
        "regime_accuracy": min(accs) if accs else None,
        "n_qualified_strategies": vet["n_qualifying"],
        # FIX-S1-006: MODEL-006 OOS uplift threaded in (None when gatekeeper unavailable => the
        # oos_uplift gate fails closed; it is no longer hard-coded to a silent pass).
        "oos_uplift": gk.get("oos_uplift"),
        "oos_uplift_significant": gk.get("significant"),
    }


def _default_promote(candidate: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Publish the bundle, persisting the candidate's gate-relevant metrics into the manifest.

    FIX-S1-006: ``regime_accuracy`` (and the OOS uplift) are forwarded to ``serialize.publish`` so
    the next run's ``_incumbent()`` can read them back and ``beats_incumbent`` can actually compare.
    """
    from src.system1.serializer import serialize as S

    candidate = candidate or {}
    metrics = {
        "regime_accuracy": candidate.get("regime_accuracy"),
        "oos_uplift": candidate.get("oos_uplift"),
        "oos_uplift_significant": candidate.get("oos_uplift_significant"),
    }
    return S.publish(register_mlflow=False, metrics=metrics)


def run(
    now: Optional[datetime] = None,
    metrics: Optional[Dict[str, Any]] = None,
    force: bool = False,
    pipeline_fn: Callable[[], Dict[str, Any]] = _default_pipeline,
    promote_fn: Callable[[Dict[str, Any]], Dict[str, Any]] = _default_promote,
    cooldown_seconds: int = TR.DEFAULT_COOLDOWN_SECONDS,
    register_mlflow: bool = True,
    allow_missing_uplift: bool = False,
) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    metrics = metrics or {}
    state = _load_state()

    if force:
        should_run, reasons = True, ["forced"]
    else:
        should_run, reasons = TR.decide(now, metrics, state, cooldown_seconds)

    decision: Dict[str, Any] = {
        "evaluated_at_utc": now.isoformat(),
        "trigger_reasons": reasons,
        "ran": False,
        "promoted": False,
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
            passed, gates = deployment_gates(candidate, incumbent, allow_missing_uplift)
            decision["gates"] = gates
            if not passed:
                decision["outcome"] = "skipped_gates_failed"
                logger.warning(
                    "Candidate failed deployment gates %s — keeping incumbent", gates
                )
            else:
                bundle = promote_fn(candidate)
                decision["promoted"] = True
                decision["bundle_version"] = bundle.get("bundle_version")
                decision["outcome"] = "promoted"
                logger.info(
                    "Promoted candidate bundle %s", bundle.get("bundle_version")
                )
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
            mlflow.log_param(
                "trigger_reasons", ",".join(decision["trigger_reasons"])[:250]
            )
            mlflow.log_param("promoted", decision["promoted"])
            return run_.info.run_id
    except Exception as e:  # noqa: BLE001
        logger.error("MLflow registration failed: %s", e)
        return None


def main() -> None:
    p = argparse.ArgumentParser(description="MODEL-009 retrain scheduler")
    p.add_argument("--force", action="store_true")
    p.add_argument("--no-mlflow", action="store_true")
    p.add_argument(
        "--allow-missing-uplift",
        action="store_true",
        help="Permit promotion when the gatekeeper (MODEL-006) OOS uplift is unavailable. "
        "Without this flag the oos_uplift gate FAILS CLOSED on a missing result.",
    )
    args = p.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    print(
        run(
            force=args.force,
            register_mlflow=not args.no_mlflow,
            allow_missing_uplift=args.allow_missing_uplift,
        )
    )


if __name__ == "__main__":
    main()
