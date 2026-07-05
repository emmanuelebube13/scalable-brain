"""MODEL-007 — serialize + publish the model bundle via StorageBackend.

Publish ordering (backend-agnostic; identical for local/gcs):
  1. compute local SHA256 for every artifact
  2. write model_metadata.json + checksums.sha256
  3. put_object all files to {bundle_version}/
  4. sha256(key) round-trip verify every object (mismatch -> delete_prefix, abort, no flip)
  5. atomic_pointer_update("latest.json", ...) ONLY after all verifies pass
  6. trim to the last RETAIN versions

Usage: python -m src.system1.serializer.serialize
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.common.storage import build_storage

logger = logging.getLogger("system1.serializer")

SCHEMA_VERSION = "1.0.0"
REGIME_MODEL_VERSION = "hmm-v1.0.0"
FEATURE_SET_VERSION = "1.0.0"
RETAIN = 5
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

# Source artifacts (local paths) -> bundle filenames.
SOURCES = {
    "hmm_model.joblib": os.path.join(_REPO_ROOT, "models", "hmm_model.joblib"),
    "strategy_weights.json": os.path.join(
        _REPO_ROOT, "results", "state", "strategy_weights.json"
    ),
    "regime_strategy_map.json": os.path.join(
        _REPO_ROOT, "results", "state", "regime_strategy_map.json"
    ),
}

# Secret patterns scanned in text artifacts before publishing.
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{16,}"),
    re.compile(
        r"(?i)(password|passwd|secret|api[_-]?key|access[_-]?key|token)\s*[:=]\s*\S{6,}"
    ),
    re.compile(r"AKIA[0-9A-Z]{16}"),
]


class PromotionRefused(Exception):
    """Raised when the serializer refuses to publish (guard tripped)."""


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _scan_secrets(path: str) -> List[str]:
    """Return matched secret snippets in a text artifact (binary files skipped)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except (UnicodeDecodeError, ValueError):
        return []  # binary (e.g. joblib) — not a place to scan for plaintext secrets
    hits = []
    for pat in SECRET_PATTERNS:
        for m in pat.findall(text):
            hits.append(str(m)[:40])
    return hits


def _bundle_version() -> str:
    # ISO-8601 UTC, filesystem-safe (colons -> dashes), immutable.
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _guard_inputs() -> Dict[str, Any]:
    missing = [name for name, p in SOURCES.items() if not os.path.exists(p)]
    if missing:
        raise PromotionRefused(f"missing required artifact(s): {missing}")
    with open(SOURCES["regime_strategy_map.json"], encoding="utf-8") as fh:
        regime_map = json.load(fh)
    n_qualified = sum(len(v) for v in regime_map.get("regimes", {}).values())
    if n_qualified == 0:
        raise PromotionRefused(
            "regime_strategy_map has zero qualifying strategies (empty map)"
        )
    return {"regime_map": regime_map, "n_qualified": n_qualified}


def publish(
    register_mlflow: bool = True,
    retain: int = RETAIN,
    metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Serialize + publish the model bundle.

    FIX-S1-006: ``metrics`` carries gate-relevant scores from the retrain candidate
    (notably ``regime_accuracy``, plus the OOS uplift) that are persisted into
    ``model_metadata.json``'s ``metrics`` block. The retrain orchestrator's
    ``_incumbent()`` reads them back so ``beats_incumbent`` can actually compare the
    next candidate to what is live. ``None`` values are dropped (the producer never
    persists a null metric). The metric key (``regime_accuracy``) is reconciled with
    the consumer in ``orchestrator.deployment_gates`` / ``orchestrator._incumbent``.
    """
    storage = build_storage()
    ctx = _guard_inputs()
    bundle_version = _bundle_version()

    # 1. local checksums + secret scan
    artifacts: Dict[str, Dict[str, Any]] = {}
    for name, path in SOURCES.items():
        secrets = _scan_secrets(path)
        if secrets:
            raise PromotionRefused(f"secret detected in {name}: {secrets[:1]}")
        artifacts[name] = {"sha256": _sha256(path), "bytes": os.path.getsize(path)}

    vetting_run_id = ctx["regime_map"].get("qualification_run_id")
    # FIX-S1-006: persist gate-relevant candidate metrics (e.g. regime_accuracy) alongside the
    # always-present n_qualified_strategies so the incumbent comparison is no longer vacuous.
    bundle_metrics: Dict[str, Any] = {"n_qualified_strategies": ctx["n_qualified"]}
    if metrics:
        bundle_metrics.update({k: v for k, v in metrics.items() if v is not None})
    metadata = {
        "bundle_version": bundle_version,
        "schema_version": SCHEMA_VERSION,
        "created_by": "computer-1",
        "regime_model_version": REGIME_MODEL_VERSION,
        "feature_set_version": FEATURE_SET_VERSION,
        "vetting_run_id": vetting_run_id,
        "mlflow_run_id": None,
        "artifacts": artifacts,
        "metrics": bundle_metrics,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    # 2. stage metadata + checksums locally, scan metadata too
    staging = tempfile.mkdtemp(prefix="bundle_")
    meta_path = os.path.join(staging, "model_metadata.json")
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2, sort_keys=True)
    if _scan_secrets(meta_path):
        raise PromotionRefused("secret detected in model_metadata.json")
    checksums_path = os.path.join(staging, "checksums.sha256")
    with open(checksums_path, "w", encoding="utf-8") as fh:
        for name, info in artifacts.items():
            fh.write(f"{info['sha256']}  {name}\n")
        fh.write(f"{_sha256(meta_path)}  model_metadata.json\n")

    # 3. upload all files to the immutable timestamped prefix
    local_files = {
        **SOURCES,
        "model_metadata.json": meta_path,
        "checksums.sha256": checksums_path,
    }
    local_sha = {name: _sha256(p) for name, p in local_files.items()}
    try:
        for name, p in local_files.items():
            storage.put_object(f"{bundle_version}/{name}", p, encrypt=True)
        # 4. round-trip verify every object BEFORE flipping the pointer
        for name in local_files:
            key = f"{bundle_version}/{name}"
            if storage.sha256(key) != local_sha[name]:
                raise PromotionRefused(f"round-trip checksum mismatch for {name}")
    except Exception:
        storage.delete_prefix(
            bundle_version
        )  # never leave a partial version pointed-to
        shutil.rmtree(staging, ignore_errors=True)
        raise

    # 5. atomic pointer flip (only after all verifies passed)
    latest = {
        "bundle_version": bundle_version,
        "path": f"model-artifacts/{bundle_version}/",
        "metadata_sha256": local_sha["model_metadata.json"],
        "promoted_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    storage.atomic_pointer_update("latest.json", latest)

    # 6. retention: keep last `retain` versions
    trimmed = _trim_versions(storage, keep=retain, current=bundle_version)
    shutil.rmtree(staging, ignore_errors=True)

    if register_mlflow:
        metadata["mlflow_run_id"] = _register_mlflow(bundle_version, metadata)

    result = {
        "bundle_version": bundle_version,
        "n_qualified_strategies": ctx["n_qualified"],
        "artifacts": list(local_files.keys()),
        "trimmed_versions": trimmed,
        "latest": latest,
    }
    logger.info(
        "Published bundle %s (%d qualifiers)", bundle_version, ctx["n_qualified"]
    )
    return result


def _list_versions(storage) -> List[str]:
    versions = set()
    for key in storage.list(""):
        top = key.split(os.sep)[0]
        if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z$", top):
            versions.add(top)
    return sorted(versions)


def _trim_versions(storage, keep: int, current: str) -> List[str]:
    versions = _list_versions(storage)
    if len(versions) <= keep:
        return []
    to_delete = versions[: len(versions) - keep]
    for v in to_delete:
        if v != current:
            storage.delete_prefix(v)
    return to_delete


def _register_mlflow(bundle_version, metadata) -> str:
    try:
        import mlflow
        from src.system1.features.feature_pipeline import _resolve_mlflow_uri

        mlflow.set_tracking_uri(_resolve_mlflow_uri())
        mlflow.set_experiment("system1-serializer")
        with mlflow.start_run(run_name=bundle_version) as run:
            mlflow.log_param("bundle_version", bundle_version)
            mlflow.log_param("regime_model_version", REGIME_MODEL_VERSION)
            mlflow.log_metric(
                "n_qualified_strategies", metadata["metrics"]["n_qualified_strategies"]
            )
            return run.info.run_id
    except Exception as e:  # noqa: BLE001
        logger.error("MLflow registration failed: %s", e)
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="MODEL-007 serializer/registry")
    parser.add_argument("--no-mlflow", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    try:
        print(publish(register_mlflow=not args.no_mlflow))
    except PromotionRefused as e:
        logger.error("PROMOTION REFUSED: %s", e)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
