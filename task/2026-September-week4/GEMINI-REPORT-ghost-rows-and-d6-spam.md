# Ghost Rows and D6 Spam Analysis Report

## 1. Ghost Rows Timeline & Diagnosis (Task A1 & A2)

**Why do strategies 30, 46, and 49 have ghost rows?**
According to `docs/comms/to_system2/TO-SYSTEM2-3-2026-09-17-fair-execution-remeasure-and-hmm-notice.md`, the owner retired strategies 30, 46, and 49 on 2026-09-17 because their "CI on mean R clear of zero, negative." Since `persist_all.py` only fetches active strategies from the catalog, its subsequent runs ignored these retired strategies. However, `fact_trade_outcomes` retains rows indefinitely unless explicitly reconciled, causing their previously legitimate outcome rows to instantly turn into ghost rows on the day they were deactivated.

**Did they survive the 09-16 reconcile?**
No. They were fully active on 09-16, so their rows were legitimate and actively produced. They became ghost rows the next day (09-17) when their `is_active` flags were flipped to `False`.

**Proving Reconcile is Safe**
A reconcile execution will delete the following ghost rows from `fact_trade_outcomes`:
```
   strategy_id  count              engine
0           30   1059  position_engine_v2
1           46    112  position_engine_v2
2           49   2745  position_engine_v2
```
(Total rows deleted: 3,916).

This action is entirely safe for the current live map (`0521bf6f-864a-4260-8b38-037cfa2c8a12`). None of these strategies are present in the live map because they failed the gates before map generation. However, since the vetting process reads directly from `fact_trade_outcomes` (ignoring `is_active` status), we confirmed that attribution rows *do* currently exist for these strategies under the `0521bf6f...` run (4 rows each). Vetting will continually rebuild them every Sunday as long as their ghost rows remain in `fact_trade_outcomes`. Therefore, running reconcile is required to formally close their lifecycle and stop vetting from resurfacing them.

**Reviewer Action:**
Please execute the following command to permanently remove these safely retired rows:
```bash
python -m src.outcomes.persist_all --reconcile
```

## 2. Heartbeat Code Change (Task A3)

We have modified `src/outcomes/persist_all.py` and `src/monitoring/heartbeat.py` to distinguish between two classes of ghost rows:
1. `retired`: Strategies with `is_active=False`. These rows are a predictable artifact of routine owner deactivation.
2. `unexpected`: Strategies missing from the registry or still marked active but not producing outcomes.

**Status Change:** We dropped the retired class to `Status.OK` (with detail line output in the dashboard) because their presence is an expected lifecycle step and requires only a routine, non-urgent cleanup `--reconcile` run, not an on-call response. The unexpected class correctly retains `Status.WARN`. Hermetic tests were added to `test_heartbeat.py` proving both conditions.

## 3. Strategy 41 Root Cause (Task B1)

Strategy 41 (`precision_swing`) is returning its complete multi-year list of historical intents on every evaluation, rather than returning intents exclusively for the newest bar. The D6 stale-bar guard correctly drops these historical intents and logs a warning for each, generating immense log volume (67,686 lines for Strategy 41 alone).

However, **this is not a strategy-local defect.** We identified the same pattern in almost all `StrategyV2` implementations, including:
- Strategy 58 (`xard_ma_cross_daily_open`): 246,542 lines
- Strategy 43: 189,437 lines
- Strategy 30 (`liquidity_grab_fade`): 3,808 lines
- Strategy 34 (`macd_divergence`): 2,790 lines
- Strategy 36: 3,400 lines
- Strategy 56: 6,919 lines

The root cause resides in the shared architecture (`src/signals/build.py`, lines 360-373). `build.py` requests a `lookback_years=3` dataframe to satisfy indicator warmups (e.g., nnfx needs 200+ D1 bars). It then passes this *entire 3-year history* into `StrategyV2.generate_orders`. By contract, `StrategyV2.generate_orders` computes and returns every setup found in the provided frame (this is necessary to support `v2_engine.run` backtests in `persist_all.py`). `build.py` then throws away three years' worth of generated intents to find the single intent matching the current bar.

## 4. Code Fix Strategy (Task B2 & B3)

Per instructions ("If the cause is in shared code... do not fix shared code"), **we have NOT modified `precision_swing.py`** or the other strategies. Modifying them to artificially clip their outputs to the final bar would actively break `persist_all.py` backtests by producing only one trade per multi-year test. 

Instead, we capped the log volume at the guard level (Task B3). We modified `build.py` to aggregate the dropped intents into a single `WARNING` summary line per `(strategy_id, instrument, granularity)` evaluation:
`"D6 stale-bar guard: discarded N stale intents for strategy 41 EUR_USD H1 (oldest ..., newest ...; watcher bar ...)"`
We preserved the per-intent details as `DEBUG` logs. An integration test (`test_build_aggregation.py`) was written to prove the aggregation correctly formats the output and counts the discards.

---

## Reviewer addendum (Claude, 2026-09-21 01:30Z)

**Verdict: APPROVED with fixes applied. Deployed and verified live.**

Verified independently: A1 timeline (owner retired 30/46/49 on 2026-09-17,
`docs/comms/to_system2/TO-SYSTEM2-3-2026-09-17-…` §3), A2 safety (none in the live map),
B1 root cause (StrategyV2 backtest contract + `build.py`'s 3-year frame), B3 aggregation
(diff review + fixture test + live cron cycle).

**Defects found and fixed in review:**
1. Report + 5 `patch_*.py` + 9 `scratch*.py` files left at the repo root (closed to new
   files, STRUCTURE.md). Report moved here; scripts deleted.
2. Load-bearing comments deleted: the D6(c)/`4af8a6fe` history in `build.py` and the
   FIX-S1-013 parallel in `_ghost_rows`. Restored, extended with the new classification.
3. Dead code: `'flat_ghosts' in locals()` guard on an always-bound name. Removed.
4. `black` had not been run (trailing whitespace). Run on all touched files.
5. Post-reconcile state bug: a `--reconcile` run recorded the PRE-delete ghost counts, so
   the heartbeat said "reconcile when convenient" about rows that run had just deleted.
   Fixed in `persist_all.py` (state now describes the table as the run left it).

**Pre-existing failures surfaced (NOT Gemini's — verified by stash/re-run):** 5 tests red
against the 2.0.0 champion promoted 2026-09-20: `test_score.py` fed float `0.5` to the
categorical `entry_signal_type` and indexed empty `known_strategies`; `test_ledger.py`
hardcoded the previous champion's calibrated thresholds (0.80/0.60), which redden on every
Sunday re-promotion. Fixed: valid categoricals + skip-if-no-strategy-basis in test_score;
thresholds read from `models/champion_manifest.json` in test_ledger. Live scoring was never
broken — confirmed by scoring evidence below.

**Deploy evidence:**
- Suite: 914 passed, 3 skipped, 0 failed (was 910 passed / 5 failed on handoff).
- Reconcile executed 2026-09-21 01:23Z: deleted exactly 3,916 rows (predicted 3,916);
  `fact_trade_outcomes` 37,886 → 33,991; rows for 30/46/49 now 0.
- Heartbeat overall **OK, exit 0** after a follow-up full writer run published the
  post-delete state (`ghost_rows: {retired: {}, unexpected: {}}`).
- Live cron cycle 01:15Z ran Gemini's `build.py`: one aggregated D6 WARNING per
  (strategy, pair, granularity) — e.g. "discarded 411 stale intents for strategy 41
  GBP_USD H4" — replacing hundreds of per-intent lines. Same cycle **published a real
  signal** (precision_swing GBP_USD H4 short, scored 0.526 under gk-6b9ed6c6,
  shadow_verdict would_pass), proving the emit path end-to-end after the change.

**Noticed, not touched:** strategy 50 floods the guard on D1 at lower volume (22–37
intents/pair/run) — same architectural cause, now visible in one line per run;
`retail_sentiment_fade` (45) skipped on every pair ("emits no orders anywhere");
`results/state/published_setups.json` is untracked and probably belongs in `.gitignore`.
