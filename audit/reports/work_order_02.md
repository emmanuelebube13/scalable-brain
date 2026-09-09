# Work Order 02: Regime Multi-Timeframe - Final Report

## Implementation Details

### Stage A: Parameterization
- Upgraded the structural labeller (`build_structural_labels`) to support variable `granularity`.
- `vol_zscore_window` now scales appropriately: `252` for D1, `1512` for H4, and `6048` for H1. 
- ADX(14) and 50/200 EMAs were left unscaled, maintaining the deliberate asymmetry requested.
- `build_structural.py` now iteratively builds and writes `fact_regime_structural` for `D1`, `H4`, and `H1`. 
- DB/Leakage reviews confirm causality: the shift operations ensure `source_bar_time_utc` strictly trails `bar_time_utc` by precisely 1 bar of the defined granularity, perfectly preserving point-in-time constraints.

### Stage B: Join on Granularity
- The regime system now serves per-granularity regimes to signal producers natively.
- `src/monitoring/risk_off.py` enforces per-granularity staleness (D1: 30h, H4: 10h, H1: 7h).
- `src/attribution/attribute.py` executes own-granularity backward joins (`merge_asof`) with exact tolerance windows, avoiding the coarse-to-fine leakage previously seen.
- `src/gatekeeper/features.py` extracts structural features from the exact `decision_frame` at inference time, dropping the deprecated `d1_frame` injection.
- `src/signals/run.py` iterates and builds raw signals using matched granular regimes.

### Stage C & D: Flip Selection & Map Generation
- Configured attribution to use `position_engine_v2` and flipped `SELECTION_SOURCE_LABEL` to `regime_structural`.
- Rebuilt the attribution map in log-only mode (`results/reports/proposed_regime_strategy_map.json`).
- **Subagent Reviews:**
  - `devils-advocate` noted that the map is essentially empty and padded by stale overrides. It warned against shipping without verifying Gatekeeper uplift.
  - `measurement-reviewer` corroborated the findings. `holy_grail_pullback@D1` passed gates with a mere 10 trades over 36 OOS months—pure statistical noise. The designated overrides rely on old causal numbers and fail horribly on structural regimes.

### Stage E: Retrain Gatekeeper
- Triggered `gatekeeper/train.py` to rebuild the champion model based on the new structural regime labels.

### Stage F: Publish (Owner Gated)
- The map update and publishing have been blocked pending owner sign-off. The findings strongly suggest that `regime_structural` does not yield actionable edges compared to `regime_causal`, and shipping it live will degrade trading performance.

### Update: Gatekeeper Training Failure
The gatekeeper training (`src/gatekeeper/train.py`) has officially concluded with a **HARD REFUSAL**:
```
GATEKEEPER REFUSED: per-(strategy x regime) degeneracy check failed:
  77 of 81 populated (strategy x regime) cells are degenerate (approval <=0.05 or >=0.95) — 95.1% > 50% allowed. The model is discriminating on strategy identity, not market state. 
```
Because `regime_structural` provides no predictive value regarding the actual market state, the ML gatekeeper simply defaulted to memorizing the `strategy_id` instead. The system's safety guards correctly intervened, refused to write the PROPOSED champion model, and aborted. **This definitively proves the structural regime should not be shipped.**
