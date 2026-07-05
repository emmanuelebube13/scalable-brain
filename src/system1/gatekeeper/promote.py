"""FIX-S1-009 Fix 5 — governed, atomic promote path for the gatekeeper champion bundle.

This module is the SOLE code in ``src/system1`` allowed to name the ``champion_*``
artifact filenames for writing. Every champion (or dry-run ``proposed_champion_*``)
write must go through :func:`atomic_promote`, which stages each artifact to a temp
file in the destination directory and ``os.replace()``-s it into place — atomic on
POSIX, so a crash mid-write can never leave a torn champion bundle on disk.

Any other module in ``src/system1`` that names ``champion_*`` for writing is a
review red flag (see docs/proposed-fixes/system-1/FIX-S1-009 §4 Fix 5).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from typing import Any, Callable, Dict, Optional

import joblib

logger = logging.getLogger("system1.gatekeeper")

# The one place the champion/proposed-champion artifact namespace is defined.
_CHAMPION_PREFIX = "champion"
_PROPOSED_PREFIX = "proposed_champion"


def bundle_paths(models_dir: str, dry_run: bool = False) -> Dict[str, str]:
    """Resolve the champion (or dry-run proposed-champion) bundle paths.

    ``dry_run=True`` targets the ``proposed_champion_*`` namespace, which never
    collides with the live champion (global rule #1 — log-only, no auto-promotion).

    Returns a dict with ``model_path`` / ``preprocessor_path`` / ``manifest_path``.
    """
    prefix = _PROPOSED_PREFIX if dry_run else _CHAMPION_PREFIX
    return {
        "model_path": os.path.join(models_dir, f"{prefix}_model.pkl"),
        "preprocessor_path": os.path.join(models_dir, f"{prefix}_preprocessor.pkl"),
        "manifest_path": os.path.join(models_dir, f"{prefix}_manifest.json"),
    }


def sha256_file(path: str) -> str:
    """SHA256 of a file, read in 1 MiB chunks (artifact-integrity contract)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def _atomic_write(stage_fn: Callable[[str], None], final_path: str) -> None:
    """Stage via ``stage_fn(tmp_path)`` in the destination dir, then ``os.replace``.

    The temp file lives in the same directory as ``final_path`` so the rename is a
    same-filesystem ``os.replace`` (atomic on POSIX). The temp file is removed on
    failure so aborted writes leave no debris.
    """
    directory = os.path.dirname(final_path) or "."
    fd, tmp_path = tempfile.mkstemp(
        dir=directory, prefix=os.path.basename(final_path) + ".", suffix=".tmp"
    )
    os.close(fd)
    try:
        stage_fn(tmp_path)
        os.replace(tmp_path, final_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def atomic_promote(
    model: Any,
    manifest: Dict[str, Any],
    models_dir: str,
    preprocessor: Optional[Any] = None,
    dry_run: bool = False,
) -> Dict[str, str]:
    """Atomically write the champion bundle (model + preprocessor + manifest).

    This is the single governed write path for ``models/champion_*`` in System-1
    (FIX-S1-009 Fix 5). Callers pass the manifest WITHOUT the ``sha256`` block:
    this function stages each artifact, computes its SHA256, appends the ``sha256``
    map to ``manifest`` (mutated in place, preserving key order — ``sha256`` last),
    writes the manifest atomically, then records the manifest's own hash in the
    in-memory dict only (the on-disk manifest cannot contain its own hash).

    Args:
        model: Trained estimator to ``joblib.dump``.
        manifest: Champion manifest dict (schema owned by the caller; ``sha256``
            key is added here).
        models_dir: Destination artifact directory (e.g. ``<repo>/models``).
        preprocessor: Fitted preprocessor to dump alongside, if any.
        dry_run: When True, write the ``proposed_champion_*`` namespace and never
            touch the live champion.

    Returns:
        The resolved ``bundle_paths`` dict for the written bundle.
    """
    os.makedirs(models_dir, exist_ok=True)
    paths = bundle_paths(models_dir, dry_run=dry_run)
    model_path = paths["model_path"]
    pre_path = paths["preprocessor_path"]
    manifest_path = paths["manifest_path"]

    _atomic_write(lambda p: joblib.dump(model, p), model_path)
    sha: Dict[str, str] = {os.path.basename(model_path): sha256_file(model_path)}
    if preprocessor is not None:
        _atomic_write(lambda p: joblib.dump(preprocessor, p), pre_path)
        sha[os.path.basename(pre_path)] = sha256_file(pre_path)
    manifest["sha256"] = sha

    def _write_manifest(p: str) -> None:
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2)

    _atomic_write(_write_manifest, manifest_path)
    manifest["sha256"][os.path.basename(manifest_path)] = sha256_file(manifest_path)

    logger.info(
        "atomic_promote: %s bundle staged+replaced in %s",
        "proposed_champion (dry-run)" if dry_run else "champion",
        models_dir,
    )
    return paths
