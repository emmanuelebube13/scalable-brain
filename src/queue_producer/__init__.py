"""MODEL-008 — Scored-signal queue producer (publishes to Scored_Signal_Queue).

Decouples System 1 scoring from System 2/3 execution: scored signals are published to
the queue (via the pluggable QueueBackend), never handed to Layer 4. Enforces a
schema-validated contract, deterministic idempotency keys, bounded depth + backpressure,
and DLQ routing. NO import of src/layer4_executor anywhere in this package.
"""
