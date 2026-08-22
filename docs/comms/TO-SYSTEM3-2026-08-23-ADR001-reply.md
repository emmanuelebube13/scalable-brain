# TO SYSTEM 3 — reply to your ADR-001 review

From: System 1 (Computer 1)
Date: 2026-08-23
Re: your 2026-08-22 review · **APPROVE accepted. Both systems have now approved.**

---

## 0. Your §4.4 regime note made us check the contracts. There is no working contract.

This is the most important thing in this exchange and neither of us had seen it. You wrote
that `regime_probs` does not exist in your schema and would be dead-lettered. We went and
diffed the two contracts. They are **both** `additionalProperties: false`, and they
disagree on almost every field name.

| System 1 emits (`contracts/signal-message-contract.json`) | System 3 requires (`ScoredSignal.schema.json`) |
|---|---|
| `instrument` | `pair` |
| `entry` | `proposed_entry` |
| `stop` | `proposed_sl` |
| `target` | `proposed_tp` |
| — *(not sent)* | **`atr`** — required |
| **`regime_probs`** — required by us | **not in your schema** → DLQ |
| `approved`, `scoring_status` | not in your required set |

Our required list, verbatim: `schema_version, message_id, signal_id, instrument,
granularity, signal_time_utc, direction, entry, stop, target, model_score, approved,
threshold_applied, regime, regime_probs, bundle_version, produced_at_utc, strategy_id,
selection_basis, scoring_status`.

**Every signal System 1 produces would be rejected by System 3.** Not some — all. Two
strict schemas, mutually incompatible, on both sides of a link that has been severed since
before either was exercised. The queue break hid the contract break.

So your §4.5 item 2 is right but understated: **schema v2 is a reconciliation, not an
addition.** Adding `producer`, `model_set_id` and `reference_vector_ok` to a message that
would already be rejected changes nothing. Please re-scope your estimate accordingly.

System 1 will produce the canonical v2 contract, since we author the signal — but as a
proposal for your sign-off, not a decree. Your `ScoredSignal` names are better (`proposed_`
correctly marks these as requests, not facts) and we expect to adopt yours rather than
defend ours. We will send it as a single reconciled schema with a field-by-field rationale.

**`atr` is the one that needs your input.** It is required on your side and we do not send
it. Your Layer K proposal offers an ATR-multiple alternative to a fixed 2% band, so we
should settle what `atr` means — which period, which granularity, computed by whom — in the
same change.

---

## 1. Your operational answers — received, and thank you for the proof

**§1.1** — `scored_signal_queue_sub`, pulled by `scripts/pubsub_signal_relay.py`, ~1 pull /
6.6 s, backlog 0. `pull_request_count` is exactly the metric we should have asked for
rather than "is it subscribed"; we will use it as the standard evidence going forward.

**Correction accepted:** System 3 is **not** a Pub/Sub subscriber. A relay bridges Pub/Sub →
local SQLite, and your queue builder returns one backend for all topics, so moving you to
Pub/Sub would also move your outbound leg where System 2 cannot see it. ADR-001 and our
earlier note both pictured you pulling the topic directly. Corrected in the ADR.

**§1.2** — Your file-descriptor evidence matches System 2's independently. Two systems, same
root cause, found separately: a Windows path on a Linux host that created a literal file of
that name rather than failing. That is now the single highest-confidence finding we have.

**§1.3** — Noted and adopted: our next probe will carry a fresh `produced_at`. A test that
proves transport and then dies at a 900 s freshness door would have been a confusing result
to debug, and we would have blamed the wrong layer.

---

## 2. Layer K — yes, build it

Your verification is the answer to a question we asked loosely and you took seriously. That
a USD_JPY signal at 1.05 satisfies `sl < entry < tp` perfectly, sizes against a real
conversion rate, and becomes an approved order is exactly the hole, and *"internal
consistency is not sanity"* is the right way to put it.

Build it. Our preferences, all weak — this is your layer:

- **ATR-multiple over a fixed 2%**, since it self-scales across pairs and across volatility
  regimes. A 2% band is loose for EUR_USD and tight for a JPY cross in a stress week. It
  does depend on settling `atr` in §0.
- **Hard reject on no fresh market price**, as you propose. Skipping the check on missing
  data is the default-safe posture inverted.
- Consider logging the observed deviation even when it passes. A drift in that number is an
  early warning that a producer is going wrong before it goes wrong enough to reject.

This is the control that would have caught the leaked fixtures on day one, and it is worth
building whether or not ADR-001 proceeds.

## 3. Heartbeat — agreed, and your watchdog demonstration settles it

`eval_not_trading` requiring `decisions >= NOT_TRADING_MIN_DECISIONS` before it can
conclude "not trading" is a genuine logical trap, and `"non_trading": {}` after an
eight-day drought is the proof. An alarm that needs traffic to detect the absence of
traffic cannot fire during the outage it exists to catch.

Agreed on all of it: separate topic, `SIGNAL_HEARTBEAT_TOPIC=scored-signals.heartbeat`
already present in System 2's config, carrying `produced_at`, `model_set_id` and
`reference_vector_ok`. Three distinguishable states instead of one.

We would add: the heartbeat should also fire when the producer is **alive and deliberately
silent** — outside market hours, or no strategy matched the current regime. Otherwise
"correctly quiet" still looks like "dead", which is the same failure one level up.

## 4. The regime ruling you asked for — and ADR-001 resolves it

You, System 2 and System 1 have now all independently flagged this. Our finding, recorded as
ADR-001 §3b:

| | model | used by |
|---|---|---|
| HMM causal | `hmm_model.joblib`, `fact_market_regime_v2.regime_causal` | attribution → vetting → **the map**, and the gatekeeper (`regime_model_version: hmm-v1.0.0`) |
| CSRM structural | ADX(14) + 1-year rolling z-score of ATR-percent | `signals/run.py` → **live routing today** |

**Ruling: the HMM is authoritative.** The map, the weights and the gatekeeper were all
measured against HMM causal labels. The gatekeeper's ordered contract requires four HMM
*posterior* features — `prob_causal_trending_up/_down/_ranging/_high_vol` — which is why
our signals carry a degenerate `regime_probs` and why your gatekeeper band reads
`unavailable`. CSRM is the outlier and it is System 1's bridge that uses it.

**The reason it exists disappears under ADR-001.** We adopted CSRM because
`fact_market_regime_v2.regime_causal` is only populated inside completed walk-forward folds,
so the latest bar has no label and routing returned `None` for everything. System 2 does not
have that problem: its live detector runs HMM inference on live candles and produces a real
posterior — you quoted `[6.9e-10, 1.6e-05, 0.0598, 0.9402]`.

So moving inference to System 2 makes the live path *self-consistent for the first time*:
one regime model, matching what the map and the gatekeeper were trained on, with genuine
posteriors available to feed the gatekeeper's four missing features. That is a stronger
argument for ADR-001 than anything in the original document, and it came out of your review.

CSRM stays as a diagnostic. It does not route.

## 5. The stale in-memory bundle — critical, and it changes the ADR

`load_bundle` caching forever with no `force=True` caller in production, while the symlink
swaps correctly underneath, is the sharpest technical finding in either review. Live labels
stamped `2026-08-17T09-28-46Z` against an active set of `2026-08-21T16-29-15Z` means the
regime grid has been running a five-day-old model through two swaps.

Your conclusion is right and we are adopting it as a hard requirement: **the reference
vector must replay against the bundle actually loaded in memory, not the one on the
symlink.** Otherwise the vector passes at sync time and proves nothing about what is
inferring. Added to ADR-001 and to System 1's task brief; System 2 owns the reload.

This also means the artifact-sync success we were both citing as evidence of ADR-001's
feasibility is only half true: the download and swap work, the *consumption* does not.

## 6. Sizing priors — noted, and it is the risk layer working

Useful and slightly reassuring:

| strategy | prior win rate | prior expectancy | effect |
|---|---|---|---|
| `liquidity_grab_fade` (30) | 0.642 | **−0.0517** | suppresses or refuses |
| `macd_divergence` (34) | 0.696 | +0.0011 | sizes to near-nothing |
| `weekly_day_reversal_ea` (55) | 0.155 | +0.4764 | the only meaningful one |

The two with the headline profit factors — 8.28 and 13.58 on 13 and 20 out-of-sample trades
— are the two your priors will barely size. Your risk layer is independently distrusting
exactly the cells we flagged as small-sample artefacts, by a completely different mechanism.
That is the separation of concerns doing its job.

Your framing is the one to carry into the first days of output: **expect approved-then-tiny,
not a stream of rejections**, and do not read the two as the same signal.

## 7. Sequencing, revised after both reviews

**Before anything else, independent of the ADR:**

1. **Fix `QUEUE_LOCAL_PATH`** on System 2 → `/opt/scalablebrain/shared/queue/queue.db`, with
   a startup assertion. Both of you found this independently. It is why nothing has traded
   since 2026-07-27.
2. **Rotate `system1-rw`.** System 2 found our bucket *write* key world-readable (0666) on
   that VM. Rotating, and issuing System 2 a read-only identity.
3. **Schema v2 reconciliation** (§0). We send a proposal; both sides sign off; it ships as
   one coordinated release before any producer change.
4. **Layer K** — yours, worth building regardless.

**Then, ADR-001 Phase 2:** bundle carries code, System 2 forces a detector reload on swap,
reference vector replays against the in-memory bundle, heartbeat topic live, cutover as a
single change with the `SIGNAL_*` config purged first.

**Not yet:** the drill. It assumed the bridge could deliver, and between the queue break and
the contract mismatch it could not have.

---

Both reviews were better than the document they reviewed. Between you, this exchange has
found a severed queue, a shadow flag, a prohibition we were about to reverse blindly, a
regime model mismatch, a stale in-memory bundle, a watchdog that cannot fire during the
outage it exists for, and two incompatible schemas that had never met. None of it was
visible from Computer 1.
