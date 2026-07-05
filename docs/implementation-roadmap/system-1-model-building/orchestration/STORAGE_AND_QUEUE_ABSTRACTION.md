# STORAGE & QUEUE ABSTRACTION — System 1

System 1 has **no object store and no message broker provisioned yet**. You will attach **Google
Cloud Storage** (and, later, a real queue broker) and wire them in by **configuration only**. So all
task code is written against two **pluggable interfaces** with **local-filesystem defaults** that
faithfully reproduce the production semantics (immutable versions, atomic pointer, SHA256 round-trip,
encryption flag, bounded depth, acks, DLQ). This satisfies **FND-001** (storage) and **FND-002**
(queue) today, unblocking MODEL-007 and MODEL-008.

> **Rule:** task code imports the **factory**, never a vendor SDK. Swapping `local → gcs` is an
> `.env` change, not a code change.

---

## 1. `StorageBackend` (FND-001 — MODEL-007 / MODEL-009)

### Configuration (`.env`)
```
STORAGE_PROVIDER=local           # local (default now) | gcs (attach later)
STORAGE_LOCAL_ROOT=model-artifacts        # used when provider=local
# --- attached later, only when STORAGE_PROVIDER=gcs ---
# GCS_BUCKET=scalable-brain-model-artifacts
# GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
# STORAGE_ENABLE_ENCRYPTION=true   # GCS is encrypted at rest by default; CMEK optional
```

### Interface (`src/common/storage/base.py`)
```python
from abc import ABC, abstractmethod
from typing import Iterable

class StorageBackend(ABC):
    @abstractmethod
    def put_object(self, key: str, local_path: str, *, encrypt: bool = True) -> None: ...
    @abstractmethod
    def get_object(self, key: str, local_path: str) -> None: ...
    @abstractmethod
    def head(self, key: str) -> dict: ...          # {size, sha256?, encrypted: bool, ...}
    @abstractmethod
    def exists(self, key: str) -> bool: ...
    @abstractmethod
    def list(self, prefix: str) -> Iterable[str]: ...
    @abstractmethod
    def sha256(self, key: str) -> str: ...          # hash of stored object (round-trip verify)
    @abstractmethod
    def atomic_pointer_update(self, pointer_key: str, payload: dict) -> None: ...  # write-temp+rename
    @abstractmethod
    def delete_prefix(self, prefix: str) -> None: ...  # cleanup partial/old versions
```

### Factory (`src/common/storage/__init__.py`)
```python
import os
def build_storage() -> "StorageBackend":
    provider = os.environ.get("STORAGE_PROVIDER", "local").lower()
    if provider == "local":
        from .local_fs import LocalFSBackend
        return LocalFSBackend(root=os.environ.get("STORAGE_LOCAL_ROOT", "model-artifacts"))
    if provider == "gcs":
        from .gcs import GCSBackend
        return GCSBackend(bucket=os.environ["GCS_BUCKET"])
    raise ValueError(f"Unknown STORAGE_PROVIDER={provider!r}")
```

### Local default semantics (`LocalFSBackend`)
- Objects are files under `STORAGE_LOCAL_ROOT/`; `key` maps to a relative path.
- **Immutable versions:** `model-artifacts/{bundle_version}/…` written once; never overwritten.
- **Atomic pointer:** `latest.json` written to a temp file then `os.replace()` (atomic on POSIX) so a
  reader never sees a half-written pointer — the local analogue of the S3 "update pointer last" rule.
- **SHA256 round-trip:** `sha256(key)` re-reads the stored bytes; MODEL-007 verifies it equals the
  locally computed hash **before** advancing `latest.json`.
- **Encryption flag:** local has no SSE; `head()` returns `encrypted=False` and `put_object(encrypt=True)`
  records the *intent* in metadata. The audit's encryption check is **skipped-with-note** for `local`
  and **enforced** for `gcs`. (Do not fake an encryption flag.)
- **Lifecycle:** keep last N (default 5) bundle versions; `delete_prefix` trims older ones.

### GCS adapter (attach later — `GCSBackend`)
- Uses `google-cloud-storage` (added to `requirements.txt` only when GCS is attached).
- GCS is **encrypted at rest by default** (Google-managed keys; CMEK optional) → `head().encrypted=True`.
- TLS in transit is default for the GCS API.
- `atomic_pointer_update` uses a single-object overwrite with generation/precondition where available;
  the upload-everything-then-flip-pointer ordering from `object-storage-protocol.md` is unchanged.
- **Same MODEL-007 code path** — only the backend object differs.

### MODEL-007 publish ordering (backend-agnostic)
1. compute local SHA256 for every artifact →
2. write `model_metadata.json` + `checksums.sha256` →
3. `put_object` all files to `model-artifacts/{bundle_version}/` →
4. `sha256(key)` round-trip verify every object (on mismatch: `delete_prefix`, abort, do **not** flip) →
5. `atomic_pointer_update("latest.json", …)` **only after** all verifies pass.

---

## 2. `QueueBackend` (FND-002 — MODEL-008)

### Configuration (`.env`)
```
QUEUE_PROVIDER=local             # local (default now) | redis | rabbitmq (attach later)
QUEUE_LOCAL_ROOT=results/state/queue
SCORED_SIGNAL_QUEUE=scored_signal_queue
MAX_QUEUE_SIZE=100000
DLQ_NAME=scored_signal_dlq
# --- attached later, only for a real broker ---
# QUEUE_URL=redis://localhost:6379/0   (or amqp://…)
```

### Interface (`src/common/queue/base.py`)
```python
from abc import ABC, abstractmethod

class QueueBackend(ABC):
    @abstractmethod
    def publish(self, queue: str, message: dict, *, idempotency_key: str) -> bool: ...  # confirm/ack
    @abstractmethod
    def depth(self, queue: str) -> int: ...
    @abstractmethod
    def at_capacity(self, queue: str) -> bool: ...   # depth >= MAX_QUEUE_SIZE → backpressure
    @abstractmethod
    def dead_letter(self, message: dict, reason: str) -> None: ...
    @abstractmethod
    def stats(self, queue: str) -> dict: ...          # {published, dlq, backpressure_events, depth}
```

### Factory (`src/common/queue/__init__.py`)
```python
import os
def build_queue() -> "QueueBackend":
    provider = os.environ.get("QUEUE_PROVIDER", "local").lower()
    if provider == "local":
        from .local_durable import LocalDurableBackend
        return LocalDurableBackend(root=os.environ.get("QUEUE_LOCAL_ROOT", "results/state/queue"))
    # redis / rabbitmq adapters added when a broker is attached
    raise ValueError(f"Unknown QUEUE_PROVIDER={provider!r}")
```

### Local default semantics (`LocalDurableBackend`)
- **Durable:** append-only log files under `QUEUE_LOCAL_ROOT/{queue}/` (one JSON line per message) +
  a sidecar offset; survives process restart (the durability MODEL-008 requires).
- **Idempotency:** a `seen/{idempotency_key}` marker (or an index) dedupes re-publishes — publishing
  the same `message_id` twice is a no-op, matching the consumer-side dedupe contract.
- **Bounded depth + backpressure:** `at_capacity()` compares depth to `MAX_QUEUE_SIZE`; the producer
  **blocks/retries with backoff** when full — never silently drops a valid scored signal.
- **DLQ:** `dead_letter()` writes to `QUEUE_LOCAL_ROOT/{DLQ_NAME}/` with `dlq_reason` + timestamp +
  original message; `stats()` exposes counts for the alert metric.
- **Publisher confirms:** `publish()` returns only after the message is durably written (at-least-once);
  exactly-once effect comes from consumer-side idempotency.

### Real broker (attach later)
- Add a `redis_streams.py` / `rabbitmq.py` adapter implementing the same interface; set `QUEUE_PROVIDER`
  + `QUEUE_URL`. **MODEL-008 code is unchanged.** The message schema in
  `tasks/agents/queue-nlp-agent.md` and `contracts/signal-message-contract.json` is the hard,
  versioned interface to System 3 regardless of backend.

---

## 3. Why this satisfies the audit gates now

- **AG-007** (bundle integrity, atomic pointer, round-trip SHA256, no-secrets scan) runs fully against
  `LocalFSBackend`. The **encryption-at-rest** check is recorded as *N/A-local, enforced-on-gcs* — an
  honest, explicit note rather than a faked pass.
- **AG-008** (message schema, idempotency, backpressure, DLQ, decoupling, confirms) runs fully against
  `LocalDurableBackend`.
- When you attach GCS / a broker, re-run AG-007 / AG-008 against the real backends — no task code
  changes, only `.env` and the new adapter file.
