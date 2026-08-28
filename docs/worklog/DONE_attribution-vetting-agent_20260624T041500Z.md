# DONE — attribution-vetting-agent — MODEL-005

**Completed:** 2026-06-24T04:15:00Z
**Task:** MODEL-005 — Strategy Vetting & Regime Map
**Audit gate:** AG-005 — **PASS (12/12)**

## What was produced
- **`results/state/regime_strategy_map.json`** — ranked qualifying strategies per regime (non-empty): Trending-Down ×1, Ranging ×1, High-Vol ×1; **Trending-Up starved** (listed in `empty_regimes`). Ranking rule `0.5*sharpe + 0.3*pf + 0.2*recovery − maxdd`, dense ranks, full rejection_summary.
- **`results/state/strategy_weights.json`** — per-regime weights (∝ composite score), sum to 1.0.
- **`results/reports/vetting_report_*.json`** — gate pass/fail + per-cell rejection detail. MLflow run (`system1-vetting`).
- **`dim_strategy_registry.is_qualified`** updated (additive column).

## Method
Re-ran the trade loader at **10-year lookback** (134,520 trades) so OOS coverage clears the 60-month gate (was the universal blocker at 5y → 59.8mo). Re-ran MODEL-004 attribution, then applied the strict per-regime gates (PF≥1.5, Sharpe≥0.8, MaxDD≤25%, WinRate≥40%, Recovery≥3.0, OOS≥60mo; low-confidence always rejected). Strict gates honestly reject most cells — rejection_summary: pf_fail 72, sharpe_fail 67, maxdd_fail 70, winrate_fail 48, recovery_fail 72, oos_fail 0, low_confidence 2.

## AG-005 results (12/12)
boundary accept/reject (all 6 gates) ✓ · low-confidence rejected ✓ · map schema ✓ · weights schema ✓ · weights sum=1 ✓ · dense ranks ✓ · rank-1 = max composite ✓ · empty regimes listed ✓ · rejection_summary matches recompute ✓ · OOS≥60 for qualifiers ✓ · legacy aggregate vetting untouched ✓ · version+lineage present ✓

## Code
`src/system1/vetting/`: `gates.py` (6 gates + composite + ranking + weights), `vet.py` (engine, log-only/live, starvation guard, registry update, schema validation), `tests/test_gates.py` (6 tests). Contracts `contracts/{regime-map,weights}-contract.json`.

## Downstream released
MODEL-007 (serializer/registry) unblocked — has `hmm_model.joblib` (MODEL-003) + `regime_strategy_map.json` + `strategy_weights.json` (MODEL-005) + StorageBackend (built in MODEL-008).
