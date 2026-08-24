# Agent prompt — System 1 signal-path hardening

Paste this whole file as the task in a fresh session, in
`/home/emmanuel/Documents/Scalable_Brain/scalable-brain`.

Context you must read first: `CLAUDE.md`, and commits `6c3ac48` and `21174d2`.

System 1 emits live signals again as of 2026-08-24. Three faults were fixed (heartbeat
topic name + IAM, an ATR call-signature bug that discarded 100% of signals, and a scorer
refusal that was read as a rejection). **Do not revisit those — they are fixed, tested and
pushed.** The four tasks below are what remains. They are independent; do them in order.

Ground rules for all four:

- Run `python -m pytest src -q --ignore=src/layer0/strategies/research/tests` before and
  after. Baseline today is **17 failed, 582 passed**. Do not increase the failure count.
- `black src/` before committing.
- The live path is `src/signals/run.py` → `build.py` → `src/queue_producer/producer.py`.
  It runs hourly from cron off the working tree. A break here stops trading.
- Never touch champion promotion. The orchestrator is the only governed writer.

---

## TASK 1 — deterministic `signal_id`, then commit the watermark after publish

**Why.** `src/signals/watcher.py:get_new_closed_bars(commit=True)` saves the watermark
*before* `build_signals` runs, so a bar consumed during a failed run is never reprocessed
and its signal is lost permanently. The obvious fix — commit after publishing — is
currently unsafe, because `build.py` assigns `signal_id = str(uuid.uuid4())` per build.
A retried bar would arrive at System 3 under a new id it cannot dedupe, and a duplicate
order is worse than a missed one.

So the ordering matters: make the id deterministic **first**, then move the commit.

**1a.** In `src/signals/build.py`, replace the uuid4 with a deterministic id derived from
`(strategy_id, instrument, granularity, decision bar timestamp)` — e.g. a UUIDv5 over a
canonical string, so it stays a valid UUID. The same bar rebuilt must produce a byte-identical
id; two different bars must not collide. The contract types `signal_id` as
`string, minLength: 1` and describes it as the dedup key, so this needs no schema change.

**1b.** Then change `run.py` so the watermark advances only after `publish_signals`
reports success. Bars whose signals failed to publish must remain unconsumed so the next
run retries them. Preserve the existing `commit=False` dry-run behaviour — a preview must
still never mutate state.

**Tests:** same bar twice → identical `signal_id`; different bars → different ids; a
publish failure leaves the watermark unmoved and the next run re-sees those bars; a
dry-run still consumes nothing.

## TASK 2 — retrain the gatekeeper on features that exist at inference time

**Why.** This is the substantial one. The champion cannot score a live signal at all, so
every signal goes out unscored and System 3's gate chain is the only safety net.

`src/gatekeeper/train.py:_load_training_frame` reads `atr_value`, `adx_value`,
`prob_causal_*` and `regime_causal` from `fact_market_regime_v2` filtered
`WHERE regime_causal IS NOT NULL`, and `entry_signal_type` from `fact_trade_outcomes`.
Every one of those is written **retrospectively** — `regime_causal` only exists for bars
inside a completed walk-forward fold, and `entry_signal_type` is a per-trade field with no
live equivalent. Confirm this yourself before changing anything: query the newest
non-null `regime_causal` per (symbol, granularity) and compare it to the newest price bar.

**What to do.** Train a variant whose entire feature set is computable from data available
the moment a bar closes. The obvious basis is the **structural regime label**
(`src/regime/structural.py`, already what routes live signals) plus ATR and ADX computed
on the bar from `src/layer0/data_access/indicators.py`. Use that one indicator module —
a second implementation is train/serve skew through the back door.

Hard requirements:

- Preserve the walk-forward discipline in `src/validation/walk_forward.py`: fold-fit
  models, forward-only inference, OOS-only gate metrics. No look-ahead.
- The live producer must be able to build the **exact** feature row the preprocessor
  expects. Add a single shared function that builds it, and call that same function from
  both training and `src/signals/run.py`. One implementation, no drift.
- Add a test that takes a real live signal dict from `build_signals` and asserts the
  scorer returns `status == "scored"` — that is the acceptance criterion for this task.
- **Do not promote it.** Report OOS uplift and leave promotion to the owner and the
  orchestrator. Write findings to `task/backlog/`.

## TASK 3 — `src/analytics/publish_regime.py` is broken at import

It does `from src.regime_aware.families import STRATEGY_FAMILIES, REGIME_MASKS`, and
`src/regime_aware/` was deleted with the failed R3 experiment. The module cannot even be
imported, and nothing catches it because it has no test. The label maths now lives in
`src/regime/structural.py`. Repair it or delete it — decide which, state why, and add a
test either way.

## TASK 4 — the stale test suite

17 failures and 2 collection errors, all stale assertions rather than broken runtime.
Fix them to the *current* behaviour; do not revert behaviour to satisfy an old test.

- `src/layer0/strategies/research/tests/test_nnfx_backtrader_fixture.py` and
  `test_kpl_donchian_breakout_fixture.py` import strategy modules that do not exist, and
  abort collection for the whole run. That is why the `--ignore` above is needed. Fix or
  remove them so plain `pytest src` works.
- `src/vetting/tests/test_gates.py` still asserts the **60-month** OOS gate. It was
  lowered to **12** by owner decision on 2026-08-21. The code is right; the tests are old.
- `src/layer0/strategies/tests/test_wave1_guards.py` pins SHA256s of files that have since
  changed legitimately. Re-pin to current hashes only after confirming each change was
  intentional.
- Remaining failures in `attribution`, `gatekeeper/test_cell_degeneracy.py`,
  `common/storage`. Diagnose individually.

Goal: `python -m pytest src -q` green, with no `--ignore`.
