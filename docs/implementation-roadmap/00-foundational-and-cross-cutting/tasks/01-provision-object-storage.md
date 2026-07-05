# FND-001 — Provision Object Storage

- **Task ID**: FND-001
- **System**: Foundational & Cross-Cutting
- **Priority**: P0-Critical
- **Estimated Effort**: 2d
- **Prerequisites**: None
- **External Dependencies**:
  - An **S3-compatible object store**: self-hosted **MinIO** (recommended primary — runs as a container on Computer 1, no recurring fee) or **Cloudflare R2** (S3 API, zero egress fee, ~$0.015/GB-mo). *Why:* the three computers no longer share a filesystem; models/configs/performance artifacts must move between them through one neutral store.
  - A DNS name + TLS certificate for the endpoint if accessed across hosts (or rely on the VPN hostname from FND-008). *Why:* encryption in transit for artifact transfer.
  - Access-key/secret-key pairs (provisioned, but their **storage** is owned by FND-003).

## Objective
Provision S3-compatible object storage as the versioned model/config/performance artifact exchange between Computer 1, Computer 2, and Computer 3.

## Current State
Model artifacts live on the local filesystem under `models/` (`champion_model.pkl`, `champion_preprocessor.pkl`, `champion_manifest.json`, plus legacy `best_ml_gatekeeper_sklearn.pkl` / `best_ml_gatekeeper_preprocessor.pkl` and `ml_gatekeeper_run_*.json`). Layer 3 writes them; Layer 4 reads them from the same box. `models/` is `.gitignore`d (only `.gitkeep` tracked). There is **no** cross-host artifact exchange today. Run reports live under `results/` (reports/sql/state).

## Target State
A single bucket (e.g. `scalable-brain`) reachable by all three hosts over the private network, with:
- Computer 1 (System 1) writing models/configs/performance with **write** scope.
- Computer 2 (System 2) reading models/configs with **read-only** scope.
- Computer 3 (System 3) reading configs + writing performance/audit artifacts.
- Versioning, lifecycle/retention, server-side encryption at rest, and a `latest.json` pointer protocol so consumers atomically learn which version is current.

## Technical Specification

### Bucket / prefix layout
```
scalable-brain/
  models/
    <model_id>/<version>/          # e.g. gatekeeper/2026-06-20T14-00Z-<sha256[:8]>/
      champion_model.pkl
      champion_preprocessor.pkl
      champion_manifest.json        # features, thresholds, sha256 (matches existing contract)
    latest.json                     # { "model_id": "...", "version": "...", "sha256": "...", "published_at": "..." }
  configs/
    layer2_strategies/<version>/    # promoted strategy SQL/config snapshots
    runtime/<system>/<version>/     # per-system runtime config snapshots
    latest.json
  performance/
    daily/<YYYY-MM-DD>/             # equity, KPI, trade summaries (System 3 / Layer 6 outputs)
    reports/<run_id>/               # qualification reports mirrored from results/reports/
```

### `latest.json` pointer protocol
- Producers write the versioned object **first**, verify the SHA256, then overwrite `latest.json` last (write-after-verify). This guarantees consumers never see a pointer to a partial object.
- Consumers read `latest.json`, fetch the referenced version, and **re-verify SHA256 against the manifest** before use (preserves the existing artifact-integrity contract). On mismatch: fall back to the last locally cached good version and raise an alert (channels owned by FND-005 / AMS-011).
- Layer 4's existing champion→legacy fallback logic is preserved: if `latest.json`/champion is unavailable, consumers may use a cached legacy artifact.

### Versioning, retention, lifecycle
- Enable **object versioning** on the bucket so an overwrite never destroys prior bytes.
- Retention: keep **all** model versions for 90 days, then keep **only** the most recent 10 plus any version still referenced by a `latest.json`. `performance/daily/` kept 1 year, then archived. `configs/` kept indefinitely (small).
- Lifecycle rule transitions old `performance/` to cheaper/cold tier where the backend supports it.

### Access keys & least privilege
- Three key pairs, scoped by prefix: `system1-rw` (write models/configs/performance), `system2-ro` (read models/configs), `system3-rwp` (read configs, write performance). No single key has delete-all.
- Keys are stored and distributed by **FND-003**, not hardcoded.

### Encryption
- **At rest:** enable server-side encryption (MinIO SSE-S3 / R2 default encryption).
- **In transit:** TLS endpoint; cross-host access only over the FND-008 VPN.

## Testing & Validation
- Round-trip: from Computer 1, publish a dummy model version + `latest.json`; from Computer 2, read `latest.json`, fetch, and SHA256-verify — must match.
- Tampering test: corrupt a stored object; consumer SHA256 check must **fail closed** and fall back to cached good artifact.
- Permission test: `system2-ro` key attempting a write or delete must be **denied**.
- Atomicity test: kill the producer mid-publish (after versioned write, before `latest.json`); consumer must still see the previous good `latest.json`.
- Versioning test: overwrite an object and confirm the prior version is still retrievable.
- Lifecycle dry-run: confirm retention rules select the correct objects for expiry without deleting referenced versions.

## Rollback Plan
Object storage is **additive** — Layer 3/4 keep working off local `models/` until consumers are switched. To roll back: repoint consumers to local paths (env flag), stop publishing to the bucket. No data loss because the local filesystem copy remains the source until cutover is confirmed. The bucket can be torn down independently.

## Acceptance Criteria
- [ ] Bucket exists with `models/`, `configs/`, `performance/` prefixes and a working `latest.json` pointer protocol.
- [ ] Three least-privilege key pairs exist; read-only key is verifiably denied write/delete.
- [ ] Versioning + at-rest encryption + a retention/lifecycle policy are enabled and dry-run-validated.
- [ ] A model published from Computer 1 is fetched and SHA256-verified from Computer 2 over the private network.
- [ ] Integrity-failure path falls back to a cached good artifact and raises an alert.

## Notes & Risks
- **MinIO vs R2 trade-off:** MinIO = zero recurring cost but couples availability to Computer 1's uptime (bad if Computer 1 is off during market hours); R2 = always-on, tiny cost, no egress fee, but external dependency. Recommendation: **R2 for production artifact exchange** (decoupled from training box), revisited in FND-010; MinIO acceptable for early dev.
- Artifact sizes (sklearn/XGBoost pkl) are small (MB-scale), so cost/bandwidth are negligible; this is about availability and integrity, not throughput.
- Assumes the SHA256 manifest contract from Layer 3 (`champion_manifest.json`) remains the integrity anchor.
