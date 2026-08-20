"""Publish the promoted gatekeeper champion bundle to object storage (GCS/local).

Follows the MODEL-007 publish contract (see src/common/storage/README.md) with an
added "beats incumbent" gate so a WORSE model can never take over the live pointer.

Ordering:
  1. read candidate metrics from the local champion manifest (OOS uplift)
  2. read the incumbent (current models/gatekeeper/latest.json) metrics, if any
  3. GATE: promote only if candidate uplift is significant AND >= incumbent uplift
           (first-ever publish fails open; --force overrides the gate)
  4. upload all files to an immutable, versioned prefix models/gatekeeper/<version>/
  5. SHA256 round-trip verify every object BEFORE advancing the pointer
     (mismatch -> delete the partial version, abort, pointer NOT flipped)
  6. archive the superseded pointer to models/gatekeeper/previous.json (rollback breadcrumb)
  7. atomic_pointer_update("models/gatekeeper/latest.json", ...) ONLY after all verify

The old model is NEVER overwritten: object storage is immutable, so each version lives
in its own folder forever (kept until retention trims the oldest). Overriding = moving
the pointer, not deleting the old artifacts.

Usage:
    python -m src.serializer.publish_gatekeeper            # publish live champion (gated)
    python -m src.serializer.publish_gatekeeper --force    # publish even if not better
    python -m src.serializer.publish_gatekeeper --dry-run  # publish PROPOSED bundle instead
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from dotenv import load_dotenv

from src.common.storage import build_storage

logger = logging.getLogger("system1.publish_gatekeeper")

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MODELS_DIR = os.path.join(_REPO_ROOT, "models")
MODEL_ID = "gatekeeper"
POINTER_KEY = f"models/{MODEL_ID}/latest.json"
PREVIOUS_KEY = f"models/{MODEL_ID}/previous.json"

BUNDLE_FILES = ("model.pkl", "preprocessor.pkl", "manifest.json")


class PublishRefused(Exception):
    """Raised when the incumbent gate blocks promotion."""


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _version(manifest_path: str) -> str:
    """Immutable, sortable version: <UTC timestamp>-<manifest sha256[:8]>."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"{ts}-{_sha256(manifest_path)[:8]}"


def _candidate_uplift(manifest_path: str) -> Tuple[float, bool]:
    """Return (uplift, significant) from a champion manifest."""
    with open(manifest_path, encoding="utf-8") as fh:
        m = json.load(fh)
    oos = m.get("oos_uplift", {})
    return float(oos.get("uplift", float("-inf"))), bool(oos.get("significant", False))


def _incumbent_uplift(storage) -> Optional[float]:
    """Uplift of the currently-pointed gatekeeper bundle, or None if none published."""
    if not storage.exists(POINTER_KEY):
        return None
    with tempfile.TemporaryDirectory() as td:
        ptr_path = os.path.join(td, "latest.json")
        storage.get_object(POINTER_KEY, ptr_path)
        with open(ptr_path, encoding="utf-8") as fh:
            ptr = json.load(fh)
        version = ptr.get("version")
        if not version:
            return None
        man_key = f"models/{MODEL_ID}/{version}/champion_manifest.json"
        if not storage.exists(man_key):
            return None
        man_path = os.path.join(td, "champion_manifest.json")
        storage.get_object(man_key, man_path)
        with open(man_path, encoding="utf-8") as fh:
            return float(json.load(fh).get("oos_uplift", {}).get("uplift", float("-inf")))


def _read_pointer(storage, key: str) -> Optional[Dict[str, Any]]:
    if not storage.exists(key):
        return None
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "ptr.json")
        storage.get_object(key, p)
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)


def publish(dry_run: bool = False, force: bool = False) -> Dict[str, Any]:
    prefix_local = "proposed_champion" if dry_run else "champion"

    local = {
        name: os.path.join(MODELS_DIR, f"{prefix_local}_{name}") for name in BUNDLE_FILES
    }
    missing = [p for p in local.values() if not os.path.exists(p)]
    if missing:
        raise SystemExit(f"missing artifact(s): {missing} — promote the champion first")

    storage = build_storage()

    # --- incumbent gate -----------------------------------------------------
    cand_uplift, cand_sig = _candidate_uplift(local["manifest.json"])
    inc_uplift = _incumbent_uplift(storage)
    if inc_uplift is None:
        logger.info("no incumbent gatekeeper on GCP — first publish (gate fails open)")
        better = True
    else:
        better = cand_sig and cand_uplift >= inc_uplift
        logger.info(
            "candidate uplift=%.6f (sig=%s) vs incumbent uplift=%.6f -> %s",
            cand_uplift, cand_sig, inc_uplift, "BETTER" if better else "NOT better",
        )
    if not better and not force:
        raise PublishRefused(
            f"candidate uplift {cand_uplift:.6f} (sig={cand_sig}) does not beat "
            f"incumbent {inc_uplift:.6f}; use --force to override"
        )

    # --- upload immutable versioned bundle ----------------------------------
    version = _version(local["manifest.json"])
    remote_prefix = f"models/{MODEL_ID}/{version}"
    local_sha = {name: _sha256(p) for name, p in local.items()}
    logger.info("publishing bundle -> %s", remote_prefix)
    try:
        for name, p in local.items():
            storage.put_object(f"{remote_prefix}/champion_{name}", p, encrypt=True)
        for name in local:
            key = f"{remote_prefix}/champion_{name}"
            if storage.sha256(key) != local_sha[name]:
                raise RuntimeError(f"round-trip checksum mismatch: {name}")
    except Exception:
        storage.delete_prefix(remote_prefix)  # never leave a half-uploaded version
        raise

    # --- archive the superseded pointer (rollback breadcrumb) ---------------
    prev = _read_pointer(storage, POINTER_KEY)
    superseded = prev.get("version") if prev else None
    if prev is not None:
        storage.atomic_pointer_update(PREVIOUS_KEY, prev)

    # --- flip the live pointer LAST (atomic) --------------------------------
    pointer = {
        "model_id": MODEL_ID,
        "version": version,
        "path": f"{remote_prefix}/",
        "manifest_sha256": local_sha["manifest.json"],
        "oos_uplift": cand_uplift,
        "supersedes": superseded,
        "promoted_at_utc": datetime.now(timezone.utc).isoformat(),
        "forced": force and not better,
        "dry_run": dry_run,
    }
    storage.atomic_pointer_update(POINTER_KEY, pointer)
    logger.info(
        "promoted %s (supersedes %s); old artifacts retained at their own folder",
        version, superseded,
    )
    print(json.dumps({"published": remote_prefix, "pointer": POINTER_KEY, **pointer}, indent=2))
    return pointer


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish gatekeeper champion to object storage")
    parser.add_argument("--dry-run", action="store_true",
                        help="Publish models/proposed_champion_* instead of the live champion.")
    parser.add_argument("--force", action="store_true",
                        help="Promote even if the candidate does not beat the incumbent uplift.")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    load_dotenv(os.path.join(_REPO_ROOT, ".env"))
    try:
        publish(dry_run=args.dry_run, force=args.force)
    except PublishRefused as e:
        logger.error("PUBLISH REFUSED: %s", e)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
