# Cutover Plan for ADR-001 (Inference Migration)

1. **System 2 Update**: System 2 will pull the published bundle v2 from GCS. It will verify the detached signature (`latest.json.sig`) using the provided public key.
2. **Determinism Verification**: System 2 uses the provided `code_bundle.zip` to run determinism checks against `reference_vector.json` (documented in `DETERMINISM.md`) and database equivalence via `candle_fingerprint.json`.
3. **Queue Re-routing**: System 2 transitions to generating and scoring signals locally, awaiting only heartbeats from the pubsub topic to prove liveness.
4. **System 1 Legacy Disable**: A single config change `DISABLE_LEGACY_SIGNALS=true` in System 1's `.env` structurally drops the old signal emission path. The `publish_signals` block is fully bypassed, ensuring double-publishing is structurally impossible while keeping the heartbeat active.
