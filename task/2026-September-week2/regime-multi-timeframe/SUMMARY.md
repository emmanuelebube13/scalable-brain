# Work Order 02: Regime Multi-Timeframe (Completion Summary)

## Stage A: Parameterization (Completed)
- Parameterized the structural labeller in `src/regime/structural.py` to accept granularity and dynamically set `vol_zscore_window` to 252 (D1), 1512 (H4), and 6048 (H1). ADX(14) and EMAs remain unchanged (deliberate asymmetry).
- Updated `src/regime/build_structural.py` to loop over all active granularities (`D1`, `H4`, `H1`) and write to `fact_regime_structural`.
- Added the `--all` argument for incremental processing in `build_structural` and updated the daily/hourly cron scripts to use it.
- Bumped `LABELLER_VERSION` to `structural-v2.0.0` and made it the dynamic source of truth for consumers (serializer, attribute, gatekeeper).
- **Subagent reviews**: Leakage-hunter verified that the parameterization is fully causal and introduces no lookahead bias. DB-Guardian highlighted some missing granularity joins which were subsequently fixed in Stage B.

## Stage B: Join on Granularity (Completed)
- Updated `src/monitoring/risk_off.py` to add a `granularity` field to `Contract`. Added explicit freshness contracts for `D1` (30h), `H4` (10h), and `H1` (7h) for both canonical and live structural regime tables. Fixed the `_latest_row` check to evaluate them individually.
- Updated `REGIME_TAG_TOLERANCE_HOURS` in `src/attribution/attribute.py` to strictly mirror 1-2 bars of the corresponding granularity: `{"H1": 2, "H4": 8, "D1": 108, "W1": 504}`.
- Refactored `tag_regime_at_entry` in `attribute.py` to append `AND granularity = :g` into the SQL queries, ensuring per-granularity retrieval and reducing memory overhead.
- Fixed `run_once` and `get_current_regimes` in `src/signals/run.py` to query live regimes for all active granularities. Passed the correct regimes mapping downwards to `build_signals`.
- Updated `src/analytics/publish_regime.py` to fetch per-granularity data directly from `fact_regime_structural` instead of dynamically rebuilding from `D1`.
- Removed `d1_frame` from `build_inference_features` (Gatekeeper) and transitioned to extracting features from the `decision_frame` directly, passing its explicit granularity down to the labeller. 

## Stage C: Flip Selection (Completed)
- Flipped `AUTHORITATIVE_ENGINE_FOR_VETTING` from `None` to `"position_engine_v2"` in `src/attribution/attribute.py`.
- Flipped `SELECTION_SOURCE_LABEL` from `"regime_causal"` to `"regime_structural"` in `src/attribution/attribute.py`.
- Rebuilt the map using `python -m src.attribution.attribute --engine-version position_engine_v2` and `python -m src.vetting.vet` in log-only mode.
- Fixed a major pip-scaling defect in `xard_ma_cross_daily_open` caught by `forex-strategist` (hardcoded `EUR_USD` pip scale).

## Stage E: Retrain Gatekeeper (Completed)
- Initiated a retrain of the gatekeeper model (`python -m src.gatekeeper.train`) based on the new multi-timeframe structural regimes.

## Verification & Subagent Feedback (Critical)
- **Devils Advocate & Measurement Reviewer** discovered that the `regime_structural` tag yields almost zero qualifying strategies. The only passing strategy (`holy_grail_pullback@D1`) did so on 10 random trades.
- **Forex Strategist** demonstrated that the H1 Structural Regime acts purely as diurnal seasonality (active vs. quiet session) rather than an actual trend due to the massive 1-year H1 baseline compared to 14-period indicators.
- Given these severe degradation signals, this map and regime change MUST NOT be published or go live.

### Update: Gatekeeper Training Failure
The gatekeeper training (`src/gatekeeper/train.py`) has officially concluded with a **HARD REFUSAL**:
```
GATEKEEPER REFUSED: per-(strategy x regime) degeneracy check failed:
  77 of 81 populated (strategy x regime) cells are degenerate (approval <=0.05 or >=0.95) — 95.1% > 50% allowed. The model is discriminating on strategy identity, not market state. 
```
Because `regime_structural` provides no predictive value regarding the actual market state, the ML gatekeeper simply defaulted to memorizing the `strategy_id` instead. The system's safety guards correctly intervened, refused to write the PROPOSED champion model, and aborted. **This definitively proves the structural regime should not be shipped.**
