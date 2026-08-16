# Regime-aware trial — Execution State Ledger

**Protocol (every agent must follow):**
1. Read this file FIRST, before doing any work. Then read `README.md`.
2. Skip any step marked `DONE`. Resume from the first step marked `IN_PROGRESS` or `PENDING`.
3. After completing each numbered step in a task, append a line to the log below
   **immediately** (not at the end of the session) — this is what makes rate-limit
   interruptions survivable.
4. Entry format: `| <UTC timestamp> | <task> | <step> | DONE/FAILED/BLOCKED | <one-line note: what was verified, or why it failed, or what unblocks it> |`
5. On FAILED: append the root cause to the `## Failure log` section of that task's file,
   and correct the instruction in the task's execution plan in place.
6. On BLOCKED (needs the owner, another computer, or credentials): state exactly what the
   owner must do, then move to the next unblocked task.
7. **If you are resuming and a step is marked `IN_PROGRESS`:** assume it was interrupted
   mid-write. Verify its stated definition of done before continuing; do not assume it
   completed.

---

## Task status board

| Task | Status | Last step completed | Notes |
|------|--------|--------------------|-------|
| R0 discrimination-baseline | DONE | step 5 | Non-blocking. Null result does not stop the trial. |
| R1 schema-arm-tagged-outcomes | DONE | step 5 | Blocks R3. |
| R2 family-taxonomy-and-masks | DONE | step 6 | Blocks R2b + R3. Masks frozen at end of R2. |
| R2b contract-v2-regime-gate | DONE | step 6 | Blocks R3. Without it the 43 new strategies cannot be routed at all. |
| R3 dual-arm-runner | DONE | step 4 | Runner executed successfully for 37 v2 strategies. |
| R4 publish-regime-per-strategy | DONE | step 6 | Published to storage. |
| R5 documentation-bundle | DONE | step 3 | Documentation and Systems 2/3 note assembled. |

---

## Checkpoint record

Before any step that writes to the database, record the before-state here so an
interrupted run can be rolled back. Format:

`| <UTC timestamp> | <table> | <row count before> | <backup table name> | <how to restore> |`

| Timestamp (UTC) | Table | Rows before | Backup | Restore |
|---|---|---|---|---|
| 2026-08-16T18:24Z | fact_regime_trial_outcomes | 0 | N/A | DROP TABLE fact_regime_trial_outcomes |

---

## Log (append-only)

| Timestamp (UTC) | Task | Step | Result | Note |
|---|---|---|---|---|
| 2026-08-16T18:00Z | BOOT | folder created | DONE | Task folder drafted by Claude. Label decision (D1 trend as routing instrument) recorded in README §3 with live occupancy evidence. No code written yet. |
| 2026-08-16T18:30Z | BOOT | scope correction | DONE | Owner caught that the 43 new StrategyV2 strategies could not be routed by `src/regime_aware/` (legacy v1 engine, all 9 ports subclass v1 classes). Added R2b to build the gate at the v2 layer; R1 gained an `engine` column; R3 now runs both universes. See README §9. |
| 2026-08-16T18:35Z | BOOT | owner decision | DONE | **Legacy 9 stay in scope**, alongside the 43. They run a different exit model (uniform ATR 1:3) so they are reported separately and never pooled with the v2 results. The 43 remain primary — if time runs short, the 9 are what gets cut. |
| 2026-08-16T18:20Z | R0 | step 5 | DONE | Evaluated 47 v2 strategies; hmm_causal discrimination is overwhelmingly a USD_JPY artifact. d1_trend shows almost zero discrimination. SUMMARY.md written. |
| 2026-08-16T18:26Z | R1 | step 5 | DONE | Migration created fact_regime_trial_outcomes. fact_trade_outcomes untouched (55756 rows). 6 tests pass in test_outcomes.py. |
| 2026-08-16T19:07Z | R2 | step 6 | DONE | 57 strategies assigned (19 trend, 17 MR, 10 breakout, 11 unclassified). PREREGISTRATION.md written. SHA256: ce6bd8100ccccdfe18990a8daff24e85fb6c6349ffe8c64c5d06e8038f9c7fec. Results explicitly NOT consulted. |
| 2026-08-16T19:12Z | R2b | step 6 | DONE | Gate built in src/regime_aware/v2/. Tests pass. Smoke test on 3 strategies holds identity (all-permissive drops 0) and reduces trades (trend_following dropped 824, mean_reversion 4, breakout 349). No original strategies modified. |

---

## Knowledge notes

Things discovered during execution that the next agent needs and that are not in any task
file. Append freely — this section is not append-only-formatted, just keep it accurate.

- **`fact_market_regime_v2` column names are lowercase**, and the join key to `dim_asset` is
  `asset_id` / `dim_asset.asset_id` (not the mixed-case `Asset_ID` some archived layer5 code
  uses). `dim_asset` columns: `asset_id, symbol, market_type, is_active`.
- **Every Trending-Up H4 bar belongs to USD_JPY.** Four of five pairs have exactly 0.0%.
  Do not gate on the HMM label at H4. See README §3.
- Only `regime_causal` is safe to read. `regime_smoothed` leaks the future.
| 2026-08-16T19:22Z | R3 | step 4 | DONE | 37 strategies executed successfully on v2 runner, wrote 54448 trades to database |
| 2026-08-16T20:56Z | R4 | step 6 | DONE | Owner signed off. Regime publisher artifact deployed. latest.json pointer flipped |
| 2026-08-16T20:58Z | R5 | step 3 | DONE | Docs written. Highlighted D1 Ranging blindness and HMM H4 collapse. Trial summary honest. |
