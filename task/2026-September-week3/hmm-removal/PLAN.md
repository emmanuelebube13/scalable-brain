# HMM removal — dependency map and ordered plan (2026-09-17)

**Owner proposal:** remove the HMM regime model from the pipeline entirely (history:
fold collapse, H4 degeneracy, rank-artifact mappings) and standardize on the structural
labeller. Dependency mapping done 2026-09-17 (read-only agent pass).

**Headline:** the decision path is ALREADY off the HMM — routing
(`map_contract.ROUTING_SOURCE_LABEL`), attribution (`SELECTION_SOURCE_LABEL`), vetting,
live regime reads, and the live 1.0.0 champion's features are all structural. The HMM
survives in exactly three load-bearing places:

1. **The orchestrator's quality gate** (`orchestrator._default_pipeline` runs
   `hmm_regime.run` and gates on `min(holdout_accuracy)`; removing it with nothing in
   its place fails `regime_accuracy_ok`/`beats_incumbent` forever and stops the weekly
   map renewal — the exact blackout the 2026-09-16 split was built to prevent). Note the
   metric is a *stability/agreement* score for a fitted model, meaningless for the
   deterministic structural rule — a replacement gate must be designed, not ported.
2. **The publish contract** — `serialize.SOURCES` + `publish_model_set.S1_ARTIFACTS`
   require `hmm_model.joblib`; dropping the artifact without changing both aborts every
   publish. Today the pipeline ships an increasingly stale frozen model (landmine).
3. **System 2's dashboard tile** — `live_regime.py` loads `hmm_model.joblib` per the
   frozen 2026-08-23 comms contract. Read-only/non-risk-bearing, but retiring the
   artifact needs a NEW dated comms notice (append-only rule), not a code change.

Everything else is trivial: inert enum members (`regime_causal` in `map_contract`,
`hmm_causal` in the status contract), dead SQL branches in `attribute.py`, the
non-blocking `risk_off` contract entry, standalone research scripts
(`discrimination.py` — its "regimes do not discriminate" finding is already a standing
finding), tombstoned layer3_ml references, and test-suite surgery proportional to the
gate redesign. `heartbeat.check_regimes` must be retired/repointed in the same change or
the heartbeat goes permanently red. `gatekeeper/train.py`'s `include_causal` path stays
until no audited bundle needs re-scoring against the causal schema (model_card check).
`build.py`'s hardcoded 0.25 `regime_probs` is NOT an HMM dependency (overwritten by
run.py with structural one-hots).

## Ordered plan (do not reorder 1→3)

1. Design + land the replacement bundle-quality gate (candidate: `non_empty_map` +
   vetting coverage stats + map-contract admissibility; retire `regime_accuracy_ok` and
   re-base `beats_incumbent` on a bundle-level metric that still exists). Update
   scheduler/serializer tests.
2. Send the dated comms notice to System 2: `hmm_model.joblib` stops publishing on
   <date>; their `LiveRegimeDetector` tile retires or serves `last_good` — their call,
   on the record.
3. Remove the artifact from `serialize.SOURCES` + `S1_ARTIFACTS` (+ tests, + any schema
   listing it).
4. Retire/repoint `heartbeat.check_regimes`.
5. Confirm no audit bundle needs `include_causal`, then delete that branch.
6. Delete `hmm_regime.py`/`mapping.py`/`schema.py`/`simulate_scatter.py`, dead causal
   branches, HMM test files; archive one-off scripts.
7. Decide `fact_market_regime_v2`'s fate last (drop vs read-only orphan for the
   discrimination study's reproducibility).

**Status:** step 0 (this map) done. Step 1 is the design task — not started, needs a
definition of done before work begins (see task/CLAUDE.md).
