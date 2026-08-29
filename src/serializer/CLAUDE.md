# src/serializer/ — the publish path

**This folder decides what Computer 2 downloads.** It is the highest-cost place in the repo
to get wrong. Full procedure: the `publish-model-set` skill. Clearance: the `release-guard`
agent.

## The contract — four steps, this order, no exceptions

1. Upload to an **immutable versioned prefix** (`system1/<version>/`, `models/gatekeeper/<version>/`).
2. **SHA256 round-trip verify every object read back from the backend** — the object read out
   of GCS, not the local file.
3. Archive the superseded pointer to `previous.json`.
4. **Atomic pointer flip LAST.** On mismatch the partial version is deleted and the run
   aborts with the pointer untouched.

An abort on checksum mismatch is **working as designed**. Retry; never bypass.

## Two pointer levels

- `system1/latest.json`, `models/gatekeeper/latest.json` — the **sub-pointers**.
- Top-level `latest.json` — the **model-set manifest**. A pure function of the two
  sub-pointers, so it cannot invent a pairing. **Only `publish_model_set` writes it.**

The local `model-artifacts/latest.json` is **not** authoritative. The backend copy is.

## Two `status` fields — never conflate (FIX-S1-016)

| Artifact | `status` values | Means |
|---|---|---|
| model-set manifest | `published` / `withdrawn` | is this model set live |
| `regime_strategy_map.json` | `proposed` / `published` | vetting's own field — **not** a publication state |

`last_run_outcome: no_model_set` means the backend manifest is withdrawn or unreadable.
**Do not "fix" it by reading the local map.** That conflation cost weeks of silent
non-emission.

## Rules

- `--withdraw` lives only in `publish_model_set`, is **CLI-only**, requires a human
  `--reason`, and is **never automated**.
- The orchestrator is the only champion promotion path (FIX-S1-009). Never add a second.
- `DETERMINISM.md` and `SIGNING.md` in this folder are contracts, not notes. Read before
  changing `fingerprint.py`, `candle_fingerprint.json`, or `reference_vector.json`.
- Publishing is byte-deterministic. A change that makes the same inputs produce different
  bytes is a defect, not a nuisance.
