# MODEL-008 — Scored Signal Queue Producer

**Task ID:** MODEL-008
**System:** System 1 — Model Building
**Priority:** P0-Critical
**Estimated Effort:** 2d
**Prerequisites:** FND-002
**External Dependencies:**
- **Message queue** (FND-002) — `Scored_Signal_Queue` broker with bounded depth, acknowledgements, and dead-letter support.
- **Queue client library** (per FND-002 choice, e.g. `pika`/`redis`) — publish messages.
- **`ForexBrainDB` (PostgreSQL 16 + TimescaleDB, FND-004)** — source of scored signals (`Fact_Signals` + gatekeeper scores); read via `src/common/db.py`. *(DB = PostgreSQL 16 + TimescaleDB; any historical SQL-Server mention is obsolete.)*

## Objective
Decouple Layer 3 from Layer 4 by publishing scored signals to the Scored_Signal_Queue (consumed by System 3), with backpressure/max-queue-size handling.

## Current State
- Layer 3's gatekeeper output is consumed **in-process** by Layer 4 (`src/layer4_executor/live_pipeline.py` loads the champion artifact and applies the threshold directly). This direct coupling binds training-side scoring to the execution pipeline and prevents the System 1 / System 2 / System 3 split.

## Target State
After scoring (model from MODEL-006 + dynamic threshold), System 1 **publishes each scored signal as a message to `Scored_Signal_Queue`** instead of handing it to Layer 4. System 3 consumes the queue. The producer enforces **bounded queue depth (max-queue-size)** and applies **backpressure** (pause/slow publishing, or block with timeout) when the queue is full, with **dead-letter handling** for un-publishable messages. No code path in System 1 imports or calls Layer 4.

## Technical Specification

**Message contract (`Scored_Signal_Queue`, illustrative):**
```
{
  "message_id": "<idempotency key: signal_id + score_run_id>",
  "signal_id": "...",
  "instrument": "EUR_USD",
  "granularity": "H1",                 // H1/H4 contract preserved
  "signal_time_utc": "...",
  "direction": "long|short",
  "model_score": 0.83,
  "approved": true,
  "threshold_applied": 0.75,           // regime-aware (MODEL-006)
  "regime": "Trending-Up",
  "regime_probs": {...},
  "bundle_version": "...",             // links to MODEL-007 bundle
  "produced_at_utc": "..."
}
```

**Producer behavior:**
- **Idempotency:** `message_id` derived from (`signal_id`, `score_run_id`) so re-publishing the same scored signal is a no-op for the consumer (dedupe key).
- **Backpressure / max-queue-size:** before publishing, respect a configured max depth; when at capacity, apply backpressure — block-with-timeout or pause-and-retry with backoff — rather than overflowing the broker. Never drop a valid scored signal silently.
- **Dead-letter:** messages that repeatedly fail to publish (broker reject, serialization error) go to a DLQ with a reason; alert on DLQ growth.
- **Delivery semantics:** publisher confirms/acks (at-least-once), relying on consumer-side idempotency for exactly-once effect.
- **Decoupling:** the scoring step writes to the queue only; remove/avoid any direct Layer 4 invocation from System 1. (Layer 4 in System 2 will instead consume via System 3's flow.)

**Config / env:** `QUEUE_URL`, `SCORED_SIGNAL_QUEUE` name, `MAX_QUEUE_SIZE`, backpressure timeout/backoff, DLQ name.

**Data flow (text):** gatekeeper scores a batch of signals → build messages with idempotency keys + regime/threshold/bundle context → check queue depth → publish with confirm; on full-queue apply backpressure; on persistent failure route to DLQ → log publish counts + queue depth metrics.

**Observability:** emit metrics for published count, current queue depth, backpressure events, and DLQ count for monitoring/alerts.

## Testing & Validation
- **Contract test:** message schema validates; required fields present; `message_id` deterministic for identical inputs.
- **Idempotency:** publishing the same scored signal twice yields one effective message at the consumer (dedupe verified with a stub consumer).
- **Backpressure:** fill queue to `MAX_QUEUE_SIZE`; assert producer applies backpressure (blocks/retries) and does not exceed the cap or drop messages.
- **DLQ:** force a publish failure; assert message lands in DLQ with reason and an alert metric increments.
- **Decoupling regression:** static check / import test confirms System 1 scoring path has no Layer 4 import or call.
- **Edge cases:** broker unavailable at startup (retry/backoff), partial batch failure (already-published not duplicated), oversized message.

## Rollback Plan
Feature-flag the producer: if the queue is unavailable or the rollout is reverted, fall back to the **existing in-process Layer 3 → Layer 4 path** (kept behind the flag during transition) so the system stays operational. Once System 3 consumption is proven, remove the direct path. The queue itself is durable, so a producer restart resumes without loss.

## Acceptance Criteria
- [ ] Scored signals are published to `Scored_Signal_Queue` with the documented, schema-validated message contract including idempotency key, regime, threshold, and bundle version.
- [ ] Bounded queue depth with backpressure prevents overflow; no valid scored signal is silently dropped.
- [ ] Dead-letter handling routes un-publishable messages with a reason and alerts on growth.
- [ ] System 1 scoring path has no direct Layer 4 import/call (verified by test).
- [ ] H1/H4 granularity contract is preserved in the message payload.

## Notes & Risks
- This is the structural cut between System 1 and System 2/3 — keep the message contract minimal and versioned; consumers (System 3) must agree on the schema.
- Backpressure must favor correctness over throughput: never drop a scored signal to keep the producer fast.
- Retain the in-process fallback only during transition to avoid a flag that quietly re-couples the systems long-term.
