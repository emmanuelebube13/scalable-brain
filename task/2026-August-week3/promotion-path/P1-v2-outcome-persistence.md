# P1 — Outcome persistence for every strategy

**Engineer:** Gemini Pro · **Reviewer:** Claude
**Est:** 4–6 h · **Risk:** high — writes to `fact_trade_outcomes`, the table attribution reads.
**Needs:** P0. **Blocks:** P2.

**Read `STATE.md`, `README.md` §3, and `CONTRACT_V2_AND_POSITION_ENGINE.md` §11.3 gaps 3–4.**

---

## Why

`fact_trade_outcomes` is the only input to attribution → vetting → map. It contains trades
from the legacy 10 and nothing else, because `persist_trade_outcomes.py` iterates
`get_all_strategies()`. The 52 research strategies produce trades that live in JSON reports
and `fact_regime_trial_outcomes` — neither of which vetting reads.

---

## The schema decision you must make first — and record

`fact_trade_outcomes` is **one row per trade, one `r_multiple`, one
`atr_sl_multiplier`/`atr_tp_multiplier`**. A contract-v2 strategy with a three-leg
scale-out and breakeven-on-TP2 is not that shape.

Two options. **Pick one, write the reasoning into `STATE.md`, and tell the owner** — it
determines what attribution can ever say about exits:

- **(a) Aggregate legs to one net r-multiple per trade plan.** Schema-compatible, nothing
  downstream changes. Loses the exit shape that contract v2 exists to preserve.
- **(b) Add `leg_index` / `is_terminal_leg` columns** (as `fact_regime_trial_outcomes`
  already has) and write one row per leg, with attribution summing terminal legs.
  Preserves the exit shape; every consumer of the table must learn to filter.

**Recommendation: (b), defaulting `leg_index=0, is_terminal_leg=true`** so existing rows
and existing queries are unaffected, and the capability exists before it is needed. But it
is the owner's call — ask, do not assume.

---

## Hard constraints

1. **Snapshot `fact_trade_outcomes` before writing** — `CREATE TABLE ..._bak_<date> AS
   SELECT *` — and record it in `STATE.md`'s checkpoint table. The existing writer is
   `DELETE`-then-rebuild **with no transaction**.
2. **Pass `--lookback-years 10`.** The default of 5 silently discards half the history; this
   has bitten before.
3. **`is_oos` and `fold_id` come from `src/system1/validation/walk_forward.py`** — that
   module, not an equivalent. Two fold implementations is how OOS stops being OOS.
4. Writes idempotent: `INSERT … ON CONFLICT DO UPDATE`.
5. The legacy 10's rows must be **byte-identical** before and after. This task adds
   strategies; it does not re-measure existing ones.
6. Cost model must match the legacy path's — spread 1.0 pip, slippage 0.5 pip entry-only,
   commission 0 — or the two universes are not comparable in one table. If `PositionEngine`
   applies different costs, **say so loudly in `STATE.md`** rather than silently pooling.

---

## Execution plan

### Step 1 — Confirm the cost models match

Compare `layer0.core_engine.BacktestEngine`'s cost config with `PositionEngine`'s. Write the
comparison into `STATE.md`. If they differ, that is a finding the owner needs before any
pooled comparison is believed — raise it, do not paper over it.

### Step 2 — The unified writer

`src/system1/outcomes/persist_all.py`, driven by P0's catalog:

- for each `StrategyRecord`, dispatch on `engine` to the right backtest path
- v1 strategies keep going through the existing code path unchanged
- v2 strategies run through `PositionEngine` exactly as `v2_harness.evaluate_cell` does —
  **reuse that machinery, do not reimplement fold attribution**
- write into `fact_trade_outcomes` keyed on the integer `strategy_id` from P0

```
python -m src.system1.outcomes.persist_all --dry-run --lookback-years 10
python -m src.system1.outcomes.persist_all --lookback-years 10
python -m src.system1.outcomes.persist_all --only kiss_h4     # one strategy
```

### Step 3 — Run it and reconcile

Report per strategy: trades written, OOS trades, OOS months, date range. Reconcile the
legacy 10's counts against the pre-run snapshot and **state that they are unchanged**.

### Step 4 — Tests

1. Legacy 10 rows unchanged after a full run (compare against the backup table).
2. A v2 strategy's trades land with correct `strategy_id`, `is_oos`, `fold_id`.
3. `is_oos`/`fold_id` provably come from `walk_forward` — assert module identity.
4. Re-running writes no duplicates.
5. A strategy with zero trades is recorded as zero, not skipped silently.
6. Leg columns (if option b) default correctly for single-leg trades.

### Step 5 — Append to `STATE.md`

---

## Definition of done

- [ ] Schema decision made, reasoning recorded, owner told
- [ ] Snapshot taken and recorded before any write
- [ ] Cost-model comparison written down
- [ ] All registered strategies have outcomes; state the row count per universe
- [ ] Legacy 10 verified unchanged against the backup
- [ ] Tests pass; state the count

## Reviewer will check

- The legacy 10 really are unchanged — by diffing against the backup table.
- That `--lookback-years 10` was used (count the date range).
- That fold assignment imports the shared module.
- The cost-model comparison exists and is honest.

---

## Failure log

| Timestamp | Step | What went wrong | Root cause | Fix |
|---|---|---|---|---|
| | | | | |
