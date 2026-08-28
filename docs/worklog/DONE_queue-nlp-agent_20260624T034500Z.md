# DONE — queue-nlp-agent — MODEL-008

**Completed:** 2026-06-24T03:45:00Z
**Task:** MODEL-008 — Scored Signal Queue Producer (pluggable QueueBackend)
**Audit gate:** AG-008 — **PASS (9/9)**

## What was produced
- **Pluggable infrastructure (FND-001 / FND-002):**
  - `src/common/queue/` — `QueueBackend` ABC + `LocalDurableBackend` (durable JSONL log, idempotency index, bounded depth, DLQ, fsync publisher confirm) + `build_queue()` factory.
  - `src/common/storage/` — `StorageBackend` ABC + `LocalFSBackend` (immutable versions, atomic pointer, SHA256 round-trip) + `GCSBackend` stub + `build_storage()` factory. (Foundation for MODEL-007.)
- **MODEL-008 producer** `src/system1/queue_producer/producer.py` — `ScoredSignalProducer`: deterministic idempotency keys (`signal_id:score_run_id`), schema-validated messages, bounded-depth backpressure (block/retry, never silent drop), DLQ routing with reasons, publisher confirms, observability metrics. Source-agnostic (consumes an iterable of scored-signal dicts).
- **Contract** `contracts/signal-message-contract.json` (versioned `schema_version: 1.0.0`).
- **Tests** `src/system1/queue_producer/tests/test_producer.py` (7 tests, all pass).

## AG-008 results (9/9)
schema-valid (100 msgs) ✓ · idempotent re-publish→1 ✓ · backpressure caps depth≤max, nothing dropped ✓ · DLQ routing with reason+metric ✓ · **decoupling: zero Layer-4 imports in `src/system1/` + `src/layer3_ml/`** ✓ · H1/H4 preserved ✓ · message_id deterministic ✓ · publisher confirm (durable, not fire-and-forget) ✓ · metrics logged ✓

## Notes
- Runs fully against `LocalDurableBackend` now; swapping to a real broker is a config flip (`QUEUE_PROVIDER` + `QUEUE_URL`) with no code change.
- The producer is **source-agnostic**: when MODEL-006 gatekeeper scores exist (currently blocked — `fact_signals`/`fact_trade_outcomes` empty), a thin DB reader feeds scored signals into `publish_signals()`. The producer, contract, backpressure, DLQ, and decoupling are complete and gated independently of that data, per STORAGE_AND_QUEUE_ABSTRACTION.md.
