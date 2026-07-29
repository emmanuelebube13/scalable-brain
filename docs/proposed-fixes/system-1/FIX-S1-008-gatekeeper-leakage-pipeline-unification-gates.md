# FIX-S1-008 — Layer 3 gatekeeper: target leakage, three divergent feature pipelines, and toothless gates

**Severity:** P0 (target leakage silently inflates every reported OOS metric; the trained model cannot be reproduced at serve time)
**Status:** Fixes 1 (leakage) + 3 (gates) + 4 (cleanup) IMPLEMENTED 2026-07-04 — log-only, no champion promoted. Fix 2 blocked (deleted serve path). NOTE: `fact_signals`/`fact_trade_outcomes` are NOT empty on the live DB (2000+ rows load) — the real OOS re-measurement is now unblocked (see §6c).
**Author:** Claude (Layer-3 audit, verified against source 2026-07-04)
**Scope:** `src/layer3_ml/training/train_ml_gatekeeper.py`, `src/layer3_ml/feature_alignment.py`, `src/layer3_ml/train_ml_gatekeeper.py` (root), `src/layer3_ml/__init__.py`
**Consumes/blocks:** feeds the champion bundle consumed by Layer 4 — tightly coupled to **FIX-S2-001** (live gatekeeper scores an all-NaN feature row) and **FIX-XC-002** (Layer-3 regime features 100% NULL). Fixing S1-008 is a precondition for S2-001 being meaningful.

---

## ENGINEER BRIEF (read this first)

### Your role
You are a **senior ML engineer specializing in financial-model validity and train/serve
parity**. Your mandate on this task is *correctness of the learning signal*, not model
accuracy. A model that scores worse but is leak-free and reproducible at serve time is a
**success**; a model that scores better on leaked features is a **regression**. You are
expected to be adversarial toward your own metrics: if OOS uplift *rises* after removing
leakage, treat that as a red flag and investigate, don't celebrate.

### Tools & environment
- **Repo:** `/home/emmanuel/Documents/Scalable_Brain/scalable-brain`, Python 3.12, venv at
  `/home/emmanuel/Documents/Scalable_Brain/.venv` (`source .venv/bin/activate`).
- **DB:** PostgreSQL 16 + TimescaleDB on `localhost:5432`, `ForexBrainDB`, role `sa`.
  Connect **only** via `src/common/db.py` (`get_engine`); never build a connection string
  inline. Parameterize all SQL (`:named` / `%s`) — no f-string interpolation of values.
  ⚠️ `fact_signals` and `fact_trade_outcomes` are currently **empty** in this DB — you will
  need to either populate a fixture or run against a snapshot; plan for a synthetic fixture
  (see Validation).
- **Commands:**
  - Dry-run load (fast, no fit): `python src/layer3_ml/training/train_ml_gatekeeper.py --dry-run-load`
  - Strict dry-run: `python src/layer3_ml/training/train_ml_gatekeeper.py --dry-run --selection-mode strict --min-expectancy 0.0`
  - Tests: `pytest src/layer3_ml/tests/ -v` (add new tests here)
  - Format/type: `black src/layer3_ml/`, `mypy src/layer3_ml/`
- **Guardrails:** additive, minimal changes; preserve H1/H4 granularity contract; preserve
  the champion artifact contract (`champion_model.pkl` / `champion_preprocessor.pkl` /
  `champion_manifest.json`) — Layer 4 depends on its exact shape. **Do not promote a champion**
  as part of this fix; every run stays log-only until sign-off.
- **Definition of done:** all four fixes below landed behind red-before/green-after tests,
  OOS uplift re-measured and reported on leak-free features, and a short written finding
  (did uplift survive? by how much?) appended to §6.

### How to work
Do the fixes **in the numbered order** — Fix 1 (leakage) must land and be re-measured before
Fix 3 (gates) means anything, because today's gate thresholds are calibrated against inflated
metrics. Land each fix as its own commit with its own test. Keep the live champion untouched.

---

## 1. Executive summary

The Layer 3 gatekeeper has four compounding defects, verified against source:

1. **Target leakage (P0).** Post-trade outcome columns and current-row-inclusive rolling
   windows built from the label enter the feature matrix. Every reported PR-AUC / expectancy /
   OOS uplift is inflated by information unavailable at prediction time.
2. **Train/serve skew (P0).** Training and inference use *different, drifted* feature builders,
   so features the model leans on arrive as constant imputed values (or NaN) in production.
3. **Three divergent copies** of the feature pipeline; `__init__.py` exports a *third* one that
   neither trains nor serves. This is the structural root cause of #2.
4. **Toothless gates (P1).** `MIN_EXPECTANCY = -0.05`, adaptive/median threshold fallbacks, and
   an auto strict→fallback switch mean "strict" rarely rejects anything.

---

## 2. Evidence (file:line, verified)

### 2a. Target leakage — two independent sources

**Source A: raw post-trade outcome columns become features.**
`training/train_ml_gatekeeper.py:436-441` selects `R_Multiple`, `Holding_Bars`,
`Entry_Signal_Type`, `Exit_Reason` (plus `ATR_SL_Multiplier`, `ATR_TP_Multiplier`) from
`fact_trade_outcomes`. The header comment even claims *"for context, not target leakage"* —
this is wrong: these are all **realized after the trade closes**. The meta-exclusion list at
`:1764-1774` drops only `Timestamp, Granularity_Key, Indicator_Snapshot, Config_Hash,
Batch_ID, Trade_Horizon_Key`, so every one of those outcome columns lands in `feature_cols`
(`:1774`) and is fed to the model. `R_Multiple` and `Exit_Reason` alone are near-perfect
proxies for `Is_Winner`.

**Source B: rolling windows include the current row's own label.**
`calculate_strategy_performance_features` (`:723-770`) computes, per strategy:
```python
strat_df["Is_Winner"].rolling(window=window, min_periods=5).mean()   # :749-751  -> Strat_WinRate_*
strat_df["R_Multiple"].rolling(window=window, min_periods=5).mean()  # :761-765  -> Strat_Expectancy_*
```
There is **no `.shift(1)`**, so row *i*'s window includes row *i*'s own `Is_Winner`/`R_Multiple`
— the label leaks into its own feature. This is a *distinct* leak from Source A and survives
even after the raw outcome columns are removed.

### 2b. Train/serve skew

Layer 4 does single-row inference: `layer4_executor/live_pipeline.py:1149`
(`pd.DataFrame([signal_row.to_dict()])`) → `safe_comprehensive_feature_engineering`
(`:1167`) → `align_features_for_inference` (`:1176`). The aligner fills any expected-but-absent
column with `np.nan` (`feature_alignment.py:274`), which the preprocessor then imputes. At
serve time:
- `R_Multiple`, `Holding_Bars`, `Exit_Reason` — trade hasn't happened → NaN → imputed.
- `Strat_WinRate_*`, `Strat_Expectancy_*`, `Strat_Trades_*`, `Bars_Since_Last_Trade` —
  impossible on one row; `safe_comprehensive_feature_engineering` never builds them at all.
- `Signal_Hour`, `Signal_Month/Quarter`, `Is_London_NY_Session`, `Is_Asian/US_Session` — built
  at train time by SQL `EXTRACT` (`:374-380`); the serve builder has no equivalent, so
  `Session_*`/`Is_Monday/Friday` (which *depend* on `Signal_Hour`) also collapse.
  `H4_D1_Agreement`, `Candle_Sentiment`, `Strategy_Category` are training-only
  (`engineer_derived_features`, `:674-694`).

Net: the model is trained leaning on features it receives as constant imputed values in
production — a severe covariate shift the moment it goes live (this is the mechanism behind
**FIX-S2-001**).

### 2c. Three divergent pipelines

| File | Lines | Role | Notable |
|------|-------|------|---------|
| `train_ml_gatekeeper.py` (root) | 270 | **exported by `__init__.py:8`, used by neither path** | has `add_temporal_features` (`:188,215`); `fillna(0.5)` win-rate default (`:161-167`) |
| `training/train_ml_gatekeeper.py` | 1957 | actual training | the leaky superset above |
| `feature_alignment.py` | 428 | actual Layer-4 inference | subset; no temporal, no strategy-perf |

`__init__.py:8` re-exports `comprehensive_feature_engineering` from the **root** file — the one
that is neither trained nor served. Layer 4 imports it (`live_pipeline.py:81`) but actually
serves via `safe_comprehensive_feature_engineering`. The `__init__` docstring's promise ("can
be imported by Layer 4 for inference") is unmet.

### 2d. Toothless gates

- `MIN_EXPECTANCY_UNIT_R = -0.05` (`:78`) admits negative-expectancy models.
- `choose_threshold` / per-model fallback assign an adaptive-percentile or median threshold
  when no threshold passes the gates (`:1474-1487`), and `all_candidates` retains failures.
- Auto strict→fallback when `--promote-as-champion` is absent (`:1817-1822`).
- The only hard `is_degenerate` backstop runs **at promote time** (`:1905-1917`) and uses
  `<= args.min_expectancy` (≤ −0.05), so a −0.04-expectancy model still promotes.

### 2e. Medium (bundle into cleanup commit)

- **SQL value interpolation** (repo rule violation): `get_distinct_nonnull_values` interpolates
  `{table_name}`/`{column_name}` (`:216-217`); granularity literals interpolated at `:335-342`.
  DB-derived, not user input, so not a live injection risk — but violates the parameterized-SQL
  convention.
- **LSTM sequences ignore instrument boundaries:** data sorted by `Timestamp` only (`:1738`);
  `ForexDataset.__getitem__` slices contiguous `X[idx:idx+SEQ_LEN]` (SEQ_LEN=50, `:72`,
  `:1178-1179`) with no asset/strategy grouping → sequences span different assets. Semantically
  meaningless.
- **Deprecated APIs:** `datetime.utcnow()` (`:1331,1374,1924,1929`) → `datetime.now(timezone.utc)`;
  `pd.to_numeric(errors='ignore')` (`feature_alignment.py:261`) removed in pandas 2.x.
- **Bare `except:`** in both `safe_json_load` implementations (`feature_alignment.py:51`, root).

---

## 3. Root cause

Feature engineering was written three times, drifting apart, with no single contract enforcing
"features present at train == features present at serve." Outcome columns were added "for
context" without recognizing they are realized post-decision. Gate thresholds were then
loosened repeatedly (see the `# Increased from…` / `# Reduced from…` comments at `:76-78`) to
make an inflated, leaky model *appear* to pass.

---

## 4. The fix (do in order)

### Fix 1 — Kill the leakage (P0, highest value)
1. **Remove post-trade columns from the feature path.** Add `R_Multiple`, `Holding_Bars`,
   `Exit_Reason`, `Entry_Signal_Type`, `ATR_SL_Multiplier`, `ATR_TP_Multiplier` to the
   meta-exclusion set at `:1764-1774` (or stop selecting them at `:436-441` if nothing else
   needs them). `R_Multiple` may stay in the raw frame **only** as an input to the *shifted*
   rolling expectancy in Fix 1.2, never as a column in `feature_cols`.
2. **Make rolling features causal.** In `calculate_strategy_performance_features` apply
   `.shift(1)` per-strategy **before** every rolling reduction so row *i*'s window is
   strictly rows `< i`:
   ```python
   past = strat_df["Is_Winner"].shift(1)
   rolling_wins = past.rolling(window=window, min_periods=5).mean()
   ```
   Same for `Strat_Expectancy_*` (shift `R_Multiple`) and `Strat_Trades_*`. Confirm
   `Bars_Since_Last_Trade` (`:768-770`) uses only past timestamps (a `.diff()` is past-only —
   verify, keep).
3. **Add a leakage guard test** (see Validation): assert no feature column's per-row value can
   be computed from that row's own `Is_Winner`.

### Fix 2 — One feature pipeline (P0, prevents skew by construction)
1. Create a single shared module (e.g. `src/layer3_ml/feature_pipeline.py`) that is the *only*
   implementation of `comprehensive_feature_engineering` and its helpers.
2. Training (`training/…`) and inference (`feature_alignment.py`) both import from it. Delete
   the root `train_ml_gatekeeper.py` feature code (or reduce it to a re-export) and fix
   `__init__.py:8` to export the shared version.
3. The shared builder must construct the **temporal features in Python** (derive `Signal_Hour`
   etc. from the `Timestamp`/`timestamp` column) so they exist identically whether the row came
   from the SQL `EXTRACT` path or a single live signal row. Serve-time-impossible features
   (strategy-perf rolling stats) must be produced by a **shared stateful helper** that Layer 4
   can feed recent history into — or be explicitly dropped from the contract. Do **not** let
   them silently impute to a constant.
4. Persist the exact ordered `feature_columns` into the manifest (already done at `:1923`) and
   have inference assert the built set matches — fail loud on drift instead of NaN-filling
   (coordinate with **FIX-S2-001**).

### Fix 3 — Give the gates teeth (P1)
1. `MIN_EXPECTANCY_UNIT_R = 0.0` (`:78`).
2. Gate failures **drop** candidates instead of being relabeled with an adaptive/median
   threshold: in `choose_threshold` (`:1003`) and the per-model blocks (`:1474-1487`,
   `:1601-1611`), return `None`/skip rather than fabricating a threshold.
3. Remove the auto strict→fallback switch (`:1817-1822`) — strict means strict; if nothing
   passes, fail the run.
4. Keep the `is_degenerate` backstop but move an equivalent check into **selection**, not just
   promotion.

### Fix 4 — Cleanup (P2, one commit)
Parameterize the two SQL builders (§2e); gate/segment the LSTM by asset+strategy before
sequence slicing (or disable it with a note if unused); replace `datetime.utcnow()` and
`pd.to_numeric(errors='ignore')`; narrow the bare `except:` to `except (ValueError, TypeError,
json.JSONDecodeError):`.

---

## 5. Validation

- **Leakage guard test (must be red before Fix 1, green after):** build features on a fixture,
  then for each feature column confirm shuffling `Is_Winner` does **not** change that column's
  values for already-emitted rows (i.e., features are label-independent). Assert
  `R_Multiple`/`Holding_Bars`/`Exit_Reason`/`Entry_Signal_Type` are absent from `feature_cols`.
- **Train/serve parity test (red before Fix 2, green after):** take one training row, run it
  through the *training* builder and through the single-row *inference* builder; assert the
  produced feature vectors are identical (same columns, same non-NaN values) — no column may be
  present-at-train-but-NaN-at-serve.
- **Gate-can-fire test (red before Fix 3):** feed a candidate with expectancy −0.02 and confirm
  strict mode now **rejects** it (previously promoted).
- **OOS re-measurement (the headline result):** re-run the strict dry-run on leak-free features
  and record PR-AUC / expectancy / OOS uplift in §6. **Expected:** metrics *drop* vs. the
  leaked baseline. If uplift survives at a smaller magnitude, that's the real edge. If it
  vanishes, that's the finding — the gatekeeper's apparent edge was leakage (compare the
  precedent in `[[fix-s1-005-oos-uplift-not-inflated]]`, where uplift *did* survive a leak fix).
- Since `fact_signals`/`fact_trade_outcomes` are empty, build a deterministic synthetic fixture
  (or restore a snapshot) with known winners so the leakage/parity tests are reproducible in CI.

---

## 6. Findings (Fix 1 — landed 2026-07-04)

**Status:** Fix 1 (leakage) implemented, log-only, no champion promoted. Fixes 2–4
deferred by decision (do Fix 1 first, then re-evaluate; Fix 2's live-serve premise
is currently unmoored — see note below).

### What landed
- **Source A closed.** Post-trade outcome columns are now excluded from the model
  feature set via a single source of truth: module constant `POST_TRADE_OUTCOME_COLS`
  = {`R_Multiple`, `Holding_Bars`, `Exit_Reason`, `Entry_Signal_Type`,
  `ATR_SL_Multiplier`, `ATR_TP_Multiplier`} and a new `select_feature_columns()`
  helper used by `main()` (replaces the inline `meta_cols` block). `R_Multiple`
  remains in the raw frame **only** as the input to the shifted rolling expectancy.
- **Source B closed.** `calculate_strategy_performance_features` now applies
  `.shift(1)` per strategy before every rolling reduction (`Strat_WinRate_*`,
  `Strat_Trades_*`, `Strat_Expectancy_*`), so row *i*'s window is strictly rows `< i`.
  `Bars_Since_Last_Trade` (`groupby.diff()`) verified past-only — kept.
- **Tests:** `src/layer3_ml/tests/test_feature_leakage.py` — 3 tests, all green.
  Red-before/green-after proven by stashing the source edits and re-running the same
  assertions: pre-fix, flipping row *i*'s own label changed
  `Strat_WinRate_{20,50,100}` + `Strat_Expectancy_{20,50,100}`; post-fix those no
  longer move. A third "sanity" test confirms flipping a *past* label still moves a
  *future* row's stats (guards against a vacuous green).

### OOS re-measurement — leaked vs leak-free
⚠️ `fact_signals` / `fact_trade_outcomes` are **empty** in this environment and there
is no snapshot, so the numbers below are a **controlled synthetic demonstration of
the inflation mechanism**, not a real-market OOS uplift. The fixture bakes in (a) a
genuine modest edge in a pre-decision feature (`Signal_Confidence`) and (b) the leak
(`R_Multiple`/`Exit_Reason` as deterministic proxies of `Is_Winner`). Same
preprocessor + XGBoost, module's own `chronological_split` (0.2 OOS), base win-rate
0.500, unrestricted expectancy −0.270R.

| Feature set | PR-AUC | Expectancy (approved @0.5) |
|---|---|---|
| Leaked (before)   | **1.0000** | **+0.2387R** |
| Leak-free (after) | **0.5994** | **−0.1967R** |

- **Leaked-baseline metrics (before):** PR-AUC 1.0000 / approved-expectancy +0.239R —
  a *perfect* classifier and *positive* expectancy conjured out of a dataset whose
  true unconditional expectancy is −0.270R. Entirely fabricated by leakage.
- **Leak-free metrics (after Fix 1):** PR-AUC 0.5994 (uplift +0.099 over the 0.500
  base rate) / approved-expectancy −0.197R (better than the −0.270R unrestricted, i.e.
  the ranking is real, but still absolutely negative on this fixture by construction).
- **Did the edge survive?** **Smaller — and re-interpreted.** The apparent
  *profitability* (positive expectancy, perfect PR-AUC) was 100% leakage and vanished.
  A genuine *ranking* edge (~0.10 PR-AUC over base) survives, because the fixture
  contains real pre-decision signal. This matches the adversarial expectation in the
  brief: metrics dropped sharply, and what remains is the honest, smaller edge (cf.
  `[[fix-s1-005-oos-uplift-not-inflated]]`, where uplift survived a leak fix).
  **The real yes/smaller/vanished verdict for the production gatekeeper is BLOCKED on
  populating `fact_signals`/`fact_trade_outcomes` and must be re-run on real data
  before any promotion.**
- **Train/serve parity confirmed identical vectors:** N/A — Fix 2 deferred. The live
  serve path (`src/layer4_executor/live_pipeline.py`) is **deleted on this branch
  (`fix/s1-integration`)**, so "parity with the live consumer" cannot be validated
  until Layer 4 is restored. When Fix 2 proceeds, the three builders will be unified
  in-repo and a training-vs-`feature_alignment` parity test written (coordinated with
  FIX-S2-001).

## 6b. Findings (Fix 3 — gates, landed 2026-07-04)

**Status:** Fix 3 implemented, log-only. Fix 1 (its prerequisite) was landed and the
gate thresholds re-evaluated against leak-free metrics first, per the brief's ordering.

### What landed
- **3.1 — expectancy gate has teeth.** `MIN_EXPECTANCY_UNIT_R` −0.05 → **0.0**. A
  non-positive-expectancy model now fails the gate.
- **3.2 — no fabricated thresholds.** Removed the adaptive-percentile fallback in
  `choose_threshold` and the adaptive/median fabrication in both the tree and LSTM
  blocks of `train_models`. When no threshold satisfies the turnover + positive-
  expectancy gates, the candidate is **dropped** (`[DROP] …`) rather than kept alive
  with an invented threshold.
- **3.3 — strict means strict.** Removed the auto strict→fallback switch that fired
  when `--promote-as-champion` was absent. ⚠️ **Behaviour change:** a strict run
  (incl. `--dry-run --selection-mode strict`) now **raises** if no model passes the
  gates instead of silently degrading to fallback. Use `--selection-mode fallback`
  for an informative non-failing diagnostic run.
- **3.4 — single-source degeneracy backstop.** New `is_degenerate_metrics()` helper
  is the one definition of "degenerate" (turnover out of `[min,max]` OR
  `expectancy ≤ min_expectancy`). Applied at **selection** time (strict mode now
  fails on a degenerate selection, not only at promotion) and reused at promotion.
  All four inline gate checks (tree, LSTM, candidate summary, promotion) now call it.

### Tests (`src/layer3_ml/tests/test_gate_teeth.py`, 5, all green)
- `choose_threshold` returns `None` on a no-edge (anti-correlated) model and a valid
  gate-satisfying threshold on a genuinely profitable one.
- `MIN_EXPECTANCY_UNIT_R == 0.0`; `is_degenerate_metrics` flags −0.02R and 0.0R and
  turnover breaches.
- **Gate-can-fire (brief §5), red-before/green-after proven** by stashing the source:
  a −0.02R candidate was `degenerate=False` → **PROMOTABLE** pre-fix (gate −0.05) and
  `degenerate=True` → **REJECTED** post-fix (gate 0.0).

### Note
Total Layer 3 test suite now 8 green (3 leakage + 5 gates). Still log-only, no champion
promoted — promotion remains blocked on the real OOS re-measurement and Fix 2
coordination per §7.

## 6c. Findings (Fix 4 — cleanup, landed 2026-07-04)

**Status:** Fix 4 implemented, log-only. Validated end-to-end with `--dry-run-load`
(exit 0, 2000 rows, 50 features).

- **4.1 — SQL parameterization.** New `_safe_sql_identifier()` validates every
  interpolated identifier (`regime_table`, `granularity_col`, `outcome_granularity_col`,
  `horizon_col`, and the table/column in `get_distinct_nonnull_values`) against a strict
  identifier pattern — these come from schema inspection, not user input, but unchecked
  interpolation violated the repo convention. Granularity **values** (the `= '…'` and
  `IN (…)` literals) are now bound parameters threaded via `build_query_with_contract →
  params → pd.read_sql(sa.text(query), engine, params=…)`. Verified the query still runs.
- **4.2 — LSTM opt-in.** The LSTM previously trained **unconditionally** (ignoring
  `--model-types`) and slices contiguous SEQ_LEN windows over a Timestamp-only-sorted
  frame, so its sequences cross asset/strategy boundaries (semantically meaningless). It
  is now gated on `"lstm" in model_types` via an early-return guard; the default
  `--model-types` excludes it, so it is **off by default** and prints a `[SKIP]` note.
  Re-enable only after the sequence builder is segmented by asset+strategy.
- **4.3 — deprecated APIs.** `datetime.utcnow()` → `datetime.now(timezone.utc)` (4 sites);
  `pd.to_numeric(errors='ignore')` (removed in pandas 2.x) → try/`except (ValueError,
  TypeError)` that keeps the original column, replicating the old column-level semantics.
- **4.4 — bare excepts.** All three `safe_json_load` bare `except:` (training,
  `feature_alignment.py`, root) narrowed to `except (ValueError, TypeError,
  json.JSONDecodeError)`.

### ⚠️ Data-availability correction (supersedes the §5/§6 "empty tables" caveat)
`fact_signals`/`fact_trade_outcomes` were assumed empty (per the brief and prior notes),
but the live DB now returns **2000+ joined rows** (`--dry-run-load`, class_ratio ≈ 2.0 →
~33% winners). **The real leaked-vs-leak-free OOS re-measurement is therefore no longer
blocked** and should be run on the actual data to replace the synthetic §6 numbers before
any promotion decision. A full strict train (Optuna × 3 tree models × CV) is required.

### Also noted (Fix 2 scope, not touched)
The dead third pipeline `src/layer3_ml/train_ml_gatekeeper.py` (root) still contains its
own leaky `calculate_strategy_performance_features` (no `.shift(1)`, `fillna(0.5)`). It is
exported by `__init__` but neither trained nor served; Fix 2 will unify/delete it.

## 6d. Findings (REAL OOS re-measurement on live data — 2026-07-04) — THE HEADLINE

Run on the **actual** Layer-3 training join (2073 rows, `Is_Winner` mean 0.492). Identical
rows / chronological split (last 20% = 415 OOS rows, base win-rate 0.4578) / XGBoost config;
the **only** difference between the two runs is the leakage (leaked run executed under
`git stash` of the fix = pre-fix leaky pipeline + outcome columns; leak-free run on the
landed code). This is the real before/after the §6 synthetic numbers stood in for.

| Feature set | n_feat | PR-AUC | expectancy_unit_r @0.5 | real R (approved) | precision |
|---|---|---|---|---|---|
| **Leaked (before)**   | 56 | **1.0000** | **+1.0000** | **+0.9615R** | 1.0000 |
| **Leak-free (after)** | 50 | **0.4958** | **−0.0340**  | **−0.0469R** | 0.4830 |

- **Leaked-baseline (before):** a **literally perfect** classifier — PR-AUC 1.0, +1.0R
  expectancy, precision 1.0. `R_Multiple` and `Exit_Reason` are exact proxies for
  `Is_Winner`, so the model just reads the answer. Every previously reported gatekeeper
  metric was this.
- **Leak-free (after):** PR-AUC **0.4958 ≈ the 0.4578 base rate** (PR-AUC baseline is the
  prevalence — i.e. **chance**), expectancy **negative** (−0.034 unit-R; −0.047R real),
  precision 0.483 ≈ base rate.
- **Did the edge survive? → VANISHED.** On real data the gatekeeper has **no real
  predictive edge** once leakage is removed; the ~perfect metrics were 100% leakage. This
  is the opposite of `[[fix-s1-005-oos-uplift-not-inflated]]` (where uplift survived) and is
  exactly the adversarial outcome the brief told us to surface rather than celebrate. The
  only faint signal: approved-trade real expectancy (−0.047R) is marginally better than
  unrestricted (−0.090R), i.e. the ranking weakly avoids the worst trades — but it is still
  negative and PR-AUC is at chance. **Not deployable.**
- **The three fixes compose correctly.** With leakage gone, the leak-free model has no
  positive-expectancy operating point, so `choose_threshold` returns `None`, the candidate
  is dropped (Fix 3.2), and a strict run **fails** rather than shipping a false champion
  (Fix 3.3) — instead of the pre-fix path where a perfect-looking leaked model sailed
  through. Leakage removal (Fix 1) reveals the truth; the gates (Fix 3) refuse to promote it.

**Implication (P0):** any champion trained before Fix 1 was fit almost entirely on leaked
outcome columns and has ~no real edge — it must not be trusted or promoted. Caveats: OOS is
415 rows; this used a single untuned XGBoost, not the trainer's Optuna×3-model tournament —
tuning will not manufacture an edge from chance-level leak-free features, but the precise
leak-free number should be reproduced via the full trainer before it is treated as final.

---

## 7. Rollout

Log-only throughout. No champion promotion until: (a) all four validation tests green,
(b) OOS re-measured and written up in §6, (c) sign-off. Because this changes the feature
contract, promotion must be coordinated with Layer 4 / **FIX-S2-001** so the serve path is
updated in the same release — otherwise the live aligner will silently NaN-fill the new
contract.
