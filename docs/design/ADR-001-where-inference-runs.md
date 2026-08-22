# ADR-001 — Where live inference runs

Status: **PROPOSED.** Requires review and explicit approval from System 2 and System 3
before any implementation begins.
Date: 2026-08-22
Supersedes: the 2026-08-02 ruling, if approved (see §3).

---

## 1. The contradiction this resolves

Two incompatible architectures are on record and neither document acknowledges the other.

**`README.md` — the ratified foundational design.** "System 2 in Brief":

> - **Artifact sync** — polls `latest.json` (~15 min), SHA256 verify, atomic swap of model cache.
> - **Live regime detector** — HMM inference on live candles with persistence smoothing.
> - **Local PostgreSQL** — own datastore; no dependency on Computer 1's database.

System 1 publishes a bundle. System 2 syncs it and runs inference. Computer 1 is
explicitly not a live dependency.

**The 2026-08-02 ruling.** System 2 is execution-only; its local signal producer should
be deleted rather than repaired. Entry logic belongs to System 1, which emits scored
signals on `Scored_Signal_Queue`.

The code implements the second. `src/signals/` and `src/queue_producer/` run a continuous
producer on Computer 1, and System 2 waits on its output.

## 2. Why the second one cannot stand

**Computer 1 is not a reliable host.** It runs on a Linux box whose wifi drops at random.
This is the stated reason GCS was introduced in the first place: so the model could be
handed over asynchronously and nothing time-critical would depend on that machine being
reachable.

Under the current implementation, **if Computer 1 is asleep, offline, or its cron is
misconfigured, no trading happens anywhere** — regardless of System 2 and System 3 being
perfectly healthy. That availability coupling is nowhere in the design documents, and it
is the direct cause of the 2026-08-22 incident in which the signal producer had never
emitted a single message in its life and no one could see why.

A system whose liveness depends on its least reliable component has its dependency
direction backwards.

## 3. What the 2026-08-02 ruling was actually about

The ruling is not wrong, it is narrower than it has been applied.

The 2026-08-02 incident was System 2 **inferring fields that were missing from a signal**
— specifically direction and exits, which System 1 was not sending. The remedy was to
make signals carry them explicitly, which the map schema now does.

That is a different claim from "System 2 must not run the model." Running a versioned,
checksummed artifact that System 1 built and validated is not inventing a signal, and it
is not the behaviour that caused the incident.

The "no downstream recomputation" principle (`README.md`) is likewise narrower than it
reads:

> System 3 never re-scores a signal. System 2 never re-sizes an order. System 1 never
> knows if it's live.

Each clause forbids **redoing a decision another system already made**. If System 1 is
not scoring live at all, System 2 scoring once is not a re-computation. The principle is
preserved, not broken, by moving inference — provided exactly one system does it.

## 3a. This ADR supersedes S1-NOTICE-2026-08-15 §4.3 — by name

Added 2026-08-22 at System 2's request (their Phase 1 review, Blocker 3). System 1 could
not see the prohibition it was proposing to reverse; System 2 quoted it from
`lifecycle.py:367–375`:

> EXEC-011's live scored-signal producer used to be built here. It was DELETED on
> 2026-08-15 (S1-NOTICE-2026-08-15 §4.3), not disabled: it fabricated an order's direction
> from the regime label — Trending-Down ⇒ short, every polling cycle, for every instrument
> — with no entry condition of any kind behind it. […] Do not reintroduce a local signal
> source here.

**That prohibition was correct and this ADR does not soften it.** What was deleted was a
System 2 module that *invented* directions from a label with no strategy behind it.
Correcting its arithmetic would have made it worse — correctly-signed orders for setups
that do not exist look right.

What ADR-001 proposes is a different object:

| deleted 2026-08-15 | proposed here |
|---|---|
| direction fabricated from a regime label | System 1's actual strategy code, unmodified |
| no entry condition | the entry conditions System 1 measured and vetted |
| authored in System 2 | authored and validated in System 1, transported |
| unverifiable | SHA256 + signed manifest + reference-vector replay gate |
| drift undetectable | refuse-to-start on any reference-vector mismatch |

The reference vector is the load-bearing distinction: it makes this **transporting System
1's logic**, not System 2 originating entries. If System 2's execution of the bundle
diverges from System 1's own output by one discrete decision, it refuses to run.

**S1-NOTICE-2026-08-15 §4.3 is superseded only for bundle-carried, checksum-verified,
reference-vector-gated strategy code from System 1.** It remains in full force for
anything else. System 2 still originates no signal of its own authorship, and if the
bundle is absent, stale, unverified, or fails replay, System 2 emits nothing — it does not
fall back to a local source.

## 3b. BLOCKING — the regime model the map was built on is not the one that routes

Found 2026-08-22 while answering System 2's check 05. Neither side had seen it. **This
must be resolved before Phase 2 and it may change the ADR.**

System 1 has two regime labellers and they are not the same model:

| | model | used by |
|---|---|---|
| **HMM causal** | `hmm_model.joblib`, 4-state Gaussian, `fact_market_regime_v2.regime_causal` | `attribution/attribute.py` → `vetting/vet.py` → **the map**, and `gatekeeper/train.py` (`regime_model_version: hmm-v1.0.0`) |
| **CSRM structural** | `regime/structural.py`, ADX(14) + 1-year rolling z-score of ATR-percent | `signals/run.py` → **live routing** |

So the regime→strategy map was measured against HMM labels and is applied against CSRM
labels. `High-Vol` under one is not the same population of bars as `High-Vol` under the
other, and nothing checks that they agree.

It gets sharper for the gatekeeper. Its ordered feature contract requires
`prob_causal_trending_up / _down / _ranging / _high_vol` — **HMM posteriors**. CSRM is a
deterministic rule and has no posterior; it emits a one-hot. That is why live signals carry
`regime_probs` of uniform `0.25` or a one-hot rather than a distribution: **the live path
cannot supply four of the gatekeeper's twelve features.** It is also consistent with System
2's observation that `gatekeeper.state: "unavailable"`.

Three ways out, to be decided before Phase 2 rather than during it:

1. **Route on the HMM causal label.** Matches what the map and gatekeeper were built on.
   Blocked by the reason CSRM was adopted: `regime_causal` is only populated inside
   completed walk-forward folds, so the latest bar has no label and routing returns `None`
   for every instrument.
2. **Rebuild attribution, vetting and the gatekeeper on CSRM labels.** Makes the live path
   self-consistent. Costs a full re-measurement and the gatekeeper loses its posterior
   features.
3. **Have the HMM emit a live causal label** for the current bar, so routing and training
   share one model.

Until this is settled, any signal the current bridge emits is routed by a label the map was
not measured against. Recorded here rather than quietly fixed, because it bears on whether
ADR-001's reference vector is even well-defined: a vector that pins CSRM output pins the
wrong thing if option 1 or 3 is chosen.

## 3c. Both systems approved. What their reviews changed.

**System 2: conditional APPROVE** (2026-08-22). **System 3: APPROVE** (2026-08-22).
Both verified against running hosts. Findings that alter this ADR:

**BLOCKING — the two signal schemas are mutually incompatible.** Found diffing
`contracts/signal-message-contract.json` against System 3's `ScoredSignal.schema.json`.
Both are `additionalProperties: false` and they disagree on nearly every field name:
`instrument`/`pair`, `entry`/`proposed_entry`, `stop`/`proposed_sl`,
`target`/`proposed_tp`; `atr` is required by System 3 and never sent; `regime_probs` is
required by System 1 and does not exist in System 3's schema. **Every signal System 1
produces would be rejected.** The severed queue meant the contract break was never
exercised. Schema v2 is a *reconciliation*, not the three-field provenance addition the
ADR proposed, and it must ship before any producer change. System 1 adopts System 3's
names.

**§3b is resolved: the HMM is authoritative, and ADR-001 is what fixes it.** CSRM exists
only because `regime_causal` is empty for the latest bar, so routing returned `None`.
System 2's live detector runs HMM inference on live candles and produces a real posterior,
so under this ADR the live path becomes self-consistent for the first time — one regime
model, matching what the map and gatekeeper were trained on, with genuine posteriors to
feed the gatekeeper's four missing features. CSRM becomes a diagnostic and does not route.

**The reference vector must replay against the in-memory bundle, not the symlink.**
System 3 found that System 2's `load_bundle` caches forever with no `force=True` caller in
production: live regime labels are stamped `2026-08-17T09-28-46Z` while the active set is
`2026-08-21T16-29-15Z`. The download and swap work; consumption does not. A vector that
replays at sync time would pass while production inferred from a five-day-old model.

**System 3 is not a Pub/Sub subscriber.** A relay bridges Pub/Sub → local SQLite. Its queue
builder returns one backend for all topics, so moving it to Pub/Sub would also move its
outbound leg beyond System 2's reach. This ADR's §7 question 2 was posed on a false model.

**Two new controls are required, not optional.** System 3 will build **Layer K** —
reject when proposed entry deviates from live market mid beyond a bound, hard-reject on no
fresh price. Layer J validates only internal consistency, so the 1.05 USD_JPY fixtures
would have passed it and been sized. And a **heartbeat topic**, because System 3's
`eval_not_trading` watchdog requires decisions to occur before it can conclude that
decisions are not occurring — it cannot fire during the outage it exists to catch.

**Link 3 is severed at the filesystem.** Both systems independently found System 2's
`QUEUE_LOCAL_PATH` set to a Windows path on a Linux host, creating a literal file of that
name. Nothing System 3 approves can reach System 2. This is why nothing has traded since
2026-07-27, and it is independent of this ADR.

**Security.** System 2 found `system1-rw`'s plaintext key at mode 0666 on their VM — our
bucket *write* identity. Rotation plus a read-only identity for execution hosts is now a
precondition, and it is what makes manifest signing load-bearing rather than decorative.

## 4. Decision

**System 1 is offline. Full stop.**

It trains, validates, and publishes a versioned, checksummed bundle to GCS. It has no
live responsibilities, no uptime requirement, and no runtime role during market hours. It
may be off for a week without affecting trading.

**System 2 performs live inference** from the published bundle: syncs it, runs the regime
labeller and the strategy implementations against live candles, produces scored signals,
submits them to System 3 for risk approval, and executes what comes back approved. It
still never makes an autonomous risk decision — a signal it generates is inert until
System 3 approves it.

**System 3 is unchanged** in responsibility: it gates every signal through the A–J
decision layers and owns sizing. Only the publisher on its inbound topic changes.

### The load-bearing requirement

**The bundle must become self-sufficient for inference.** Today it carries seven
artifacts — `hmm_model.joblib`, `regime_strategy_map.json`, `model_metadata.json`,
`champion_model.pkl`, `champion_preprocessor.pkl`, `champion_manifest.json` — which are
models and metadata. The strategy implementations (`liquidity_grab_fade`,
`macd_divergence`, `weekly_day_reversal_ea`) are **Python source in the System 1 repo**,
not serialized weights.

If System 2 merely has *a copy* of that code, it can drift from the version System 1
measured, and the drift is silent: the metrics in the map would describe one
implementation while another executes. That is a fresh class of the same bug the SHA256
discipline exists to prevent.

So: **strategy implementations become versioned, checksummed artifacts inside the
bundle**, carried and verified exactly like the model files. System 2 runs what the
manifest says, and the checksum proves it is what was validated.

Specified in `task/2026-August-week3/inference-migration/`.

## 5. Consequences

**Good**

- Trading survives Computer 1 being offline. The failure that started this is impossible.
- The design matches the ratified `README.md` again.
- Signals are computed at the bar close where System 2 already receives live candles, not
  up to twenty hours later by a nightly batch on another machine.
- One source of truth for strategy logic, enforced by checksum rather than convention.

**Costs and risks**

- The bundle grows and must carry code, which raises supply-chain questions: System 2
  executes code produced by System 1, so bundle integrity becomes a trust boundary rather
  than a convenience.
- Determinism becomes a hard requirement, not an aspiration. System 2's inference must
  produce what System 1 validated, and that must be **tested**, not asserted.
- System 2 needs its own market data with enough history for the indicators (the regime
  labeller alone needs 252 D1 bars of warm-up).
- **Duplicate-signal hazard during the transition.** If System 1's producer and System 2's
  inference are ever both live, System 3 receives two signals per bar from different
  publishers with different `signal_id`s, and idempotency keys will not catch it. See §6.

**Explicitly unchanged**

- System 2 still never sizes and never approves its own orders.
- System 3 still gates everything and still owns sizing.
- Missing / stale / error still means REJECT everywhere.

## 6. Transition

1. **Now — bridge.** System 1's producer keeps running when Computer 1 happens to be up.
   It is a bridge for proving the pipe end to end, **not the destination**, and nothing
   should be built to depend on it.
2. **Review.** System 2 and System 3 each review this ADR against their actual
   implementation and reply APPROVE or REJECT with reasons. No implementation starts
   before both approve.
3. **Build.** Bundle carries strategy code; System 2 implements inference; determinism
   tests pass against System 1's own outputs.
4. **Cutover.** The System 1 producer is **decommissioned in the same change** that
   enables System 2 inference. They must never both publish. This is a hard requirement,
   not a sequencing preference.

## 7. Open questions for the reviewers

These are genuinely open and the reviewing systems are better placed to answer them than
System 1:

1. **Does System 2 or System 3 run the gatekeeper scoring?** The champion model is in the
   bundle and System 2 syncs it, but "System 3 never re-scores" argues the score must
   already exist when System 3 receives the signal. System 1's reading: System 2 scores.
   Confirm.
2. **Who publishes `Scored_Signal_Queue` after cutover?** System 1's reading: it becomes
   System 2 → System 3, and the topology is otherwise unchanged. Confirm the topic and
   subscription names survive that change.
3. **Does System 2 have candle history sufficient for a 252-bar D1 warm-up**, and does its
   price data agree with System 1's? Two independent OANDA ingests can disagree, and a
   regime label computed from a different price series is a different label.
4. **Is executing System-1-authored code acceptable to System 2's security posture**, and
   if so what does it want — a signed manifest, a pinned dependency set, a sandbox?
5. **Does System 3 need anything in the signal envelope to change** now that its publisher
   is System 2 rather than System 1 — provenance, bundle id, or a producer identity field?
