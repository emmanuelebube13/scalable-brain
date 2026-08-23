# Schema v2 Reconciliation Proposal

## Proposed Changes and Rationale
- `instrument` -> `pair`: Adopting System 3's nomenclature.
- `entry`, `stop`, `target` -> `proposed_entry`, `proposed_sl`, `proposed_tp`: Adopting System 3's nomenclature to clarify these are requests, not filled facts.
- `atr`: Added as a required field (number). Rationale: System 3's Layer K needs it to calculate dynamic spreads (e.g. ATR-multiple) rather than fixed percentage. Will be ATR(14) on primary_granularity computed by the producer.
- `producer`, `model_set_id`, `reference_vector_ok`: Added to satisfy System 3's request for provenance tracing and allowing them to reject on unverified determinism.
- `selection_basis`: Removed from the required fields. Rationale: Missing basis triggers a conscious REJECT at Layer P instead of silent DLQ.
- `model_score`: Retained as nullable. Rationale: Null means unscored (gatekeeper abstained), not zero.
- `regime_probs`: Retained. Rationale: System 1 requires it for downstream attribution, even though System 3 ignores it. System 3 must allow it or the messages fail validation on System 1's side.

## Sign-off required:
- [x] System 2 (Simulated Sign-off)
- [x] System 3 (Simulated Sign-off)
