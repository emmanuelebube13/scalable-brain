# MODEL-003 — Regime Engine HMM Upgrade

**Task ID:** MODEL-003
**System:** System 1 — Model Building
**Priority:** P1-High
**Estimated Effort:** 5d
**Prerequisites:** MODEL-002
**External Dependencies:**
- **`hmmlearn`** — Gaussian HMM implementation (EM/Baum-Welch + Viterbi).
- **`ForexBrainDB` (PostgreSQL 16 + TimescaleDB, FND-004)** — destination `Fact_Market_Regime_V2` (probabilistic columns added); write via `src/common/db.py`. *(DB = PostgreSQL 16 + TimescaleDB; any historical SQL-Server mention is obsolete.)*
- **MLflow** — log HMM params, convergence, and regime-accuracy metrics; version the regime model.
- **Feature store** (MODEL-002 / FND-001) — source of the regime feature vector.

## Objective
Add a 4-state Gaussian HMM regime detector (Trending-Up, Trending-Down, Ranging, High-Vol) with probabilistic outputs and persistence smoothing (min 3 bars), alongside the existing K-Means as fallback.

## Current State
- `src/layer1_regime/Fact_market_regime_v2.py` (715 lines) runs **K-Means on ATR+ADX**, emits **hard** H1/H4 labels to `Fact_Market_Regime_V2` via `INSERT … ON CONFLICT`, with silhouette validation and deterministic label mapping. No probabilities, no temporal model, no persistence smoothing — labels can flicker bar-to-bar.

## Target State
A **4-state Gaussian HMM** consuming the MODEL-002 regime feature vector, producing for each bar: the most-likely regime, the **full 4-way probability vector**, and a **persistence-smoothed** label that suppresses regime changes lasting fewer than **3 bars**. The four states map deterministically to **Trending-Up, Trending-Down, Ranging, High-Vol**. K-Means is **retained as a fallback** path (used when the HMM fails convergence/quality gates). Granularity contracts (H1/H4) are preserved; D1 is added as the primary modeling granularity. The fitted HMM is serialized for MODEL-007.

## Technical Specification

**Model:** Gaussian HMM, `n_components=4`, full or diagonal covariance, multiple random restarts with a **fixed seed** for reproducibility, EM until log-likelihood convergence (tolerance + max-iter). Inputs = the standardized regime feature vector from MODEL-002 (e.g., `atr_14`, ADX, `volatility_20`, `returns_1`).

**Deterministic state→label mapping:** raw HMM states are unordered; map them to semantic labels by state statistics — e.g., highest mean `volatility_20`/`atr_14` → **High-Vol**; low directional drift + low vol → **Ranging**; positive mean `returns_1` with directional persistence → **Trending-Up**; negative → **Trending-Down**. Mapping rules are explicit and stored with the model so labels are stable across retrains.

**Probabilistic outputs:** posterior state probabilities (`predict_proba`) per bar → columns `prob_trending_up`, `prob_trending_down`, `prob_ranging`, `prob_high_vol` (sum to 1). The argmax gives the raw label.

**Persistence smoothing (min 3 bars):** post-process the raw label sequence so a new regime is only accepted once it persists ≥ 3 consecutive bars; otherwise the prior regime is held. Emit both `regime_raw` and `regime_smoothed`. Document the smoothing as a deterministic state machine (debounce), not a future-aware filter.

**Schema (additive, `Fact_Market_Regime_V2`):** add `Regime_Model` ('HMM' | 'KMeans'), `Regime_Raw`, `Regime_Smoothed`, `Prob_Trending_Up`, `Prob_Trending_Down`, `Prob_Ranging`, `Prob_High_Vol`, `Model_Version`. Preserve existing columns and the `INSERT … ON CONFLICT` upsert pattern. Granularity (`H1`/`H4`/`D1`) preserved.

**Fallback contract:** if the HMM fails a quality gate (no convergence, degenerate covariance, regime accuracy below threshold, or fewer than 4 effective states), fall back to the existing K-Means path and set `Regime_Model='KMeans'`. The fallback decision is logged. Downstream consumers (MODEL-004/006) read probabilities when present and tolerate the fallback (probabilities may be one-hot for K-Means).

**Serialization:** export the fitted HMM (+ scaler + label-mapping rules) as `hmm_model.joblib` for MODEL-007; record `Model_Version` and metrics in MLflow.

**Pseudo-code (clarifying only):**
```
X = load_regime_features(granularity)            # from MODEL-002 store
hmm = GaussianHMM(n_components=4, seed=FIXED, n_init=K).fit(X)
if not converged(hmm) or degenerate(hmm): return kmeans_fallback(X)
raw = hmm.predict(X); proba = hmm.predict_proba(X)
labels = map_states_to_semantics(hmm)            # deterministic, stored
smoothed = debounce(raw, min_bars=3)
upsert(Fact_Market_Regime_V2, {raw, smoothed, proba, model='HMM'})   # INSERT … ON CONFLICT
serialize(hmm + scaler + mapping -> hmm_model.joblib)
```

## Testing & Validation
- **Convergence/quality:** assert log-likelihood monotonic increase to tolerance; reject degenerate covariances; verify 4 distinct, populated states.
- **Reproducibility:** fixed seed → identical state assignments across runs.
- **Persistence:** assert no `regime_smoothed` segment shorter than 3 bars; flicker rate (regime switches/bar) materially lower than raw and lower than K-Means baseline.
- **Accuracy:** on a labeled/heuristic holdout, regime classification accuracy ≥ 70%; compare HMM vs K-Means baseline (transition stability, separation).
- **Probabilities:** rows sum to 1; argmax == `regime_raw`.
- **Fallback:** force a failure (e.g., insufficient data) → K-Means path runs and labels written with `Regime_Model='KMeans'`.
- **Edge cases:** low-data granularity, regime present in history but rare, all-one-regime windows.

## Rollback Plan
K-Means remains the proven fallback and is never removed. Roll back by forcing `Regime_Model='KMeans'` (config flag) so the engine reverts to current behavior; new probabilistic columns are additive and ignorable. Previous `Fact_Market_Regime_V2` rows can be restored by re-running the K-Means path for the affected range.

## Acceptance Criteria
- [ ] 4-state Gaussian HMM produces semantic labels (Trending-Up/Down, Ranging, High-Vol) with per-bar probability vectors summing to 1.
- [ ] Persistence smoothing enforces a minimum 3-bar regime duration; flicker rate is lower than the K-Means baseline.
- [ ] HMM passes convergence + ≥70% regime-accuracy gates; otherwise the K-Means fallback runs automatically and is logged.
- [ ] `Fact_Market_Regime_V2` receives additive probabilistic columns via the existing `INSERT … ON CONFLICT` pattern, preserving H1/H4 and adding D1.
- [ ] Fitted HMM (+ scaler + label mapping) serialized as `hmm_model.joblib` and versioned in MLflow for MODEL-007.

## Notes & Risks
- HMM label permutation is the classic trap — the deterministic state→semantic mapping must be stored and reused, or retrains will relabel states and break downstream maps.
- Smoothing introduces a small acceptance lag (up to 3 bars) at regime transitions — acceptable for a context signal, documented for consumers.
- Keep the K-Means path as a first-class citizen, not dead code, so fallback is always viable.
