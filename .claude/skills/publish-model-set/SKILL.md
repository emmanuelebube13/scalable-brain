---
name: publish-model-set
description: The end-to-end procedure for publishing a System 1 model set to GCS — dry runs, deployment gates, the four-step publish contract, the two pointer levels, verification, and withdrawal. Use whenever publishing, promoting a champion, flipping latest.json, or withdrawing a model set.
---

# Publishing a model set

This is the only procedure that changes what Computer 2 downloads. Follow it in order.
Skipping a step here has cost weeks before.

Activate the environment first:

```bash
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain
source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate
```

## Step 0 — Know what is live now

```bash
python -m src.monitoring.model_card --verify
```

Read `results/state/regime_strategy_map.json` directly for the current cells — the count
evolves with each vetting run, so any number written in a doc is a snapshot, not a fact.
Note every cell with `selection_basis: "designated"`; those failed their gates and are in the
map by owner override, carrying `designated_reason`, `ci_mean_r`, `pairs_passed_fraction`
and `tail_dependence`. **Read those reasons before touching them.**

## Step 1 — Dry run everything

Log-only / dry-run is the default for every promotion-capable stage. Run it, and read the
output before doing anything live.

```bash
python -m src.vetting.vet                    # no --live ⇒ results/reports/proposed_*
python -m src.gatekeeper.train --dry-run     # ⇒ proposed_champion_*
python -m src.serializer.publish_gatekeeper --dry-run
python -m src.analytics.publish_analytics --dry-run
```

Compare the proposed artifacts against what is live. If nothing changed, there is nothing to
publish — stop here.

## Step 2 — Check the deployment gates

Read the newest `results/state/retrain_log_*.json`. Four gates must pass:

| Gate | Bar |
|---|---|
| `regime_accuracy_ok` | ≥ 0.70 |
| `non_empty_map` | map has at least one cell |
| `oos_uplift_ok` | bootstrap-significant OOS uplift |
| `beats_incumbent` | a ratchet, re-armed at 0.965 — confirm what it compares against |

Read the actual values. Do not infer a pass from the absence of an error.

Vetting gates for reference: PF ≥ 1.5, Sharpe ≥ 0.8, MaxDD ≤ 25%, WinRate ≥ 40%,
Recovery ≥ 3.0, **OOS ≥ 12 months** (lowered from 60 by owner decision 2026-08-21). There is
**no minimum-trade-count gate** — `trade_count` is only a ranking tie-break, so check sample
size yourself.

## Step 3 — Invoke `release-guard`

Before anything live runs, get the read-only clearance. It checks the contract, the gates,
designated cells, and integrity flags. `NEEDS HUMAN DECISION` on a designated cell or a
withdrawal is the correct outcome — those are owner calls.

## Step 4 — The publish contract, in this order

The code implements this; your job is to confirm it was not bypassed.

1. Upload to an **immutable versioned prefix** (`system1/<version>/`,
   `models/gatekeeper/<version>/`).
2. **SHA256 round-trip verify every object read back from the backend** — the object read out
   of GCS, not the local file.
3. Archive the superseded pointer to `previous.json`.
4. **Atomic pointer flip LAST.** On mismatch: the partial version is deleted and the run
   aborts with the pointer untouched.

```bash
python -m src.serializer.serialize
python -m src.serializer.publish_gatekeeper      # gated champion publish
python -m src.serializer.publish_model_set       # flips the top-level latest.json
```

**An abort on checksum mismatch is working as designed.** Retry. Never bypass.

## The two pointer levels

- `system1/latest.json`, `models/gatekeeper/latest.json` — the **sub-pointers**.
- Top-level `latest.json` — the **model-set manifest** System 2 downloads. It is a pure
  function of the two sub-pointers, so it cannot invent a pairing. **Only
  `publish_model_set` writes it.**

The local `model-artifacts/latest.json` is **not** authoritative. The backend copy is.

## The two `status` fields — never conflate

| Artifact | Field | Values | Means |
|---|---|---|---|
| model-set manifest | `status` | `published` / `withdrawn` | is this model set live |
| `regime_strategy_map.json` | `status` | `proposed` / `published` | vetting's own field, **not** a publication state |

If `last_run_outcome: no_model_set` appears, the backend manifest is `withdrawn` or
unreadable (check GCS creds). **Do not "fix" it by reading the local map** — that conflation
is FIX-S1-016 and it caused weeks of silent non-emission.

## Step 5 — Verify and announce

```bash
python -m src.monitoring.model_card --verify
python -m src.monitoring.publish_health
```

Then draft the notice to Computer 2 with the `comms-liaison` skill/agent — version, artifact
count, SHA256 verification result, what changed, and **every designated cell disclosed**.

## Withdrawal

```bash
python -m src.serializer.publish_model_set --withdraw --reason "…"
```

**CLI-only, never automated, mandatory human reason.** This is deliberate. If you find code
or cron calling `--withdraw`, that is a defect to report, not a convenience to preserve.

## Single governed writer — do not add a second

- The **orchestrator** (`src/scheduler/orchestrator.py`) is the only champion promotion path
  (FIX-S1-009).
- `publish_model_set` is the only writer of the top-level pointer.
- There are two gatekeeper trainers in history; `src/gatekeeper/` is canonical and
  `src/layer3_ml/` is a deliberate tombstone. Do not restore it.

## Known and expected

- Pub/Sub `scored-signals.heartbeat` does not exist — every hourly run logs a 404. See
  `shell/provision_pubsub.sh`. Not a blocker.
- The retrain cron is **not installed** — declared hold in `results/state/cron_holds.json`,
  at Computer 2's request. Re-enable only when Computer 2 asks explicitly.
