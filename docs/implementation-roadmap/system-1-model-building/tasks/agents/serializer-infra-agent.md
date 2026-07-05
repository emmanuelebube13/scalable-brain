# Serializer & Infrastructure Agent

**Agent ID:** `serializer-infra-agent`
**File:** `docs/implementation-roadmap/system-1-model-building/tasks/agents/serializer-infra-agent.md`
**Role:** Bundle serialization, artifact registry with atomic publication, and automated retraining orchestration.

---

## Assigned Tasks

| Task | Description | Priority | Est. Days | Prerequisites |
|------|-------------|----------|-----------|---------------|
| [MODEL-007](../07-model-serializer-and-artifact-registry.md) | Model Serializer & Artifact Registry | P0 | 3d | FND-001, MODEL-003, MODEL-005 |
| [MODEL-009](../09-retraining-scheduler.md) | Retraining Scheduler | P2 | 3d | MODEL-007 |

---

## Skills

Before starting, load these skill files:

- `skills/object-storage-protocol.md` — Atomic pointer, SHA256 round-trip, encryption, lifecycle
- `skills/postgres-patterns.md` — DB connection for reading live performance metrics
- `skills/layer3-contract.md` — Champion manifest structure (for bundle metadata compatibility)

The following packages must be in `requirements.txt` before starting:
```
boto3>=1.34.0          # or minio>=7.2.0 for object storage
joblib>=1.3.0          # already present — for HMM deserialization
```

---

## Communication With Other Agents

### Upstream (dependencies)
| Producer Agent | Consumed Artifact | Path |
|----------------|-------------------|------|
| `ml-regime-agent` | `hmm_model.joblib` (fitted HMM + scaler + mapping) | `models/hmm_model.joblib` |
| `attribution-vetting-agent` | `regime_strategy_map.json` | `results/state/regime_strategy_map.json` |
| `attribution-vetting-agent` | `strategy_weights.json` | `results/state/strategy_weights.json` |
| `ml-regime-agent` | Champion manifest (optional, for dynamic thresholds ref) | `models/champion_manifest.json` |
| `data-pipeline-agent` | Feature store version metadata | `feature-store/{version}/lineage.json` |
| (System 2/3 telemetry) | Live performance metrics (for MODEL-009 triggers) | Queue/telemetry |

### Downstream (consumers)
| Consumer | Consumes | Contract |
|----------|----------|----------|
| System 2 / Computer 2 | `latest.json` → full bundle | `contracts/bundle-contract.json` |
| `auditor-traceback-agent` | Bundle checksums, promotion logs | MLflow / `results/state/` |
| (Self, MODEL-009) | Scheduled/triggered retrain orchestration | Cron + performance triggers |

---

## Input Contracts

### MODEL-007 Inputs (collected artifacts)
- `models/hmm_model.joblib` — From `ml-regime-agent` (MODEL-003). Must exist and be loadable via `joblib.load()`.
- `results/state/regime_strategy_map.json` — From `attribution-vetting-agent` (MODEL-005). Must pass JSON schema validation.
- `results/state/strategy_weights.json` — From `attribution-vetting-agent` (MODEL-005). Must pass JSON schema validation.
- `models/champion_manifest.json` — Optional. If present, reference `dynamic_thresholds` in bundle metadata.
- `feature-store/{version}/lineage.json` — For `feature_set_version` in metadata.
- Object storage credentials from `.env`: `STORAGE_ENDPOINT`, `STORAGE_ACCESS_KEY`, `STORAGE_SECRET_KEY`, `STORAGE_BUCKET`, `STORAGE_USE_TLS=true`.

### MODEL-009 Inputs
- Cron: system-level crontab entry (or scheduler library).
- Performance metrics source (for triggers):
  - 14-day rolling Sharpe from live trade outcomes (System 2/3 telemetry queue or `Fact_Live_Trades`).
  - Regime accuracy from MLflow or HMM evaluation (produced by `ml-regime-agent`).
  - Circuit-breaker events from System 2/3 (queue message).
- All pipeline step executables (ingest, features, regime, attribution, vetting, gatekeeper, serialize).

---

## Output Contracts

### MODEL-007 Outputs

1. **Bundle per version** — `model-artifacts/{bundle_version}/`
   ```
   model-artifacts/2026-06-23T00-00-00Z/
   ├── hmm_model.joblib
   ├── strategy_weights.json
   ├── regime_strategy_map.json
   ├── model_metadata.json
   └── checksums.sha256
   ```
   - All files immutable once written.

2. **`model_metadata.json`**
   ```json
   {
     "bundle_version": "2026-06-23T00:00:00Z",
     "schema_version": "1.0.0",
     "created_by": "computer-1",
     "regime_model_version": "hmm_v1",
     "feature_set_version": "1.0.0",
     "vetting_run_id": "...",
     "mlflow_run_id": "...",
     "artifacts": {
       "hmm_model.joblib": {"sha256": "abc123...", "bytes": 12345},
       "strategy_weights.json": {"sha256": "def456...", "bytes": 234},
       "regime_strategy_map.json": {"sha256": "ghi789...", "bytes": 567}
     },
     "metrics": {
       "regime_accuracy": 0.82,
       "n_qualified_strategies": 4
     },
     "dynamic_thresholds_ref": "champion_manifest.json#dynamic_thresholds"
   }
   ```

3. **`checksums.sha256`** — SHA256 hash per file, one per line (standard `sha256sum` format).
   ```
   abc123...  hmm_model.joblib
   def456...  strategy_weights.json
   ghi789...  regime_strategy_map.json
   ```

4. **`latest.json`** (mutable pointer at bucket root)
   ```json
   {
     "bundle_version": "2026-06-23T00:00:00Z",
     "path": "model-artifacts/2026-06-23T00-00-00Z/",
     "metadata_sha256": "xyz789...",
     "promoted_at_utc": "2026-06-23T00:05:00Z"
   }
   ```

5. **MLflow run** — Log bundle version, artifact checksums, promotion status.

### MODEL-009 Outputs

1. **Scheduled/triggered pipeline runs** — Each run produces:
   - MLflow run with trigger reason, step outcomes, gate results, candidate vs incumbent metrics, promote/skip decision.
   - `results/state/retrain_log_{timestamp}.json` — Local copy of the run record.
   - Incremental data updates (MODEL-001 delta pass).

2. **Promotion decision** — Either:
   - `latest.json` updated to new `bundle_version` (candidate passed all gates).
   - `latest.json` left unchanged (candidate failed a gate). Alert emitted.

3. **`results/state/retrain_state.json`** — Cooldown tracking, last successful retrain timestamp, last trigger reason.

---

## Verification Gates (Self-Check Before Handoff)

### MODEL-007 Gates
- [ ] **Round-trip checksum**: upload → download → recompute SHA256 → must match for every artifact.
- [ ] **Atomic pointer**: simulate upload interruption (kill after partial upload) → `latest.json` must still point to the previous valid version, not the incomplete one.
- [ ] **Guard: missing artifact**: serializer refuses to promote if any required artifact is absent (exit non-zero).
- [ ] **Guard: checksum mismatch**: serializer refuses to promote if any artifact's SHA256 doesn't match its computed value (exit non-zero).
- [ ] **Guard: empty regime map**: serializer refuses to promote if `regime_strategy_map.json` has zero qualifying strategies across all regimes.
- [ ] **Encryption**: every uploaded object has server-side encryption-at-rest flag enabled.
- [ ] **TLS**: all transfers use HTTPS (verify via endpoint URL).
- [ ] **No secrets in artifacts**: scan every file in the bundle for credential patterns (API keys, passwords, tokens).
- [ ] **Lifecycle policy**: bucket retains at least the last 5 versions for rollback.

### MODEL-009 Gates
- [ ] **Scheduled retrain**: cron fires at Sunday 00:00 UTC (simulate clock skew) → pipeline runs end-to-end within the compute budget.
- [ ] **Performance triggers** (each tested independently):
  - Inject 14-day Sharpe < 0.3 → retrain fires.
  - Inject regime accuracy < 70% → retrain fires.
  - Inject circuit-breaker message → retrain fires.
- [ ] **Cooldown debounce**: trigger fires twice within cooldown window → only one retrain executes.
- [ ] **Single-flight lock**: scheduled + triggered runs overlap → only one runs, the other exits with "locked" status.
- [ ] **Deployment gate: degraded candidate**: inject a deliberately degraded model → NOT promoted, incumbent `latest.json` unchanged, alert emitted.
- [ ] **Deployment gate: passing candidate**: a candidate passing all gates → `latest.json` atomically updated to new version.
- [ ] **Interrupted retrain**: kill pipeline mid-run → no partial promotion (relies on MODEL-007 atomic pointer), clean restart possible.
- [ ] **Missing metrics**: live metrics unavailable (e.g., empty `Fact_Live_Trades`) → fail safe, do NOT trigger performance retrain, log "metrics unavailable".

---

## Failure Modes & Escalation

| Failure | Detection | Action | Escalate To |
|---------|-----------|--------|-------------|
| Object storage unreachable | Connection error / timeout | Retry with backoff (3 attempts). If persistent, abort, keep incumbent, alert. | `auditor-traceback-agent` |
| Checksum mismatch after upload | Read-back SHA256 ≠ local SHA256 | Delete the corrupt object, re-upload, re-verify. If persistent, abort, alert. | `auditor-traceback-agent` |
| Concurrent publish attempt | Lock contention on `latest.json` | Later publisher wins atomically (S3 last-write-wins). Both log their attempt. | Self (handled) |
| Deployment gate failure (candidate worse) | OOS uplift < incumbent or other gate fail | Block promotion, log comparison, alert, keep incumbent. Shadow/canary the candidate. | `auditor-traceback-agent` |
| Pipeline step failure during retrain | Non-zero exit code from any step | Abort retrain, log which step failed, alert, keep incumbent. Do NOT promote. | The agent responsible for the failed step (for rework) |
| Cooldown storm | Performance metric oscillating around trigger threshold | Debounce prevents repeated retrains. Log trigger frequency for investigation. | Self (handled) |
| `latest.json` rollback needed | A promoted model misbehaves in production | Revert `latest.json` to point to previous `bundle_version`. Instant rollback. | Self (manual or automated) |

---

## Notes

- **Version drift between Computer 1 and Computer 2 is the highest-impact failure mode.** The atomic `latest.json` + mandatory checksum verification on the consumer side is the primary control. Computer 2 must verify checksums before loading.
- Keep the bundle's `schema_version` strict. Any change to `regime_strategy_map.json` / `strategy_weights.json` shape is a coordinated, versioned change with System 2.
- No secrets ever in metadata or artifacts. Scan every file before upload.
- Auto-promoting a worse champion is the key MODEL-009 risk. The must-beat-incumbent OOS gate + optional shadow/canary + one-click pointer rollback are the controls.
- Performance triggers depend on live metrics flowing back from System 2/3. Define that contract before MODEL-009 goes live — if System 2/3 doesn't emit telemetry, performance triggers are inert (which is safe: no false retrains).
- `shell/retrain_tournament.sh` and `shell/cron_layer4_pipeline.sh` patterns exist and can be extended for MODEL-009's scheduler.
- Single-flight locking: use a file lock (`results/state/retrain.lock`) or DB advisory lock to prevent concurrent runs.
