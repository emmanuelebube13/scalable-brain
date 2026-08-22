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

# System 3's DEPLOYED ScoredSignal contract pins {"const": "1"} and is
# additionalProperties: false. We emitted "2.0.0" plus three provenance fields it has
# never seen, so every message dead-lettered on arrival. System 1 conforms to the
# consumer's live contract; the consumer is not asked to move for us. v2 ships only when
# both sides agree it, as one coordinated release.
SCHEMA_VERSION = "1"
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CONTRACT_PATH = os.path.join(_REPO_ROOT, "contracts", "signal-message-contract.json")

REGIME_LABELS = {"Trending-Up", "Trending-Down", "Ranging", "High-Vol"}


def build_message_id(signal_id: str, score_run_id: str) -> str:
    """Deterministic idempotency key: same (signal_id, score_run_id) → same id."""
    return f"{signal_id}:{score_run_id}"


def build_message(signal: Dict[str, Any], score_run_id: str) -> Dict[str, Any]:
    """Assemble the queue message from a scored signal (point-in-time fields only)."""
    score = (
        float(signal["model_score"]) if signal.get("model_score") is not None else None
    )
    threshold = (
        float(signal["threshold_applied"])
        if signal.get("threshold_applied") is not None
        else None
    )

    # Exactly System 3's ScoredSignal v1. It is additionalProperties: false, so a field
    # it does not know is DEAD-LETTERED, not ignored — nothing extra may be added here
    # without the consumer's schema moving first.
    #
    # Deliberately NOT sent, though System 1 has them: message_id (idempotency travels
    # out-of-band as the publish key, not in the payload), signal_time_utc, approved,
    # regime_probs, and the v2 provenance trio producer / model_set_id /
    # reference_vector_ok. Each one would reject the whole message.
    msg: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "signal_id": str(signal["signal_id"]),
        # Their freshness window is 900 s and it is measured from this field, so it is
        # stamped at send time rather than carrying the bar's timestamp.
        "produced_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "pair": signal.get("pair", signal.get("instrument")),
        "direction": signal["direction"],
        "strategy_id": str(signal["strategy_id"]),
        "regime": signal["regime"],
        "model_score": score,
        "granularity": signal["granularity"],
        "proposed_entry": float(signal.get("proposed_entry", signal.get("entry", 0))),
        "proposed_sl": float(signal.get("proposed_sl", signal.get("stop", 0))),
        "proposed_tp": float(signal.get("proposed_tp", signal.get("target", 0))),
        # No default. A hardcoded ATR was previously shipped on every signal (0.0015),
        # which is wrong by two orders of magnitude for a JPY pair and would misfeed
        # System 3's ATR-multiple sizing. build_signals() computes the real value and
        # refuses to emit without it, so its absence here is a bug, not a fallback case.
        "atr": float(signal["atr"]),
        # Optional in their schema, but scoring provenance is worth stating explicitly:
        # NULL model_score means "unscored", never "scored zero".
        "scoring_status": "scored" if score is not None else "unscored",
    }
    if threshold is not None:
        msg["threshold_applied"] = threshold
    if signal.get("strategy_key"):
        msg["strategy_key"] = str(signal["strategy_key"])
    # Their enum is {qualified, designated}; anything else is dropped rather than sent,
    # because a bad value rejects the message where a missing one is merely auditable.
    if signal.get("selection_basis") in ("qualified", "designated"):
        msg["selection_basis"] = signal["selection_basis"]
    if signal.get("gate_failures"):
        msg["gate_failures"] = [str(g) for g in signal["gate_failures"]]
    return msg


class ScoredSignalProducer:
    def __init__(
        self,
        backend=None,
        queue_name: Optional[str] = None,
        backpressure_timeout_ms: int = None,
        backpressure_max_retries: int = None,
    ):
        self.backend = backend or build_queue()
        self.queue = queue_name or os.environ.get(
            "SCORED_SIGNAL_QUEUE", "scored_signal_queue"
        )
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

    def publish_signals(
        self, signals: Iterable[Dict[str, Any]], score_run_id: str
    ) -> Dict[str, int]:
        published = 0
        dlq_count = 0
        backpressure_events = 0
        deduped = 0

        for signal in signals:
            try:
                message = build_message(signal, score_run_id)
            except (KeyError, ValueError, TypeError) as e:
                self.backend.dead_letter(
                    {"raw": str(signal)[:500]}, f"BUILD_ERROR: {e}"
                )
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

            # The idempotency key travels out-of-band, not in the payload: System 3's
            # contract is additionalProperties: false and has no message_id field, so
            # carrying it inside the message would dead-letter every publish. Same
            # deterministic value as before — (signal_id, score_run_id).
            idempotency_key = build_message_id(str(signal["signal_id"]), score_run_id)
            before = self.backend.depth(self.queue)
            ok = self.backend.publish(
                self.queue, message, idempotency_key=idempotency_key
            )
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

    def emit_heartbeat(self, model_set: Dict[str, Any] = None) -> bool:
        """Emit a heartbeat message to prove liveness even when no signals are generated."""
        topic = os.environ.get("SIGNAL_HEARTBEAT_TOPIC", "scored-signals.heartbeat")
        now_str = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        message = {
            "produced_at_utc": now_str,
            # The manifest identifier, not the map's generated_at_utc — System 3 uses
            # this to tell which published set a producer is running.
            "model_set_id": model_set.get("model_set_id") if model_set else None,
            # False until a replay actually runs. "Assuming determinism passed at
            # startup" is not evidence, and this is the field System 3 rejects on.
            "reference_vector_ok": bool(
                model_set.get("reference_vector_ok", False) if model_set else False
            ),
        }
        return self.backend.publish(topic, message, idempotency_key=f"hb:{now_str}")


def _load_validator():
    """Return a callable(message) that raises on invalid; tolerant if jsonschema absent."""
    try:
        import jsonschema

        with open(CONTRACT_PATH, encoding="utf-8") as fh:
            schema = json.load(fh)
        validator = jsonschema.Draft202012Validator(schema)
        return validator.validate
    except Exception as e:  # noqa: BLE001
        logger.error(
            "jsonschema/contract unavailable (%s) — minimal validation only", e
        )

        def _minimal(message):
            required = [
                "schema_version",
                "message_id",
                "signal_id",
                "pair",
                "granularity",
                "signal_time_utc",
                "direction",
                "proposed_entry",
                "proposed_sl",
                "proposed_tp",
                "atr",
                "model_score",
                "approved",
                "threshold_applied",
                "regime",
                "regime_probs",
                "producer",
                "model_set_id",
                "reference_vector_ok",
                "produced_at_utc",
                "strategy_id",
                "scoring_status",
            ]
            missing = [f for f in required if f not in message]
            if missing:
                raise ValueError(f"missing fields: {missing}")

        return _minimal
