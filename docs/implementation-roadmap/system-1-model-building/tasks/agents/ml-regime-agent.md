# ML & Regime Agent

**Agent ID:** `ml-regime-agent`
**File:** `docs/implementation-roadmap/system-1-model-building/tasks/agents/ml-regime-agent.md`
**Role:** HMM-based market regime detection and ML gatekeeper with regime-aware dynamic thresholds.

---

## Assigned Tasks

| Task | Description | Priority | Est. Days | Prerequisites |
|------|-------------|----------|-----------|---------------|
| [MODEL-003](../03-regime-engine-hmm-upgrade.md) | Regime Engine HMM Upgrade | P1 | 5d | MODEL-002 |
| [MODEL-006](../06-ml-gatekeeper-regime-features-and-dynamic-threshold.md) | ML Gatekeeper: Regime Features & Dynamic Threshold | P2 | 4d | MODEL-003 |

---

## Skills

Before starting, load these skill files:

- `skills/hmm-semantic-mapping.md` — Gaussian HMM, state→label determinism, persistence smoothing
- `skills/layer3-contract.md` — Champion artifact contract, `ColumnTransformer` alignment, SHA256
- `skills/postgres-patterns.md` — DB connection, schema-aware writes
- `skills/point-in-time-leakage.md` — No-look-ahead feature joins
- `skills/financial-metrics.md` — Sharpe, OOS uplift significance testing

The following package must be in `requirements.txt` before starting:
```
hmmlearn>=0.3.0
```

---

## Communication With Other Agents

### Upstream (dependencies)
| Producer Agent | Consumed Artifact | Path |
|----------------|-------------------|------|
| `data-pipeline-agent` | Feature store Parquet | `feature-store/{version}/` |
| `data-pipeline-agent` | `Fact_Market_Prices` (price data) | DB |
| `data-pipeline-agent` | `schema.json` + `lineage.json` | `feature-store/{version}/` |

### Downstream (consumers of this agent's output)

| Consumer Agent | Consumes | Contract |
|----------------|----------|----------|
| `attribution-vetting-agent` | `Fact_Market_Regime_V2` (smoothed regime labels + probs) | DB schema |
| `queue-nlp-agent` | Champion manifest with dynamic thresholds | `models/champion_manifest.json` |
| `queue-nlp-agent` | `Fact_Market_Regime_V2` (regime probs at signal time) | DB schema |
| `serializer-infra-agent` | `models/hmm_model.joblib` | `contracts/hmm-serialization-contract.json` |
| `auditor-traceback-agent` | MLflow run logs, convergence metrics, OOS uplift | MLflow |

---

## Input Contracts

### MODEL-003 Inputs
- **Feature store** (`feature-store/{version}/`): Parquet files with `regime_feature_vector` columns (ATR(14), ADX, volatility_20, returns_1) per granularity D1/H4/W1.
- **Existing K-Means code**: `src/layer1_regime/Fact_market_regime_v2.py` (preserve as fallback path).
- **`Fact_Market_Regime_V2` schema**: existing columns (K-Means labels) must be preserved; new HMM columns are additive.

### MODEL-006 Inputs
- **Champion artifact contract**: `models/champion_model.pkl`, `models/champion_preprocessor.pkl`, `models/champion_manifest.json` (the existing Layer 3 contract).
- **`Fact_Signals`**: signal-level data with features.
- **`Fact_Trade_Outcomes`**: supervised labels for gatekeeper training.
- **`Fact_Market_Regime_V2`**: HMM regime probabilities at signal time (produced by MODEL-003).
- **Feature-alignment module**: `src/layer3_ml/feature_alignment.py` — ColumnTransformer with column-name tracking.

---

## Output Contracts

### MODEL-003 Outputs

1. **`Fact_Market_Regime_V2` (additive columns)**
   - `regime_model` — `'HMM'` or `'KMeans'`
   - `regime_raw` — argmax of HMM state (Trending-Up/Down, Ranging, High-Vol)
   - `regime_smoothed` — persistence-denoised (min 3 bars)
   - `prob_trending_up`, `prob_trending_down`, `prob_ranging`, `prob_high_vol` — float, sum = 1.0
   - `model_version` — version string
   - Existing K-Means columns preserved unchanged.

2. **`models/hmm_model.joblib`**
   - Contains: fitted `GaussianHMM` object, `StandardScaler`, state→label mapping dict, fixed seed value.
   - Loadable via `joblib.load()`.
   - Validated: loaded model reproduces same predictions on a test slice.

3. **MLflow run**
   - Log: HMM params (n_components=4, covariance_type, n_init), convergence log-likelihood, 4-state population counts, regime accuracy on labeled holdout.
   - Tag: `feature_set_version`, `model_version`.

### MODEL-006 Outputs

1. **`models/champion_model.pkl`** — Trained gatekeeper model (XGBoost/LightGBM).
2. **`models/champion_preprocessor.pkl`** — Fitted ColumnTransformer including regime feature columns.
3. **`models/champion_manifest.json`** — Extended with:
   ```json
   {
     "regime_features": ["prob_trending_up", "prob_trending_down", "prob_ranging", "prob_high_vol", "regime_smoothed"],
     "dynamic_thresholds": {
       "Trending-Up": 0.72,
       "Trending-Down": 0.65,
       "Ranging": 0.80,
       "High-Vol": 0.55,
       "fallback": 0.75
     },
     "oos_uplift": {
       "approved_pnl": 1234.56,
       "rejected_pnl": -89.01,
       "uplift": 1323.57,
       "p_value": 0.012,
       "significant": true
     },
     "feature_set_version": "1.0.0",
     "regime_model_version": "hmm_v1",
     "...existing fields...": "..."
   }
   ```
   - SHA256 preserved over all artifacts (existing mechanism).

4. **MLflow run** — Log: feature list (including regime features), per-regime threshold curve, OOS uplift metrics, turnover band compliance.

---

## Verification Gates (Self-Check Before Handoff)

### MODEL-003 Gates
- [ ] Fixed seed → identical state assignments across two independent runs.
- [ ] 4 distinct states populated (no state has < 1% of bars).
- [ ] Log-likelihood monotonic increase to convergence tolerance (no divergence).
- [ ] No degenerate covariance matrices (check eigenvalues > ε).
- [ ] `prob_*` columns sum to 1.0 for every row (tolerance ±1e-6).
- [ ] argmax == `regime_raw` for every row.
- [ ] `regime_smoothed` has zero segments shorter than 3 bars.
- [ ] Flicker rate (switches/bar) of `regime_smoothed` < flicker rate of `regime_raw` < flicker rate of K-Means baseline.
- [ ] Regime accuracy ≥ 70% on labeled holdout.
- [ ] Forced failure (e.g., insufficient data) triggers K-Means fallback path, sets `Regime_Model='KMeans'`, and logs the decision.

### MODEL-006 Gates
- [ ] Regime probability features flow through `ColumnTransformer` with train/inference column parity (feature-alignment test).
- [ ] No look-ahead: regime probs at signal time `t` come from `Fact_Market_Regime_V2` where `bar_time_utc <= signal_time`.
- [ ] Per-regime approval rates stay within configured turnover band (min-max from MODEL-006 args).
- [ ] OOS uplift positive and significant (p < 0.05 via bootstrap/t-test on per-trade returns).
- [ ] Missing-regime case falls back to `dynamic_thresholds.fallback`.
- [ ] Champion artifact loads under existing Layer 4 loader (preserves legacy fallback contract).
- [ ] SHA256 verification passes for all three champion files.

---

## Failure Modes & Escalation

| Failure | Detection | Action | Escalate To |
|---------|-----------|--------|-------------|
| HMM fails to converge | Log-likelihood not converged after max_iter | Fall back to K-Means, log decision, set `Regime_Model='KMeans'` | Self (fallback handled) |
| Degenerate covariance | Eigenvalue ≤ 0 | Fall back to K-Means | Self (fallback handled) |
| State relabeling on retrain | New labels don't match semantic mapping | Re-apply deterministic mapping rules, verify stability | `auditor-traceback-agent` if persistent |
| Feature alignment mismatch | ColumnTransformer input cols ≠ training cols | Rebuild preprocessor, verify feature-alignment module | Self (fix code) |
| OOS uplift not significant (p ≥ 0.05) | Bootstrap/t-test result | Block promotion, log result, do NOT update champion artifacts | `auditor-traceback-agent` (rework gatekeeper) |
| Dynamic threshold overfitting | Per-regime approval rate too narrow/samples too thin | Fall back to fallback threshold for thin regimes, constrain with turnover band | Self (handled) |
| New champion degrades vs incumbent | OOS uplift < 0 | Block promotion, log comparison, keep incumbent | `auditor-traceback-agent` |

---

## Notes

- **HMM label permutation is the #1 risk.** The deterministic state→semantic mapping must be stored in `models/hmm_model.joblib` alongside the fitted HMM. Retrains reuse this mapping — never re-derive it from scratch on new data without explicit versioning and validation.
- K-Means fallback is a first-class citizen, not dead code. MODEL-003 must keep the existing `Fact_market_regime_v2.py` code path fully functional.
- Smoothing introduces up to 3-bar lag at regime transitions — acceptable for a context signal. Document this for consumers (`attribution-vetting-agent` and `queue-nlp-agent`).
- MODEL-006 can start in parallel with MODEL-004 after MODEL-003 completes (MODEL-006 depends only on MODEL-003, not MODEL-004/005).
- The 0.20 vs 0.75 threshold gap in the current codebase is a calibration artifact. MODEL-006's per-regime calibration + OOS uplift analysis resolves which operating point is correct — do NOT hard-code either value.
