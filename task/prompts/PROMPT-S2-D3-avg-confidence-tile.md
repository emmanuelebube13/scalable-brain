# Agent prompt — D3: `AVG CONFIDENCE 0.650` is not a System 1 number

**Run this in the System 2 repo** (the one that owns the telemetry dashboard and its API).

**Priority:** P2 · **Owner:** System 2 · **Source:** `docs/comms/to_system2/TO-SYSTEM2-3-2026-09-03-dashboard-reconciliation-and-mock-data.md` §D3

**Do D2 first.** This tile shares a root cause with the mock trade blotter and will most likely
resolve as a side effect. Verify it does; do not assume.

> **⚠ Read `PROMPT-S2-D0-where-to-work.md` first.** There are two dashboard apps in that repo
> and one renders nothing. The live one is **`telemetry-dashboard/src/App.tsx`** (loaded via
> `index.html` → `src/main.tsx`). **Do not edit `src/App.jsx`, `src/screens/*.jsx` or
> `src/main.jsx`** — they are dead, and `CONNECTIONS.md` documents the dead app.

---

## The problem

The Live Telemetry overview shows `AVG CONFIDENCE 0.650`.

**No System 1 signal has ever scored 0.650.** The mean `model_score` across all nine signals
emitted in the week of 2026-08-30 is **0.469**, range **0.409 – 0.741**:

```
0.438  0.427  0.424  0.741  0.480  0.429  0.429  0.409  0.441
mean 0.469
```

The displayed `0.650` is the flat **65.0%** repeated on every mock row in the Live Trades table
(see D2). It is an average of placeholder data, not of model output.

## Why this one matters despite being cosmetic

`0.650` sits above every observed live score except one. Anyone reading this tile would
conclude the gatekeeper is more confident than it is — and that conclusion runs in the opposite
direction from reality. Under System 1's calibrated per-regime thresholds (0.60–0.80), **eight
of the nine signals score below every cutoff.** A tile reading 0.650 makes a set of low-scoring
signals look like high-scoring ones.

## What to change

1. **Source the tile from real `model_score` values** in the System 1 signal ledger, or remove
   the tile. Those are the only confidence numbers that exist.

2. **Define the window explicitly in the label.** "Avg confidence" over what — the last 24h, the
   last N signals, all time? At current volume (~9 signals/week) a 24h window will frequently
   have a sample size of 0 or 1. State the window and the sample size on the tile.

3. **Render an explicit empty state when the sample is empty.** Do not display `0.000`, and do
   not carry forward the last known value. A missing average is not a zero average — this is the
   same zero-imputation defect raised in `TO-SYSTEM2-3-2026-08-23-telemetry-ui-fixes.md` §4.

4. **Exclude unscored rows from the mean.** A row with `gate1_outcome: "unscored"` has no
   `model_score`. Including it as 0 would drag the average down and misrepresent the model.
   Currently 0 of 9 rows are unscored, but that is not guaranteed to hold.

## What NOT to do

- **Do not present this as a confidence the system acted on.** System 1 applies no threshold at
  inference (`threshold_applied: 0.5` on the wire is a placeholder, not a gate). A high or low
  average score did not change what was published.
- **Do not average `threshold_applied`, `threshold_calibrated`, or `shadow_verdict` into
  anything.** Those are different fields answering different questions.

## Acceptance criteria

- [ ] With the current ledger, the tile reads **≈0.469** over an all-time window, or an
      explicitly-labelled shorter window with its sample size shown.
- [ ] The value `0.650` no longer appears anywhere on the page.
- [ ] With an empty sample, the tile renders an empty state — not `0.000`, not a stale value.
- [ ] The tile label names its window and sample size.

## Where the data lives

| Field | Object |
|---|---|
| `model_score` (float, null when unscored) | `gs://scalable-brain-artifacts/telemetry/signals/<YYYY-MM-DD>/<ts>-<sha8>.ndjson` |

See the ledger caveats in `PROMPT-S2-D2-mock-strategy-attribution.md` — chunked objects, no
index, LIST-based discovery. Read access to bucket `scalable-brain-artifacts` is required;
credentials are not in this file.
