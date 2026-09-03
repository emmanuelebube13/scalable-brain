import json
import logging
from typing import Dict, Any

from google.cloud import pubsub_v1
from src.common.queue.base import QueueBackend

logger = logging.getLogger("system1.queue.pubsub")


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
            future.result()  # Wait for confirmation
            self._published_count += 1
            return True
        except Exception as e:
            logger.error("PubSub publish failed: %s", e)
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
