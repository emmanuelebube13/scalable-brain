# Code review 2026-08-15 — triaged findings on the uncommitted T4/T5 work

**Source:** `/code-review` agent run against `origin/main...HEAD` + working tree.
**Triaged by:** Claude, same day, by re-running the claims against the live tree.
**Why this file exists:** the review named 15 findings. Some had already been fixed by the time it
reported; others are real and unfixed. **Do not act on the raw review — act on this triage.**

---

## Read this first: the review's headline finding did NOT reproduce

The review's finding #1 claimed the `atr_14 → atr_pct_14` rename broke **29 tests** in
`test_mapping.py`, `test_label_thresholds.py` and `test_causal_labels.py`.

**Re-run at triage time: `src/system1/regime/tests/` → 64 passed, 0 failed.**

`mapping.py:78` does reference `atr_pct_14`, but its callers were updated. The review appears to
have run mid-edit and caught a transient state. **Finding #1 is stale — ignore it.**

Full suite at triage: **666 passed, 3 failed** (not 29). The 3 failures are unrelated to the
rename — see §3.

This is the general lesson: the review agent is a useful bug-finder but its snapshot may lag the
tree. Verify before acting.

---

## 1. CONFIRMED and unfixed — the feature store is internally contradictory

**This is the real damage, and it is worse than the review described.**

`feature-store/1.1.0/` has been **built** — 65 parquet partitions — and:

```
PARQUET COLUMNS:  asset_id, bar_time_utc, returns_1, atr_14, adx_14,
                  price_position_20, volatility_20          ← no atr_pct_14
schema.json  "columns":                 [... atr_14 ...]    ← no atr_pct_14
schema.json  "regime_feature_columns":  ["atr_pct_14", ...] ← advertises it
```

**The store advertises a regime feature vector it does not contain.** Any consumer that reads the
store using the declared regime columns gets a `KeyError`.

Three causes, all still present:

| # | file | defect |
|---|---|---|
| 1 | `features/feature_pipeline.py:50` | `ARROW_SCHEMA` still lists `atr_14`, not `atr_pct_14`. `OUTPUT_COLUMNS` derives from it, `_write_partition` selects on it → the new feature is silently dropped at write time |
| 2 | `features/feature_pipeline.py:157` | `schema.json`'s `"columns"` block is a **second, hand-maintained list** while `feature_columns` / `regime_feature_columns` come from `definitions.py`. Half the schema contract is a literal, which is exactly why the drift went undetected |
| 3 | `features/feature_pipeline.py:41` | `DEFAULT_VERSION` is still `"1.0.0"`. Running the pipeline without `--version` **overwrites `feature-store/1.0.0/`** with content built from the new definitions, destroying the documented byte-identical determinism guarantee for v1.0.0 |

`definitions.py` is correct (`atr_pct_14` computed at line 80, declared at 29/37/43/52). The break
is entirely in the pipeline's write path.

**Fix order:** add `atr_pct_14` to `ARROW_SCHEMA`; derive `schema.json`'s `columns` from
`ARROW_SCHEMA` instead of hardcoding it; bump `DEFAULT_VERSION` to `1.1.0`; **rebuild
`feature-store/1.1.0/` and verify a parquet actually contains the column.**

> **It does NOT void the T5 refit.** Checked: `hmm_regime.load_features()` reads prices straight
> from `fact_market_prices` and computes features live via `D.compute_features()` — it never
> touches the parquet store. Since `definitions.py` is correct, the refit used the normalized
> feature as intended. The store bug hits *other* consumers of `feature-store/1.1.0`, not the HMM.

---

## 2. CONFIRMED — my own bug in `persist_trade_outcomes.py`

**This one is mine, from the 2026-08-15 granularity fix. It is a data-loss bug.**

`run()` deletes rows for **all** seeded strategies:

```sql
DELETE FROM fact_trade_outcomes WHERE strategy_id IN (1..10)
```

and `granularities_for()` now returns `[]` for any strategy whose declared frame is not in the
requested list. So:

```bash
python -m src.layer0.persist_trade_outcomes --granularities H4
```

**deletes every H1-declared strategy's history and re-inserts nothing.** They vanish. Before the
granularity change they were at least re-backtested on H4. The `SKIPPING` warning is a log line,
not a guard.

**Fix:** scope the DELETE to the strategies that will actually be re-run, not to every seeded id.

**Related, lower severity (`persist_trade_outcomes.py` docstring):** the change is justified there
by two duplicate pairs, but `TrendDonchian_VCP`, `RangeBollinger_Aggressive` and
`RangeStochastic_Divergence` never override `primary_granularity` — they inherit `"H4"` from their
base class. They are not duplicates of anything, yet they also lost their H1 population. The
*behaviour* is defensible (they declare H4, so H4 is what they should trade); the *docstring's
explanation of the 72→36 cell drop is incomplete*. Fix the wording, not the code.

---

## 3. Currently failing tests — unrelated to any of the above

```
src/layer0/strategies/research/tests/test_precision_swing_fixture.py
  test_long_setup_matches_hand_computed_arithmetic
  test_short_setup_matches_hand_computed_arithmetic
  test_strategy_is_free_of_lookahead
```

3 failed, 666 passed. Not named by the review. **The look-ahead one matters most** — that is a
v2 research strategy failing its own leakage probe. Triage before the 30 new strategies land.

---

## 4. Not yet verified — plausible, worth checking

Listed by the review, not re-run at triage. Treat as leads.

| # | file | claim |
|---|---|---|
| 7 | `regime/hmm_regime.py:60` | `MODEL_VERSION` still `hmm-v1.0.0` despite the input vector changing → old and new regime rows are indistinguishable in `fact_market_regime_v2` |
| 8 | `regime/hmm_regime.py:259` | new `getattr(..., 0.0)` fallback turns a missing/NaN `atr_14`/`adx_14` into a plausible-looking `0.0` instead of raising. `atr_14` is no longer in `FEATURE_NAMES`, so it is no longer covered by the `dropna` guard |
| 9 | `regime/hmm_regime.py:747` | `--output-table` doesn't cover the schema migration — `ensure_regime_columns()` is hardcoded to `fact_market_regime_v2`, so a scratch run **ALTERs production** and inserts into a table that may lack the columns |
| 10 | `regime/hmm_regime.py:764` | `--output-table` without `--model-path` still **overwrites `models/hmm_model.joblib`** and registers an MLflow run as if it were a production retrain |
| 11 | `regime/hmm_regime.py:212` | table name f-string-interpolated into SQL from an unvalidated CLI arg |
| 12 | `regime/hmm_regime.py:764` | `--model-path scratch.joblib` (bare filename) → `os.makedirs("")` raises, *after* the full fit and the DB writes have committed |
| 13 | `monitoring/holds.py:91` | two holds naming the same check silently last-write-wins |
| 14 | `task/2026-August-week1/wave2/risk_audit.py:353` | still writes to `task/2026-W32/...`, a folder that no longer exists — the sibling `audit_wave2.py` was fixed, this one wasn't |
| 15 | `task/2026-August-week1/wave2/AUDIT.json` | regenerated register dropped 3 strategies and downgraded the remaining verdict — looks like a filtered re-run overwrote a fuller audit rather than merging |

**#9 and #10 are the dangerous pair** — together they mean the natural "try it on a scratch table
first" invocation touches production schema *and* clobbers the production model. If a T5 refit was
run with `--output-table` alone, check `models/hmm_model.joblib`'s mtime.

---

---

## 5. T5 ALREADY RAN — and Gate B passed decisively

`models/hmm_model_exp_atrpct.joblib` (2026-08-15 15:57) and table
`fact_market_regime_v2_exp_atrpct` both exist. Production `models/hmm_model.joblib` is untouched
(2026-08-14 08:34), so finding #10 did **not** bite — `--model-path` was passed correctly.

**H4 regime distribution, before → after the `atr_pct_14` fix:**

```
              BEFORE (production)                    AFTER (exp_atrpct)
          Rang  Up    Dn    HiVol              Rang  Up    Dn    HiVol
EUR_USD   95.6   0.0   1.0    3.4      →       68.8   7.9   4.8   18.5
GBP_USD   92.6   0.0   3.1    4.3      →       64.6   9.6   6.1   19.7
AUD_USD   92.4   0.0   3.1    4.5      →       42.1   6.8  13.6   37.6
USD_CAD   97.6   0.0   1.0    1.4      →       70.3   9.2   3.9   16.6
USD_JPY    7.6  23.9  14.0   51.2      →       57.8  11.3   8.5   22.4
```

**Every pair now registers Trending-Up (6.8–11.3%). The four zeros are gone.** USD_JPY is no
longer an outlier — it is now the *most* balanced pair. And AUD_USD is now the highest High-Vol
pair at 37.6%, which matches the raw data (AUD_USD had the largest bar range as a share of price,
0.39%, while USD_JPY was mid-pack at 0.32%).

**The diagnosis was right and the fix worked.** The unit artifact was the cause of the degenerate
labels.

### Gate A — read from `logs/hmm_refit_atrpct_20260815.log`

```
        BEFORE (2026-08-14)          AFTER (2026-08-15)
D1      HMM   acc 0.939 k 0.836  →   HMM     acc 0.987  k 0.975   PASS
H4      HMM   acc 0.940 k 0.833  →   HMM     acc 0.983  k 0.962   PASS
H1      HMM   acc 0.964 k 0.942  →   HMM FAILED (acc 0.683 < 0.70)
                                     K-Means acc 0.973  k 0.938   PASS (fallback)
```

Kappa went **up**, not down — as predicted: the old labels were 75–95% one class, so chance
agreement was high and suppressed kappa. Redistributing them raised it.

### But two new problems came with the fix

**(a) H1 is no longer an HMM.** Its HMM failed the accuracy gate (0.683 < 0.70) and fell back to
K-Means. The fallback works as designed and clears both gates, but H1 regime labels are now
produced by a simpler model than before. Previously it was the *strongest* HMM fit
(acc 0.964 / k 0.942). Do not describe H1 as HMM-labelled any more.

**(b) `regime_smoothed` is degenerate — this is what the `unused=[...]` log warnings mean.**

```
granularity   smoothed Trending-Up   smoothed Ranging   smoothed High-Vol
D1                   0.0%                62.8%              27.1%
H4                   0.0%                65.0%              26.9%
H1                  64.0%                 0.0%               0.0%
```

D1 and H4 never emit `Trending-Up`; H1 emits **only** the two trending labels. The *causal*
column is fine (see below) and it is the one attribution and strategies read (FIX-S1-005), so the
decision path is unaffected. Two consequences that still matter:

1. Charts and dashboards driven by `regime_smoothed` are wrong.
2. **The kappa numbers may be flattered.** Accuracy/kappa are computed by aligning model states
   against a reference labelling; if that labelling collapses to 2–3 effective classes, agreement
   is a mechanically easier problem. Treat 0.975 as "passed the gate", not as "the model got much
   better".

### The causal column — the one that matters — is genuinely fixed

```
granularity   Ranging   Trending-Up   Trending-Down   High-Vol
D1             50.5         16.1            7.5          25.9
H4             60.7          9.0            7.4          23.0
H1             42.6         15.0           17.1          25.4
```

All four labels populated at all three granularities, and every pair registers Trending-Up
(6.8–11.3% at H4). The degeneracy that made the label a proxy for "is this USD_JPY" is gone.

---

## What to do, in order

1. **Read Gate A** (accuracy + kappa) for the experimental refit. That is the only thing standing
   between §5 and a promotion decision.
2. **Fix the feature-store write path** (§1) and rebuild 1.1.0. Verify the column is in a parquet.
   Independent of the HMM, but it breaks any other consumer.
3. **Fix the DELETE scope** in `persist_trade_outcomes.py` (§2) — data-loss bug, mine.
4. **Triage the 3 failing tests** (§3), the look-ahead one first.
5. Work §4 as a checklist — **#9 first**, since a scratch-table run still ALTERs production schema.

## What is NOT affected

`src/regime_aware/` is read-only by construction and untouched by all of this. Production data at
triage time: `fact_trade_outcomes` 55,756 · `fact_strategy_regime_attribution` 1,360 ·
`fact_market_regime_v2` 847,151 — all unchanged.
