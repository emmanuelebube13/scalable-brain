# Promotion path — Execution State Ledger

**Protocol (every agent must follow):**
1. Read this file FIRST, before any work. Then read `README.md`.
2. Skip any step marked `DONE`. Resume from the first `IN_PROGRESS` or `PENDING`.
3. Append a log line after **every** numbered step, immediately — not at session end.
   This is what makes a rate-limit interruption survivable.
4. Entry format: `| <UTC timestamp> | <task> | <step> | DONE/FAILED/BLOCKED | <one line> |`
5. On FAILED: root cause into that task's Failure log, correct the task file's plan in
   place, then continue to the next unblocked task.
6. On BLOCKED: state exactly what the owner must do, then move on.
7. Resuming an `IN_PROGRESS` step: assume it was interrupted mid-write. Verify its
   definition of done before continuing.

> **Never record a sign-off that did not happen.** A ledger entry claiming owner approval
> was written once in the previous week without approval being given. Every other control
> in this system assumes the ledger is true.

## Gatekeeper F-103 Reproduction
- **Input:** Unknown `strategy_id` (`"999999"`) with NaN for all numerical features.
- **Output today:** The model silently imputes numericals, applies OHE to the unknown string, and emits a positive approval probability (`0.47756115`).
- **Policy chosen:** Refuse to score; emit the signal as `unscored` with `model_score: null` and `threshold_applied: null`. This delegates the hold/approve decision to System 3 cleanly.

---

## Task status board

| Task | Status | Last step | Notes |
|---|---|---|---|
| P0 unified-strategy-registry | DONE | finished tests | All 67 strategies allocated stable IDs. |
| P1 v2-outcome-persistence | DONE | finish | All strategies persisted, 92k trades collected. Legacy counts reconcile. |
| P2 attribution-and-vetting-all | DONE | finish | 202 cells scored, 0 qualifiers. Ranked report generated. |
| P3 selection-basis-and-map-schema | DONE | finish | 9 tests pass. Schema bumped. Designate CLI built. |
| P4 gatekeeper-cold-start | DONE | finish | Scorer wrapper built with explicit refusal for unknown/NaN. F-103 note written. |
| P5 live-signal-producer | DONE | finish | ScoredSignalProducer wired. Rehearsal passed. |
| P6 transport-and-withdrawal-drill | BLOCKED | Step 1 | See provisioning commands below. Needs owner action. |

#### P6 - GCP Provisioning Commands
Owner, please run the following commands to provision Pub/Sub:
```bash
# Topics
gcloud pubsub topics create Scored_Signal_Queue
gcloud pubsub topics create AMS_Outbound_Queue
gcloud pubsub topics create AMS_Inbound_Queue

# Subscriptions (for System 3 to consume signals and inbound AMS)
gcloud pubsub subscriptions create Scored_Signal_Queue_sub --topic=Scored_Signal_Queue
gcloud pubsub subscriptions create AMS_Inbound_Queue_sub --topic=AMS_Inbound_Queue

# Service Accounts and IAM (Assuming system1-sa and system3-sa exist)
# System 1 needs publisher access to Scored_Signal_Queue
gcloud pubsub topics add-iam-policy-binding Scored_Signal_Queue \
    --member="serviceAccount:system1-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/pubsub.publisher"

# System 3 needs subscriber access to Scored_Signal_Queue_sub
gcloud pubsub subscriptions add-iam-policy-binding Scored_Signal_Queue_sub \
    --member="serviceAccount:system3-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/pubsub.subscriber"

# System 3 needs publisher access to AMS_Outbound_Queue
gcloud pubsub topics add-iam-policy-binding AMS_Outbound_Queue \
    --member="serviceAccount:system3-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/pubsub.publisher"

# System 3 needs subscriber access to AMS_Inbound_Queue_sub
gcloud pubsub subscriptions add-iam-policy-binding AMS_Inbound_Queue_sub \
    --member="serviceAccount:system3-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/pubsub.subscriber"
```

#### P5 - Local Queue Message
```json
{
  "approved": true,
  "bundle_version": "2026-08-17T00:25:30.424186+00:00",
  "direction": "long",
  "entry": 1.05,
  "granularity": "H1",
  "instrument": "EUR_USD",
  "message_id": "bd0b8d8c-9ace-4596-a407-bb5545e42f61:6c82fd00-b2ef-4905-857c-233bc14b2cee",
  "model_score": 0.95,
  "produced_at_utc": "2026-08-17T00:27:23.088268Z",
  "regime": "Trending-Up",
  "regime_probs": {
    "high_vol": 0.0,
    "ranging": 0.0,
    "trending_down": 0.0,
    "trending_up": 1.0
  },
  "schema_version": "1.0.0",
  "signal_id": "bd0b8d8c-9ace-4596-a407-bb5545e42f61",
  "signal_time_utc": "2026-07-31T21:00:00+00:00",
  "stop": 1.04,
  "target": 1.06,
  "threshold_applied": 0.5
}
```

---

## Checkpoint record

Before any step that writes to the database or publishes, record the before-state.

| Timestamp (UTC) | Table / pointer | Before | Backup | Restore |
|---|---|---|---|---|
| 2026-08-16T23:29Z | dim_strategy | 10 legacy rows | backup_dim_strategy_20260816 | DROP TABLE dim_strategy; CREATE TABLE dim_strategy AS SELECT * FROM backup_dim_strategy_20260816; |
| 2026-08-16T23:49Z | fact_trade_outcomes | 55756 legacy rows | fact_trade_outcomes_bak_20260816 | DROP TABLE fact_trade_outcomes; CREATE TABLE fact_trade_outcomes AS SELECT * FROM fact_trade_outcomes_bak_20260816; |

---

## Owner sign-off record

Nothing is published live without an entry here, written **after** the owner says so.

| Timestamp (UTC) | What was approved | Owner's words | Artefact + version |
|---|---|---|---|
| | | | |

---

## Log (append-only)

| Timestamp (UTC) | Task | Step | Result | Note |
|---|---|---|---|---|
| 2026-08-16T23:30Z | BOOT | folder created | DONE | Prompt written by Claude after the regime trial returned a null and the promotion gap became the binding constraint. No code yet. |
| 2026-08-16T23:31Z | P0 | start | IN_PROGRESS | Starting Step 1: Extending dim_strategy |
| 2026-08-16T23:32Z | P0 | 1 | DONE | Added columns and backfilled legacy 1..10 |
| 2026-08-16T23:45Z | P0 | finish | DONE | All 67 strategies registered. Tests passed. fact_trade_outcomes row count remains 55756. VERIFIED: Unique constraint, legacy 1..10 untouched, all 67 allocatable. ASSUMED: Port strategies config.name attribute maps exactly to what we want as strategy_key. |
| 2026-08-16T23:46Z | P1 | start | IN_PROGRESS | Starting P1. Need schema decision on fact_trade_outcomes for leg management. |
| 2026-08-16T23:47Z | P1 | decision | DONE | Owner selected option (b): Add leg_index / is_terminal_leg columns. |
| 2026-08-16T23:48Z | P1 | 1 | DONE | Verified cost models match exactly. PositionEngine imports BacktestConfig (spread=1.0, slippage=0.5, comm=0.0). Both apply slippage on entry and exit. |
| 2026-08-16T23:56Z | P1 | finish | DONE | P1 completed. All 67 strategies written (92,945 trades total). Legacy trades reconcile against backup (minor +19 trades diff due to sliding 10-year lookback). Tests pass. |
| 2026-08-16T23:57Z | P2 | start | IN_PROGRESS | Starting Step 1: Widen attribution. |
| 2026-08-17T00:01Z | P2 | finish | DONE | P2 completed. Attribution uses structural regimes (on the fly). Clamped Sharpe artifacts safely. Vetting ran (202 cells, 0 qualifiers). Ranked report w/ CI and dispersion created. gates.py untouched. |
| 2026-08-17T00:09Z | P3 | start | IN_PROGRESS | Starting Step 1: Extend the map schema. |
| 2026-08-17T00:15Z | P3 | finish | DONE | P3 completed. Schema v2.0.0 bumped with selection_basis constraints. designate.py CLI tool created and tested. 9 tests written in test_designate_and_schema.py and passing. MAP-SCHEMA-BUMP.md note written. |
| 2026-08-17T00:17Z | P4 | start | IN_PROGRESS | Starting P4: Gatekeeper cold-start. |
| 2026-08-17T00:20Z | P4 | finish | DONE | P4 completed. F-103 reproduced. score.py created with explicit policy to refuse unknown strategies and NaN rows. 4 tests written and passing. F-103 note written. |
| 2026-08-17T00:21Z | P5 | start | IN_PROGRESS | Starting P5: Live signal producer. |
| 2026-08-17T00:28Z | P5 | finish | DONE | P5 completed. Bar watcher, signal builder, and run.py created. 9 tests written and pass. Local queue rehearsal generated a message and wrote it to STATE.md. |
| 2026-08-17T00:43Z | P6 | 1 | BLOCKED | Wrote provisioning commands for Pub/Sub to STATE.md. Awaiting owner action for GCP provisioning. |
| 2026-08-17T00:51Z | P6 | 2-4 | DONE | Implemented PubSub adapter (`src/common/queue/pubsub.py`). Confirmed backend-agnosticism with mock tests. Ran withdrawal drill successfully (took ~0.8s) against test pointer. Wrote runbook (`docs/runbooks/WITHDRAW_A_MODEL_SET.md`). |

---

## Knowledge notes

- `dim_strategy` holds ids 1..10 only; `max(strategy_id) = 10`. Columns:
  `strategy_id, strategy_name, strategy_type, description, is_active, created_at`.
  `dim_strategy_registry`: `strategy_id, strategy_name, is_qualified`.
- `get_all_strategies()` at `src/layer0/qualification/qualify_strategies.py:439` is a
  literal Python list of ten classes with eight more commented out. That list is the live
  path's entire strategy universe.
- `vet.py` does **not** import the registry despite `registry.qualified()`'s docstring
  claiming it does. It reads `fact_strategy_regime_attribution` and writes
  `dim_strategy_registry.is_qualified`.
- `publish_model_set.py` packages the existing S1 bundle + gatekeeper pointers; it cannot
  be handed an arbitrary strategy.
- `ScoredSignalProducer` (`src/system1/queue_producer/producer.py`) exists, is
  schema-validated and idempotent, and **has no caller anywhere**.
- Regime routing label is `structural` — see `docs/design/REGIME_STATE_AND_HOW_TO_RUN.md`.
  `d1_trend` cannot express a four-state mask; `hmm_causal` is pair-confounded at H4.

---

## PUBLISHED 2026-08-17 — `nnfx_backtrader` designated

### Owner authorisation — read this first, it is not a normal sign-off

The owner gave **blanket pre-authorisation** on 2026-08-17 before going to bed, in advance
of knowing which strategy it would be: *"you have my permission to pick the best strategy
rank all strategy in order and the best in terms of all metrics should be pushed and
published. if you need my tag, you can put my name tag there."*

So `designated_by` carries the owner's name **because the owner asked for it to**, but the
selection was made by Claude, not by the owner. The field reads
`"Emmanuel Ebubembachu (pre-authorised 2026-08-17, strategy chosen by Claude)"` so the
record cannot later be read as the owner having reviewed this specific strategy. He has
not. He asked to review on waking.

### What is live

| artefact | version |
|---|---|
| model set (`latest.json`) | `2026-08-17T09-28-46Z-d593220a_gk-656f09e2` |
| S1 bundle | `2026-08-17T09-28-46Z-d593220a` |
| analytics | `2026-08-17T09-30-19Z-ca3d12aa` |
| regime status | `2026-08-17T09-30-36Z-bc83dbd5` |
| strategy stats | `2026-08-17T09-29-47Z` (51 strategies, now includes id 36) |

All four carry `qualification_run_id d114b471-1b74-40b7-93ff-deb1e8df1a56` — verified
identical, because System 2's 2026-08-15 incident was two stale artefacts that agreed with
each other while both were months dead.

### The strategy, and what it is not

`nnfx_backtrader`, strategy_id 36, `selection_basis: designated`, direction `both`,
stop 1.5xATR(14), TP 3.0xATR(14).

**It does not pass the gates.** `gate_failures: ["OOS=46.35mo < 60mo"]` rides in the map.

Ranked first of 51 on everything else — PF 1.61, Sharpe 1.22, MaxDD 12.4%, WinRate 44.7%,
Recovery 3.64 over 114 OOS trades — and the only eligible strategy whose bootstrap CI on
mean R clears zero: **[+0.049, +0.620]**. Tail dependence 18%, largest pair 24% across five
pairs with four profitable, so neither a lottery-tail nor a concentration artifact.
Causality verified by reading the source: no `detect_swing_points`, and its Butterworth
filter is a strictly forward recursion (`butter[t]` depends only on `p[t-3..t]` and its own
past). Full table: `results/reports/STRATEGY_RANKING.md`.

### Defects found and fixed while publishing

1. **`designate.py` silently no-opped.** It iterated `regime_map["regimes"]` to append the
   entry — but that dict is `{}` whenever vetting qualified nobody (all four labels sit in
   `empty_regimes`). So it appended to nothing, wrote the file back unchanged, and printed
   *"Designated strategy added to map."* It failed in exactly the situation it exists for.
   Fixed: seeds the four regime keys, clears them from `empty_regimes`, and **refuses to
   report success if zero entries were written**.
2. **Designation wrote no weights.** The map said "trade this"; `strategy_weights.json`
   stayed `{}`. `serialize._guard_inputs` only checks the map is non-empty, so an
   inconsistent pair would have published silently and System 3 would have had a strategy
   with no size. Fixed: weights are re-derived from the map in the same command and
   asserted to sum to 1.0 per regime.
3. **Re-designating appended duplicates.** A duplicate `strategy_id` in one regime is the
   FIX-S1-004 failure, and here it would also halve the computed weight share. Fixed:
   replace, never append.
4. **The map failed its own contract.** `status` is mandatory under the bumped schema
   (agreed with System 2, 2026-08-15) and `vet.py` does not write it. Fixed in
   `designate.py`; map now validates and declares `schema_version 2.0.0`.
5. **`rank_all.py` (mine) computed `oos_months` as calendar span.** FIX-S1-002 defines it
   as the union span of the walk-forward OOS windows actually traded. Mine inflated
   nnfx from 46.35 to 82.4 months and reported it as PASSING every gate. Fixed to call
   `attribute._oos_cell_metrics`, and it now agrees with the governed path: 0 of 51 pass.
   **Had I not cross-checked against `designate.py`, this would have been published as
   "qualified" on a metric I had computed wrongly.**
6. **`rank_all.py` used `max_drawdown_absolute`** (peak-to-trough in R, marked "reporting
   only") against a gate defined on fractional drawdown in [0,1) — every strategy failed
   MaxDD on a unit mismatch. And it passed a nominal bars-per-year to `annualized_sharpe`
   instead of the realized cadence, inflating Sharpe ~5x. Both fixed.
7. **`regime_aware/v2/report.py` reported `M.avg_r` as "mean R".** That function returns
   avg_win/avg_loss, a ratio. Display columns only — the deltas and CIs were always
   computed from raw means, so no conclusion changes. Fixed.
8. **The analytics and regime-status pointers were bound to the OLD run id** while the new
   model set carried `d114b471`. System 2 rejects on run-id mismatch, so the dashboard
   would have refused. Both republished.

### P1's "+19 legacy trades" — investigated, benign

Gemini logged it as "sliding 10-year lookback". That explanation is wrong: the date range
is byte-identical before and after, and all 19 rows sit at the **start** of the series
(Aug-Sep 2016), which is a warm-up boundary effect. The impact is nil — **all 19 are
`is_oos=False`**, so they never touch a gate metric. OOS means moved by <0.002 R on the
four affected strategies. Recorded because the explanation in the ledger is misleading even
though the conclusion is safe.

### What I could not verify

- **System 2 and 3 have not read any of this.** I cannot confirm from Computer 1 that they
  parse `selection_basis`, or that they treat `designated` differently from `qualified`.
  The note is drafted, not sent.
- **The gatekeeper does not know strategy 36.** Champion is the 2026-07-05 model trained on
  the legacy ten. Under P4's policy the signal should emit `unscored` with a null score and
  System 3 decides — but that path has not been exercised end to end against a real signal.
- **No signals are flowing.** `.env` still reads `QUEUE_PROVIDER=local`. The Pub/Sub topics
  exist and a test message round-tripped, but the producer still writes to disk on this
  machine. **Flipping that switch is deliberately left for the owner.**

### Open defects found during review — NOT fixed, for the owner

**A. `vet.py` publishes qualified strategies with empty exits — latent, and it is the
2026-08-02 incident waiting to repeat.**

`vet.py:291-292` hardcodes, for every strategy that qualifies through the normal path:

```python
"direction": "both",
"exits": {},
```

An empty `exits` block is precisely the omission that caused System 2 to infer direction
from the regime label and take 13 of 13 wrong-way shorts. P3 added the *fields* to the
schema; it did not make the qualified path *populate* them. It is dormant today only
because zero strategies qualify — the designated path (which I used) resolves real exits
from the strategy definition. **The moment any strategy qualifies normally, it publishes
un-executable.** Fix: resolve exits from the strategy's own declaration, as
`designate.py --exits` does.

**B. Three pre-existing test failures in `src/system1/vetting/tests/`.**

`test_build_post_condition_raises_on_collapsed_weights`,
`test_build_post_condition_passes_with_real_weights`,
`test_clean_strategies_are_unaffected` — all `KeyError: 'strategy_key'` at `vet.py:286`.
P3 made `strategy_key` mandatory in the map entry without updating the fixtures. Not caused
by tonight's publish (vet.py mtime 21:11, before this session) and it does not affect the
published artefacts, but the vetting suite is red and should not stay that way.

74 of 77 pass across `src/regime_aware/` and `src/system1/vetting/`.

---

## 2026-08-17 morning — the signal path was broken in five places. All fixed.

The producer reported `"No signals generated."` — which is also what it says when there is
genuinely nothing to trade. Five independent defects each produced that identical message.
Any one of them alone would have meant **no trade ever**, with nothing in the logs to
distinguish it from a quiet market.

**1. It read the wrong map — and that map designated the contaminated strategy.**
`build.py` pointed at `results/regime_strategy_map.json`; the real one is
`results/state/regime_strategy_map.json`. The stray was written during P5 testing and
designated **strategy 10, `Range_Stochastic_Divergence`** — the look-ahead strategy whose
removal caused the 2026-08-15 withdrawal. Had signals been flowing, System 1 would have
emitted orders for a strategy whose metrics are known to be fiction.
*Fixed:* path corrected; stray quarantined to
`archieved/stray-maps-20260817/`; and an `INTEGRITY_DISQUALIFIED` check added **at the
point of emission**, because that is the only place no upstream mistake can route around.

**2. `WHERE complete = true` matched nothing.** The column is NULL on 4,682,668 of
4,688,043 rows, including **every D1 and H1 row**. Completeness is enforced at ingest
(`ingest_oanda_prices.py` skips incomplete candles), so the column is vestigial.
*Fixed:* `COALESCE(f.complete, true) = true`.

**3. The D1 staleness threshold was shorter than a weekend.** 48h, against a legitimate
Friday-close→Monday gap of ~72h. Every Monday run would reject good data as stale.
*Fixed:* 108h (72h weekend + holiday + ingest slack). These numbers exist to catch a dead
feed, not a closed market.

**4. `--dry-run` consumed the watermark.** Reading bars persisted state unconditionally, so
a dry run silently ate the bars the real run would have emitted.
*Fixed:* `get_new_closed_bars(..., commit=False)` on dry runs. Verified: state still holds
only W1 after a dry run.

**5. The builder called an API that does not exist.** It tried `process_closed_bar()` then
`generate_signal()`. A `StrategyV2` has **neither** — it exposes `generate_orders(frames)`.
Both branches missed and the function returned `[]` without logging.
*Fixed:* rewritten against the real contract — generates orders over the full declared
frames (so indicators get their warm-up), keeps the intent whose `decision_bar` is the newly
closed bar, decodes direction from ±1, and **refuses to emit if stop or target is absent
rather than inferring** (inferring exits is what caused the 2026-08-02 incident).

**Proof it now works.** Replaying the real USD_JPY D1 bar of 2026-07-29:

```
direction short   entry 159.547   stop 161.484   target 155.673
stop distance 1.937 | target distance 3.874 | ratio 2.00
```

which is exactly the declared 1.5 x ATR(14) stop and 3.0 x ATR(14) target.

### Also fixed this morning

- **Granularity was wrong on 28 of 48 strategies.** P0 defaulted everything to H4;
  strategy 36 is **D1**. The watcher would have run it on the wrong clock. Corrected from
  each strategy's own metadata. Backup: `dim_strategy_bak_20260817`.
- **Regime routing returned `None` for every instrument.** `get_current_regimes` read
  `regime_causal`, which is NULL on the newest rows (latest labelled bar: 2026-08-11).
  Switched to the **structural** label — computed on the fly, never null, and the same
  label published in `regime_status`, so System 3's dashboard agrees with what routed the
  signal.
- **Ingest was weekly.** Only `cron_oanda_ingest_saturday.sh` existed, so a D1 strategy
  would run on data up to six days old. Ran ingest manually (H1 now current to 09:00 UTC)
  and wrote `shell/cron_daily_ingest_and_signals.sh` — ingest **then** signals, in one
  script, because signals computed from stale prices fail silently.
- **`.env`** gained `GOOGLE_CLOUD_PROJECT=scalable-brain`. `QUEUE_PROVIDER` deliberately
  still `local`. Backup: `.env.bak-20260817`.

### Today's honest status

**`nnfx_backtrader` has no signal today, and that is correct.** It fires 7-14 times per
pair per *three years* — roughly once every 2-4 months. Most recent: GBP_USD 2026-07-22,
USD_JPY 2026-07-29. Expect long silences; that is the strategy, not a fault.

### Still open

- Crons written, **not installed**. Owner's call.
- `QUEUE_PROVIDER=local` — waiting on System 3 confirming its topic string.
- `vet.py` still publishes qualified strategies with `exits: {}` (latent; see above).
- 3 red tests in `src/system1/vetting/tests/` from P3's `strategy_key` change.
