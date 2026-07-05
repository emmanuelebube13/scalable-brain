# DONE — MODEL-006 (ML Gatekeeper: Regime Features & Dynamic Threshold)

**Agent:** ml-regime-agent
**Completed (UTC):** 2026-06-24T23:58:43Z
**Audit:** AG-006 PASS 9/9 (self-audited as orchestrator-auditor).

## What was produced
- **`models/champion_model.pkl`** — XGBoost gatekeeper (GridSearchCV-selected: lr=0.03, max_depth=5, n_estimators=200, subsample=0.7), trained on 134,520 backtested trades (`fact_trade_outcomes`, win rate 0.384), `scale_pos_weight` for class imbalance.
- **`models/champion_preprocessor.pkl`** — fitted `ColumnTransformer` (12 input cols): StandardScaler over numeric+derived `[atr_value, adx_value, prob_trending_up/down/ranging/high_vol, volatility_regime, trending_strength, adx_over_atr]`, OneHotEncoder(handle_unknown="ignore") over `[regime_smoothed, strategy_id, entry_signal_type]`.
- **`models/champion_manifest.json`** — features, `regime_features`, `dynamic_thresholds` (per-regime + fallback), `turnover_band [0.05, 0.60]`, `oos_uplift`, `feature_set_version=1.0.0`, `regime_model_version=hmm-v1.0.0`, SHA256 of model+preprocessor.
- **MLflow run** `8d63aa5be05642da877715c0da2169d0` (experiment `system1-gatekeeper`): logged features, regime_features, turnover_band, oos_uplift / p_value / approval_rate.

## Method
- **Point-in-time join** (no look-ahead): trades joined to `fact_market_regime_v2` via `merge_asof(direction="backward")` so every regime bar_time ≤ trade entry_time (verified 0/134520 violations).
- **Regime-aware dynamic threshold:** per-regime threshold calibrated on each fold's validation set to maximize mean approved `r_multiple` within the turnover band; global `fallback` for thin/missing regimes.
  - High-Vol 0.55, Ranging 0.60, Trending-Down 0.45, Trending-Up 0.50, fallback 0.60.
- **OOS uplift study:** 5-fold expanding-window walk-forward. Aggregated OOS approved vs rejected per-trade `r_multiple`, bootstrap permutation test (20k).
  - **uplift = 0.031902, p = 0.0001, significant = True**, OOS approval 29.6% (n_approved 33,134 / n_rejected 78,966) — within band, non-degenerate (promotion gate passes).
- **Champion contract & legacy fallback preserved** (model/preprocessor/manifest triad + SHA256); Layer 4 loader unchanged.

## Note on re-run
Prior-session artifacts were stale relative to committed `train.py` (manifest `n_folds=3` vs code `N_FOLDS=5`). Re-ran `python -m src.system1.gatekeeper.train` so committed code reproduces the artifacts; manifest now `n_folds=5`, SHA256 verified.

## AG-006 (9/9 PASS)
1. Feature alignment: ColumnTransformer in-cols == training == manifest (12). 2. No look-ahead (0 violations). 3. Per-regime approval in [0.05,0.60] (HV 0.38 / Rng 0.30 / TrDn 0.55 / TrUp 0.43). 4. OOS uplift +0.0319, p=0.0001, significant. 5. Missing-regime → fallback 0.60. 6. Champion triad loads, predict_proba OK. 7. SHA256 verifies (model+preprocessor). 8. MLflow run has all 6 required fields. 9. Degenerate refusal functional.
