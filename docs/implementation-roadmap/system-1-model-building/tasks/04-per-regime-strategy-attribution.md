# MODEL-004 — Per-Regime Strategy Attribution

**Task ID:** MODEL-004
**System:** System 1 — Model Building
**Priority:** P1-High
**Estimated Effort:** 3d
**Prerequisites:** MODEL-003
**External Dependencies:**
- **`ForexBrainDB` (PostgreSQL 16 + TimescaleDB, FND-004)** — read `Fact_Market_Regime_V2` (regime labels/probabilities) and trade/backtest outcomes; write attribution. Connect via `src/common/db.py`. *(DB = PostgreSQL 16 + TimescaleDB; any historical SQL-Server mention is obsolete.)*
- **MLflow** — log per-regime attribution metrics per qualification run.

## Objective
Extend Layer 0 vetting (`src/layer0/qualify_strategies.py`) with per-regime performance attribution so each strategy gets win-rate/PF/Sharpe per regime.

## Current State
- `src/layer0/qualify_strategies.py` (1105 lines) backtests 6 strategy families / 18 variants and vets on **aggregate** metrics only: positive expectancy, ≥20 trades, ~1.15 profit factor. Helper metrics live in `src/layer0/strategy_analyzer.py`. There is **no per-regime attribution** — a strategy good only in Ranging looks the same as one good across all regimes.

## Target State
Each backtested trade is tagged with the **market regime in force at entry** (from MODEL-003's `Fact_Market_Regime_V2`, using the smoothed label and probabilities). Layer 0 then computes, **per strategy × per regime**, the core metrics — **win-rate, profit factor, Sharpe** (plus trade count, expectancy, MaxDD for completeness). This per-regime attribution table is the input contract for the MODEL-005 vetting gate and regime→strategy map. Aggregate vetting still runs (backward compatible).

## Technical Specification

**Regime tagging (point-in-time):** for each backtest trade, join the entry timestamp to the regime label active **at or before entry** for the matching instrument/granularity in `Fact_Market_Regime_V2` (4 states: Trending-Up, Trending-Down, Ranging, High-Vol). Use `regime_smoothed`; retain entry probability vector for confidence weighting. No future regime is used (must reflect what was known at entry).

**Per-cell metrics (strategy × regime):**
- `win_rate` = winning trades / total trades in cell.
- `profit_factor` = gross profit / gross loss in cell.
- `sharpe` = annualized mean/std of per-trade (or per-period) returns in cell.
- Supporting: `trade_count`, `expectancy`, `max_drawdown`, `avg_R`.

**Small-sample handling:** cells with `trade_count < N_min` (configurable, e.g. 20) are flagged `low_confidence=true`; apply Bayesian shrinkage of the cell metric toward the strategy's global metric so sparse regimes don't produce extreme, unreliable numbers. Never let a low-confidence cell alone qualify a strategy (enforced in MODEL-005).

**Output schema:** an attribution table/artifact `Fact_Strategy_Regime_Attribution` (or a Parquet artifact) keyed by (`Strategy_Id`/variant, `Regime`, `Granularity`, `Instrument`-or-portfolio) with the metric columns above plus `low_confidence`, `model_version` (regime model from MODEL-003), and `qualification_run_id` lineage. Emitted alongside the existing qualification reports in `results/`.

**Backward compatibility:** existing aggregate vetting (expectancy/20-trade/PF) continues to run and report; per-regime attribution is additive. Granularity (H1/H4/D1) preserved.

**Data flow (text):** run backtests (existing engine) → for each trade, look up entry regime from `Fact_Market_Regime_V2` → group trades by (strategy, regime) → compute metrics + shrinkage + low-confidence flags → persist attribution table + report → log to MLflow.

## Testing & Validation
- **Unit:** regime-at-entry lookup (no look-ahead; picks the label active at/just before entry), per-cell metric math against fixtures, shrinkage formula, low-confidence flagging at the `N_min` boundary.
- **Consistency:** sum of per-regime trade counts == aggregate trade count; weighted per-regime metrics reconcile with aggregate within tolerance.
- **Statistical:** for cells with adequate samples, report confidence intervals on win-rate/PF; verify Sharpe annualization factor matches bar granularity.
- **Edge cases:** strategy never traded in a given regime (cell absent, not zero-padded misleadingly), all trades in one regime, regime label missing for some entries (handled/flagged, not dropped silently).

## Rollback Plan
Purely additive analytics. Roll back by disabling the attribution step (config flag); Layer 0 reverts to aggregate-only vetting with no change to existing outputs. Attribution artifacts/tables can be dropped without affecting any other layer.

## Acceptance Criteria
- [ ] Every backtest trade is tagged with the point-in-time entry regime from `Fact_Market_Regime_V2`.
- [ ] Per strategy × regime, win-rate, profit factor, and Sharpe (plus trade count, expectancy, MaxDD) are computed and persisted.
- [ ] Cells below `N_min` trades are flagged low-confidence and shrunk toward global metrics.
- [ ] Per-regime trade counts reconcile with aggregate counts; attribution carries regime-model + run lineage.
- [ ] Existing aggregate vetting still runs unchanged (backward compatible).

## Notes & Risks
- Small-sample bias is the dominant risk — many strategy×regime cells will be thin; shrinkage + low-confidence flags are mandatory, and MODEL-005 must not promote on a thin cell alone.
- Regime smoothing lag (MODEL-003) slightly shifts the entry-regime tag at transitions; acceptable and documented.
- Requires `Fact_Market_Regime_V2` coverage over the full backtest history — depends on MODEL-003 having labeled the backfilled range.
