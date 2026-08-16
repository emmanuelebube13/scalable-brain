# T3 — Re-score and sync the live map

## Before/After Map Comparison

| Metric | Before (Stale 08-01 run) | After (Live 08-15 run) |
|---|---|---|
| `generated_at_utc` | `2026-08-14T10:50:48Z` | `2026-08-15T09:36:22.110308+00:00` |
| `qualification_run_id` | `47fa3bd0-8f42-47f8-a59a-9c5dc9329b03` | `4f608511-72f2-4451-87c4-956619f80ead` |
| Cells scored | 80 | 40 |
| Qualifiers | 0 | 0 |
| `rejection_summary` | `{'pf_fail': 72, 'sharpe_fail': 72, 'maxdd_fail': 53, 'winrate_fail': 47, 'recovery_fail': 72, 'oos_fail': 7, 'low_confidence_fail': 0, 'integrity_fail': 8}` | `{'pf_fail': 36, 'sharpe_fail': 36, 'maxdd_fail': 16, 'winrate_fail': 23, 'recovery_fail': 35, 'oos_fail': 11, 'low_confidence_fail': 0, 'integrity_fail': 4}` |

## Commands Run

```bash
# 1. Capture pre-state
cp results/state/regime_strategy_map.json /tmp/map_before.json
cp results/state/strategy_weights.json    /tmp/weights_before.json

psql -h localhost -p 5432 -U sa -d ForexBrainDB -A -F'|' \
  -c "SELECT count(*), min(timestamp), max(timestamp) FROM fact_trade_outcomes;" \
  -c "SELECT qualification_run_id, count(*), max(created_at) FROM fact_strategy_regime_attribution GROUP BY 1 ORDER BY 3 DESC LIMIT 5;" \
  -c "SELECT count(*) FROM dim_strategy_registry WHERE is_qualified;" \
  > /tmp/t3_before.txt

# 2. Back up the live map
cp results/state/regime_strategy_map.json results/state/regime_strategy_map.json.bak-20260815-pre-t3
cp results/state/strategy_weights.json    results/state/strategy_weights.json.bak-20260815-pre-t3

# 3. Re-run attribution
python -m src.system1.attribution.attribute 2>&1 | tee logs/t3_attribution_20260815.log

# 4. Run vetting in preview mode
python -m src.system1.vetting.vet 2>&1 | tee logs/t3_vetting_preview_20260815.log

# 5. Run vetting with --live
python -m src.system1.vetting.vet --live 2>&1 | tee logs/t3_vetting_live_20260815.log
```

## Attribution Report
- **Path:** `/home/emmanuel/Documents/Scalable_Brain/scalable-brain/results/reports/attribution_report_20260815T093601Z.json`
- **n_trades:** 55756
- **n_oos_trades:** 38610
- **n_cells:** 40
- **reconciliation_ok:** True

## Vetting Reports
- **Preview Run Path:** `/home/emmanuel/Documents/Scalable_Brain/scalable-brain/results/reports/proposed_regime_strategy_map.json`
- **Live Run Path:** `/home/emmanuel/Documents/Scalable_Brain/scalable-brain/results/state/regime_strategy_map.json`

## Verification Checks

| # | Check | Pass/Fail | Actual Value |
|---|---|---|---|
| 1 | map `generated_at_utc` later than 2026-08-15T02:28:13Z | Pass | `2026-08-15T09:36:22.110308+00:00` |
| 2 | attribution determinism (step 3's cells/trades/OOS identical to run 29709fc8) | Pass | cells: 40, trades: 55756, OOS: 38610 |
| 3 | map `qualification_run_id` equals step 3's new run_id | Pass | `4f608511-72f2-4451-87c4-956619f80ead` |
| 4 | `n_qualifying` | Pass | 0 |
| 5 | `empty_regimes` | Pass | `['Trending-Up', 'Trending-Down', 'Ranging', 'High-Vol']` |
| 6 | live vs proposed identical apart from `generated_at_utc` | Pass | True |
| 7 | registry `is_qualified` is 0 | Pass | 0 |
| 8 | `strategy_weights.json` rewritten, mtime today, weights empty | Pass | mtime is `2026-08-15 06:36:22.162965419 -0300`, `weights` is `{}` |

## Backups created
- `results/state/regime_strategy_map.json.bak-20260815-pre-t3`
- `results/state/strategy_weights.json.bak-20260815-pre-t3`

## Observations
- Did the verdict change? No, there are still 0 qualifiers. What changed is the **provenance**; the attribution now correctly aligns with the post-T2 fact_trade_outcomes rebuild (de-duplicated data from primary_granularity fix), using honest labels, and reducing the total cells from 80 to 40. The counts roughly halved exactly as expected, making the data properly sourced and legitimate.
- I deliberately did not touch any gates, thresholds, or strategies. The map correctly remains empty and honest (Milestone M1). I did not start the orchestrator or any promotion paths.
