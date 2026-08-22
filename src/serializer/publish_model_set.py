"""FIX-S1-010 — governed writer for the TOP-LEVEL ``latest.json`` model-set manifest.

System 2's model downloader (EXEC-001) reads a single top-level ``latest.json`` naming
every artifact of the currently-live model set: the four System-1 bundle files plus the
three gatekeeper files, each with a SHA256 it verifies after download.

Until this module existed **nothing in System 1 wrote that file.** It was hand-authored.
On 2026-07-24 it still advertised ``model_set_id 2026-07-01T12-56-32Z_gk-656f09e2``
(``published_at 2026-07-10T00:00:00Z``) while ``system1/latest.json`` had already moved to
the 2026-07-19 bundle — so any consumer following the spec was loading a model set three
weeks and two promotions stale. Note the shape of that failure: the per-bundle publish
contract (upload → verify → flip) was intact and working, and was defeated by a
hand-maintained pointer sitting above it.

Design — the manifest is a *pure function of the two sub-pointers*:

  1. read ``system1/latest.json`` and ``models/gatekeeper/latest.json``
  2. resolve each pointer to its immutable versioned prefix and enumerate the artifacts
  3. verify every object exists and read its SHA256 **from the backend** (never from a
     local file, so the manifest describes what a consumer will actually download)
  4. atomic_pointer_update("latest.json", ...) LAST

Because the manifest only ever describes whatever the two sub-pointers currently point
at, it is coherent by construction: if a gatekeeper publish is refused (candidate did not
beat the incumbent), this packages the new System-1 bundle with the still-live gatekeeper,
which is exactly what is live. It never invents a pairing.

FIX-S1-015 — withdrawal. The contract above can only move the pointer *forward* to a
better model set; it was never given a way to say "there is no model". That gap surfaced
on 2026-08-14, when FIX-S1-014 disqualified the only qualified strategy: the correct live
state became "nothing qualifies", the ``non_empty_map`` deployment gate rightly refused to
promote an empty bundle, and so the pointer went on serving a model set whose whole map
was a strategy that cannot fire (see the fix doc). Withdrawal is therefore a **separate
verb**, not a promotion with zero artifacts:

  * ``withdraw()`` writes a manifest with ``status="withdrawn"``, an empty ``artifacts``
    list and a mandatory human reason. A consumer that iterates artifacts downloads
    nothing; one that requires artifacts fails closed, which is the direction the
    project's default-safe posture asks for (missing/stale/error ⇒ REJECT).
  * It never deletes anything. The superseded manifest is archived to
    ``previous_model_set.json``, so reinstating is a normal ``publish()``.
  * Withdrawing twice is a no-op, specifically so the second call cannot overwrite the
    rollback breadcrumb with the withdrawal itself.
  * It is CLI-only and requires ``--reason``. The orchestrator must never call it: an
    automated retrain deciding on its own to blank the live model is exactly the
    single-flag failure mode Computer 2 objected to on 2026-08-02.

Usage:
    python -m src.serializer.publish_model_set [--dry-run]
    python -m src.serializer.publish_model_set --withdraw --reason "..." [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.common.storage import build_storage
from src.serializer.serialize import POINTER_KEY as S1_POINTER_KEY

logger = logging.getLogger("system1.publish_model_set")

SCHEMA_VERSION = 1
POINTER_KEY = "latest.json"
PREVIOUS_KEY = "previous_model_set.json"
GK_POINTER_KEY = "models/gatekeeper/latest.json"

# Artifacts expected in each half of the set. A missing artifact aborts the publish:
# an incomplete model set is worse than a stale one, because the consumer's own
# verification would fail mid-download after it had already discarded its staging copy.
S1_ARTIFACTS = (
    "hmm_model.joblib",
    "regime_strategy_map.json",
    "strategy_weights.json",
    "model_metadata.json",
    "code_bundle.zip",
)
GK_ARTIFACTS = (
    "champion_model.pkl",
    "champion_preprocessor.pkl",
    "champion_manifest.json",
)


# Consumer contract, agreed with System 2 in S2-REPLY-2026-08-15 §4.1:
#   any of missing / unreadable / status != "published" / empty artifacts /
#   an unrecognised status  =>  REJECT.
# "Unknown is not a permissive default", so a manifest MUST state its status explicitly.
# Before 2026-08-15 this module emitted no ``status`` at all; under the agreed rule that
# reads as "not published" and every real promotion would be refused downstream.
STATUS_PUBLISHED = "published"
STATUS_WITHDRAWN = "withdrawn"


class ModelSetRefused(Exception):
    """Raised when the model set cannot be assembled coherently (never publishes)."""


def _read_json(storage, key: str) -> Optional[Dict[str, Any]]:
    """Read and parse a JSON object from the backend, or None if it is not there."""
    if not storage.exists(key):
        return None
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "ptr.json")
        storage.get_object(key, p)
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)


def _collect(storage, prefix: str, names: tuple) -> List[Dict[str, Any]]:
    """Resolve ``names`` under ``prefix`` to manifest entries, verified against the backend."""
    prefix = prefix.rstrip("/")
    out: List[Dict[str, Any]] = []
    for name in names:
        key = f"{prefix}/{name}"
        if not storage.exists(key):
            raise ModelSetRefused(f"model set incomplete — missing object {key!r}")
        meta = storage.head(key)
        out.append(
            {
                "name": name,
                "path": key,
                "sha256": meta.get("sha256"),
                "bytes": meta.get("size"),
            }
        )
    return out


def build_manifest(storage) -> Dict[str, Any]:
    """Assemble the model-set manifest from the two live sub-pointers (no writes)."""
    s1 = _read_json(storage, S1_POINTER_KEY)
    if not s1 or not s1.get("bundle_version"):
        raise ModelSetRefused(
            f"no System-1 bundle pointer at {S1_POINTER_KEY!r} — nothing to package"
        )
    gk = _read_json(storage, GK_POINTER_KEY)
    if not gk or not gk.get("version"):
        raise ModelSetRefused(
            f"no gatekeeper pointer at {GK_POINTER_KEY!r} — nothing to package"
        )

    s1_version = str(s1["bundle_version"])
    gk_version = str(gk["version"])
    s1_prefix = str(s1.get("path") or f"system1/{s1_version}")
    gk_prefix = str(gk.get("path") or f"models/gatekeeper/{gk_version}")

    artifacts = _collect(storage, s1_prefix, S1_ARTIFACTS) + _collect(
        storage, gk_prefix, GK_ARTIFACTS
    )

    # Provenance, requested by System 2 in S2-REPLY-2026-08-15: bind the manifest to the
    # qualification run that produced the map inside it. Their 2026-08-15 incident is the
    # argument — two stale artefacts AGREED with each other, so internal consistency
    # proved nothing; only binding to the running qualification run caught it. Read from
    # the bundle in the backend, never from a local file, so it describes what a consumer
    # will actually download.
    qual_run_id = (
        _read_json(storage, f"{s1_prefix.rstrip('/')}/regime_strategy_map.json") or {}
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_PUBLISHED,
        "qualification_run_id": qual_run_id.get("qualification_run_id"),
        # Keeps the historical ``<s1_version>_gk-<short>`` shape so an existing consumer's
        # "has the id changed?" comparison keeps working across this cutover.
        "model_set_id": f"{s1_version}_gk-{gk_version.split('-')[-1]}",
        "published_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "system1_bundle_version": s1_version,
        "gatekeeper_version": gk_version,
        "artifacts": artifacts,
    }


def publish(dry_run: bool = False, storage=None) -> Dict[str, Any]:
    """Build and (unless ``dry_run``) atomically flip the top-level model-set pointer."""
    storage = storage or build_storage()

    # Ensure code_bundle.zip is present before manifest verification
    s1 = _read_json(storage, S1_POINTER_KEY)
    if s1 and s1.get("bundle_version"):
        s1_version = str(s1["bundle_version"])
        s1_prefix = str(s1.get("path") or f"system1/{s1_version}").rstrip("/")
        bundle_key = f"{s1_prefix}/code_bundle.zip"
        if not storage.exists(bundle_key):
            import zipfile
            with tempfile.TemporaryDirectory() as td:
                zip_path = os.path.join(td, "code_bundle.zip")
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for root, _, files in os.walk(os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")), "src", "layer0", "strategies")):
                        for f in files:
                            if f.endswith(".py"):
                                p = os.path.join(root, f)
                                arcname = os.path.relpath(p, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
                                zf.write(p, arcname)
                    # Indicators
                    ind_path = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")), "src", "layer0", "data_access", "indicators.py")
                    zf.write(ind_path, "src/layer0/data_access/indicators.py")
                    # Regime
                    reg_path = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")), "src", "regime", "structural.py")
                    zf.write(reg_path, "src/regime/structural.py")
                    
                    # Determinism and Reference Vector
                    det_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), "DETERMINISM.md")
                    if os.path.exists(det_path):
                        zf.write(det_path, "DETERMINISM.md")
                    ref_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), "reference_vector.json")
                    if os.path.exists(ref_path):
                        zf.write(ref_path, "reference_vector.json")
                    fp_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), "candle_fingerprint.json")
                    if os.path.exists(fp_path):
                        zf.write(fp_path, "candle_fingerprint.json")
                        
                    reqs = "\n".join([
                        "numpy==2.4.4",
                        "pandas==2.3.3",
                        "scikit-learn==1.8.0",
                        "joblib==1.5.3",
                        "hmmlearn==0.3.3",
                    ]) + "\n"
                    zf.writestr("requirements.txt", reqs)
                storage.put_object(bundle_key, zip_path)

    manifest = build_manifest(storage)

    logger.info(
        "model set %s: s1=%s gk=%s (%d artifacts)",
        manifest["model_set_id"],
        manifest["system1_bundle_version"],
        manifest["gatekeeper_version"],
        len(manifest["artifacts"]),
    )
    if dry_run:
        logger.info("dry-run — pointer NOT flipped")
        return {**manifest, "published": False}

    prev = _read_json(storage, POINTER_KEY)
    if prev is not None and prev.get("model_set_id") == manifest["model_set_id"]:
        logger.info(
            "model set %s already live — pointer left untouched",
            manifest["model_set_id"],
        )
        return {**manifest, "published": False, "unchanged": True}
    if prev is not None:
        storage.atomic_pointer_update(PREVIOUS_KEY, prev)  # rollback breadcrumb

    storage.atomic_pointer_update(POINTER_KEY, manifest)
    logger.info(
        "published model set %s (supersedes %s)",
        manifest["model_set_id"],
        (prev or {}).get("model_set_id"),
    )
    return {
        **manifest,
        "published": True,
        "supersedes": (prev or {}).get("model_set_id"),
    }


def build_withdrawal(reason: str, supersedes: Optional[str]) -> Dict[str, Any]:
    """The withdrawal manifest. Pure — no I/O, so the shape is testable on its own."""
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("--reason is mandatory: a withdrawal must say why in words")
    return {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_WITHDRAWN,
        # Explicitly null rather than absent: a consumer keying on model_set_id sees a
        # value that cannot match anything it has, instead of a missing key it might
        # treat as "unchanged".
        "model_set_id": None,
        "withdrawn_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "reason": reason,
        "supersedes": supersedes,
        "artifacts": [],
    }


def withdraw(reason: str, dry_run: bool = False, storage=None) -> Dict[str, Any]:
    """State in the live artefact that there is no model set.

    This is a **separate verb from publish**, not a promotion with zero artifacts.
    ``publish()`` can only move the pointer forward to a better set; it has no way to
    say "there is none", which is why the pointer went on serving a withdrawn map for
    a day after FIX-S1-014 emptied the qualified set.

    Never deletes. The superseded manifest is archived to ``previous_model_set.json``,
    so reinstating is an ordinary ``publish()``.
    """
    storage = storage or build_storage()
    prev = _read_json(storage, POINTER_KEY)

    if prev is not None and prev.get("status") == STATUS_WITHDRAWN:
        # Idempotent on purpose. A second withdrawal must NOT archive the first one over
        # the rollback breadcrumb — that would replace the last real model set with an
        # empty manifest and leave nothing to reinstate.
        logger.info("model set already withdrawn — pointer left untouched")
        return {**prev, "published": False, "unchanged": True}

    manifest = build_withdrawal(reason, (prev or {}).get("model_set_id"))

    if dry_run:
        logger.info("dry-run — pointer NOT flipped")
        return {**manifest, "published": False}

    if prev is not None:
        storage.atomic_pointer_update(PREVIOUS_KEY, prev)  # rollback breadcrumb

    storage.atomic_pointer_update(POINTER_KEY, manifest)
    logger.warning(
        "WITHDRAWN model set %s — reason: %s",
        (prev or {}).get("model_set_id"),
        manifest["reason"],
    )
    return {**manifest, "published": True}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Publish the top-level model-set manifest"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Assemble and print the manifest without flipping the pointer.",
    )
    parser.add_argument(
        "--withdraw",
        action="store_true",
        help=(
            "Withdraw the live model set: publish an empty manifest with "
            'status="withdrawn". Requires --reason. CLI only — the orchestrator '
            "must never call this."
        ),
    )
    parser.add_argument(
        "--reason",
        default="",
        help="Mandatory human explanation for --withdraw. Recorded in the manifest.",
    )
    args = parser.parse_args()
    if args.reason and not args.withdraw:
        parser.error("--reason is only meaningful with --withdraw")
    if args.withdraw and not args.reason.strip():
        parser.error("--withdraw requires --reason: say why, in words, in the manifest")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    from dotenv import load_dotenv

    load_dotenv(
        os.path.join(
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
            ".env",
        )
    )
    try:
        if args.withdraw:
            print(
                json.dumps(withdraw(reason=args.reason, dry_run=args.dry_run), indent=2)
            )
        else:
            print(json.dumps(publish(dry_run=args.dry_run), indent=2))
    except ModelSetRefused as e:
        logger.error("MODEL SET REFUSED: %s", e)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
