"""MODEL-008 — ScoredSignalProducer.

Publishes scored signals to ``Scored_Signal_Queue`` via the pluggable QueueBackend with:
  * a versioned, JSON-schema-validated message contract,
  * deterministic idempotency keys (signal_id + score_run_id),
  * bounded depth + backpressure (block/retry with backoff, never silent drop),
  * DLQ routing for invalid / un-publishable messages,
  * publisher confirms (at-least-once) + observability metrics.

Source-agnostic: consumes an iterable of *scored signal* dicts so it has zero knowledge
of how signals are produced and ZERO dependency on the execution layer (Layer 4).
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from src.common.queue import build_queue

logger = logging.getLogger("system1.queue_producer")

SCHEMA_VERSION = "1.0.0"
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
CONTRACT_PATH = os.path.join(_REPO_ROOT, "contracts", "signal-message-contract.json")

REGIME_LABELS = {"Trending-Up", "Trending-Down", "Ranging", "High-Vol"}


def build_message_id(signal_id: str, score_run_id: str) -> str:
    """Deterministic idempotency key: same (signal_id, score_run_id) → same id."""
    return f"{signal_id}:{score_run_id}"


def build_message(signal: Dict[str, Any], score_run_id: str) -> Dict[str, Any]:
    """Assemble the queue message from a scored signal (point-in-time fields only)."""
    score = float(signal["model_score"])
    threshold = float(signal["threshold_applied"])
    return {
        "schema_version": SCHEMA_VERSION,
        "message_id": build_message_id(str(signal["signal_id"]), score_run_id),
        "signal_id": str(signal["signal_id"]),
        "instrument": signal["instrument"],
        "granularity": signal["granularity"],
        "signal_time_utc": signal["signal_time_utc"],
        "direction": signal["direction"],
        "model_score": score,
        "approved": score >= threshold,
        "threshold_applied": threshold,
        "regime": signal["regime"],
        "regime_probs": signal["regime_probs"],
        "bundle_version": signal["bundle_version"],
        "produced_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


class ScoredSignalProducer:
    def __init__(
        self,
        backend=None,
        queue_name: Optional[str] = None,
        backpressure_timeout_ms: int = None,
        backpressure_max_retries: int = None,
    ):
        self.backend = backend or build_queue()
        self.queue = queue_name or os.environ.get("SCORED_SIGNAL_QUEUE", "scored_signal_queue")
        self.bp_timeout_ms = int(
            backpressure_timeout_ms
            if backpressure_timeout_ms is not None
            else os.environ.get("BACKPRESSURE_TIMEOUT_MS", 5000)
        )
        self.bp_max_retries = int(
            backpressure_max_retries
            if backpressure_max_retries is not None
            else os.environ.get("BACKPRESSURE_MAX_RETRIES", 3)
        )
        self._validator = _load_validator()

    def _validate(self, message: Dict[str, Any]) -> Optional[str]:
        """Return None if valid, else a short reason string."""
        try:
            self._validator(message)
        except Exception as e:  # noqa: BLE001 — jsonschema ValidationError or absence
            return f"SCHEMA_INVALID: {str(e).splitlines()[0][:120]}"
        if message["regime"] not in REGIME_LABELS:
            return "BAD_REGIME"
        return None

    def publish_signals(self, signals: Iterable[Dict[str, Any]], score_run_id: str) -> Dict[str, int]:
        published = 0
        dlq_count = 0
        backpressure_events = 0
        deduped = 0

        for signal in signals:
            try:
                message = build_message(signal, score_run_id)
            except (KeyError, ValueError, TypeError) as e:
                self.backend.dead_letter({"raw": str(signal)[:500]}, f"BUILD_ERROR: {e}")
                dlq_count += 1
                continue

            reason = self._validate(message)
            if reason is not None:
                self.backend.dead_letter(message, reason)
                dlq_count += 1
                continue

            # Backpressure: never overflow, never silently drop.
            if self.backend.at_capacity(self.queue):
                backpressure_events += 1
                if not self._await_capacity():
                    self.backend.dead_letter(message, "QUEUE_FULL")
                    dlq_count += 1
                    continue

            before = self.backend.depth(self.queue)
            ok = self.backend.publish(self.queue, message, idempotency_key=message["message_id"])
            if not ok:
                self.backend.dead_letter(message, "PUBLISH_NACK")
                dlq_count += 1
                continue
            after = self.backend.depth(self.queue)
            if after > before:
                published += 1
            else:
                deduped += 1  # idempotent no-op (already published)

        metrics = {
            "published_count": published,
            "deduped_count": deduped,
            "dlq_count": dlq_count,
            "backpressure_events": backpressure_events,
            "queue_depth": self.backend.depth(self.queue),
        }
        logger.info(json.dumps({"event": "queue_publish", **metrics}))
        if dlq_count > 0:
            logger.warning("DLQ growth this run: %d messages", dlq_count)
        return metrics

    def _await_capacity(self) -> bool:
        """Block/retry with linear backoff while the queue is full. True if drained."""
        for retry in range(self.bp_max_retries):
            time.sleep(self.bp_timeout_ms / 1000.0 * (retry + 1))
            if not self.backend.at_capacity(self.queue):
                return True
        return not self.backend.at_capacity(self.queue)


def _load_validator():
    """Return a callable(message) that raises on invalid; tolerant if jsonschema absent."""
    try:
        import jsonschema

        with open(CONTRACT_PATH, encoding="utf-8") as fh:
            schema = json.load(fh)
        validator = jsonschema.Draft202012Validator(schema)
        return validator.validate
    except Exception as e:  # noqa: BLE001
        logger.error("jsonschema/contract unavailable (%s) — minimal validation only", e)

        def _minimal(message):
            required = [
                "schema_version", "message_id", "signal_id", "instrument", "granularity",
                "signal_time_utc", "direction", "model_score", "approved",
                "threshold_applied", "regime", "regime_probs", "bundle_version",
                "produced_at_utc",
            ]
            missing = [f for f in required if f not in message]
            if missing:
                raise ValueError(f"missing fields: {missing}")

        return _minimal
