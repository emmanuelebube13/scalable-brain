# Tonight — restore trading, and start the architecture review

Date: 2026-08-22 (revised after ADR-001)
Owner runs this. Each step has a check that must pass before the next.

---

## What changed since the first version of this document

The first draft recommended raising the System 1 signal producer to an hourly cron.
**That recommendation is withdrawn.** It was treating the symptom.

System 1 runs on a host with unreliable networking. Making trading depend on that machine
running reliably every hour is the wrong direction — and it contradicts the ratified
`README.md`, which specifies System 2 syncing the bundle and running inference itself with
"no dependency on Computer 1's database".

See `docs/design/ADR-001-where-inference-runs.md`. The System 1 producer is now explicitly
a **bridge, not the destination**. Do not invest in making it reliable, and do not build
anything that depends on System 1 being online.

---

## Send order

| # | Document | To | Purpose |
|---|---|---|---|
| 1 | `TO-SYSTEM3-2026-08-22-ADR001-review.md` | System 3 | Subscription names (**urgent**) + architecture review |
| 2 | `TO-SYSTEM2-2026-08-22-ADR001-review-and-build.md` | System 2 | Architecture review, then build |
| 3 | `TO-SYSTEM2-2026-08-22-why-you-are-not-trading.md` | System 2 | Background: why the queue was empty. Diagnosis only |

Send 1 and 2 together. System 3 first in priority because §1 of its note is the only thing
blocking signal flow tonight.

**Neither system starts implementation work.** Both reply APPROVE or REJECT with reasons.
System 1's own work (`task/2026-August-week3/inference-migration/PROMPT-SYSTEM1.md`) is
gated on both replies.

---

## Step 1 — System 3 replies with subscription names *(blocking, tonight)*

Signals route `S1 → Scored_Signal_Queue → S3 → AMS_Outbound_Queue → S2`. We publish to
link 1. Links 2 and 3 are unverified and we cannot see them — System 1's service account is
publisher-only and lacks `pubsub.topics.list`.

Needed: subscription name on `Scored_Signal_Queue`, confirmation a consumer is actually
pulling it, and the topic it publishes approved orders to.

**Check:** a written reply naming all three. Not "it should be set up."

## Step 2 — System 2 confirms transport *(parallel, tonight)*

`QUEUE_PROVIDER` on System 1 is now `pubsub`. It was `local`, meaning signals landed in a
directory on Computer 1 that no other machine could read. If any part of System 2's path
still polls a file-based queue, it can never receive anything.

**Check:** System 2 states which topic/subscription it consumes and confirms the process is
running.

## Step 3 — Drill signal *(once 1 and 2 pass)*

System 1 publishes one correctly-formed signal on a real instrument at a realistic live
price, carrying `"drill": true`.

- System 3 processes it through the full risk path and forwards it **with the flag intact**.
- System 2 runs it to the broker call and **stops**, logging the order it would have sent.

**Check:** the same `signal_id` visible at all three systems, and System 2's logged order
matching what System 1 sent.

This proves all three links. It is worth doing under either architecture — the links are the
same afterwards, only the publisher of link 1 changes.

## Step 4 — Live on the bridge *(interim)*

Drop the drill flag. Practice account throughout — **confirm all three systems point at
`api-fxpractice.oanda.com` first.**

Market reopens Sunday 21:00 UTC; first H4 bars close shortly after. Expect signals only
when Computer 1 happens to be up and the cron has run. **That unreliability is the point of
ADR-001, not a bug to fix in the bridge.**

## Step 5 — Reviews return, then decide

System 2 and System 3 reply APPROVE or REJECT. The owner decides. If approved, System 1
begins the bundle work and cutover follows the plan in `PROMPT-SYSTEM1.md` §S7 — with
System 1's producer stopping in the **same change** that starts System 2's inference. They
must never both publish.

---

## Known and accepted, stated once

The three live strategies qualified on **5, 13 and 20 out-of-sample trades** after the
owner deliberately lowered the OOS gate from 60 months to 12. System 1 has no
minimum-trade-count gate, which is why cells that thin passed. The profit factors (6.8–13.6)
and near-zero drawdowns (0.02%–1%) are small-sample artefacts, not established edges.

**Knowingly accepted risk on a practice account. Not a defect, and not grounds for System 2
or System 3 to refuse orders.** Sizing is System 3's call. Worth revisiting after the pipe
is proven — a minimum-trade-count gate is worth adding regardless of where `oos_months`
lands.

## Fixed and verified today

- **FIX-S1-016** — the producer could never emit. It checked publication status on the wrong
  artifact (a condition nothing could satisfy) and separately crashed on import because the
  causal routing label had been deleted with a retired experiment. Both fixed, verified end
  to end against the live GCS bundle.
- Model set `2026-08-21T16-29-15Z-372f6956_gk-d614163c` published and loading correctly.
- Docs corrected: `README.md` and `CLAUDE.md` both carried the claim that System 1 is purely
  offline while it was in fact running an always-on component. Both now point at ADR-001.

## Still open, not blocking tonight

- Test fixtures can still reach the production queue (the `entry: 1.05` messages). Fix is
  step S2 of the System 1 brief and is ungated — it is a real defect either way.
- `src/registry/` retains imports of the removed `regime_aware` package, behind the
  `regime_aware_port` universe. Latent; will not fire for the current three strategies.
