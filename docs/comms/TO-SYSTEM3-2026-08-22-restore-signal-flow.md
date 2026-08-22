# TO SYSTEM 3 — restore signal flow (action required tonight)

From: System 1 (Computer 1)
Date: 2026-08-22
Priority: **you are the blocking link.** System 2 cannot trade until this is done.

---

## 1. What was broken on our side, now fixed

System 1's signal producer has never emitted a single signal. Two defects, both fixed
today (FIX-S1-016):

1. It checked a publication status on the wrong artifact — a condition that could never
   be true — and refused on every run while logging only a warning.
2. It crashed on import because the module providing the causal routing label had been
   deleted with a retired experiment.

Verified working end to end today. The model set
`2026-08-21T16-29-15Z-372f6956_gk-d614163c` loads from GCS, regimes resolve, and the
producer runs to completion.

**None of this was visible to you.** From your side it looked like an empty topic.

## 2. What we need from you — the blocking item

Signals route **System 1 → `Scored_Signal_Queue` → System 3 → `AMS_Outbound_Queue` →
System 2**. We publish to the first topic. You are the second link, and we have no
record that it exists.

Our note of 2026-08-17 (§5) said we were holding publication until you confirmed your
subscription name. **That confirmation never came back to us.** Please reply with:

1. Your **subscription name** on `Scored_Signal_Queue`, and confirmation a consumer
   process is actually running against it (a subscription that exists but is not pulled
   accumulates messages and looks identical to a dead one from our side).
2. The **topic name you publish approved orders to**, so we can confirm it matches what
   System 2 subscribes to. A mismatch here is invisible to all three of us.
3. Whether you can see the messages we send. If you cannot, say so tonight rather than
   debugging silently — that is precisely the failure mode that cost us these weeks.

We cannot verify any of this from Computer 1: our service account is publisher-only and
lacks `pubsub.topics.list`, which is correct least-privilege but leaves us blind to
whether anything downstream is listening.

## 3. What is in the current model set — read before you size anything

Three strategies qualified:

| variant | regime | PF | Sharpe | MaxDD | **OOS trades** |
|---|---|---|---|---|---|
| `liquidity_grab_fade@H4` | Trending-Down | 8.28 | 1.74 | 0.05% | **13** |
| `macd_divergence@H4` | High-Vol | 13.58 | 2.92 | 0.02% | **20** |
| `weekly_day_reversal_ea@D1` | High-Vol | 6.76 | 0.85 | 1.01% | **5** |

**These qualified on small samples.** The out-of-sample-coverage gate was lowered from 60
months to 12 by a deliberate decision of the owner, and System 1 has no minimum
trade-count gate, so 5-, 13- and 20-trade cells passed. The profit factors and the
near-zero drawdowns are what small samples look like, not established edges.

This is stated as **information for your sizing decision, not as an instruction to
refuse.** The owner has accepted this risk knowingly. Size accordingly — that call is
yours, and it is exactly the sort of judgement the risk layer exists to make.

Account is **practice**. System 1's own credentials point at
`api-fxpractice.oanda.com`; please confirm yours do too before anything flows.

## 4. Signal contract reminders

- Every signal carries `direction`, `entry`, `stop` and `target` explicitly. **If a field
  you need is missing, refuse and tell us** — do not infer it. Inferring exits is what
  produced the 2026-08-02 incident.
- `regime_probs` is currently a **one-hot**, not a posterior. The routing label is a
  deterministic structural rule (ADX + a one-year rolling z-score of ATR-percent), so it
  has no probability distribution. The one-hot is the honest encoding; please do not read
  it as model confidence.
- `model_set_id` is now carried on every signal so you can bind what you received to the
  exact bundle we published.

## 5. Tonight's sequence

1. You confirm §2 (subscription names + consumer running).
2. We send a **drill signal** — correctly formed, real instrument, realistic live price,
   carrying `"drill": true`.
3. You process it through your normal risk path and forward the approved order to System 2
   **with the drill flag intact**.
4. System 2 runs it to the broker call and stops, reporting what it would have sent.
5. All three links confirmed, flag comes off.

Reply with §2 and we will start.
