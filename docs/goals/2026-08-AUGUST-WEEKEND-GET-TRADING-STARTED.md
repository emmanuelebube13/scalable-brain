# THE AIM — get trading started

Weekend of **2026-08-22 → 2026-08-24**. Market reopens **Sunday 21:00 UTC**.

This is the core aim. Everything else this weekend is subordinate to it.

---

## The goal, stated so it can be judged

**One real order placed on the OANDA practice account, by System 2, from a signal System 1
produced, that passed System 3's risk gate — by Monday 2026-08-25.**

Not a plan for it. Not a drill. An order with a fill or a documented reason it did not fill.

**Fallback if that is not reached:** all three links proven end to end with a drill signal —
same `signal_id` visible at System 1, System 3 and System 2, with System 2 logging the exact
order it would have sent. That is the honest partial win and it is worth having.

---

## Where we actually stand

Nothing has traded since **2026-07-27**. Four separate faults, found this week, all of them
now understood:

| # | fault | owner | effort |
|---|---|---|---|
| 1 | `QUEUE_LOCAL_PATH` is a Windows path on a Linux host — SQLite created a literal file of that name. **Link 3 severed.** | System 2 | minutes |
| 2 | `EXEC_SHADOW=true` — orders constructed, never submitted to the broker | System 2 | minutes |
| 3 | **The two signal schemas are mutually incompatible.** Both `additionalProperties: false`, disagreeing field names. Every System 1 signal would be rejected by System 3 | System 1 | ~a day |
| 4 | System 1's producer could never emit (FIX-S1-016) | System 1 | **done 2026-08-22** |

Faults 1 and 2 are why nothing traded even when something was sent. Fault 3 is why nothing
would have worked even after 1 and 2 were fixed. Fault 4 is why nothing was sent at all.

## The fastest path — and it is not the ADR

**ADR-001 is not required for this goal and must not block it.** It is the right destination
and it is approved by both systems, but it is weeks of work.

The weekend path is narrower: **System 1 adapts its emitter to System 3's existing
contract.** System 3's `ScoredSignal.schema.json` is already deployed, already validated,
already consumed by a relay that is provably pulling. There is no need to negotiate a "v2"
this weekend — one side changes, and it should be ours, because we are the producer and
theirs is the deployed consumer.

Concretely, on System 1's side:

- `instrument` → `pair`
- `entry` / `stop` / `target` → `proposed_entry` / `proposed_sl` / `proposed_tp`
- add `atr` (our strategies already compute it for their stops)
- drop `regime_probs` (it is degenerate today and unknown to System 3's schema)
- keep `model_score` **nullable** — System 3 branches on NULL as "unscored", never "scored zero"
- carry `selection_basis` forward, so a miss produces an auditable REJECT rather than a silent DLQ

That is a one-sided change to a producer that emits nothing today. Low risk by definition.

## Sequence

1. **System 2** — fix `QUEUE_LOCAL_PATH`, add a startup assertion that the resolved path
   exists and is the shared file. Confirm a message crosses.
2. **System 1** — emit in System 3's dialect. Validate against their schema before sending.
3. **Drill** — one correctly-formed signal, real instrument, live price, `produced_at`
   stamped at send time (System 3's freshness window is 900 s and will reject a stale probe).
   Confirm it at all three systems.
4. **System 2** — flip `EXEC_SHADOW` to false, deliberately, only after the drill passes.
5. **Live** — market reopens Sunday 21:00 UTC. First H4 bars close shortly after.
6. **Producer cadence** — the cron runs once daily at 22:30 weekdays. Two of three strategies
   are H4. For the weekend, run it manually or temporarily more often. Do **not** invest in
   making Computer 1 reliable; that is what ADR-001 exists to remove.

## What to expect, so it is not misread as failure

System 3's sizing priors, from their own review:

| strategy | prior expectancy | effect |
|---|---|---|
| `liquidity_grab_fade` | **−0.0517** | will suppress or refuse sizing outright |
| `macd_divergence` | +0.0011 | sizes to near-nothing |
| `weekly_day_reversal_ea` | +0.4764 | the only one that sizes meaningfully |

The two strategies with the headline profit factors (8.28 and 13.58) are the two that will
barely size. **Expect approved-then-tiny, not a stream of rejections.** Those are different
outcomes and reading one as the other will send someone debugging a system that is working.

Also: these strategies qualified on **5, 13 and 20 out-of-sample trades** after the OOS gate
was deliberately lowered from 60 months to 12. They may legitimately not fire at all this
weekend. **A quiet weekend is not necessarily a broken weekend** — which is exactly why the
observability work matters.

## Not this weekend

- ADR-001 Phase 2 (bundle carries strategy code). Approved, specified, weeks away.
- Adding instruments beyond the current 5.
- Changing the gates or adding a minimum trade-count gate. Owner has ruled; revisit after.
- Making the Computer 1 producer reliable.

## Definition of done

- [ ] A message crosses from System 3 to System 2 on the shared queue
- [ ] System 1 emits a signal that validates against System 3's schema
- [ ] Drill signal observed at all three systems with the same `signal_id`
- [ ] `EXEC_SHADOW=false`, decided deliberately
- [ ] **One real order on the practice account** — or a written reason none fired
- [ ] Whatever happens is written down in this folder before the week starts

---

*Note: `docs/goals/` already holds `JULY_2026_GOALS.md`, `VALUE_MILESTONES.md` and
`SYSTEM1_METRICS_AND_TARGETS.md`. This file lives in `goal/` at the root by the owner's
explicit request; consolidate later if that is preferred. `STRUCTURE.md` otherwise treats
the root as closed to new entries.*
