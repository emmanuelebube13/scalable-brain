# MODEL-006 — ML Gatekeeper: Regime Features & Dynamic Threshold

**Task ID:** MODEL-006
**System:** System 1 — Model Building
**Priority:** P2-Medium
**Estimated Effort:** 4d
**Prerequisites:** MODEL-003
**External Dependencies:**
- **`ForexBrainDB` (PostgreSQL 16 + TimescaleDB, FND-004)** — read `Fact_Signals`, `Fact_Trade_Outcomes`, `Fact_Market_Regime_V2`. Connect via `src/common/db.py`. *(DB = PostgreSQL 16 + TimescaleDB; any historical SQL-Server mention is obsolete.)*
- **`xgboost` / `lightgbm` / `scikit-learn`** — gatekeeper model + preprocessing.
- **MLflow** — log features, threshold curves, and OOS uplift metrics; version the gatekeeper model.
- **Feature store** (MODEL-002 / FND-001) — regime feature vector + HMM probabilities.

## Objective
Add HMM regime-probability features to the Layer 3 gatekeeper, introduce dynamic (regime-aware) thresholding, and add out-of-sample uplift analysis (approved vs rejected P&L).

## Current State
- `src/layer3_ml/training/train_ml_gatekeeper.py` (1755 lines) trains XGBoost/LightGBM with a `ColumnTransformer` (`src/layer3_ml/feature_alignment.py`), tournament selection, SHA256-hashed champion artifacts (`champion_model.pkl`, `champion_preprocessor.pkl`, `champion_manifest.json`), and a **single static threshold** (`LAYER3_APPROVAL_THRESHOLD=0.20` in `.env`; proposed docs mention 0.75), ~35–45% approval. No regime-probability features; no regime-aware threshold; no formal OOS uplift study.

## Target State
The gatekeeper consumes the **HMM regime-probability vector** (`prob_trending_up/down/ranging/high_vol`) and smoothed regime label from MODEL-003 as additional features. Thresholding becomes **dynamic and regime-aware**: a per-regime approval threshold (or a continuous function of regime probabilities) replaces the single static value, calibrated to maximize OOS P&L uplift subject to a turnover budget. A repeatable **OOS uplift analysis** quantifies approved-vs-rejected P&L on walk-forward folds and gates promotion. Champion artifact contract and feature alignment are preserved.

## Technical Specification

**New features (point-in-time, joined at signal time):** `prob_trending_up`, `prob_trending_down`, `prob_ranging`, `prob_high_vol`, `regime_smoothed` (one-hot or ordinal), and optionally `regime_confidence` (max prob). Joined from `Fact_Market_Regime_V2` on (instrument, granularity, signal time) with no look-ahead. Added through the existing `ColumnTransformer`/feature-alignment path so train/inference columns stay aligned.

**Dynamic threshold:** replace the single `LAYER3_APPROVAL_THRESHOLD` with a **regime-aware threshold map** `{regime: threshold}` (and/or a function `threshold(regime_probs)`), stored in the champion manifest and consumed at scoring time (MODEL-008). Thresholds are calibrated per regime on validation folds to maximize net OOS P&L while keeping approval within a configured turnover band (preserves the current min/max turnover gates). A global fallback threshold remains for missing-regime cases.

**OOS uplift analysis:** on walk-forward OOS folds, compute the P&L of **approved** signals vs the counterfactual P&L of **rejected** signals (and vs all signals). Report uplift = approved-set net return minus baseline, plus a significance test (e.g., bootstrap/t-test on per-trade returns, p<0.05). This becomes a **deployment gate**: a new gatekeeper must show non-negative, significant uplift over the incumbent on OOS before promotion (feeds MODEL-009 gates).

**Artifacts / manifest:** extend `champion_manifest.json` with `regime_features` list, `dynamic_thresholds` map, `oos_uplift` metrics, feature-set + regime-model versions, and SHA256 (existing integrity mechanism). Champion/legacy fallback contract for downstream loading is preserved.

**Data flow (text):** assemble training frame (signals + outcomes + MODEL-002 features + MODEL-003 regime probs) → train/tournament-select model → calibrate per-regime thresholds on validation → run OOS uplift study on holdout folds → if uplift gate passes, write champion artifacts with dynamic thresholds → log all to MLflow.

## Testing & Validation
- **Feature join test:** regime probs joined at signal time without look-ahead; one-hot/ordinal encoding stable across train/inference (feature-alignment test).
- **Threshold calibration test:** per-regime thresholds reproduce the intended approval/turnover band; missing-regime falls back to global threshold.
- **OOS uplift:** walk-forward (≥ multiple folds; OOS horizon consistent with MODEL-005's ≥60-month philosophy), uplift positive and significant (p<0.05); no leakage between folds.
- **Regression:** approval rate stays within an operationally sane band; champion artifact loads under the existing loader; SHA256 verifies.
- **Edge cases:** regime missing for a signal, near-uniform regime probabilities, a regime with too few samples to calibrate (use global threshold).

## Rollback Plan
Dynamic thresholds default-fall-back to the existing static `LAYER3_APPROVAL_THRESHOLD` if the threshold map is absent — so reverting is a config/manifest change, not a retrain. Regime features can be disabled via the feature list; the previous champion artifact remains loadable. No change to the artifact handoff contract.

## Acceptance Criteria
- [ ] HMM regime-probability features are added through the existing feature-alignment/`ColumnTransformer` path with no look-ahead.
- [ ] A regime-aware dynamic threshold map replaces the single static threshold, with a global fallback, stored in `champion_manifest.json`.
- [ ] OOS uplift analysis (approved vs rejected P&L) is produced on walk-forward folds with a significance test and acts as a promotion gate.
- [ ] Champion artifact contract (model/preprocessor/manifest + SHA256) and legacy fallback are preserved.
- [ ] All features, thresholds, and uplift metrics are versioned in MLflow.

## Notes & Risks
- Dynamic thresholds risk overfitting per-regime to noise in thin regimes — constrain with the turnover band, require OOS significance, and fall back to global where samples are thin.
- The proposed-doc 0.75 vs current 0.20 threshold gap signals miscalibration; the per-regime calibration plus uplift study should resolve which operating point is correct rather than hard-coding either.
- Keep MODEL-006 strictly upstream of scoring (MODEL-008) — the threshold map travels in the manifest so scoring stays deterministic.
