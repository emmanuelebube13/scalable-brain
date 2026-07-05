"""LocalDurableBackend — durable, idempotent local-filesystem queue (FND-002 default).

Reproduces the production semantics MODEL-008 needs without a broker:
  * Durable: append-only JSONL log per queue (survives process restart).
  * Idempotency: a ``seen`` index dedupes re-publishes (same idempotency_key = no-op).
  * Bounded depth + backpressure: ``at_capacity`` compares depth to MAX_QUEUE_SIZE.
  * DLQ: ``dead_letter`` writes to a separate DLQ queue with reason + timestamp.
  * Publisher confirm: ``publish`` returns only after the message is durably written.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Dict, Set

from .base import QueueBackend


class LocalDurableBackend(QueueBackend):
    def __init__(self, root: str, max_queue_size: int | None = None, dlq_name: str | None = None):
        self.root = root
        self.max_queue_size = int(
            max_queue_size if max_queue_size is not None else os.environ.get("MAX_QUEUE_SIZE", 100000)
        )
        self.dlq_name = dlq_name or os.environ.get("DLQ_NAME", "scored_signal_dlq")
        self._lock = threading.Lock()
        self._seen_cache: Dict[str, Set[str]] = {}
        os.makedirs(self.root, exist_ok=True)

    # ----- paths -----
    def _qdir(self, queue: str) -> str:
        d = os.path.join(self.root, queue)
        os.makedirs(d, exist_ok=True)
        return d

    def _log(self, queue: str) -> str:
        return os.path.join(self._qdir(queue), "log.jsonl")

    def _seen_file(self, queue: str) -> str:
        return os.path.join(self._qdir(queue), "seen.txt")

    def _load_seen(self, queue: str) -> Set[str]:
        if queue in self._seen_cache:
            return self._seen_cache[queue]
        seen: Set[str] = set()
        p = self._seen_file(queue)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                seen = {line.strip() for line in fh if line.strip()}
        self._seen_cache[queue] = seen
        return seen

    # ----- interface -----
    def publish(self, queue: str, message: dict, *, idempotency_key: str) -> bool:
        with self._lock:
            seen = self._load_seen(queue)
            if idempotency_key in seen:
                return True  # dedupe: already durably published → no-op confirm
            line = json.dumps(
                {"idempotency_key": idempotency_key, "message": message}, sort_keys=True
            )
            with open(self._log(queue), "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
                os.fsync(fh.fileno())  # durable confirm
            with open(self._seen_file(queue), "a", encoding="utf-8") as fh:
                fh.write(idempotency_key + "\n")
            seen.add(idempotency_key)
            return True

    def depth(self, queue: str) -> int:
        p = self._log(queue)
        if not os.path.exists(p):
            return 0
        with open(p, encoding="utf-8") as fh:
            return sum(1 for _ in fh)

    def at_capacity(self, queue: str) -> bool:
        return self.depth(queue) >= self.max_queue_size

    def dead_letter(self, message: dict, reason: str) -> None:
        wrapped = {
            "original_message": message,
            "dlq_reason": reason,
            "dlq_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        # Unique key per DLQ entry (don't dedupe legitimately-distinct failures).
        key = f"{message.get('message_id', 'unknown')}:{reason}:{wrapped['dlq_timestamp']}"
        self.publish(self.dlq_name, wrapped, idempotency_key=key)

    def stats(self, queue: str) -> Dict[str, int]:
        return {
            "published": self.depth(queue),
            "depth": self.depth(queue),
            "dlq": self.depth(self.dlq_name),
        }
