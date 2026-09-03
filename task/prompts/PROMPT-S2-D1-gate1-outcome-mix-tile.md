# Agent prompt — D1: the Gate-1 Outcome Mix tile is reading the wrong scope

**Run this in the System 2 repo** (the one that owns the telemetry dashboard and its API).
Nothing in System 1 needs to change — the data you need is already published and was verified
live in GCS at **2026-09-03 00:47Z**.

**Priority:** P1 · **Owner:** System 2 · **Source:** `docs/comms/to_system2/TO-SYSTEM2-3-2026-09-03-dashboard-reconciliation-and-mock-data.md` §D1

> **⚠ Read `PROMPT-S2-D0-where-to-work.md` first.** There are two dashboard apps in that repo
> and one renders nothing. The live one is **`telemetry-dashboard/src/App.tsx`** (loaded via
> `index.html` → `src/main.tsx`). **Do not edit `src/App.jsx`, `src/screens/*.jsx` or
> `src/main.jsx`** — they are dead, and `CONNECTIONS.md` documents the dead app.
>
> **For this defect specifically:** the backend `cloud/telemetry-web/` (FastAPI) **already reads
> `s1_health.json` by default**, so `gate1` is reachable server-side with no new wiring. This is
> a rendering fix, not an integration one — confirm the field reaches the frontend before you
> write any fetch code.

---

## The problem

The **Gate-1 Outcome Mix** tile on the Live Telemetry overview renders:

```
GATE-1 OUTCOME MIX        [RATE BLOCKED]
0/0
No candidates evaluated yet — the gatekeeper is scoring,
but no strategy has fired on a closed bar.
```

**That caption is false.** Nine candidates have been evaluated, eight of them in the trading
week of 2026-08-30, and each has a durable ledger row.

The tile is displaying the **per-run** counters under an **all-time** caption. Both scopes are
present in the object you already fetch, and you are picking the wrong pair.

## What the object actually contains

`gs://scalable-brain-artifacts/telemetry/s1_health.json`, path `emitter.gate1`, read live at
2026-09-03 00:47Z:

```json
"gate1": {
  "scored_total": 9,
  "unscored_total": 0,
  "dropped_total": 0,
  "last_run_scored": 0,
  "last_run_unscored": 0,
  "last_run_dropped": 0,
  "last_run_by_regime": {},
  "approval_rate_computable": false,
  "approval_rate_blocked_by": "FIX-S1-018: no threshold is applied at inference",
  "shadow": {
    "enforced": false,
    "scope": "would-have-decided; not applied to routing",
    "would_pass_total": 1,
    "would_refuse_total": 8,
    "last_run_would_pass": 0,
    "last_run_would_refuse": 0,
    "refusal_rate": 0.8889,
    "label_as": "Shadow Gate-1 refusal rate (not enforced)"
  }
}
```

The `0/0` you are rendering is `last_run_scored` / `last_run_unscored`. Those are **genuinely
zero and genuinely correct** — the 00:15Z run built nothing, because no strategy fired on that
bar. The all-time figure is **9 scored / 0 unscored / 0 dropped**.

This matters because System 1 emits roughly one signal per several hours. **Most runs build
nothing.** A tile keyed on `last_run_*` will therefore read "no candidates ever" during most
hours of a normal, healthy day.

## What to change

1. **Headline the cumulative counters.** Render `scored_total` / `unscored_total` /
   `dropped_total` as the tile's primary figure. If you want the per-run numbers too, label
   them explicitly "last run" — do not let them carry an all-time caption.

2. **Key the empty state on `scored_total == 0`, not `last_run_scored == 0`.** Only when
   `scored_total` is 0 is "no candidates evaluated yet" a true statement.

3. **Add a "last run" sub-line if useful.** The Factory panel elsewhere on the same page
   already does this correctly — *"0 built last run · 58 published all-time"*. That is the
   pattern to copy. It is on the same screen as the broken tile, so the distinction is already
   understood somewhere in your codebase.

4. **Optionally add the shadow refusal rate.** `shadow.refusal_rate` is populated (`0.8889`)
   and ships with its own display string in `shadow.label_as`. If you render it, **use that
   string verbatim**: `"Shadow Gate-1 refusal rate (not enforced)"`.

## What NOT to change

- **Keep the `RATE BLOCKED` badge.** It is correct. It reads `approval_rate_computable: false`
  and it must stay until System 1 ships FIX-S1-018. This was specified in
  `TO-SYSTEM2-3-2026-08-30-signal-ledger-and-rfc-corrections.md` §2 and has not changed.
- **Never compute or display a runtime approval rate** from these fields. The denominator does
  not exist — nothing in System 1's live path compares a score to a threshold, so there is no
  "refused" bucket. `0/0` is undefined, not zero.
- **Never put `dropped_total` in a denominator.** It counts corrupt-feature *data faults*, not
  gatekeeper verdicts. Using it measures System 1's data-quality failure rate and mislabels it
  as a model gate.
- **Never label the shadow rate as an approval or rejection rate.** It is what the gate *would*
  have decided on signals that were published anyway. The gate is off.

## Acceptance criteria

- [ ] With the current object, the tile reads **9 scored / 0 unscored / 0 dropped**, not `0/0`.
- [ ] The "no candidates evaluated yet" empty state does **not** appear while `scored_total > 0`.
- [ ] Simulate `scored_total: 0` with all other fields unchanged → the empty state **does** appear.
- [ ] Simulate `last_run_scored: 0, scored_total: 9` (the live case) → tile shows all-time
      figures; any per-run figure shown is labelled "last run".
- [ ] The `RATE BLOCKED` badge still renders, still driven by `approval_rate_computable`.
- [ ] No string anywhere in the tile reads "approval rate".

## Where the data lives

| Object | Path | Use |
|---|---|---|
| Health object | `gs://scalable-brain-artifacts/telemetry/s1_health.json` | `emitter.gate1.*` — everything above |

Read access to bucket `scalable-brain-artifacts` is required. Credentials are not in this file;
request them from the System 1 owner if your service account does not already have read.

Do **not** cache the resolved values indefinitely — the object is rewritten every hour by
System 1's signal cron.
