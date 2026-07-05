# FOLDER STRUCTURE & PLACEMENT RULES — System 1

Owned by the **structure-coherency-agent**. **Before creating any new file or folder, an agent must
confirm its path here** (or get this doc updated). Goal: one obvious home for everything, no drift,
no duplication, no surprise paths. Reuse existing locations over inventing new ones.

---

## Canonical layout

```
scalable-brain/
├── src/
│   ├── common/
│   │   ├── db.py                          # canonical DB connection (EXISTS — use, never bypass)
│   │   ├── storage/                        # NEW — pluggable StorageBackend (MODEL-007)
│   │   │   ├── __init__.py                 #   factory: build_storage() reads STORAGE_PROVIDER
│   │   │   ├── base.py                      #   StorageBackend ABC
│   │   │   ├── local_fs.py                  #   LocalFSBackend (default)
│   │   │   └── gcs.py                       #   GCSBackend (stub now; wired when GCS attaches)
│   │   └── queue/                           # NEW — pluggable QueueBackend (MODEL-008)
│   │       ├── __init__.py                  #   factory: build_queue() reads QUEUE_PROVIDER
│   │       ├── base.py                      #   QueueBackend ABC
│   │       └── local_durable.py             #   LocalDurableBackend (default)
│   ├── system1/                            # NEW — System-1 task code lives here (additive)
│   │   ├── ingestion/                       # MODEL-001 extensions (W1, DQ, quarantine, lineage, gap report)
│   │   ├── features/                        # MODEL-002 feature pipeline
│   │   ├── regime/                          # MODEL-003 HMM (+ K-Means fallback adapter)
│   │   ├── attribution/                     # MODEL-004 per-regime attribution
│   │   ├── vetting/                         # MODEL-005 gates + map/weights emitters
│   │   ├── gatekeeper/                      # MODEL-006 regime features + dynamic threshold + OOS uplift
│   │   ├── serializer/                      # MODEL-007 bundle/registry
│   │   ├── scheduler/                       # MODEL-009 retraining orchestrator
│   │   ├── queue_producer/                  # MODEL-008 scored-signal producer
│   │   └── macro/                           # MODEL-010 FinBERT macro features + veto
│   ├── layer0/ … layer7/, nlp/             # EXISTING — extend in place where the spec says so
│   └── …
├── feature-store/                          # MODEL-002 output (versioned Parquet)
│   └── {feature_set_version}/
│       ├── schema.json
│       ├── lineage.json
│       └── granularity={D1|H4|W1}/year=YYYY/part-*.parquet
├── model-artifacts/                        # MODEL-007 output (local StorageBackend root)
│   ├── latest.json                         # mutable pointer (atomic update)
│   └── {bundle_version}/                    # immutable version
│       ├── hmm_model.joblib
│       ├── strategy_weights.json
│       ├── regime_strategy_map.json
│       ├── model_metadata.json
│       └── checksums.sha256
├── models/                                 # EXISTING — champion artifacts (MODEL-003/006 write here)
│   ├── hmm_model.joblib
│   ├── champion_model.pkl / champion_preprocessor.pkl / champion_manifest.json
├── results/
│   ├── reports/                            # *_manifest_*.json, dq_gap_report_*.json, attribution_*, vetting_*
│   └── state/                              # the coordination + handoff surface
│       ├── ingest_progress.json
│       ├── regime_strategy_map.json / strategy_weights.json
│       ├── retrain_state.json / retrain_log_*.json
│       ├── queue/                          # LocalDurableBackend root (queue + DLQ)
│       ├── audit_log.json / audit_log.md
│       ├── DONE_{agent}_{ts}.md            # completion markers
│       ├── rework/{agent}_{ts}.md          # auditor rework directives
│       └── blocked/{agent}.md              # auditor blocks
├── contracts/                              # JSON-schema contracts referenced by fleet README
│   ├── feature-store-contract.json, hmm-serialization-contract.json, champion-manifest-contract.json
│   ├── regime-map-contract.json, weights-contract.json, bundle-contract.json
│   ├── signal-message-contract.json, macro-veto-contract.json, cursor-contract.json
└── docs/implementation-roadmap/system-1-model-building/
    ├── tasks/ (specs, agents, skills)      # EXISTING — specs are source of truth
    └── orchestration/                       # THIS folder — prompt + living docs + governance
```

---

## Naming conventions

- **Python modules:** `snake_case.py`; one module = one responsibility; type hints + docstrings
  (mypy/black clean per repo CLAUDE.md).
- **Fact/Dim tables:** `Fact_*` / `Dim_*`; columns lowercase except `"Open"`/`"Close"`/`"timestamp"`.
- **Versioned dirs:** feature store = `feature_set_version` (semver or content hash);
  bundles = ISO-8601 UTC `bundle_version` (e.g. `2026-06-23T00-00-00Z`), immutable.
- **State/handoff files:** `DONE_{agent}_{ISO-UTC}.md`, `rework/{agent}_{ISO-UTC}.md`,
  `blocked/{agent}.md`, reports as `{kind}_report_{ISO-UTC}.json`.
- **Contracts:** `contracts/{name}-contract.json`, validated by both producer and consumer.

---

## Placement rules ("where does a new file go?")

1. **DB access?** Use `src/common/db.py`. Never create another connection module.
2. **Storage/queue access?** Use `src/common/storage/` and `src/common/queue/` factories. Never
   import a cloud SDK directly in task code.
3. **New System-1 logic?** Under `src/system1/<module>/` matching the task — unless the spec says to
   extend an existing layer file (e.g., MODEL-001 extends `src/layer0/ingest_oanda_prices.py`,
   MODEL-003 extends `src/layer1_regime/Fact_market_regime_v2.py`, MODEL-006 extends
   `src/layer3_ml/…`). Extend-in-place beats new-file when the spec points at existing code.
4. **An artifact a downstream task consumes?** Put it at the **exact path** in the producing agent's
   `## Output Contracts`. Do not relocate contracted paths.
5. **Tests?** Beside the code under a `tests/` subfolder (mirrors existing `src/layerN/tests/`).
6. **Anything ambiguous?** Stop and have the structure-coherency-agent decide + record it here.

---

## Coherency invariants (enforced with the auditor's AG-CROSS)

- **One canonical granularity set:** D1 primary, H4 entry, W1 macro context, H1/H4 preserved for
  Layer 2/3. No module may assume a granularity an upstream didn't produce.
- **No duplicated logic:** indicators/metrics come from the feature store / skills, not re-implemented
  per module.
- **Versions align across the chain:** `feature_set_version` (MODEL-002) ↔ HMM input (MODEL-003) ↔
  champion manifest (MODEL-006) ↔ bundle metadata (MODEL-007).
- **Additive & reversible:** new columns/files only; every task's Rollback Plan must hold.
