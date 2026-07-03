"""QueueBackend interface (FND-002). See STORAGE_AND_QUEUE_ABSTRACTION.md §2."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict


class QueueBackend(ABC):
    @abstractmethod
    def publish(self, queue: str, message: dict, *, idempotency_key: str) -> bool:
        """Durably publish a message. Returns True after a publisher confirm.

        Re-publishing the same ``idempotency_key`` is a no-op (returns True) so the
        producer is safe to retry; exactly-once effect comes from consumer dedupe.
        """

    @abstractmethod
    def depth(self, queue: str) -> int:
        """Current number of messages in the queue."""

    @abstractmethod
    def at_capacity(self, queue: str) -> bool:
        """True when depth >= MAX_QUEUE_SIZE (producer must apply backpressure)."""

    @abstractmethod
    def dead_letter(self, message: dict, reason: str) -> None:
        """Route an un-publishable message to the DLQ with a reason."""

    @abstractmethod
    def stats(self, queue: str) -> Dict[str, int]:
        """{published, depth, dlq} counters for observability."""
