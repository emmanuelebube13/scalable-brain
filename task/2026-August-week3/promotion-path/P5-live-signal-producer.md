# P5 — The live signal producer

**Engineer:** Gemini Pro · **Reviewer:** Claude
**Est:** 6–8 h · **Risk:** high — this is the component that causes real orders.
**Needs:** P0, P3. **This is the task that decides whether System 2 can trade at all.**

---

## Why

**Nothing in any of the three systems currently emits a trading signal.**

- `ScoredSignalProducer` (`src/system1/queue_producer/producer.py`) is built, schema-
  validated, idempotent, has backpressure and a DLQ — and **has no caller anywhere**.
- System 2 deleted its own `live_signal_producer/` on 2026-08-02, at System 1's request
  (commit `b3b0abc`), and confirmed the deletion on 2026-08-15. That was the correct call:
  System 2 executes, it does not decide.
- So a published model set today produces **zero orders**. Publishing more of them changes
  nothing.

This task builds the missing half: something that reads the model set, watches for new
closed bars, asks the strategies what they want to do, and puts scored signals on the queue.

---

## The rule that must never break

**System 1 decides. System 2 executes. Neither recomputes the other's work.**

The signal carries direction, entry, stop and target. System 2 must never infer any of
them — that inference caused the 2026-08-02 incident (13 of 13 wrong-way shorts). If a
field the executor needs is missing, the producer **refuses to emit the signal** rather
than emitting a partial one.

---

## Hard constraints

1. **Closed bars only.** A signal may be computed only from bars that have closed. Acting
   on a forming bar is look-ahead in production, and it is the same defect that
   disqualified `Range_Stochastic_Divergence`.
2. **Idempotent.** The same bar must never produce two signals. `build_message_id` already
   gives a deterministic key from `(signal_id, score_run_id)` — use it.
3. **Fail closed.** Missing model set, `status != "published"`, stale artefact, unknown
   `selection_basis`, missing direction/exits, unreachable database ⇒ **emit nothing** and
   log loudly. Silence is the safe output; a guess is not.
4. **Dry-run is the default.** A real emit requires an explicit flag.
5. **No order routing, no sizing, no account state.** Those are Systems 2 and 3. This
   produces *scored signals* only.
6. Reuse `ScoredSignalProducer` — do not write a second publisher.
7. Only `regime_causal`; the routing label is `structural` if regime gating is applied at
   all (see P2 step 2 — the trial says it does not help, so default it **off**).

---

## Execution plan

### Step 1 — Read what exists

`producer.py`, `contracts/signal-message-contract.json`, and the two S2 replies in
`docs/comms/` describing what System 2 expects. Do not design against imagination.

### Step 2 — The bar watcher

`src/system1/signals/watcher.py`. Detects newly closed bars per (pair × granularity) from
`fact_market_prices`. Must be:

- **restart-safe** — persist the last-emitted bar per cell, so a restart does not replay or
  skip
- **honest about lateness** — if ingest is behind, report the lag rather than emitting a
  signal from a bar that is hours old

### Step 3 — The signal builder

`src/system1/signals/build.py`. For each active strategy in the model set:

- load its record from P0's catalog and instantiate it
- feed it the closed frame and take its `OrderIntent`s (v2) or signal (v1)
- carry through direction, stop and target from the strategy's own declaration
- refuse to emit if any required field is absent

### Step 4 — Scoring

If a gatekeeper champion exists, score through it; apply P4's cold-start policy for a
strategy with no history. If no champion exists — which is the case today — emit with an
explicit `model_score: null` and `threshold_applied: null`, and **mark the signal
`unscored`** so System 3 can decide what to do with it. Do not invent a score.

### Step 5 — Wire it together

```
python -m src.system1.signals.run --dry-run    # print what would be emitted
python -m src.system1.signals.run --once       # one pass, real emit
python -m src.system1.signals.run              # continuous
```

A cron entry in `shell/` matching the granularity being traded. **Do not install the cron**
— write it and let the owner install it.

### Step 6 — Tests

1. A forming (unclosed) bar produces no signal.
2. The same closed bar processed twice emits one message, not two.
3. A missing/withdrawn model set emits nothing and logs.
4. A signal missing direction, stop or target is refused, not emitted partially.
5. Restart after a crash resumes without replaying or skipping.
6. Ingest lag beyond a threshold suppresses emission and reports.
7. Dry-run emits nothing to the queue.
8. An unrecognised `selection_basis` in the map is refused.
9. A `designated` strategy's signals carry that basis through to the message.

### Step 7 — End-to-end rehearsal on the local queue

With `QUEUE_PROVIDER=local`, run a full pass and show the messages landing in
`results/state/queue/`. Paste one complete message into `STATE.md`. That message is what
System 2 will receive — the owner should read it before it ever goes to Pub/Sub.

---

## Definition of done

- [ ] Watcher, builder, scorer, runner; dry-run default
- [ ] Restart-safe, idempotent, fails closed on every condition in constraint 3
- [ ] Tests pass; state the count
- [ ] One real message shown end to end on the local queue and pasted into `STATE.md`
- [ ] Cron written, **not installed**
- [ ] No sizing, routing or account logic anywhere in it

## Reviewer will check

- That a forming bar cannot produce a signal — by constructing one.
- That killing the process mid-run and restarting neither duplicates nor skips.
- That a missing direction refuses rather than defaults.
- That nothing here recomputes what belongs to System 2 or 3.

---

## Failure log

| Timestamp | Step | What went wrong | Root cause | Fix |
|---|---|---|---|---|
| | | | | |
