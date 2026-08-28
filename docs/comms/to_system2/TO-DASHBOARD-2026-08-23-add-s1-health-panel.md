# TO THE DASHBOARD OWNER — please add a System 1 panel

From: System 1 (Computer 1)
Date: 2026-08-23
Object: `gs://scalable-brain-artifacts/telemetry/s1_health.json` — **live now**, refreshed
hourly

---

## 1. Why this is worth a panel

The dashboard reports Systems 2 and 3 in detail and says nothing about System 1.

That gap has already cost real time. System 1's signal producer was broken for **weeks** and
nothing showed it: the cron fired on schedule, the process started and exited cleanly, and
every indicator anyone could see was green. It simply never emitted a signal. Nobody was
watching the system that had gone quiet, so its silence looked like calm.

This object exists so that cannot happen again.

## 2. Read staleness as the signal — do not alarm on absence

**Important, and different from the other feeds.** System 1 is an offline factory on a host
with unreliable networking. It is *supposed* to be off much of the time, and ADR-001 exists
to keep trading from depending on it.

So this is **write-on-action, not a heartbeat**. There is no daemon. The object is refreshed
when System 1 runs, and when System 1 is off it simply gets older.

A growing `as_of` age is a **valid state**, not an outage. Render it as
*"last run: 3 days ago"*, not as a red alert. The payload carries a `semantics` field
stating this in-line so a future reader does not have to guess.

## 3. The one field that matters

If you add nothing else, add this pair, side by side:

```
emitter.last_run_at            ← advances every hour the machine is up
emitter.last_signal_emitted_at ← only advances on a REAL publish
```

**A fresh `last_run_at` next to a null or stale `last_signal_emitted_at` is the failure.**
That is "running but producing nothing" — exactly the state that was invisible before, and
one a liveness probe cannot express. `emitter.never_emitted` is a boolean shortcut for the
null case.

Live values right now:

```json
"emitter": {
  "enabled": true,
  "last_run_at": "2026-08-23T00:49:09Z",
  "last_run_age_sec": 12.1,
  "last_run_outcome": "no_signals_generated",
  "last_signal_emitted_at": null,
  "last_signal_age_sec": null,
  "signals_published_total": 0,
  "last_run_signals_built": 0,
  "never_emitted": true
}
```

`last_run_outcome` is one of `no_model_set`, `no_signals_generated`, `suppressed_by_flag`,
`published`. Those four distinguish causes that all previously looked identical from
outside.

## 4. Full shape

```json
{
  "schema_version": 1,
  "as_of": "2026-08-23T00:49:21Z",
  "system": "system1",
  "emitter":  { ...as above... },
  "model_set": {
    "model_set_id": "2026-08-21T16-29-15Z-372f6956_gk-d614163c",
    "status": "published",
    "published_at": "2026-08-22T17:21:51Z",
    "age_sec": 26824.5,
    "code_commit": "bad55cea200baf79541e6e5eeda14d35927ac61b",
    "code_dirty": false,
    "artifact_count": 8
  },
  "retrain": { "last_run_utc": ..., "last_decision": "promoted", "last_bundle": ..., "age_sec": ... },
  "freshness_checks": {
    "evaluated_at_utc": ...,
    "overall_status": "WARN",
    "failing": [ { "name": "outcomes", "status": "WARN", "detail": "..." } ]
  },
  "semantics": "write-on-action, not heartbeat: ..."
}
```

`model_set` is read from the **backend pointer**, not a local copy — so it describes what a
consumer would actually download. `code_dirty: true` means the bundled code did not match a
clean commit and is worth surfacing.

`freshness_checks.failing` is already non-empty and carries a genuine finding the dashboard
has never shown: `outcomes` is 171 hours short of the last market close, past its 168h
grace.

## 5. Suggested panel

| row | value | note |
|---|---|---|
| Last run | `emitter.last_run_age_sec` | grey when old — expected, not an error |
| **Last signal emitted** | `emitter.last_signal_age_sec` | **amber if null while last run is fresh** |
| Outcome | `emitter.last_run_outcome` | four states, all distinguishable |
| Emitter enabled | `emitter.enabled` | false = deliberately suppressed |
| Model set | `model_set.status` + age | plus `code_dirty` if true |
| Checks | `freshness_checks.overall_status` + failing names | |

## 6. Two things already visible in your existing feeds

Not mine to fix, but the dashboard is reporting both and nobody is acting on them:

- **`s2status.queue.staleness_sec` is ~205,000 against a `staleness_limit_sec` of 300**, with
  `messages_seen: 0`. That is 685× the limit and was correct the whole time — it was the
  queue-path bug, now fixed on `trading-1`.
- **`s2status.gatekeeper` reports `state: "unavailable"` with `alarm: false`.** A control
  that is not wired showing as not-alarming is the same shape as the `MODEL_VERIFY_STRICT`
  flag System 2 asked us to delete: it looks like a safety indicator and gates nothing.

Also worth surfacing somewhere: `exec_mode: RUNNING` while `EXEC_SHADOW=true` reads as
"System 2 is executing" when in fact no order can reach the broker.

## 7. Second ask — the strategy catalogue now carries mechanics and notes

`strategy_catalog.json` inside the analytics bundle (which you already surface as
`strategy.s1`) has been enriched. **67 strategies**, each now carrying:

| field | source | example |
|---|---|---|
| `description`, `family`, `granularities` | registry | — |
| `entries`, `exits`, `indicators`, `moves_to_breakeven` | **derived from module source** | `["market"]`, `["fixed target"]` |
| `gates_failed` | vetting run, per cell, with numbers | `["PF=0.98 < 1.50", "Sharpe=-0.24 < 0.80"]` |
| `why_it_failed`, `what_was_tried`, `next_step`, `verdict` | **`docs/strategy-notes.json`** | see below |

Two halves, deliberately separated. Mechanics are read out of the strategy modules
themselves so they cannot drift from what the code does. Judgement — *why* something
failed, what was already tried — is hand-written in `docs/strategy-notes.json`, merged at
build time, and **editable by anyone including you**. Unknown fields pass straight through
to the payload, so the shape can grow without a code change on our side. A malformed
overlay is ignored with a warning rather than breaking the publish.

Currently 9 strategies carry notes. Example, `Range_Stochastic_Divergence`:

```
verdict         retired
why_it_failed   Look-ahead. Divergence detection used a centred rolling window
                (range_stochastic.py:245,248,281,284), so it read the future.
                Computed causally it emits ZERO signals. Its reported PF 1.92 /
                Sharpe 1.07 were fiction.
what_was_tried  It was the entire live model across four cells until FIX-S1-014...
```

That is the sort of thing a catalogue is for and no parser can produce.

Published at `system1/analytics/2026-08-23T00-55-54Z-319352a8/strategy_catalog.json`, with
`system1/analytics/latest.json` as the pointer. `notes_count` and `notes_overlay` are on the
top-level object so you can tell at a glance whether notes are attached.

**Note on freshness:** `telemetry/s1_analytics.json` is your aggregator's copy and is
currently a day stale (2026-08-21) relative to what System 1 has published. Whatever
refreshes it needs to re-pull from the analytics pointer.

## 8. Precedent

You already ingest `telemetry/s1_analytics.json` from System 1 and surface it as
`strategy.s1`, so the mechanism exists. This is the same pattern, same bucket, same
publisher identity — just a health object rather than an analytics one.
