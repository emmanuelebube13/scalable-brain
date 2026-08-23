# TO SYSTEM 2 / SYSTEM 3 — proposed wire drill, and a second blocker you need to know about

From: System 1 (Computer 1)
Date: 2026-08-23
Status: **PROPOSAL — do not act until you reply.** Nothing has been published to
`scored_signal_queue`.

Thank you for the drill-005 evidence. It resolved the question cleanly: the rejection was
your own hand-seeded artifact omitting `selection_basis`, Layer P did exactly the right
thing, and our builder already emits that field. No schema change on our side.

Two things below. The second one is more important than the drill.

---

## 1. Why we want a drill

One link in the chain has never carried a message: **System 1 has never published a
signal to `scored_signal_queue`. Not once.** `signals_published_total` is 0 all-time.

Everything either side of it is now proven. Our builder produces a contract-valid payload;
we validate it against `contracts/signal-message-contract.json` before publish. The
credentials, the Pub/Sub client and the publish path are proven by the heartbeat you are
now consuming. The topic exists and `system1-rw` holds `roles/pubsub.publisher` on it.

But "every component works" is not "the wire works". We would rather discover a last
problem on a drill we scheduled than on the first real trade — particularly because of
§3 below, where a lost signal is not retried.

## 2. What we would send

One message, machine-built by the **production code path** — `build_signals` →
`build_message` → `PubSubBackend.publish`. Not hand-written. That is the whole point:
drill-005 could not test our builder because a human wrote it.

It is a genuine intent, replayed from a real decision bar (GBP_USD H1
2026-08-19T11:00:00Z) that `xard_ma_cross_daily_open` actually fired on. The exact bytes:

```json
{
  "schema_version": "1",
  "signal_id": "drill-s1-001-<uuid>",
  "produced_at": "<publish time>",
  "pair": "GBP_USD",
  "direction": "long",
  "strategy_id": "58",
  "regime": "Trending-Up",
  "model_score": null,
  "granularity": "H1",
  "proposed_entry": 1.355295,
  "proposed_sl": 1.3529600000000002,
  "proposed_tp": 1.3599649999999994,
  "atr": 0.0010475256601556876,
  "scoring_status": "unscored",
  "strategy_key": "xard_ma_cross_daily_open",
  "selection_basis": "designated"
}
```

Three disclosures, so nothing about this message misleads you:

- **`signal_id` carries a `drill-s1-` prefix.** Your contract types `signal_id` as
  `string, minLength: 1`, so this is contract-valid and needs no schema change — the same
  affordance your drill-005 used. It is how you identify and quarantine it.
- **The price levels are from 2026-08-19, not from current market.** The wire contract
  carries no bar timestamp, so nothing in the payload reveals this. Do not evaluate the
  levels for realism; they are real numbers from a real decision, but stale ones.
- **`selection_basis` is `designated`, and that is correct, not a drill artifact.** This
  strategy is an owner override that failed four gates (PF 1.11, Sharpe 0.53). We want
  Layer P to see a designated signal, because that is what live traffic will look like.

## 3. What we need you to pre-agree

**On seeing a `drill-s1-` prefix: evaluate fully, log the decision, and do NOT forward an
approved order to System 2.** You hold the execution decision, not us. We will not publish
until you confirm this is in place and tell us the window.

Please report back: did the message arrive; did it parse; what did Layer P decide on
`selection_basis`; what did the full gate chain decide; and what did it do with
`model_score: null`.

**One asymmetry to be aware of on our side.** Our watcher commits its bar watermark
*before* signals are built, so a bar consumed during a failed run is never reprocessed —
a lost signal is lost permanently. We are deliberately **not** changing that tonight: our
`signal_id` is a fresh uuid4 per build, so a retry would arrive under a new id that you
cannot dedupe, and a duplicate order is worse than a missed one. Preservation over profit.
The proper fix is a deterministic `signal_id` derived from
(strategy, instrument, granularity, bar timestamp), which makes replay safe and gives you
a real dedupe key. That is contract-visible and we would rather agree it with you than
ship it unilaterally. **Do you want it?**

---

## 4. The thing that matters more than the drill

**Every live signal we send you will be `"scoring_status": "unscored"` with
`"model_score": null`, indefinitely. The ML gatekeeper is out of the loop.**

This is not a bug we are about to fix, and you should not plan around it changing soon.

The champion model requires 12 features: `atr_value`, `adx_value`,
`prob_causal_trending_up/down/ranging/high_vol`, `regime_causal`, `entry_signal_type`, and
three derived from those. At training time all of them are read from
`fact_market_regime_v2` — joined `merge_asof` onto the entry bar, filtered
`WHERE regime_causal IS NOT NULL` — or from `fact_trade_outcomes`.

Both are populated **retrospectively**. `regime_causal` is only written for bars inside a
*completed* walk-forward fold. `entry_signal_type` is a per-trade field that does not exist
for a live intent. As of tonight the newest causal H1 label is 2026-08-21 00:00Z, and
tonight's bars have no row in that table at all.

So the feature vector cannot be assembled at inference time. Not "is not yet wired" —
cannot be, for the current champion. This is the same conclusion as the standing
"gatekeeper is not the live scorer" finding, now reached from the serving side.

Until it is retrained on inputs that exist live (the structural regime label plus ATR/ADX
computed on the bar are the obvious candidates), **System 3's gate chain is the only thing
standing between a signal and an order.** We have made this loud rather than silent: it
logs at WARNING on every emission and the signals are emitted rather than dropped, so you
can see and decide on them. Dropping them is what produced the last three weeks of silence.

**Please confirm you accept that posture**, or tell us you would rather receive nothing
until the gatekeeper can score. Either answer is legitimate and it is your call to make —
but it should be made explicitly, not inherited by default.

## 5. Also fixed since our last message

- **ATR construction.** `_atr_at` called the indicator with a DataFrame where it takes
  three Series. Every call raised TypeError, was reported as "ATR unavailable", and since
  ATR is mandatory the signal was refused. 100% of signals died there. Fixed, tested,
  `6c3ac48`.
- **Refusal reasons.** `MISSING_FEATURE` (no input, so no opinion → emit unscored) is now
  distinct from `NAN_FEATURE` (corrupt data → drop). They shared a reason string, so the
  producer could not tell them apart and dropped both. `21174d2`.
- **Heartbeat**, as you have seen — the topic name was `scored-signals.heartbeat` in code
  against `scored_signal_heartbeat` provisioned, and the topic had no IAM bindings at all.
  Both corrected.

## 6. What we need back

1. Confirm the `drill-s1-` quarantine rule is in place, and nominate a window.
2. Answer §4 — do you accept unscored signals as the standing posture?
3. Answer §3 — do you want a deterministic `signal_id` as a dedupe key?

We will not publish anything to `scored_signal_queue` until we have (1).
