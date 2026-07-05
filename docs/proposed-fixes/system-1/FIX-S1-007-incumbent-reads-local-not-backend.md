# FIX-S1-007 — `_incumbent()` reads a local pointer while promotion publishes to the storage backend (so `beats_incumbent` never binds on GCS)

**Severity:** P1 (re-inerts the FIX-S1-006 `beats_incumbent` gate whenever `STORAGE_PROVIDER=gcs`)
**Status:** VERIFIED (fix landed) — `_incumbent()` now reads through `build_storage()`; regression test red-before/green-after; surfaced during the 2026-07-01 live promotion
**Author:** Claude (surfaced verifying the first post-fix promotion)
**Date raised:** 2026-07-01
**Scope:** `src/system1/scheduler/orchestrator.py` (`_incumbent`, `LATEST_JSON`), `src/system1/scheduler/tests/test_scheduler.py`
**Risk to live trading:** Low direct risk, but it means the "is the new model better than what's live?" gate silently stops comparing after any real (GCS) promotion.

---

## 1. Evidence

The live promotion on 2026-07-01 published bundle `2026-07-01T12-56-32Z` to the GCS bucket
(`STORAGE_PROVIDER=gcs`) and the **GCS** `latest.json` advanced correctly. But the **local**
`model-artifacts/latest.json` still pointed at the previous bundle `2026-06-26T22-53-39Z`:

```
GCS   latest.json -> 2026-07-01T12-56-32Z   (metrics.regime_accuracy = 0.717)   ✓ what Computer 2 pulls
local model-artifacts/latest.json -> 2026-06-26T22-53-39Z   (metrics has no regime_accuracy)   ✗ stale
```

`orchestrator._incumbent()` read the **local** file (`LATEST_JSON = _REPO_ROOT/model-artifacts/latest.json`),
while `serialize.publish()` writes the pointer via `storage.atomic_pointer_update("latest.json", …)` — the
**GCS** backend. The two diverge under `STORAGE_PROVIDER=gcs`.

## 2. Root cause

Producer/consumer read the pointer from different places. `publish()` is backend-aware; `_incumbent()`
was not. So on the *next* retrain, `_incumbent()` returns the stale (or `regime_accuracy`-less) local
bundle, `inc_acc` is old/`None`, and `beats_incumbent` fails **open** — the FIX-S1-006 comparison gate
that is supposed to block a worse candidate never actually binds against the truly-live model. Same
failure class as FIX-S1-006 itself: a gate reading the wrong source can't measure what it claims.

## 3. Fix

`_incumbent()` now reads the incumbent through the **same** `build_storage()` backend `publish()` writes
to: `latest.json` pointer + `<bundle_version>/model_metadata.json`, downloaded to a temp dir. On the
local backend this reads the identical local file it always did (dev unchanged); on GCS it reads the
truly-live bundle. The dead `LATEST_JSON` constant is removed.

## 4. Validation

- **Regression test** `test_incumbent_tracks_storage_backend_not_local_file`: with the backend rooted at
  an empty dir, `_incumbent()` returns `{}` even though a real local `model-artifacts/latest.json` exists;
  after publishing to that backend it reads the bundle + `regime_accuracy` back. **Red before / green
  after** (pre-fix it returned the stale local `2026-06-26…` bundle instead of `{}`).
- Autouse `_isolate_storage` fixture roots the storage backend at an empty per-test dir so the scheduler
  unit tests are neither order-dependent nor network-bound.
- `test_incumbent_regime_accuracy_round_trips_and_blocks_worse` simplified (the old `_REPO_ROOT` /
  local-`latest.json` workaround is no longer needed) and still green.
- Full System-1 suite: **125 passed**. `black` + `mypy` clean on `orchestrator.py`.

## 5. Rollout / non-goals

- Additive, no schema/DB change, backward-compatible (local backend behaviour identical).
- **Non-goal:** the `_default_pipeline` quirk that writes the live map via `vet.run(live=True)` *before*
  the gates are checked, and the count-based gatekeeper `_walk_forward` — tracked separately.
