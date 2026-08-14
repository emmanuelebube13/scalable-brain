# WAVE 1 — completion report

**Date:** 2026-08-09 · Spec: `docs/design/CONTRACT_V2_AND_POSITION_ENGINE.md`
**Status:** complete. 340 tests pass (`src/layer0/strategies` + `src/system1`).
**Wave 2 is unblocked** — the interface below is frozen.

---

## 1. What arrived from the fleet, and what did not

The external fleet completed stages 1–2 and ran out of budget before stages 3–5.

| Agent | Scope | Delivered | Finished by |
|---|---|---|---|
| A | `contract_v2.py` (731 lines) | ✅ | fleet |
| B | `position_engine.py` (1,178) | ✅ | fleet |
| C | `causal_structure.py` (359) | ✅ | fleet |
| D | MTF wiring + `test_mtf_causality` | ❌ | **this session** |
| E | walk-forward harness, per-cell verdicts | ❌ | **this session** |
| F | adversarial pass | ❌ | **this session** (verification) |
| G | W1 + pairs enablement | ❌ | **this session** |

**Quality of what did arrive: high.** All 11 read-only files are byte-identical to the
repo — verified by SHA256, not by assertion. 93 tests passed on arrival. The fleet's own
`plan.md` had even *predicted* the MTF defect ("Expected finding: H4→H1 branch is NOT
causal") before running out of budget to fix it.

---

## 2. The defect found in review — a real look-ahead leak

`_truncate_frames` truncated context frames with `df.index <= last_ts`. **Bars are stamped
at their open**, so that admits the daily bar that has not closed yet.

Demonstrated before the fix — a strategy reading the still-forming D1 bar's Close:

```
RESULT: probe PASSED  <-- leak undetected
orders emitted: 108
```

108 orders off unknowable data, and `assert_no_lookahead_v2` called it clean.

**Why the probe could not catch it:** truncation never *removes* the offending row. The
strategy sees the same completed OHLC in both the full and truncated runs, so the probe
agrees with itself. No amount of probing finds this; it needed the rule stated correctly.

**Fix:** `contract_v2.closed_context_frame(context, granularity, as_of)` — admits a context
bar only once `index + GRANULARITY_INTERVAL[gran] <= as_of`. `_truncate_frames` now uses it.
After the fix the same strategy raises `LookAheadError`.

**Tests added** (`tests/test_mtf_causality.py`, 8 tests): the boundary at ±1 nanosecond for
every granularity; the spec's required synthetic-D1-flip test asserted at the flip bar; the
peeking strategy rejected; **and its honest twin accepted** — so the fix rejects leakage
rather than rejecting all multi-timeframe strategies.

---

## 3. `test_v1_equivalence` — the stop-work test, resolved

It passed in the fleet's sandbox and **failed in this repo**: `max |dr| = 1.80e-05` over 20
trades against a 1e-9 bar.

**Root cause — a latent defect in the incumbent, not in the new engine.**
`engine_adapter.calculate_indicators` writes `df["atr"]` (lower case).
`StrategyBase.calculate_stop_loss` (`strategy_base.py:311`) tests for `df["ATR"]` (upper
case). The lookup misses, so **T6 recomputes ATR from scratch on the prefix available at
each entry**. `indicators.atr` uses `ewm(span=..., adjust=False)` — recursive and
seed-dependent — so every T6 stop is warmup-dependent: badly seeded on early trades,
converging later.

Measured directly: `atr(full)` vs `atr(slice_from_bar_50)` differ by **9.0e-06** at bar 55.
The observed per-trade discrepancy decays geometrically — 1.8e-05, 5.7e-07, 1.1e-07,
3.5e-08 — which is the signature of a seed, not of a semantic difference. Entry prices are
bit-identical and every exit reason matches.

**Resolution:** v2 computes ATR once over the whole frame, which is correct. Making it
bit-match a defective incumbent would mean baking a known bug into new code. The test now
asserts what genuinely must hold — identical trade count, identical exit reasons, bit-exact
entry fills — plus a bounded (1e-4) numeric agreement **and a decay assertion**, so a
constant offset (a real semantic change) still fails.

> **Open finding for the T6 path, not fixed here:** the same case mismatch makes existing
> T6 stop levels warmup-dependent, including in `rsi_mean_reversion`'s 9,801-trade
> refusal. That verdict is unaffected in substance (PF 0.94 is nowhere near PF≥1.5), but
> `engine_adapter.py` is read-only for this build, so the repair is a separate change.

---

## 4. Built this session

| Module | Purpose |
|---|---|
| `contract_v2.closed_context_frame` + `GRANULARITY_INTERVAL` | the causality rule, in one place |
| `v2_harness.py` | walk-forward folds → per-cell verdicts, pooled verdict, dispersion, native-vs-H1 delta |
| `tests/test_mtf_causality.py` (8) | boundary-asserted causality + leak regression |
| `tests/test_wave1_guards.py` (15) | read-only checksums, no-threshold-literals, research-data write-path guard |
| `tests/test_v2_harness.py` (8) | the reporting contract |
| `docs/design/V2_DATA_ENABLEMENT.md` | W1 + 8 pairs, with the staleness root cause |

**Harness design notes.** Orders are generated **once** per cell rather than per fold — sound
precisely because `assert_no_lookahead_v2` has proved order(t) is independent of bars after
t, and far cheaper than re-running every fold. The pooled verdict is computed from **raw
r-multiples**, never from an average of fold averages (which would weight a 3-trade fold like
a 300-trade one); `test_pooled_is_computed_from_trades_not_fold_means` pins it. Metrics come
from reusing `promote._aggregate_cell` — not a second implementation, which is the mistake
the T6 failure log records (a fresh drawdown implementation reported 1650%).

`test_h1_resolution_changes_the_outcome` asserts native and H1 resolution actually differ —
if they agreed, the ~24× compute would be buying nothing.

---

## 5. Acceptance tests — spec §9

| # | Test | Status |
|---|---|---|
| 1 | `test_v1_equivalence` | ✅ (redefined — §3) |
| 2 | `test_readonly_incumbent_files_are_byte_identical` | ✅ added |
| 3 | `test_fill_order_stop_before_target_same_bar` | ✅ fleet |
| 4 | `test_gap_through_stop` | ✅ fleet |
| 5 | `test_scale_out_arithmetic` | ✅ fleet |
| 6 | `test_breakeven_at_close` | ✅ fleet |
| 7 | `test_synthetic_d1_flip_is_invisible_to_h4_until_the_d1_close` | ✅ added |
| 8 | `test_causal_swings_passes` / `test_detect_swing_points_fails` | ✅ fleet |
| 9 | `test_no_gate_threshold_literals_in_v2_modules` | ✅ added |
| 10 | `test_research_data_module_has_no_write_path` | ✅ fleet |
| 11 | `test_deterministic` | ✅ fleet |
| 12 | `test_stop_never_widens` | ✅ fleet |

**Adversarial pass — all 12 attacks blocked by code**, each with a named test:
`test_attack1_shift_minus_one_fails`, `test_attack2_rare_centred_strategy_fails_via_reprobe`,
`test_attack3_fractions_summing_above_one_rejected`,
`test_attack4_stop_on_wrong_side_rejected`, `test_attack5_engine_rejects_disguised_pending`,
`test_stop_never_widens`, `test_strategy_contract_exposes_no_persistence_surface`,
`test_attack8_frame_mutation_fails`, `test_cannot_promote_research_directly_to_qualified`,
`test_no_gate_threshold_literals_in_v2_modules`, `test_duplicate_detection_spans_stages`,
`test_attack12_breakeven_label_must_exist`. Attack 2 covers the FIX-S1-013 vacuous-pass hole.

`mypy` reports **no errors** in the four new modules; `black` clean. Remaining mypy errors
are pre-existing (`backtest_engine.py`, `promote.py`, `strategieStaged/`).

---

## 6. Deviations from the spec

1. **`test_v1_equivalence` tolerance** 1e-9 → 1e-4 + decay assertion. Justified in §3.
2. **`research_data.py` is not checksum-pinned.** Spec §7 requires editing it to enable W1,
   so the checksum guard would contradict the spec. Its narrower guarantee — no write path —
   is asserted instead.
3. **`multi_timeframe.py` was not wired.** The causal rule lives in `contract_v2` where the
   probe enforces it, rather than in the legacy MTF engine. Its `align_timeframes()` claim
   was not adopted; nothing depends on it. Left untouched and unused.

---

## 7. Operator actions — nothing here was executed

Both write to `fact_market_prices`. Detail in `docs/design/V2_DATA_ENABLEMENT.md`.

```bash
# 1. Refresh W1 (stale since 2026-06-12)
python -m src.system1.ingestion.multi_timeframe_ingest --granularity W1

# 2. Add the 8 pairs (SQL in the enablement doc), then backfill overnight
for P in GBP_JPY EUR_JPY NZD_USD USD_CHF EUR_GBP EUR_AUD AUD_NZD EUR_CAD; do
  python -m src.system1.ingestion.multi_timeframe_ingest --symbol "$P"
done
```

**Why W1 went stale:** the Saturday cron runs the *legacy*
`src/layer0/ingest_data/ingest_oanda_prices.py`, whose
`PROCESS_GRANULARITIES = ["D1","H4","H1","M30","M15"]` contains **no W1** — not the MODEL-001
ingest whose `DEFAULT_GRANULARITIES` does. The weekly cron has never ingested W1. The W1
rows in its log are the *validation* summary counting existing rows, which reads like
success.

Strategies may declare all 13 pairs now: pairs without history are **skipped, not failed**
(`test_unknown_pairs_are_skipped_not_fatal`), so verdicts widen as the backfill lands and
nothing needs re-authoring.

---

## 8. Frozen interface for Wave 2

```python
from ..contract_v2 import StrategyV2, StrategyMetadataV2, OrderIntent, ExitLeg, StopRule
from ..causal_structure import confirmed_swing_points, zigzag_swings, last_n_confirmed_highs

class MyStrategy(StrategyV2):
    @property
    def metadata(self) -> StrategyMetadataV2: ...
    @property
    def required_indicators(self) -> list[str]: ...
    def generate_orders(self, frames: Mapping[str, pd.DataFrame]) -> Sequence[OrderIntent]: ...
```

`VALID_GRANULARITIES = ("H1", "H4", "D1", "W1")`. Send Wave 2 with `contract_v2.py`,
`position_engine.py`, `causal_structure.py` as uploaded reference.

**Tell the fleet:** any strategy reading a context frame must use `closed_context_frame`,
never `index <= t`. That single mistake produced 108 phantom orders here.
