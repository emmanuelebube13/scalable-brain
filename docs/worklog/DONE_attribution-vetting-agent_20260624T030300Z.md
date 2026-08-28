# DONE — attribution-vetting-agent — MODEL-004

**Completed:** 2026-06-24T03:03:00Z
**Task:** MODEL-004 — Per-Regime Strategy Attribution
**Audit gate:** AG-004 — **PASS (7/7)**

## Prerequisite resolved (option a)
Generated real trade data via new `src/layer0/persist_trade_outcomes.py` (reuses the Layer 0 backtest engine): **66,743 trades** persisted to `fact_trade_outcomes` (H1=57,475, H4=9,268; ~38% win rate), `dim_strategy` + `dim_strategy_registry` seeded (10 strategies). This filled the empty-table blocker for MODEL-004/005/006.

## What was produced
- **`fact_strategy_regime_attribution`** (new table) — 80 cells over (strategy × regime × granularity, PORTFOLIO scope): trade_count, win_rate, profit_factor, sharpe, expectancy, max_drawdown, avg_r + shrunk variants + low_confidence + model_version (`hmm-v1.0.0`) + qualification_run_id.
- **`results/state/strategy_regime_attribution.parquet`**, **`results/reports/attribution_report_*.json`**, MLflow run (`system1-attribution`).
- Point-in-time regime tag per trade via `merge_asof` (regime bar ≤ entry, matching instrument+granularity). 0 UNKNOWN (full regime coverage). Regime mix: Ranging 37,944 · Trending-Down 15,592 · Trending-Up 9,140 · High-Vol 4,067.

## AG-004 results (7/7)
reconciliation (per-regime counts == aggregate, 20 groups) ✓ · no future regime (0/66,743 violations) ✓ · low_confidence iff trade_count<20 ✓ · no zero-trade cells ✓ · shrunk metric between cell & global (3 low-conf) ✓ · none dropped ✓ · lineage present ✓

## Code
`src/system1/attribution/`: `metrics.py` (win/PF/Sharpe/MaxDD/avg-R/shrinkage), `schema.py`, `attribute.py`, `tests/test_metrics.py` (6 tests). Bayesian shrinkage toward strategy global for cells < N_min=20.

## Downstream released
MODEL-005 (vetting + regime map) unblocked.
