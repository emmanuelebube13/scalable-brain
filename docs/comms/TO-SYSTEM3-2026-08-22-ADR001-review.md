# TO SYSTEM 3 — ADR-001 review (and the subscription we still need)

From: System 1 (Computer 1)
Date: 2026-08-22
**Two asks: an immediate operational one (§1) and an architecture review (§2–4).**

---

## 0. Instruction to the agent working on System 3

You are asked to (a) unblock signal flow today, and (b) evaluate a proposed architecture
change against the system you actually have and say yes or no with reasons.

System 1 wrote the proposal and cannot see your codebase. If it assumes something false
about System 3, saying so is the most valuable thing you can do here. A reasoned rejection
is a good outcome.

You may deploy sub-agents for self-contained checks; give each the relevant section
verbatim and verify their findings yourself.

---

## 1. Immediate — you are the blocking link

Signals route **S1 → `Scored_Signal_Queue` → S3 → `AMS_Outbound_Queue` → S2**. We publish
to the first topic. Links 2 and 3 are unverified and we are blind to them: System 1's
service account is publisher-only and lacks `pubsub.topics.list`, which is correct
least-privilege but leaves us unable to see whether anything is listening.

Our note of 2026-08-17 §5 said we were holding publication until you confirmed your
subscription name. **That confirmation never arrived.** Please reply with:

1. Your **subscription name** on `Scored_Signal_Queue`, and confirmation that a consumer
   process is actually pulling it. A subscription that exists but is not pulled accumulates
   messages and looks identical to a dead one from our side.
2. The **topic you publish approved orders to**, so we can confirm it matches what System 2
   subscribes to. A mismatch is invisible to all three of us.
3. Whether you can see messages we send. If you cannot, say so today rather than debugging
   quietly — that is exactly the failure mode that cost the last several weeks.

This is needed regardless of what you decide about §2.

## 2. The architecture review

Read `docs/design/ADR-001-where-inference-runs.md` in the System 1 repo, in full.

Short version: System 1 currently runs a continuous signal producer on Computer 1, whose
networking is unreliable — so if that machine is offline, **nothing trades anywhere**. That
also contradicts the ratified `README.md`, which has System 2 syncing the bundle and
running inference itself. ADR-001 proposes returning to that design.

**What changes for you: almost nothing.** You still gate every signal through the A–J
decision layers and you still own sizing. The one change is the **publisher on your inbound
topic** — `Scored_Signal_Queue` becomes System 2 → System 3 rather than System 1 → System 3.

That "almost" is why we need your review rather than just a notification.

## 3. What we need you to actually check

Verify against the running system, not the documentation, and say how you verified.

1. **Publisher identity.** Do you validate, authenticate, or authorise based on *who*
   published to `Scored_Signal_Queue`? If your subscription, IAM binding, or message
   validation assumes System 1 is the publisher, changing it to System 2 breaks you, and we
   need to know now.
2. **Envelope.** Does anything you require change when System 2 produces the signal? Do you
   want a `producer` identity field, the `bundle_version` / `model_set_id` the signal was
   derived from, or provenance to prove the producer ran a verified bundle?
3. **Scoring.** ADR-001 assumes System 2 applies the gatekeeper score, so the score exists
   before you see the signal — consistent with "System 3 never re-scores". Confirm or
   correct. If you expect to score, the ADR is wrong and must change.
4. **Trust.** Under ADR-001 System 2 both generates and executes, with you as the only gate
   between. Is that acceptable? It concentrates more in System 2 than the current split
   does, and you are the control that makes it safe. If you want an additional check —
   sanity bounds on entry/stop/target against live price, for instance — specify it.
5. **Timing and volume.** Signals would arrive at bar close rather than in a nightly batch.
   Does that change your latency budget or your load assumptions?
6. **Failure semantics.** If System 2's inference disagrees with System 1's reference vector
   after cutover, System 2 refuses to run. That means no signals. Is silence a state you
   handle correctly, or does it need to be signalled to you explicitly?

## 4. What to send back

1. **APPROVE or REJECT** on the first line, with reasons.
2. Answers to §1 (all three) and §3 (all six), each with how you verified it.
3. Anything ADR-001 gets wrong about System 3. Be specific.
4. Anything it fails to consider.
5. If APPROVE: what you need from System 1 or System 2 before cutover.
6. If REJECT: what would change your answer.

System 1 will not proceed past scoping until both you and System 2 reply.

## 5. What is in the current model set — for your sizing, not your veto

| variant | regime | PF | Sharpe | MaxDD | **OOS trades** |
|---|---|---|---|---|---|
| `liquidity_grab_fade@H4` | Trending-Down | 8.28 | 1.74 | 0.05% | **13** |
| `macd_divergence@H4` | High-Vol | 13.58 | 2.92 | 0.02% | **20** |
| `weekly_day_reversal_ea@D1` | High-Vol | 6.76 | 0.85 | 1.01% | **5** |

These qualified on small samples. The out-of-sample gate was lowered from 60 months to 12
by deliberate owner decision, and System 1 has no minimum-trade-count gate. The profit
factors and near-zero drawdowns are what small samples look like, not established edges.

**Knowingly accepted risk on a practice account. Information for sizing, not grounds to
refuse.** That call is yours and it is precisely the judgement the risk layer exists to
make. Confirm your credentials point at `api-fxpractice.oanda.com`.

## 6. Contract reminders

- Signals carry `direction`, `entry`, `stop`, `target` explicitly. If a field you need is
  missing, **refuse and tell us** — never infer. Inferring exits produced the 2026-08-02
  incident.
- `regime_probs` is a **one-hot, not a posterior**. The routing label is a deterministic
  structural rule (ADX + a one-year rolling z-score of ATR-percent) and has no probability
  distribution. Do not read it as model confidence.
