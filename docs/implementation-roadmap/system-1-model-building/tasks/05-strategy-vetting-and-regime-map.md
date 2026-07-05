# MODEL-005 — Strategy Vetting & Regime Map

**Task ID:** MODEL-005
**System:** System 1 — Model Building
**Priority:** P1-High
**Estimated Effort:** 3d
**Prerequisites:** MODEL-004
**External Dependencies:**
- **`ForexBrainDB` (PostgreSQL 16 + TimescaleDB, FND-004)** — read attribution + outcomes; update `Dim_Strategy_Registry` qualification status. Connect via `src/common/db.py`. *(DB = PostgreSQL 16 + TimescaleDB; any historical SQL-Server mention is obsolete.)*
- **MLflow** — log gate pass/fail and emitted-map versions.
- **Object storage / shared volume** (FND-001) — staging for `regime_strategy_map.json` + `strategy_weights.json` consumed by MODEL-007.

## Objective
Upgrade the vetting gate (PF≥1.5, Sharpe≥0.8, MaxDD≤25%, WinRate≥40%, Recovery≥3.0, OOS≥60mo) and emit a regime→ranked-strategy map artifact (`regime_strategy_map.json`) + `strategy_weights.json`.

## Current State
- Vetting in `src/layer0/qualify_strategies.py` is lenient and aggregate: positive expectancy, ≥20 trades, ~1.15 profit factor. No drawdown, Sharpe, recovery-factor, or out-of-sample-duration gate. No machine-readable regime→strategy routing artifact exists; promotion is via `results/sql/layer2_strategies.sql` and `Dim_Strategy_Registry`.

## Target State
A stricter, multi-criteria vetting gate applied with **per-regime awareness** (from MODEL-004): a strategy qualifies **for a regime** only if it clears all gates **PF≥1.5, Sharpe≥0.8, MaxDD≤25%, WinRate≥40%, Recovery≥3.0, OOS≥60 months** in that regime (with adequate sample size). The system then emits two machine-readable artifacts: **`regime_strategy_map.json`** (per regime, the ranked list of qualifying strategies) and **`strategy_weights.json`** (per regime allocation weights). These feed MODEL-007's bundle for Computer 2.

## Technical Specification

**Vetting gates (per strategy × regime, all must pass):**
| Gate | Threshold |
|------|-----------|
| Profit Factor | ≥ 1.5 |
| Sharpe Ratio | ≥ 0.8 |
| Max Drawdown | ≤ 25% |
| Win Rate | ≥ 40% |
| Recovery Factor (net profit / MaxDD) | ≥ 3.0 |
| Out-of-Sample coverage | ≥ 60 months |

Plus the MODEL-004 sample-size guard: cells flagged `low_confidence` (below `N_min` trades) **cannot qualify** regardless of metrics. The legacy aggregate gate is retained as a coarse pre-filter; the per-regime gates are authoritative for the map.

**OOS≥60 months:** qualification must demonstrate performance over an out-of-sample window of at least 60 months (walk-forward design: train/in-sample window then forward OOS folds; the union of OOS folds must span ≥60 months). MODEL-001's 2005 backfill makes this feasible.

**Ranking:** within each regime, qualifying strategies are ranked by a documented composite score (e.g., a weighted blend of Sharpe, PF, and Recovery Factor, penalized by MaxDD), with deterministic tie-breaking (e.g., higher trade count). Ranking rule is recorded in the artifact metadata.

**`regime_strategy_map.json` (shape, illustrative):**
```
{
  "schema_version": "1.0.0",
  "generated_at_utc": "...",
  "regime_model_version": "...",
  "ranking_rule": "0.5*sharpe + 0.3*pf + 0.2*recovery - penalty(maxdd)",
  "regimes": {
    "Trending-Up":   [{"strategy_id": "...", "variant": "...", "rank": 1, "metrics": {...}}, ...],
    "Trending-Down": [...],
    "Ranging":       [...],
    "High-Vol":      [...]
  }
}
```

**`strategy_weights.json` (shape, illustrative):** per regime, normalized weights over the qualifying strategies (sum to 1 per regime), derived from the composite score; includes the same versioning/lineage fields.

**Registry update:** set per-regime qualification status in `Dim_Strategy_Registry` (additive columns or a linked table); keep `results/sql/layer2_strategies.sql` emission for Layer 2 compatibility.

**Lineage/versioning:** both artifacts carry `schema_version`, `regime_model_version` (MODEL-003), `qualification_run_id`, and checksums computed downstream by MODEL-007.

## Testing & Validation
- **Gate unit tests:** each threshold (PF/Sharpe/MaxDD/WinRate/Recovery/OOS-months) accepts at boundary and rejects just outside; low-confidence cells always rejected.
- **Walk-forward / OOS:** verify OOS span ≥60 months is correctly measured across folds; statistical significance of in-sample vs OOS metric stability checked.
- **Artifact validation:** JSON schema validation for both files; weights sum to 1 per regime; ranks are dense and consistent with the ranking rule; only qualifying strategies appear.
- **Starvation guard:** report per-gate rejection counts; if a regime ends up with zero qualifying strategies, surface it explicitly (do not silently emit an empty regime without a warning).
- **Edge cases:** ties in composite score, a strategy qualifying in some regimes but not others, regime with no candidates.

## Rollback Plan
Run the new gates in **log-only mode** first (compute pass/fail and would-be artifacts without changing promotion). Roll back by reverting to the legacy aggregate gate via config and not emitting the maps; MODEL-007 then falls back to the previous artifact version. No destructive registry change without dependency check.

## Acceptance Criteria
- [ ] Per-regime gates enforce PF≥1.5, Sharpe≥0.8, MaxDD≤25%, WinRate≥40%, Recovery≥3.0, and OOS≥60 months; low-confidence cells are excluded.
- [ ] `regime_strategy_map.json` emitted with a ranked list of qualifying strategies per regime and a documented ranking rule.
- [ ] `strategy_weights.json` emitted with per-regime weights summing to 1, sharing version/lineage metadata.
- [ ] Both artifacts pass JSON-schema validation and carry regime-model + run lineage.
- [ ] Per-gate rejection reasons reported; empty-regime cases surfaced explicitly.

## Notes & Risks
- The stricter gate may reject most or all current strategies — calibrate on history first and run log-only; expose rejection reasons so the gate can be tuned with an audit trail rather than silently relaxed.
- OOS≥60mo depends on MODEL-001 backfill depth per instrument; instruments with shorter history may not satisfy it and must be flagged.
- The two JSON artifacts are a hard interface to Computer 2 — schema changes are breaking and must be versioned.
