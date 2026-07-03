# MODEL-007 — Model Serializer & Artifact Registry

**Task ID:** MODEL-007
**System:** System 1 — Model Building
**Priority:** P0-Critical
**Estimated Effort:** 3d
**Prerequisites:** FND-001, MODEL-003, MODEL-005
**External Dependencies:**
- **Object storage** (FND-001) — destination for timestamped bundles + `latest.json`; must provide encryption at rest, TLS in transit, scoped write (Computer 1) / read-only (Computer 2) credentials.
- **`joblib`** — serialize the fitted HMM.
- **Object-storage client** (`boto3`/`minio`) — upload with checksums.
- **MLflow** — link bundle version to the producing experiment run.

## Objective
Build the model serializer/packager that bundles `hmm_model.joblib`, `strategy_weights.json`, `regime_strategy_map.json`, `model_metadata.json` plus a `latest.json` pointer with SHA256 checksums and uploads timestamped versions to object storage for Computer 2.

## Current State
- Layer 3 already uses SHA256 integrity and a champion manifest (`champion_manifest.json`) written locally to `models/`. The HMM (MODEL-003) and the maps (MODEL-005) are produced but there is **no unified packager**, no object-storage publication, and no `latest.json` pointer for Computer 2 to discover the newest valid bundle.

## Target State
A serializer that gathers the System 1 outputs — `hmm_model.joblib` (MODEL-003), `strategy_weights.json` + `regime_strategy_map.json` (MODEL-005), and a generated `model_metadata.json` — computes a **SHA256 per file**, assembles an immutable **timestamped version** in object storage, and updates a `latest.json` **pointer** referencing that version and its checksums. Computer 2 (System 2) pulls `latest.json`, then the bundle, and **verifies checksums before loading**. Encryption at rest and in transit are enforced.

## Technical Specification

**Bundle contents (one version):**
- `hmm_model.joblib` — fitted Gaussian HMM + scaler + state→label mapping (MODEL-003).
- `strategy_weights.json` — per-regime weights (MODEL-005).
- `regime_strategy_map.json` — per-regime ranked strategies (MODEL-005).
- `model_metadata.json` — manifest tying it together (see below).
- `checksums.sha256` — SHA256 of each artifact (also embedded in metadata).

**`model_metadata.json` (shape, illustrative):**
```
{
  "bundle_version": "2026-06-20T00:00:00Z",      // timestamped, immutable
  "schema_version": "1.0.0",
  "created_by": "computer-1",
  "regime_model_version": "...",                 // MODEL-003
  "feature_set_version": "...",                  // MODEL-002
  "vetting_run_id": "...",                        // MODEL-005
  "mlflow_run_id": "...",
  "artifacts": {
    "hmm_model.joblib":        {"sha256": "...", "bytes": 12345},
    "strategy_weights.json":   {"sha256": "...", "bytes": 234},
    "regime_strategy_map.json":{"sha256": "...", "bytes": 567}
  },
  "metrics": { "regime_accuracy": 0.xx, "n_qualified_strategies": N },
  "dynamic_thresholds_ref": "champion_manifest.json#dynamic_thresholds"  // optional, MODEL-006
}
```

**`latest.json` (pointer, shape):**
```
{ "bundle_version": "2026-06-20T00:00:00Z",
  "path": "model-artifacts/2026-06-20T00-00-00Z/",
  "metadata_sha256": "...",
  "promoted_at_utc": "..." }
```

**Storage layout:** `model-artifacts/{bundle_version}/{files...}` (immutable) + `model-artifacts/latest.json` (mutable pointer). Lifecycle policy retains the last N versions for rollback.

**Upload protocol:** write all artifacts to the timestamped prefix first; verify each uploaded object's SHA256 matches the local computation (read-back or stored checksum); **only then** atomically update `latest.json`. This ordering guarantees Computer 2 never sees `latest.json` pointing at an incomplete bundle.

**Encryption:** server-side encryption at rest on the bucket; TLS for all transfers; credentials from env only — **never** serialize any secret into metadata or artifacts.

**Deployment gate hook:** publication is conditional on upstream gates (MODEL-003 quality, MODEL-005 non-empty map, MODEL-006 OOS-uplift when present). The serializer refuses to promote a bundle missing a required artifact or failing checksum verification — analogous to the existing "refuses degenerate models" guard in Layer 3.

**Data flow (text):** collect artifacts → compute SHA256 → build `model_metadata.json` + `checksums.sha256` → upload to timestamped prefix → verify checksums in storage → update `latest.json` atomically → log bundle version to MLflow.

## Testing & Validation
- **Round-trip:** upload bundle, re-download, recompute SHA256 — must match for every artifact (the core SC6 test).
- **Pointer integrity:** `latest.json` resolves to the newest fully-uploaded valid version; an interrupted upload never advances `latest.json`.
- **Guard tests:** missing artifact, checksum mismatch, or empty regime map → serializer refuses to promote and exits non-zero.
- **Security:** confirm encryption-at-rest flag on objects, TLS enforced, no secret strings present in any artifact/metadata (scan).
- **Edge cases:** concurrent publish attempts (later one wins atomically), object-storage transient failure (retry/backoff, no partial promotion).

## Rollback Plan
Versions are immutable; rollback = repoint `latest.json` to the previous good `bundle_version`. Because Computer 2 reads `latest.json` and verifies checksums, a single pointer revert fully rolls back the deployed brain. Retained version history (lifecycle policy) makes prior bundles available.

## Acceptance Criteria
- [ ] Serializer bundles `hmm_model.joblib`, `strategy_weights.json`, `regime_strategy_map.json`, and `model_metadata.json` with per-file SHA256.
- [ ] Timestamped immutable versions are uploaded to object storage; `latest.json` pointer updates only after full upload + checksum verification.
- [ ] Round-trip download reproduces matching SHA256 for every artifact; encryption at rest + TLS in transit enforced.
- [ ] Serializer refuses to promote on missing artifact, checksum mismatch, or empty regime map.
- [ ] Rollback is a single `latest.json` pointer revert to a retained prior version.

## Notes & Risks
- Version drift between Computer 1 and Computer 2 is the highest-impact failure mode — the atomic `latest.json` + mandatory checksum verification on the consumer side is the primary control.
- Keep the bundle's `schema_version` strict; any change to `regime_strategy_map.json` / `strategy_weights.json` shape is a coordinated, versioned change with System 2.
- No secrets ever in metadata or artifacts.
