"""Pluggable message-queue backends (FND-002).

Task code imports ``build_queue()`` — never a vendor SDK. Swapping ``local`` → a real
broker (redis/rabbitmq) is an ``.env`` change (``QUEUE_PROVIDER``), not a code change.
See orchestration/STORAGE_AND_QUEUE_ABSTRACTION.md.
"""
from __future__ import annotations

import os


def build_queue():
    """Construct the configured QueueBackend (local default)."""
    provider = os.environ.get("QUEUE_PROVIDER", "local").lower()
    if provider == "local":
        from .local_durable import LocalDurableBackend

        return LocalDurableBackend(root=os.environ.get("QUEUE_LOCAL_ROOT", "results/state/queue"))
    # redis / rabbitmq adapters attach later via QUEUE_PROVIDER + QUEUE_URL.
    raise ValueError(f"Unknown QUEUE_PROVIDER={provider!r}")
