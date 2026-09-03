# SIGNAL-EMISSION-DEFECTS — state

Resume file for `PROMPT.md` in this folder. **Read that first.**
Tick a box only after the step is verified **and** committed.

**Register:** O-23 (D6), O-24 (D7), O-25 (D8) in `task/OPEN.md`.

## Checklist

- [x] S1 — Read `GOVERNANCE.md`, `CLAUDE.md` §AGENT RULES, `docs/proposed-fixes/system-1/`,
      `task/OPEN.md` (O-16/17/19/20/21/22). Confirm none of D6/D7/D8 is already covered.
      Create a branch. **Branch:** `fix/signal-emission-defects-d6-d7-d8`.
- [x] S2 — **Reproduce D6, no writes.** Causes (a), (b), (c) confirmed independently.
      `FINDINGS-D6.md` written. `devils-advocate` agent run. Committed.
- [x] S3 — **CLOSED. Owner decided 2026-09-03: no re-affirmation.** See "Owner decisions" below.
- [-] S4 — Implement D6: **(b) committed** (`acaa71d`). Tests pass on both backends (LocalDurable
      and PubSub-like stub). **(a) and (c) UNBLOCKED 2026-09-03 — implement per the Q1
      decision below. (c) is the priority: the stale-bar guard.**
- [x] S5 — **Investigate D7, no writes.** `FINDINGS-D7.md` written. Two causes confirmed:
      (a) no minimum R:R floor; (b) `confirmed_lows_list` leakage. `forex-strategist` and
      `leakage-hunter` agents run. Committed.
- [x] S6 — **CLOSED. Owner decided 2026-09-03: fix the leakage, publish R:R, add no gate.**
      See "Owner decisions" below.
- [ ] S7 — **UNBLOCKED 2026-09-03.** Implement D7 per the Q2 decision below: leakage fix
      FIRST, then re-measure, then publish R:R. **No enforcing gate.**
- [-] S8 — **SCOPE CHANGED 2026-09-03. `publish_index()` is superseded — do not ship it.**
      Systems 2/3 answered Q4 and do **not** want an index object. Their ingester
      (`cloud/signal-ingester/ingest.py`, written, **undeployed**) already does an unbounded LIST,
      and they would rather change it than have us build a manifest. What they asked for instead:
      **(i)** keep the LIST, bounded by the existing `telemetry/signals/{date}/` partition —
      no manifest to go stale; **(ii)** **never** a mutable `latest.json` at the prefix root,
      because they cannot distinguish a stale read from an empty day; **(iii)** never rename or
      rewrite an object (their idempotence is keyed on `object_name`); **(iv)** keep
      `<ts>-<sha8>.ndjson` — it sorts lexically into chronological order; **(v)** emit
      **`bar_content_sha256`** over `(signal_time_utc, proposed_entry, proposed_sl, proposed_tp,
      atr)`, canonicalised sorted-keys/no-whitespace. **That hash is the new D8 deliverable** — it
      would have made the `4af8a6fe` collision self-describing. Still gated on **O-19** (remote
      retention stated 365d but unenforced) — do not put a hash on the wire then redefine it.
      Source: `docs/comms/replies/S2-REPLY-2026-09-03-*.md` §2.
- [x] S9 — Full suite run: **938 passed**, 0 new reds, 20 pre-existing warnings.
      `black`: 1 file reformatted (producer.py). `mypy`: 0 new errors vs baseline.
- [-] S10 — `DELIVERABLE.md` written. `OPEN.md` update pending. `REPO_STATE.md` no change
      needed (state unchanged). `auditor` and `structure-warden` run.

## Questions — Q1/Q2 answered by the owner 2026-09-03; Q3/Q4 answered by Systems 2/3

| # | Question | Blocks | Answer |
|---|---|---|---|
| Q1 | Is re-affirming a still-current signal ever **wanted**? | S4 (a) and (c) | **DECIDED by owner, 2026-09-03: NO.** See "Owner decisions" below. |
| Q2 | Refuse a bad-R:R signal, or publish R:R and let System 3 decide? Fix the strategy-30 leakage? | S7 | **DECIDED by owner, 2026-09-03: fix the leakage, publish the number, no gate.** See below. |
| Q3 | (External, System 2) Did **any** of the nine `signal_id`s reach their subscription? | priority of D6 | **ANSWERED 2026-09-03: ALL NINE.** 9 publishes, 9 acks, 1:1. **Three became live orders and all three lost** (−70.19, −10.77, −83.56 CAD), tipping `consecutive_losses` to 5 and firing System 3's circuit breaker 2026-09-02 14:50:47. **D6 is not lower priority — it is higher.** The `4af8a6fe` duplicate traversed the entire path as two independent messages and was stopped only by a `UNIQUE INDEX` on `ams_decision_log(signal_id)` — "a structural accident, not a designed dedupe" — which has **never had to work**, because both copies were rejected at layer S for an unrelated reason. |
| Q4 | (External, System 2) Have they already built the prefix-LIST path? | S8 design | **ANSWERED 2026-09-03: yes, and they do not want an index.** See the S8 line above — scope changed. |

## Owner decisions — 2026-09-03. S3 and S6 are CLOSED; S4 and S7 are unblocked.

### Q1 — no re-affirmation

**A signal is emitted once, for one bar, and is never restated.**

1. **Emit once** per `(strategy_id, instrument, granularity, signal bar)`. A repeat is a no-op.
2. **Add a stale-bar guard: never emit a signal whose bar is not the bar that just closed.** This
   is the higher-value half — it kills the duplicate *and* the entry/levels mismatch in one rule,
   because the defect only appears when the strategy's signal bar lags the watcher's.
3. **The wire idempotency key must be a pure function of the signal**, not of the run. Drop
   `score_run_id` from the key; it stays in the payload.
4. **Do not build restatement machinery.** No "this is an update" flag, no recomputed-levels path.
   That option was considered and declined — System 1 cannot know whether System 2 filled, and
   re-sending is System 1 modelling downstream state it is forbidden to model.
5. **Retry-after-failed-publish is a different thing and is out of scope.** It has never occurred
   (`dlq_count_total: 0`, no NACK in any log). Do not build for it now.
6. **The ledger still records whatever actually happened.** If a duplicate ever reaches the wire,
   two rows is correct. Never suppress the record to make the metric look clean.

### Q2 — fix the leakage, publish the number, add no gate

1. **Fix the `confirmed_lows_list` loop order in strategy 30.** Appending bar `i`'s own swing low
   before the order logic reads it is look-ahead. This is a correctness fix to the strategy, not a
   policy change. Run `leakage-hunter` on the result.
2. **Then re-run attribution and re-vet.** This folds into **O-2**, which is already open for
   exactly this. Do not publish a new map without it.
3. **The owner has accepted the likely outcome in advance: the live map may go to zero qualified
   cells.** Strategy 30 is currently the only qualified emitter, and System 3 independently
   rejected it as `no_positive_edge` (Kelly −0.660). If its qualification came from leaked
   targets, that is an artefact being removed, not capability being lost. **Report the number; do
   not soften it.**
4. **Publish the risk/reward ratio as an observation.** System 1 computes it — System 3 must never
   derive it. **Additive to the ledger is fine. Anything added to the wire that System 3 reads is
   a contract change and needs a notice via the `write-comms` skill first**, same as the
   `bar_content_sha256` in S8.
5. **Do not add an enforcing R:R gate.** Every live gate is off or in shadow by owner decision;
   adding one as a bug fix breaks that consistency, which is what the FIX-S1-018 decision exists
   to prevent.
6. **Sequence matters: leakage first.** The leakage is the likely *cause* of the 2.6-pip target.
   Fix it, then re-measure — the bad-R:R case may disappear, and you will have avoided building a
   guard nothing needed.

## Log

- 2026-09-03 — Folder opened, brief written (Claude). **No code changed yet.** All evidence in
  `PROMPT.md` §4 was measured 2026-09-03 00:43–00:51Z from `results/signals/*.ndjson`,
  `results/state/*.json` and a live read of `telemetry/s1_health.json`. **Re-verify before
  acting** — the ledger grows hourly and the offsets in §D8 will have moved.
- 2026-09-03 — S1–S5 + partial S4/S8 + S9 complete (commit `acaa71d` + comment fix).
  D6 cause (b): `deduped_count` honest; both backends tested.
  D7: `FINDINGS-D7.md` written; two causes confirmed (missing R:R floor + leakage).
  D8: `publish_index()` implemented, dry-run default, `release-guard` sign-off.
  S3, S6, S8-live blocked on human answers Q1, Q2, Q4/O-19.
- 2026-09-03 — **S2/S3 replied. Read `docs/comms/replies/S2-REPLY-2026-09-03-*.md` before
  resuming.** Three things changed:
  **(1) `FINDINGS-D6.md` cause (c) was FALSIFIED** — see the correction appended to that file. The
  `PUBLISH_NACK`/watcher-rollback mechanism and its bar-revision sub-theory are both refuted by
  two queries the investigation recorded as "not run": the 14:15Z run logged `published_count: 1`
  with zero NACKs anywhere in the log, and the 13:00Z bar closed at 158.568 and was **never
  revised** (158.849 is the **16:00Z** close). The real mechanism is the original one — built from
  the newly-closed bar, stamped with the strategy's stale signal bar. **Do not build a fix on the
  rollback story.**
  **(2) D8 scope changed** — no index; `bar_content_sha256` instead. See S8.
  **(3) O-26 is new and is not D6** — strategy 58 re-fired USD_CAD H1 long twice, two hours apart,
  entries 1 pip apart; System 3 sized and filled **both**, both stopped out. Distinct `signal_id`s
  on distinct bars, so **no dedupe key catches it** and the D6 fix will not either. Ownership is an
  open question with Systems 2/3 — do not fix it here.
  **Urgency:** the owner intends to close the circuit breaker shortly. Signals resume against an
  unfixed producer, so **D6 is the item that should land first.**
