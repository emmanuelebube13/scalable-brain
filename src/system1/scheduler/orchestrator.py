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
import tempfile
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from src.system1.scheduler import triggers as TR

logger = logging.getLogger("system1.scheduler")

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
STATE_DIR = os.path.join(_REPO_ROOT, "results", "state")
MODELS_DIR = os.path.join(_REPO_ROOT, "models")
RETRAIN_STATE = os.path.join(STATE_DIR, "retrain_state.json")
LOCK_FILE = os.path.join(STATE_DIR, "retrain.lock")
REGIME_ACCURACY_FLOOR = 0.70
# FIX-S1-006: the gatekeeper's OOS uplift (MODEL-006) must clear this absolute floor AND be
# bootstrap-significant for the candidate to promote. 0.0 keeps the historical "non-negative
# uplift" threshold but now *also* requires statistical significance (a positive-but-noisy
# uplift no longer passes). Bump this above 0.0 to demand a minimum measured edge.
MIN_UPLIFT = 0.0
# FIX-S1-011: anti-ratchet tolerance for the head-to-head `beats_incumbent` gate.
#
# The gate used to be a bare `acc >= inc_acc`. Because every promotion republishes the
# challenger's own accuracy as the next baseline, that made the baseline monotonically
# non-decreasing — a high-water mark on a *noisy* estimate. Such a process converges on the
# luckiest draw ever observed and then blocks everything behind it, including models that are
# genuinely better but happened to sample lower. The live baseline had already climbed
# 0.717 -> 0.8603 -> 0.965 in three promotions.
#
# The challenger must now stay within this relative band of the live incumbent. The band is
# symmetric in effect: the bar tracks whatever is *currently live* rather than the best value
# ever seen, so it can fall as well as rise and cannot compound upward.
#
# Downward drift is bounded by the absolute REGIME_ACCURACY_FLOOR, which still binds — a
# sequence of small regressions can never walk the model below 0.70.
BEATS_INCUMBENT_TOLERANCE = 0.965


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
    """Read the currently-live bundle pointer + its gate metrics from the STORAGE BACKEND.

    Fix (2026-07-01): read the incumbent through the same ``build_storage()`` backend that
    ``serialize.publish`` writes to — the ``{MODEL_PREFIX}/latest.json`` pointer and
    ``{MODEL_PREFIX}/<bundle_version>/model_metadata.json`` — rather than a hard-coded local
    ``model-artifacts/latest.json``. Previously the consumer read a local file while the
    producer published to GCS (``STORAGE_PROVIDER=gcs``), so the pointer diverged: after a
    real promotion the local file stayed stale and ``_incumbent`` returned an old/absent
    ``regime_accuracy``, so ``beats_incumbent`` never bound on the next retrain. Going through
    the backend keeps producer and consumer consistent on every backend (local dev reads the
    same local file it always did; GCS reads the truly-live bundle Computer 2 pulls).

    FIX-S1-010 (orphaned incumbent): resolution now also falls back to the **top-level
    model-set manifest** when the prefixed pointer is absent. This is not hypothetical —
    it already cost a real comparison. When ``MODEL_PREFIX = "system1"`` was introduced,
    the pre-existing bundle was still published at the bucket ROOT
    (``2026-07-01T12-56-32Z/``), so ``system1/latest.json`` did not exist. On the
    2026-07-19 retrain ``_incumbent()`` returned ``{}``, ``beats_incumbent`` took its
    documented first-publish fail-open branch, and the candidate was promoted **without
    ever being compared to its predecessor** — the regression gate silently reset itself
    during a storage-layout migration.

    The returned dict carries ``resolution`` so the caller can tell the three cases apart
    and record which one applied:

    * ``"prefixed"`` — found at ``{MODEL_PREFIX}/latest.json`` (the normal path)
    * ``"legacy_model_set"`` — found via the top-level ``latest.json`` manifest
    * ``"absent"`` — genuinely nothing published anywhere; only here is fail-open correct
    """
    from src.common.storage import build_storage
    from src.system1.serializer.serialize import MODEL_PREFIX, POINTER_KEY

    storage = build_storage()

    def _load_metrics(td: str, meta_key: str) -> Dict[str, Any]:
        if not storage.exists(meta_key):
            return {}
        meta_path = os.path.join(td, "model_metadata.json")
        storage.get_object(meta_key, meta_path)
        with open(meta_path, encoding="utf-8") as fh:
            return json.load(fh).get("metrics", {})

    with tempfile.TemporaryDirectory() as td:
        if storage.exists(POINTER_KEY):
            latest_path = os.path.join(td, "latest.json")
            storage.get_object(POINTER_KEY, latest_path)
            with open(latest_path, encoding="utf-8") as fh:
                latest = json.load(fh)
            bundle_version = latest.get("bundle_version")
            metrics = (
                _load_metrics(
                    td, f"{MODEL_PREFIX}/{bundle_version}/model_metadata.json"
                )
                if bundle_version
                else {}
            )
            return {
                "bundle_version": bundle_version,
                "metrics": metrics,
                "resolution": "prefixed",
            }

        # Fallback: a model set published before the prefix migration. Its manifest names
        # model_metadata.json by full path, so the incumbent stays comparable across the
        # layout change instead of the gate resetting.
        from src.system1.serializer.publish_model_set import POINTER_KEY as SET_POINTER

        if storage.exists(SET_POINTER):
            set_path = os.path.join(td, "model_set.json")
            storage.get_object(SET_POINTER, set_path)
            with open(set_path, encoding="utf-8") as fh:
                model_set = json.load(fh)
            meta = next(
                (
                    a
                    for a in model_set.get("artifacts", [])
                    if a.get("name") == "model_metadata.json"
                ),
                None,
            )
            if meta and meta.get("path"):
                logger.warning(
                    "no bundle at %s — incumbent resolved from the legacy model set %s",
                    POINTER_KEY,
                    model_set.get("model_set_id"),
                )
                return {
                    "bundle_version": model_set.get("system1_bundle_version")
                    or model_set.get("model_set_id"),
                    "metrics": _load_metrics(td, str(meta["path"])),
                    "resolution": "legacy_model_set",
                }

    logger.warning(
        "NO INCUMBENT FOUND at %s or the top-level model set — beats_incumbent will "
        "FAIL OPEN. This is correct only for a genuine first-ever publish; if a model is "
        "already live, the storage layout has drifted and the regression gate is inert.",
        POINTER_KEY,
    )
    return {"resolution": "absent"}


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
    * ``beats_incumbent`` — the candidate's ``regime_accuracy`` is within
      ``BEATS_INCUMBENT_TOLERANCE`` of the incumbent's persisted
      ``metrics["regime_accuracy"]`` (the serializer writes that key; see
      ``serialize.publish``). **FIX-S1-011**: this was a bare ``>=``, which turned
      the baseline into a monotonically-climbing high-water mark on a noisy
      estimate and would eventually have blocked every challenger. It now tracks
      the *currently live* incumbent within a tolerance band, so the bar can fall
      as well as rise; ``regime_accuracy_ok`` bounds any downward drift.

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
    # Must not regress against the incumbent on the comparable score (regime accuracy here).
    # FIX-S1-011: compared against the *currently live* incumbent within a tolerance band,
    # not against a historical high-water mark — see BEATS_INCUMBENT_TOLERANCE. No incumbent
    # metric (first-ever comparison) => fail open; the absolute gates above still bind.
    inc_acc = (incumbent.get("metrics") or {}).get("regime_accuracy")
    if inc_acc is None:
        gates["beats_incumbent"] = True
    elif acc is None:
        gates["beats_incumbent"] = False
    else:
        gates["beats_incumbent"] = acc >= inc_acc * BEATS_INCUMBENT_TOLERANCE
    gates["beats_incumbent_detail"] = {
        "candidate_regime_accuracy": acc,
        "incumbent_regime_accuracy": inc_acc,
        "required": (
            None if inc_acc is None else round(inc_acc * BEATS_INCUMBENT_TOLERANCE, 6)
        ),
        "tolerance": BEATS_INCUMBENT_TOLERANCE,
    }
    # Only the boolean entries are gates; `*_detail` keys carry evidence for the retrain log
    # and must never influence the verdict (a truthy dict would silently "pass").
    passed = all(v for k, v in gates.items() if isinstance(v, bool))
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


def _promote_gatekeeper() -> Dict[str, Any]:
    """Promote the audited dry-run gatekeeper to champion and publish it (FIX-S1-010).

    ``_gatekeeper_metrics()`` trains the gatekeeper in dry-run to produce the OOS uplift
    that the ``oos_uplift_ok`` gate approved. This ships **that same artifact** — not a
    retrain, which would publish a model whose uplift is not the number the gate cleared.

    A refusal here does NOT fail the promotion. ``publish_gatekeeper`` refuses when the
    candidate does not beat the incumbent's uplift, which is a legitimate outcome: the
    regime/weights bundle can still be an improvement while the gatekeeper is not. The
    model set published afterwards is assembled from whatever the sub-pointers hold, so a
    refusal simply keeps the incumbent gatekeeper paired with the new bundle.
    """
    from src.system1.gatekeeper.promote import ProposedBundleInvalid, promote_proposed
    from src.system1.serializer import publish_gatekeeper as PG

    # FIX-S1-010 staged rollout: the wiring exists but is OPT-IN. The recalibrated
    # gatekeeper raises aggregate approval from 17.2% to ~21.6%, which is a real change in
    # trade volume for System 2/3 to absorb, so it must not ride along with the first
    # scheduled retrain after this fix lands. Without this flag, rollout "Stage 1" (code
    # applied, nothing promoted) would be undone automatically by the next Sunday trigger.
    # Set GATEKEEPER_AUTOPROMOTE=true only at rollout Stage 3.
    if os.environ.get("GATEKEEPER_AUTOPROMOTE", "false").strip().lower() != "true":
        logger.info(
            "gatekeeper auto-promotion disabled (GATEKEEPER_AUTOPROMOTE not set) — "
            "proposed bundle left in place; live champion untouched"
        )
        return {"promoted": False, "reason": "autopromote_disabled"}

    try:
        promote_proposed(MODELS_DIR)
    except (ProposedBundleInvalid, FileNotFoundError) as e:
        logger.warning("gatekeeper not promoted (no valid proposed bundle): %s", e)
        return {"promoted": False, "reason": str(e)}
    try:
        pointer = PG.publish()
        logger.info("gatekeeper published: %s", pointer.get("version"))
        return {"promoted": True, "version": pointer.get("version")}
    except PG.PublishRefused as e:
        logger.info("gatekeeper publish refused (incumbent retained): %s", e)
        return {"promoted": False, "reason": f"refused: {e}"}


def _default_promote(candidate: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Publish the bundle, persisting the candidate's gate-relevant metrics into the manifest.

    FIX-S1-006: ``regime_accuracy`` (and the OOS uplift) are forwarded to ``serialize.publish`` so
    the next run's ``_incumbent()`` can read them back and ``beats_incumbent`` can actually compare.

    FIX-S1-010: the promote now completes the whole set — regime/weights bundle, then the
    audited gatekeeper, then the top-level model-set manifest that System 2 reads. The
    manifest is written LAST and only ever describes what the sub-pointers already hold,
    so a consumer never sees a set naming an artifact that is not live.
    """
    from src.system1.serializer import serialize as S

    candidate = candidate or {}
    metrics = {
        "regime_accuracy": candidate.get("regime_accuracy"),
        "oos_uplift": candidate.get("oos_uplift"),
        "oos_uplift_significant": candidate.get("oos_uplift_significant"),
    }
    bundle = S.publish(register_mlflow=False, metrics=metrics)
    bundle["gatekeeper"] = _promote_gatekeeper()

    from src.system1.serializer import publish_model_set as PMS

    # Also staged: flipping the top-level manifest changes which model set System 2
    # downloads. That pointer currently names the 2026-07-01 set, so refreshing it is a
    # live behaviour change in its own right and does not belong in rollout Stage 1.
    # Set MODEL_SET_AUTOPUBLISH=true to hand the manifest over to the governed writer.
    if os.environ.get("MODEL_SET_AUTOPUBLISH", "false").strip().lower() != "true":
        logger.info(
            "top-level model set NOT refreshed (MODEL_SET_AUTOPUBLISH not set) — "
            "run `python -m src.system1.serializer.publish_model_set` to publish it"
        )
        bundle["model_set_published"] = False
        return bundle

    try:
        model_set = PMS.publish()
        bundle["model_set_id"] = model_set.get("model_set_id")
    except PMS.ModelSetRefused as e:
        # The sub-pointers are live and correct; only the top-level manifest is stale.
        # Surfaced loudly rather than raised: rolling back a verified publish over a
        # packaging failure would leave the bundle live but unreferenced either way.
        bundle["model_set_error"] = str(e)
        logger.error("top-level model set NOT updated: %s", e)
    return bundle


def _default_analytics() -> Dict[str, Any]:
    """S1-EXPORT-002 analytics refresh. Injectable so tests never touch the real
    staging dir (a tracked path) or attempt a real upload — see ``run()``."""
    from src.system1.analytics import publish_analytics as PA

    return PA.run()


def run(
    now: Optional[datetime] = None,
    metrics: Optional[Dict[str, Any]] = None,
    force: bool = False,
    pipeline_fn: Callable[[], Dict[str, Any]] = _default_pipeline,
    promote_fn: Callable[[Dict[str, Any]], Dict[str, Any]] = _default_promote,
    # Resolved in-body, not bound here: a default argument captures the function
    # object at def-time, which monkeypatching the module attribute cannot reach.
    analytics_fn: Optional[Callable[[], Dict[str, Any]]] = None,
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
            # FIX-S1-010: record HOW the incumbent was resolved. A `beats_incumbent: true`
            # alongside `"absent"` means the gate did not compare anything — the 2026-07-19
            # promotion looked identical to a real pass in the log until this was recorded.
            decision["incumbent_resolution"] = incumbent.get("resolution", "unknown")
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
                # S1-EXPORT-002: refresh the read-only analytics bundle after a
                # successful promote. Derived data only — a failure here must never
                # fail or roll back the promotion itself.
                try:
                    _analytics = analytics_fn or _default_analytics
                    decision["analytics_version"] = _analytics().get("version")
                except Exception as e:  # noqa: BLE001
                    decision["analytics_error"] = str(e)
                    logger.error(
                        "analytics publish failed (promotion unaffected): %s", e
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
