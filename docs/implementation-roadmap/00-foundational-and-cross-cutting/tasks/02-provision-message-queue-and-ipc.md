# FND-002 — Provision Message Queue & Inter-Process Communication Layer

- **Task ID**: FND-002
- **System**: Foundational & Cross-Cutting
- **Priority**: P0-Critical
- **Estimated Effort**: 2d
- **Prerequisites**: None
- **External Dependencies**:
  - A **Redis** instance (recommended primary — single binary, durable AOF, native list/stream primitives, auth + TLS). *Why:* the three queues that decouple Layer 3 → System 3 → Layer 4 must survive across hosts and process restarts; in-process calls cannot cross the Computer 1/2/3 boundary.
  - **Fallback option:** PostgreSQL `LISTEN/NOTIFY` + a durable `queue` table, reusing the FND-004 database. *Why:* avoids running a second service if minimizing moving parts is preferred; documented as the no-new-infra alternative.
  - Network reachability over the FND-008 VPN and credentials stored via FND-003.

## Objective
Provision a durable, authenticated inter-process queue layer carrying `Scored_Signal_Queue`, `AMS_Outbound_Queue`, and `AMS_Inbound_Queue` between Layer 3 (System 1), System 3, and Layer 4 (System 2).

## Current State
Layer 3 (`src/layer3_ml/`) is directly coupled to Layer 4 (`src/layer4_executor/live_pipeline.py`) — the executor loads signals straight from `Fact_Signals` and applies gating in-process. There is no message broker, no cross-host transport, and no backpressure mechanism. Everything runs on one box today.

## Target State
A broker reachable by all three systems exposing three logical queues with at-least-once delivery, durability across restarts, consumer acknowledgement, and a defined staleness/backpressure contract:
- `Scored_Signal_Queue`: produced by Layer 3 (MODEL-008), consumed by System 3 Decision Gate (AMS-003).
- `AMS_Outbound_Queue`: produced by System 3 (AMS-008), consumed by Layer 4 (EXEC-004).
- `AMS_Inbound_Queue`: produced by Layer 4 (EXEC-005), consumed by System 3 post-trade processor (AMS-007).

## Technical Specification

### Topology (Redis Streams recommended)
- One Redis Stream per queue with a consumer group per consumer system, enabling acknowledgement (`XACK`) and replay of unacknowledged entries (`XPENDING`/`XCLAIM`).
- Each message is a self-describing envelope (shared contract owned here, consumed by MODEL/EXEC/AMS):
  ```
  {
    schema_version: int,
    message_id: uuid,          # producer-generated, used for idempotency
    correlation_id: uuid,      # ties signal → decision → fill across all 3 queues
    produced_at: iso8601_utc,
    granularity: "H1"|"H4",    # preserve granularity contract end-to-end
    payload: { ... }           # queue-specific body
  }
  ```
- `correlation_id` is set when Layer 3 emits the signal and propagated unchanged through the decision and the fill, giving end-to-end traceability.

### Durability, delivery, idempotency
- Enable Redis **AOF** persistence (everysec) so queued-but-unprocessed messages survive a broker restart.
- Delivery is **at-least-once**; consumers must be idempotent keyed on `message_id` (de-dup table or seen-set). The trading decision must remain deterministic under redelivery.

### Backpressure & staleness (safety-critical)
- `Scored_Signal_Queue` `MAX_QUEUE_SIZE = 100`. If System 3 is not consuming and depth exceeds the cap, Layer 3 (MODEL-008) **stops producing** new signals rather than unbounded buffering.
- `AMS_Outbound_Queue` carries a `produced_at`; if Layer 4 (EXEC-008) sees the newest approved order is older than **5 minutes**, it enters safe-pause (never trade on stale risk approval).
- A consumer lag metric per queue is exported to FND-005.

### Security
- Require `requirepass`/ACL auth (per-system users with least privilege: producers can only `XADD` to their queue, consumers only read+ack their group).
- TLS in transit; reachable only over the FND-008 VPN. Credentials from FND-003.

### PostgreSQL fallback contract
If Redis is rejected: a `mq_message` table (same envelope columns) with `LISTEN/NOTIFY` for wakeups, `SELECT ... FOR UPDATE SKIP LOCKED` for safe concurrent consume, and a `processed_at` column for ack. Same backpressure/staleness semantics enforced in SQL.

## Testing & Validation
- Round-trip: produce to each queue, consume + ack from the intended system, confirm `correlation_id` survives all three hops.
- Restart durability: enqueue messages, restart the broker, confirm unacked messages are redelivered (none lost).
- Idempotency: redeliver the same `message_id`; consumer must process it exactly once (no duplicate trade).
- Backpressure: stall the `Scored_Signal_Queue` consumer; confirm producer halts at depth 100 and resumes when drained.
- Staleness: stop System 3; confirm `AMS_Outbound_Queue` age crosses 5 min and EXEC-008 safe-pause triggers (validated jointly with EXEC-008).
- AuthZ: a producer key attempting to read another group, or write another queue, is denied.

## Rollback Plan
Queue is introduced behind a feature flag. Until MODEL-008/EXEC-004 are cut over, the legacy in-process Layer 3 → Layer 4 path remains the default. Roll back by flipping the flag to in-process mode and stopping the broker; no persisted trading state is lost because `Fact_Signals`/`Fact_Live_Trades` remain the systems of record.

## Acceptance Criteria
- [ ] Broker provisioned with the three queues, per-system auth, and TLS over the VPN.
- [ ] Message envelope contract documented and round-trip validated with `correlation_id` traceability.
- [ ] Durability across broker restart proven (no unacked message lost).
- [ ] Backpressure (depth 100) and 5-minute staleness semantics demonstrated.
- [ ] PostgreSQL fallback design documented and runnable if Redis is rejected.

## Notes & Risks
- **Redis vs Postgres-NOTIFY trade-off:** Redis Streams give purpose-built consumer-group + replay semantics at the cost of a second service; Postgres fallback adds zero infra but couples queue throughput to the DB and is harder to reason about under load. For H1 cadence either is ample on latency.
- The broker is on the critical execution path — its uptime SLO (FND-005) and the EXEC-008 safe-pause are the paired safety controls.
- Keep payloads small (signal/decision/fill metadata only); large artifacts go through object storage (FND-001), never the queue.
