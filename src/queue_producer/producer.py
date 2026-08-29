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
# Stamped on every message as `producer`. Kept a constant rather than a hostname: the
# claim is "System 1 authored this", which stays true if the process moves to a container
# or to the cloud, whereas a hostname would silently become the answer to a different
# question.
PRODUCER_ID = "system-1"
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CONTRACT_PATH = os.path.join(_REPO_ROOT, "contracts", "signal-message-contract.json")

REGIME_LABELS = {"Trending-Up", "Trending-Down", "Ranging", "High-Vol"}

# Values of EMIT_PROVENANCE_FIELDS that turn stamping OFF. Everything else, including
# the variable being unset, leaves it ON.
_PROVENANCE_OFF_VALUES = {"false", "0", "no", "off"}


def _provenance_enabled() -> bool:
    """Whether to stamp `producer` / `bundle_id` / `drill`. Default ON.

    A KILL SWITCH, not a feature flag, and deliberately defaulted in code rather than in
    ``.env``. ``.env`` is git-ignored, so an env-var default is a promise that only exists
    on this host: the same mistake as the heartbeat topic (see ``emit_heartbeat``), where
    the literal in the file — not the variable — was what any other host inherited.

    It matters more here than there. System 2 reads an absent ``drill`` as ``false``,
    i.e. a REAL order, and says plainly that the reading is only unambiguous because we
    stamp the flag on every message including real ones. If stamping silently reverted on
    a restart or a redeployed host, nothing would become unsafe — ``emit_drill`` re-reads
    the built message and refuses to publish a rehearsal it cannot mark, so a drill can
    never arrive looking real. What would be lost is the rehearsal path itself, silently.
    Set ``EMIT_PROVENANCE_FIELDS=false`` to stop stamping, and tell Systems 2 and 3 when
    you do.
    """
    return (
        os.environ.get("EMIT_PROVENANCE_FIELDS", "").strip().lower()
        not in _PROVENANCE_OFF_VALUES
    )


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

    # Provenance trio, added to the contract 2026-08-28 as System 3's condition on its
    # ADR-001 approval. Until then the contract was additionalProperties:false with no
    # slot for any of them, which is why the block above says they are "deliberately NOT
    # sent" — the constraint was the consumer's schema, not a choice.
    #
    # `producer` matters the moment inference may run somewhere other than here: the
    # topic alone stops identifying the author. `bundle_id` ties the decision to the exact
    # checksummed artifact set instead of a wall-clock time.
    #
    # ON since 2026-08-29 (S2-REPLY-2026-08-29). The migration order we got wrong the
    # first time was CONSUMER-ACCEPTS-FIRST, then producer-emits, and it is now satisfied
    # in both halves: Systems 2 and 3 deployed a schema that accepts all three (unknown
    # fields still reject, so the contract was widened, not loosened), and System 2 honours
    # `drill` by stopping immediately before the broker submit — after construction, §7.2
    # validation and the backup guard. Accepting `drill` without that short-circuit would
    # have moved us from "safely rejects a rehearsal" to "silently executes one".
    if _provenance_enabled():
        msg["producer"] = PRODUCER_ID
        if signal.get("model_set_id"):
            msg["bundle_id"] = str(signal["model_set_id"])
        # Stamped on EVERY message, not only rehearsals. An always-present boolean cannot
        # be lost in transit; a flag that appears sometimes turns "absent" into
        # "ambiguous", and the ambiguous reading of a drill is a live order. System 2
        # reads absent as `false` — that reading is only safe while this line runs
        # unconditionally, so it is stamped even when the value is False.
        msg["drill"] = bool(signal.get("drill", False))
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
        """Emit a heartbeat message to prove liveness even when no signals are generated.

        The default topic name is ``scored_signal_heartbeat`` — underscores, matching the
        ``scored_signal_queue`` / ``scored_signal_dlq`` family. It was previously
        ``scored-signals.heartbeat``, a name that has never existed in the project: every
        run since the hourly cron landed logged ``404 Resource not found`` here, so the one
        message whose entire job is to say "System 1 is alive, it just has nothing to send"
        was the only message that could never arrive. Systems 2 and 3 therefore read total
        silence, which is indistinguishable from a dead producer, and reported System 1 as
        not sending signals while the signal path itself was healthy.

        Keep this default in sync with ``shell/provision_pubsub.sh``. ``.env`` is
        git-ignored, so the literal here — not an env var — is what any other host inherits.
        """
        topic = os.environ.get("SIGNAL_HEARTBEAT_TOPIC", "scored_signal_heartbeat")
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
