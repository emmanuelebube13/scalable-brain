"""Pluggable message-queue backends (FND-002).

Task code imports ``build_queue()`` — never a vendor SDK. Swapping ``local`` → a real
broker (redis/rabbitmq) is an ``.env`` change (``QUEUE_PROVIDER``), not a code change.
See orchestration/STORAGE_AND_QUEUE_ABSTRACTION.md.
"""

from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _ensure_env_loaded() -> None:
    """Load ``.env`` before reading QUEUE_PROVIDER.

    The same defect FIX-S1-012 closed in ``build_storage()``, still open here.
    ``build_queue()`` read ``os.environ`` directly and defaulted to ``local``, so any
    entry point that had not already imported something calling ``load_dotenv()`` got
    the LOCAL durable backend while ``.env`` said ``pubsub`` — silently, with no error,
    writing signals to disk on Computer 1 while every log line claimed success.

    Found 2026-08-17 minutes after switching QUEUE_PROVIDER to pubsub for go-live:
    ``build_queue()`` still returned ``LocalDurableBackend`` and both
    ``SCORED_SIGNAL_QUEUE`` and ``GOOGLE_CLOUD_PROJECT`` read as ``None``. Nothing would
    have reached System 3, and the failure mode is indistinguishable from a quiet market.

    ``load_dotenv`` does not override variables already in the environment, so explicit
    test/CI overrides still win.
    """
    if os.environ.get("QUEUE_PROVIDER"):
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(_REPO_ROOT / ".env")
    except Exception:  # noqa: BLE001 - missing dotenv must not break local dev
        pass


def build_queue():
    """Construct the configured QueueBackend (local default)."""
    _ensure_env_loaded()
    provider = os.environ.get("QUEUE_PROVIDER", "local").lower()
    if provider == "local":
        from .local_durable import LocalDurableBackend

        return LocalDurableBackend(
            root=os.environ.get("QUEUE_LOCAL_ROOT", "results/state/queue")
        )
    elif provider == "pubsub":
        from .pubsub import PubSubBackend

        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "test-project")
        return PubSubBackend(project_id=project_id)
    # redis / rabbitmq adapters attach later via QUEUE_PROVIDER + QUEUE_URL.
    raise ValueError(f"Unknown QUEUE_PROVIDER={provider!r}")
