"""Pluggable object-storage backends (FND-001).

Task code imports ``build_storage()`` — never a vendor SDK. Swapping ``local`` → ``gcs``
is an ``.env`` change (``STORAGE_PROVIDER``), not a code change.
See orchestration/STORAGE_AND_QUEUE_ABSTRACTION.md §1.
"""
from __future__ import annotations

import os


def build_storage():
    """Construct the configured StorageBackend (local default)."""
    provider = os.environ.get("STORAGE_PROVIDER", "local").lower()
    if provider == "local":
        from .local_fs import LocalFSBackend

        return LocalFSBackend(root=os.environ.get("STORAGE_LOCAL_ROOT", "model-artifacts"))
    if provider == "gcs":
        from .gcs import GCSBackend

        return GCSBackend(bucket=os.environ["GCS_BUCKET"])
    raise ValueError(f"Unknown STORAGE_PROVIDER={provider!r}")
