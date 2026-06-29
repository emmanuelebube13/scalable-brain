# FIX-S2-001 — Live ML gatekeeper scores every signal on an all-NaN feature vector against the wrong threshold (champion-artifact contract break)

**Severity:** P0 (the single most important pre-trade gate is non-functional in the live path)
**Status:** Proposed
**Author:** Claude (System-2 audit)
**Date raised:** 2026-06-26
**Scope:** `src/layer4_executor/live_pipeline.py` (manifest loader, signal query, feature prep) ↔ `models/champion_manifest.json` + `champion_preprocessor.pkl` (System-1 gatekeeper output) + `src/layer3_ml/feature_alignment.py`
**Affected pipeline:** System-1 gatekeeper (MODEL-007 champion bundle) → Layer 4 Stage 2 ML gatekeeper → broker execution
**Risk to live trading:** High — the gate that is supposed to filter low-quality signals is making decisions on empty inputs at an uncalibrated threshold.

---

## 1. Executive summary

Layer 4's ML gatekeeper (Stage 2, the gate immediately before risk sizing and order
placement) does **not** run the champion model the way System 1 trained and calibrated it.
Three independent contract mismatches stack up so that, in the live path, the XGBoost
gatekeeper is handed a feature row that is **entirely NaN** and is thresholded at a **flat
0.20** instead of the calibrated **per-regime 0.45–0.60**. The model therefore emits a
near-constant score and the gate is effectively inert. This is not a tuning problem; the two
systems disagree on the artifact contract.

---

## 2. Evidence (code + real artifacts)

**(a) The champion manifest is silently rejected by Layer 4.**
`load_model_manifest` requires six fields (`live_pipeline.py:733-741`):
```python
required_fields = ["model_type","artifact_path","preprocessor_path","threshold","feature_columns","run_id"]
```
The shipped `models/champion_manifest.json` (System-1 output, created 2026-06-24) contains
**none of `artifact_path`, `preprocessor_path`, `threshold`, `feature_columns`, `run_id`**.
Recomputed:
```
Layer4 required-but-missing manifest fields: ['artifact_path','preprocessor_path','threshold','feature_columns','run_id']
=> load_model_manifest returns: None
manifest keys present: ['model_type','schema_version','features','regime_features',
 'dynamic_thresholds','turnover_band','oos_uplift','regime_model_version',
 'feature_set_version','n_train','created_at_utc','sha256']
```
So `load_model_artifact` falls through to the stable-alias branch (`live_pipeline.py:813-839`),
discarding everything the manifest carried.

**(b) The threshold collapses to a flat env value.**
On the fallback path `threshold = float(os.getenv("LAYER3_APPROVAL_THRESHOLD","0.82"))`
(`live_pipeline.py:834`); `.env` sets `0.20`. The manifest's calibrated
`dynamic_thresholds` are **ignored**:
```
High-Vol 0.55 · Ranging 0.60 · Trending-Down 0.45 · Trending-Up 0.50 · fallback 0.60
```
Live therefore approves at 0.20 against a gate calibrated at 0.45–0.60 — a completely
different operating point than the one whose OOS uplift (`oos_approval_rate: 0.2956`) was
measured.

**(c) Every model feature arrives as NaN (name/pipeline mismatch).**
The preprocessor's required inputs (`champion_preprocessor.pkl.feature_names_in_`, all
lowercase snake_case):
```
atr_value, adx_value, prob_trending_up, prob_trending_down, prob_ranging, prob_high_vol,
volatility_regime, trending_strength, adx_over_atr, regime_smoothed, strategy_id, entry_signal_type
```
Layer 4's signal query selects **mixed-case** aliases (`ATR_Value`, `ADX_Value`,
`Strategy_ID`, …, `live_pipeline.py:529-530,572`) and **never selects** `prob_trending_up/down/
ranging/high_vol`, `regime_smoothed`, `trending_strength`, `adx_over_atr`, or
`entry_signal_type` (grep over the file finds only `Volatility_Regime`). `align_features_for_inference`
matches **case-sensitively** and fills any non-match with NaN (`feature_alignment.py:268-274`):
```python
for col in expected_columns:
    if col in df.columns: result[col] = df[col]
    else:                 result[col] = np.nan   # ATR_Value != atr_value → NaN
```
Result: all 12 features (including the ones Layer 4 *does* have, e.g. `atr_value`, lost to the
casing difference) are NaN. XGBoost tolerates NaN, so nothing raises — the model just scores a
blank row. The post-alignment guard at `live_pipeline.py:1184` passes because the frame now has
exactly the 12 expected names (all NaN).

---

## 3. Root cause

System 1's champion bundle and Layer 4's consumer were written against **different contracts**:
- **Manifest schema** drifted (`features`/`dynamic_thresholds`/`sha256` vs the loader's
  `feature_columns`/`threshold`/`artifact_hash` + `artifact_path`/`preprocessor_path`/`run_id`).
- **Feature contract** drifted: System 1 trained on a 12-column lowercase snake_case vector
  produced by its own feature pipeline; Layer 4 re-derives features with a *different* pipeline
  (`safe_comprehensive_feature_engineering`) that emits mixed-case names and omits the regime
  probability/derived columns entirely.
- **Threshold semantics** drifted: per-regime dynamic thresholds vs a single env scalar.

Each mismatch is silent (logged at WARNING/none), so the pipeline "runs" while the gate is dead.

---

## 4. Proposed fix

1. **Reconcile the manifest contract.** Teach `load_model_manifest` to read the System-1
   schema (`features` → feature list; `dynamic_thresholds` → per-regime thresholds with
   `fallback`; `sha256[champion_model.pkl]` → hash), or have System 1 also emit the legacy
   field names. Fail **loudly** (non-zero exit) when a champion bundle is present but
   unreadable, instead of falling back to env defaults.
2. **Honour per-regime thresholds.** Select the threshold by the row's `Regime_Label`
   (`dynamic_thresholds[regime]`, else `fallback`) rather than a flat env scalar.
3. **Fix the feature contract.** Either (a) select the model's exact features in the SQL using
   their trained snake_case names (add `prob_*`, `regime_smoothed`, `volatility_regime`,
   `trending_strength`, `adx_over_atr`, `entry_signal_type`, lowercase `atr_value/adx_value/
   strategy_id`) and skip Layer 4's divergent feature engineering, or (b) make
   `align_features_for_inference` case-insensitive **and** add the missing regime-probability
   columns to the query. Option (a) is preferred — reuse System 1's feature builder so there is
   one feature pipeline, not two.
4. **Add a non-NaN assertion.** Fail the gatekeeper call if >X% of the transformed feature row
   is NaN, so an empty-feature regression can never silently ship.

---

## 5. Validation plan

1. Load the champion bundle through the fixed loader; assert it reads model_type=xgboost,
   12 features, and the five regime thresholds (no fallback to env).
2. Pull one real H4 signal joined to its point-in-time regime row; build the feature frame and
   assert **0 NaN** across the 12 model inputs; assert the score varies across ≥20 distinct
   signals (not constant).
3. Diff approval rate at the calibrated per-regime thresholds vs the old flat 0.20 on a batch;
   expect it to move toward the manifest's `oos_approval_rate ≈ 0.296`.

---

## 6. Rollout / risk

Read/contract-only change plus a query edit; no schema migration. Roll out behind `--dry-run`
first and compare approval distributions. Reversible. **Until fixed, do not trust any live or
dry-run "APPROVED"/"VETOED_MODEL" decision** — they are produced from blank inputs.

---

## 7. One-paragraph summary

Layer 4's champion-manifest loader requires fields (`feature_columns`, `threshold`,
`artifact_path`, `preprocessor_path`, `run_id`) that the System-1 champion manifest does not
contain (it ships `features`, `dynamic_thresholds`, `sha256`), so the manifest is silently
rejected and the pipeline falls back to a flat `LAYER3_APPROVAL_THRESHOLD=0.20` instead of the
calibrated per-regime 0.45–0.60. Worse, the model's 12 trained inputs are lowercase snake_case
(`atr_value`, `prob_trending_up`, `regime_smoothed`, …) while Layer 4 produces mixed-case names
and never even queries the regime-probability features, so the case-sensitive aligner fills
**all 12 with NaN**. The XGBoost gatekeeper therefore scores every live signal on an empty row
at the wrong threshold — the pre-trade ML gate is effectively non-functional. Fix by reconciling
the manifest/feature/threshold contract (ideally reuse System 1's single feature pipeline) and
asserting non-NaN inputs so this can never silently recur.
