import json
import logging
from typing import Dict, Any

from google.cloud import pubsub_v1
from src.common.queue.base import QueueBackend

logger = logging.getLogger("system1.queue.pubsub")

#: Seconds to wait for a publish to be acknowledged before giving up on it.
#:
#: ``future.result()`` defaults to waiting FOREVER. On 2026-09-09 a producer run sat for
#: over an hour on 2 seconds of CPU with five sockets to Google in CLOSE-WAIT — the remote
#: end had closed, the client never noticed, and nothing timed it out. Because
#: ``cron_hourly_signals.sh`` takes a non-blocking ``flock``, every subsequent hourly run
#: was skipped for as long as that one process lived, so a single stuck publish silently
#: stopped the whole signal cadence.
#:
#: A publish that has not been acknowledged in this long is not going to be. Failing the
#: call returns False, the caller records it, and the next scheduled run gets to try —
#: which is strictly better than one hung call holding the lock indefinitely.
PUBLISH_TIMEOUT_SECONDS = 30.0


class PubSubBackend(QueueBackend):
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.publisher = pubsub_v1.PublisherClient()
        # For simplicity, we don't have deep observability of depth in this backend
        # unless we query monitoring or keep local counters.
        self._published_count = 0
        self._dlq_count = 0

    def publish(self, queue: str, message: dict, *, idempotency_key: str) -> bool:
        topic_path = self.publisher.topic_path(self.project_id, queue)
        data = json.dumps(message).encode("utf-8")
        try:
            future = self.publisher.publish(
                topic_path, data, idempotency_key=idempotency_key
            )
            # BOUNDED wait. Never bare `future.result()` — see PUBLISH_TIMEOUT_SECONDS.
            future.result(timeout=PUBLISH_TIMEOUT_SECONDS)
            self._published_count += 1
            return True
        except Exception as e:
            # A timeout lands here like any other failure: logged, False returned, the
            # signal left for the next run. Deliberately NOT re-raised — a stuck broker
            # must not take the producer down with it.
            logger.error(
                "PubSub publish failed after up to %.0fs: %s: %s",
                PUBLISH_TIMEOUT_SECONDS,
                type(e).__name__,
                e,
            )
            # Recreate the client to heal the dead GRPC channel and avoid sequential 30s timeouts.
            self.publisher = pubsub_v1.PublisherClient()
            return False

    def depth(self, queue: str) -> int:
        # PubSub doesn't expose a simple depth on the topic level.
        # Returning published_count for now to satisfy producer's simplistic idempotency check.
        return self._published_count

    def reports_depth_accurately(self) -> bool:
        # `depth()` returns `_published_count`, a monotonically increasing per-instance
        # counter. It increments on EVERY successful publish() regardless of whether the
        # broker treated it as a new message or an idempotent replay. The depth delta is
        # therefore always positive for any successful publish, making deduped_count
        # structurally always 0 — the same class of fabricated metric as the status
        # conflation in FIX-S1-016. Reporting False tells the producer not to infer
        # dedup from the depth delta and to report None instead. D6 cause (b).
        return False

    def at_capacity(self, queue: str) -> bool:
        # Pub/Sub scales automatically. Backpressure handled by GCP.
        return False

    def dead_letter(self, message: dict, reason: str) -> None:
        self._dlq_count += 1
        logger.error("DLQ [%s]: %s", reason, json.dumps(message)[:500])
        # We could publish to a DLQ topic if needed.

    def stats(self, queue: str) -> dict:
        return {
            "published": self._published_count,
            "dlq": self._dlq_count,
            "backpressure_events": 0,
            "depth": self.depth(queue),
        }
