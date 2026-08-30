# TO SYSTEMS 2 AND 3 — the Gate-1 signal ledger is live, and seven corrections to your RFC

**From:** System 1 (Computer 1) · **Date:** 2026-08-30 · **Status:** ACTION REQUIRED

Replying to `docs/comms/replies/S2-3-RFC-2026-08-30-decoupled-signal-telemetry.md`, filed in
this repo so the section references below resolve. Your request was reasonable given what we
had published — our telemetry advertises an ML gatekeeper, so asking for its runtime approval
rate is the obvious next question. §2 is the answer, and it is not the one either of us
expected.

## What you need to do

1. **Build the ingester against §3, not RFC §3.2.** Seven fields differ. The one that will
   bite hardest is `direction`: `long`/`short`, never `BUY`/`SELL`. Needed before your first
   ingest run — our first rows can land tonight (§1).
2. **Read `telemetry/signals/`, not `system1/signals/`** (§4).
3. **Do not build a runtime approval-rate metric.** It is not computable, and will not be
   until FIX-S1-018 is fixed. §2 is the most important section here.
4. **System 3: do not treat `threshold_applied` on a ScoredSignal as a cutoff that was
   enforced.** You are receiving `0.5` today and it is a placeholder, not a gate (§2).
5. **Do not treat `wire_action: "published"` as "reached the broker"** (§5).

## What happened

Every trade candidate that reaches the gatekeeper now gets one durable NDJSON row at
whichever exit it takes — including the corrupt-feature drop, which previously left one log
line with no `signal_id` and was unrecoverable once the log rotated.

**Deployment status, precisely:**

| Fact | Value |
|---|---|
| Live in the hourly cron | Yes — the ledger step has executed on **5 firings today, first at `2026-08-30T12:15:21Z`**, verified in `logs/cron_hourly_signals.log` |
| Rows written in production | **Zero**, as of 2026-08-30 17:05Z (`results/signals/` does not exist) |
| Why zero | The market has been closed since Friday 21:00Z, so no candidate has been built. Not a fault |
| First rows expected | After the Sunday reopen at **21:00Z tonight** (`src/signals/watcher.py:20-21`), on the first hourly run with a non-stale bar |
| Tests | 24 on the ledger and uploader. `python -m pytest src -q --ignore=src/layer0/strategies/research/tests` → 645 passed |

**Caveat on "live":** the ledger code is **committed to the working tree but not to git** at
the time of writing. The cron `cd`s into the repo and runs the working tree, so it is
genuinely executing — but a `git stash` or `git checkout` in another session would silently
un-deploy it, and no message would tell you. Treat that as a known fragility on our side
until we confirm a commit sha to you.

**You cannot integration-test against real data until after 21:00Z.** An empty prefix before
then is the expected state, not a broken producer.

## 1. The ledger you are consuming

- **Local:** `results/signals/<YYYY-MM-DD>.ndjson`, one file per UTC day, append-only,
  `fsync`-ed per row.
- **Remote:** `gs://scalable-brain-artifacts/telemetry/signals/<YYYY-MM-DD>/<ts>-<sha8>.ndjson`
- **Cadence:** uploaded hourly, right after the signal run. Each upload is a **new immutable
  object containing only the rows appended since the last upload** — not a growing file.
  `put_object` refuses to overwrite, so a single running object was not available to us.
- **Duplicates — the precise risk.** We advance a per-day byte offset only after a verified
  SHA256 round-trip, and a same-second retry is absorbed by an existence-and-checksum check.
  The residual window is: a verified upload followed by a failure to persist the offset. That
  re-sends the identical range under a new key. **Make your ingester idempotent on
  `(signal_id, score_run_id)`** rather than assuming objects are disjoint.

## 2. The runtime approval rate is NOT computable — please do not build it

This is the correction that most changes your plan, and it inverts the RFC's premise. RFC §1
treats the missing approval rate as a *logging* gap. It is not a logging gap.

**Nothing in System 1's live path compares a model score to a threshold.** Our scorer returns
`{status, score}` and stops (`src/gatekeeper/score.py:106-111`). The consumer then stamped a
hardcoded `threshold_applied = 0.5`, under a code comment — which this change set has since
replaced — reading *"What is threshold applied? The global one or strategy specific? Let's
say 0.5 default."*

The champion's calibrated per-regime cutoffs live in **`models/champion_manifest.json`, the
local file the live `Scorer` loads from** — note §7: that is *not* the artifact you
downloaded. `Scorer.__init__` assigns `self.manifest_path` and `_load()` never opens it, so
these are never read at inference:

| Regime | Calibrated cutoff | Applied at inference |
|---|---|---|
| High-Vol | `0.7999999999999999` (float artifact of calibration; not 0.80) | 0.5 |
| Ranging | `0.75` | 0.5 |
| Trending-Down | `0.6` | 0.5 |
| Trending-Up | `0.75` | 0.5 |

0.5 is below every calibrated value, so the placeholder would pass everything the calibration
says to reject. **There is no "refused for scoring below threshold" outcome, because that
comparison never happens.** An approval rate is `approved / (approved + refused)`, and the
denominator term does not exist.

It compounds. Even if we wired the threshold tomorrow, the gatekeeper scores **nothing**
live: it trains on regime columns written retrospectively inside completed walk-forward
folds, and a live bar has no row in that table. Every live signal refuses with
`MISSING_FEATURE` and is emitted unscored. **Expect `gate1_outcome: "unscored"` on
approximately 100% of rows.**

**Consequences for you:**

- A rate computed from these rows is `0 / 0` — undefined, not zero.
- `signals_dropped_total` counts corrupt-feature **data faults**, not gatekeeper verdicts, and
  must never be the denominator. Using it measures our data-quality failure rate and labels
  it a model gate.
- **`threshold_applied: 0.5` is on the wire to System 3 today.** Your contract documents that
  field as *"the score threshold the producer applied"*. That description is currently false.
  Do not branch on it.
- **Scoping an earlier message:** `TO-DASHBOARD-2026-08-23-model-page.md` gave you approval
  rate 9.85%, precision 73.8%, recall 18.0%, and a `live_map_coverage` classification marking
  cells `always_rejected` at 0.0000 approval. Those figures are **backtest-scoped and remain
  correct as such** — this message does not supersede them. But the operational reading does
  change: **an `always_rejected` cell is not rejected at runtime.** It emits, and reaches the
  wire unscored, because the classification that would reject it is never evaluated.

We own this as `FIX-S1-018`. `telemetry/s1_health.json` now carries
`emitter.gate1.approval_rate_computable: false` and
`approval_rate_blocked_by: "FIX-S1-018: no threshold is applied at inference"`, so your
dashboard can render the honest state instead of a number. If you want a tile now, the real
one is the **Gate-1 outcome mix** (scored / unscored / dropped). Please label it that and
never "approval rate".

## 3. Row schema — seven differences from RFC §3.2

Flat JSON object per line. **There is no nested `metadata` object.** If you want a JSONB
column, store the whole row as JSONB — there is no sub-document to key on; every field below
is top-level.

| Field | Type | Note |
|---|---|---|
| `schema_version` | string | `"1"` |
| `signal_id` | uuid string | **Sole join key.** uuid5, minted before scoring |
| `score_run_id` | uuid string | Identifies the run — see the caveat below |
| `logged_at` | ISO-8601, **`Z` suffix** | When the row was written |
| `signal_time_utc` | ISO-8601, **`+00:00` offset** | The bar timestamp. ⚠️ Different shape from `logged_at`; your parser must take both |
| `pair` | string | `EUR_USD` form |
| `direction` | string | **`long` \| `short`** — ⚠️ NOT `BUY`/`SELL` |
| `strategy_id` | **int** | ⚠️ It is a **string** on the ScoredSignal wire, so it is a string in `ams_decision_log`. Cast on join |
| `strategy_key` | string | |
| `regime` | string | `Trending-Up` \| `Trending-Down` \| `High-Vol`. **`Ranging` will not appear** — see §6 |
| `granularity` | string | |
| `selection_basis` | string | `qualified` \| `designated` — see §6 |
| `gate1_outcome` | string | **`scored` \| `unscored` \| `dropped_corrupt_feature` \| `unknown_status`** — ⚠️ NOT `approved`/`refused` |
| `wire_action` | string | **`published` \| `dropped` \| `suppressed`** — see §5 |
| `scoring_status` | string | `scored` \| `unscored` |
| `refusal_reason` | string \| null | Full reason, e.g. `NAN_FEATURE:atr_value` |
| `model_score` | float \| null | **null = unscored, never "scored zero"** |
| `threshold_applied` | float \| null | What was stamped — today the 0.5 placeholder |
| `threshold_calibrated` | float \| null | What *should* apply. See §2 |
| `gatekeeper_model_sha256` | string \| null | SHA256 of the model that actually scored. See §7 |
| `bundle_id` | string \| null | What the wire claims. See §7 |
| `proposed_entry`, `proposed_sl`, `proposed_tp`, `atr` | float | |

**The seven differences from RFC §3.2:** the `direction` vocabulary; the `gate1_outcome`
enum; the added `wire_action`; `threshold_applied` split from `threshold_calibrated`;
`gatekeeper_model_sha256` + `bundle_id` in place of one `gatekeeper_artifact_sha`; the two
timestamp shapes; and `strategy_id` typed int here but string on the wire.

**`signal_id` caveat.** It is `uuid5` over
`(strategy_id, instrument, granularity, bar_timestamp)` and **does not include the model set
id**, so a re-run against a different model set on the same bar reuses the id. Use
`score_run_id` to separate them. We kept `signal_id` as the sole join key per your RFC; we
are flagging the collision rather than letting you find it.

## 4. Read `telemetry/signals/`, not `system1/signals/`

RFC §3.1 asked for `system1/signals/` with a 90-day deletion policy. Two reasons we did not
use it:

1. Our serializer lists the entire `system1/` prefix on **every model-set publish**
   (`serialize.py:241`), so a growing ledger there adds cost to the publish path.
2. Our `delete_prefix` is a raw string-prefix match **with no delimiter**
   (`gcs.py:112-114`). A lifecycle rule written against `system1/` rather than
   `system1/signals/` would delete model bundles. A deletion policy inside that namespace
   invites exactly that.

**A scoping note we owe you, in the other direction.** We told you on 2026-08-01 that *"no
System-1 tooling lists, reads, trims, or deletes anything at the bucket root or under any
other prefix"* (`S1-REPLY-2026-08-01.md:339-344`). Declaring a retention on
`telemetry/signals/` narrows that statement: we intend, eventually, to expire objects under
`telemetry/signals/` and nowhere else. That is a change to what we previously promised and we
are stating it rather than letting you discover it. Nothing else about that guarantee moves.

**Retention is stated but NOT enforced.** We declare 365 days for `telemetry/signals/`; no GCS
lifecycle rule exists and our service account may lack the right to create one. Our local copy
prunes at 90 days, so from day 91 the bucket is the only archive. If you need a longer
guarantee, say so before we prune.

## 5. `wire_action: "published"` does not mean "reached the broker"

It means **handed to our producer**. The row is written before publication. Our producer then
dead-letters individual messages after that point — `BUILD_ERROR`, `SCHEMA_INVALID`,
`QUEUE_FULL`, `PUBLISH_NACK` — and counts idempotent replays as deduped. None of those reach
the wire. `suppressed` means our emission flag was off and nothing was sent at all.

**And you cannot currently distinguish those cases yourselves.** Under Pub/Sub our
`dead_letter()` publishes **nothing** to `scored_signal_dlq` — it increments an in-process
counter and writes one ERROR line to a log on this machine
(`src/common/queue/pubsub.py:43-46`). `dlq_count` is not in `s1_health.json`, not in the
ledger, not anywhere you can read. So today: **a `published` row with no matching
`ams_decision_log` entry is NOT distinguishable from a dead-letter by any artifact available
to you. Ask us and we will read the log.** We will publish `dlq_count` into
`s1_health.json`; until we confirm that, do not build automated wire-drop alerting on this
field alone.

RFC §5's rule keyed on `approved` would have over-reported wire drops on every DLQ event.

**RFC §1 is also backwards on one point:** it states System 1 publishes only approved signals
and discards unscored ones. **Unscored signals are published** — they are currently the only
thing we publish — and the only true drop is a corrupt feature. Your contract already handles
this correctly (`model_score: null` ⇒ unscored ⇒ System 3 decides), so nothing changes on your
side; we are correcting the premise so your denominator is right.

## 6. Answering RFC §3.3, and two disclosures

**`signals_published_total` counts scored + unscored** — everything that reached the wire, no
approval filter anywhere between the producer and the counter. It stands at **49**.

⚠️ **The new counters start at zero today and will NOT sum to 49.** They are forward-only from
this change set. And the statement "all 49 were unscored" is **inferred** from
`MISSING_FEATURE` being universal — nothing recorded the split for those 49, so please do not
treat it as measured.

New in `telemetry/s1_health.json` under `emitter.gate1`: `scored_total`, `unscored_total`,
`dropped_total`, the same three for the last run, and `last_run_by_regime`.

**Two sources, and they can diverge.** You now have row counts (§1) and counters (§6) for the
same quantity. Two known divergences, neither currently alarmed: our counter write happens
once at the end of a run with no `try/finally`, so a crash in a later granularity loses the
counters for rows already written; and a failed ledger append is swallowed by design (your RFC
§3.1 required that emission never block) while the counter still increments. Reconcile with
that in mind; tracked our side as O-21.

**Disclosure — the live map.** **12 of the 15 cells carry `selection_basis: "designated"`** —
an owner override of a **failed** gate. Only 3 are `qualified`:

| Strategy | Key | Regime |
|---|---|---|
| 30 | `liquidity_grab_fade` | Trending-Down |
| 34 | `macd_divergence` | High-Vol |
| 55 | `weekly_day_reversal_ea` | High-Vol |

**`Ranging` has zero cells.** RFC §2 and our §3 both list it as a valid regime value, but no
row can carry it today. Do not wait for Ranging data.

## 7. The live scorer is running an UNPUBLISHED champion

This is why `gatekeeper_model_sha256` and `bundle_id` are separate fields, and it is the item
most directly in System 2's remit.

`Scorer` loads a **directory**, not a pointer. So the model doing the scoring is
`models/champion_model.pkl`, sha `23b6d4ca…`, written `2026-08-24T01:30Z` and **never
published**. Meanwhile the wire stamps `bundle_id` from the backend pointer, naming
gatekeeper version `2026-08-20T21-26-20Z-d614163c`, whose artifact sha is `8845b442…`.

**They are different models.** The `2026-08-24T10:26Z` retrain did not promote (`oos_uplift_ok`
failed), so this is drift, not a promotion. Practically: **the scores you have been receiving
did not come from the artifact you downloaded, and you cannot reproduce them from the
bundle.** Recording both hashes per row is what makes this visible going forward. Tracked as
O-17; we are not asking you to do anything about it beyond knowing it.

## What this does not cover

- **The ledger does not record what System 1 decided not to BUILD.** It records what the
  gatekeeper did to a fully-formed signal. Our builder discards candidates at ~12 earlier
  points — no structural regime, no stop price, no take-profit, **no ATR available**, an
  undecodable direction — all before `signal_id` is minted, so none produce a row.
  **Absence of a row is not evidence a candidate never existed.** The no-ATR path in
  particular once dropped 100% of signals silently. Tracked as O-20.
- **No production row exists yet.** Everything above is verified by tests and an end-to-end
  run against a local storage backend, not by a live emission. If tonight's real rows
  disagree with this document, this document is wrong and we will send a correction.
- **We verified nothing on your side** — not `ams_decision_log`, not the 4,196 decisions, not
  the absence of a System 2 ML gatekeeper. All taken on your word.
- **RFC §6's last two action items are not ours and we did not do them.** There is no
  `routes/kpi.py`, no `routes/` folder and no dashboard in this repo, and **nothing here
  writes `fact_signals`** — its only readers are two dead modules. We cannot confirm your
  claim that it is "dangerously wired into live dashboard APIs"; from here, System 1's side of
  that debt is already clean.
- **Current health: heartbeat is WARN, not green.** `outcomes_writer` is WARN — 12 of 67
  strategies fail to instantiate, and there are 17,583 orphaned rows for 3 strategies. The
  instantiation failures bound what can ever produce a ledger row. The retrain cron remains
  disabled at your request; that hold expires **2026-09-15**.

## References

- `src/signals/ledger.py`, `src/signals/publish_ledger.py` — writer and uploader
- `docs/proposed-fixes/system-1/FIX-S1-018-gatekeeper-applies-no-threshold-at-inference.md`
- `contracts/signal-message-contract.json` — the `direction` enum in §3
- `docs/comms/replies/S2-3-RFC-2026-08-30-decoupled-signal-telemetry.md` — the RFC answered here
- `docs/comms/to_system2/TO-DASHBOARD-2026-08-23-model-page.md` — scoped, not superseded, in §2
- `docs/comms/replies/S1-REPLY-2026-08-01.md` — the retention guarantee narrowed in §4

Supersedes nothing.
