"""Pluggable object-storage backends (FND-001).

Task code imports ``build_storage()`` — never a vendor SDK. Swapping ``local`` → ``gcs``
is an ``.env`` change (``STORAGE_PROVIDER``), not a code change.
See orchestration/STORAGE_AND_QUEUE_ABSTRACTION.md §1.
"""
from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _ensure_env_loaded() -> None:
    """Load ``.env`` before reading STORAGE_PROVIDER.

    FIX-S1-012. ``build_storage()`` read ``os.environ`` directly and defaulted to
    ``local``. Any entry point that had not already imported something which calls
    ``load_dotenv()`` therefore got a LocalFS backend while ``.env`` said ``gcs`` —
    silently, with no error, returning plausible-looking data from the wrong place.

    That is not hypothetical. ``scheduler.orchestrator`` never loads ``.env`` at
    import time, so ``_incumbent()`` resolved against the local ``model-artifacts/``
    tree instead of GCS on every real retrain, found no ``system1/latest.json``
    there, and logged "NO INCUMBENT FOUND". ``beats_incumbent`` then took its
    fail-open branch — so the regression gate was structurally inert on all three
    2026 promotions, which is exactly the producer/consumer divergence FIX-S1-007
    and FIX-S1-010 were written to close. The abstraction was correct; the
    configuration was never loaded.

    ``load_dotenv`` does not override variables already present in the environment,
    so explicit test/CI overrides still win.
    """
    if os.environ.get("STORAGE_PROVIDER"):
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(_REPO_ROOT / ".env")
    except Exception:  # noqa: BLE001 - missing dotenv must not break local dev
        pass


def build_storage():
    """Construct the configured StorageBackend (local default)."""
    _ensure_env_loaded()
    provider = os.environ.get("STORAGE_PROVIDER", "local").lower()
    if provider == "local":
        from .local_fs import LocalFSBackend

        return LocalFSBackend(root=os.environ.get("STORAGE_LOCAL_ROOT", "model-artifacts"))
    if provider == "gcs":
        from .gcs import GCSBackend

        return GCSBackend(bucket=os.environ["GCS_BUCKET"])
    raise ValueError(f"Unknown STORAGE_PROVIDER={provider!r}")
