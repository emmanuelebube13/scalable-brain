# TO SYSTEM 2 — ADR-001 review, then build

From: System 1 (Computer 1)
Date: 2026-08-22
**Phase 1 is REVIEW. Do not write implementation code until §4 is sent and the owner
confirms both systems approved.**

---

## 0. Instruction to the agent working on System 2

You are being asked to **evaluate a proposed architecture change against the system you
actually have**, and to say yes or no with reasons. You are not being asked to agree.

System 1 wrote the proposal and cannot see your codebase. If the proposal assumes
something about System 2 that is false, **that is the single most valuable thing you can
report**, and it is worth more than a fast approval.

A rejection with a concrete reason is a good outcome. A "looks good" that turns out to be
wrong three weeks into implementation is the bad one.

You may deploy specialised sub-agents for self-contained checks in §3 (e.g. "measure our
candle history depth"). Give each the relevant section verbatim — they do not inherit your
context — and verify their findings yourself before recording them.

---

## 1. Read first

`docs/design/ADR-001-where-inference-runs.md` in the System 1 repo, in full.

Short version: System 1 currently runs a continuous signal producer on Computer 1 and you
wait on its output. Computer 1 has unreliable networking, so **if it is offline nothing
trades anywhere** — which is how its producer sat broken for weeks unnoticed. It also
contradicts the ratified `README.md`, which specifies *you* syncing the bundle and running
live inference with "no dependency on Computer 1's database".

ADR-001 proposes returning to that: System 1 offline-only, you performing inference from a
bundle that carries the strategy code.

## 2. What would change for you

**You gain:** syncing a bundle that now contains strategy implementations as well as
models, running the regime labeller and strategies against your live candles, producing
scored signals, and publishing them to `Scored_Signal_Queue`.

**Unchanged:** you still never size and never approve your own orders. A signal you
generate is inert until System 3 approves it and returns it on `AMS_Outbound_Queue`.

**Also unchanged:** you must never *infer* a missing field. That was the 2026-08-02
incident and it still stands. Running a checksummed artifact System 1 validated is a
different act from guessing at a value that was not sent.

## 3. What we need you to actually check

Do not answer these from memory or from your documentation. Verify each against the
running system and say how you verified it.

1. **Candle history.** The regime labeller needs **252 D1 bars of warm-up** before it emits
   anything but `UNKNOWN`. Do you have that depth per instrument, and does it persist
   across restarts? If you would need to backfill from OANDA, say so and estimate it.
2. **Price agreement.** Your candles and System 1's come from independent OANDA ingests.
   Two independent ingests can disagree, and a regime label computed from a different price
   series is a *different label*. How would we detect divergence? Would you accept a
   periodic reconciliation against System 1's series?
3. **Executing System-1-authored code.** The bundle would carry Python from another machine
   and you would execute it. Is that acceptable to your security posture? If yes, what do
   you require — a signed manifest, a pinned dependency set, a sandbox, a review gate? If
   no, say so plainly; it likely kills the ADR and that is a legitimate outcome.
4. **Artifact sync.** `README.md` says you already poll `latest.json` (~15 min), SHA256
   verify, and atomically swap the model cache. **Is that built and working today?** Much of
   the ADR's feasibility rests on it. If it is aspirational rather than real, say so.
5. **Scoring.** Does the gatekeeper score get applied by you or by System 3? System 1's
   reading is that you score, because "System 3 never re-scores" implies the score exists
   before System 3 sees it. Confirm or correct.
6. **Timing.** Two of the three live strategies are **H4**. Can you evaluate and publish
   within a reasonable window of an H4 bar close? What is that window in practice?
7. **Determinism.** System 1 will ship a **reference vector** — fixed input bars plus the
   exact signals its own code produces. You would replay it after each sync and compare.
   Is that workable, and what float tolerance do you want? State a number.
8. **Runtime.** Python version, available memory, whether you can install the pinned
   dependency set (hmmlearn, xgboost, scikit-learn, pandas, ta) without disturbing your
   existing environment.

## 4. What to send back — Phase 1 deliverable

A single document containing:

1. **APPROVE or REJECT**, stated in the first line, with reasons.
2. Your answer to each of the eight items in §3, each with how you verified it.
3. Anything the ADR assumes about System 2 that is **wrong**. Be specific and blunt.
4. Anything it does not consider that it should.
5. If APPROVE: your estimate of the work, and what you need from System 1 first.
6. If REJECT: what would have to change for you to approve, or why the current
   architecture should stand despite the Computer 1 availability problem.

Send it to the owner. System 1 will not proceed past scoping until both you and System 3
have replied.

## 5. Phase 2 — only after both systems approve

Do not start this until the owner confirms.

1. System 1 publishes bundle v2 with strategy code, pinned dependencies, and the reference
   vector.
2. You build inference: sync, verify checksums, replay the reference vector, and **refuse
   to run at all if it does not match**.
3. Drill: generate a signal carrying `"drill": true`, publish it, and confirm it traverses
   System 3 and returns to you. Stop at the broker call and log what you would have sent.
4. **Cutover is a single coordinated change.** System 1's producer stops in the same change
   that starts your inference. If both publish, System 3 receives two signals per bar with
   different `signal_id`s and idempotency will not catch it. This is a hard requirement.

## 6. Meanwhile — three things worth fixing regardless

These are real System 2 defects independent of the ADR:

1. **Alarm on malformed signals; do not drop them silently.** You received signals telling
   you to buy USD_JPY at 1.05 — an instrument trading near 159. They were test fixtures
   that leaked from System 1's test suite into the production queue (our fault, being
   fixed). Rejecting them was right. But had that *alarmed*, this would have surfaced in a
   day instead of weeks.
2. **Make idle observable.** "No signals in N hours", "signals received and rejected", and
   "consumer process down" must be distinguishable from outside. Right now they are not.
3. **Confirm your transport.** `QUEUE_PROVIDER` on System 1 is now `pubsub`; it was `local`,
   meaning signals landed in a directory on Computer 1 that nothing else could read. If any
   part of your path still polls a file queue, it can never receive anything.

## 7. One honest note about the current bundle

The three live strategies qualified on **5, 13 and 20 out-of-sample trades** after the
owner deliberately lowered the out-of-sample gate from 60 months to 12. System 1 has no
minimum-trade-count gate, which is how cells that thin passed. The profit factors (6.8–13.6)
and near-zero drawdowns are small-sample artefacts, not established edges.

This is a knowingly accepted risk on a **practice** account. It is stated for context and
sizing, **not** as grounds to refuse orders. Confirm you are pointed at
`api-fxpractice.oanda.com` before anything executes.
