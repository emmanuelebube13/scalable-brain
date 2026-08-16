# R1 — Arm-tagged, regime-tagged trade outcomes

**Engineer:** Gemini Pro · **Reviewer:** Claude
**Repo:** `/home/emmanuel/Documents/Scalable_Brain/scalable-brain`
**Venv:** `source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate`
**Estimated time:** 2–3 hours · **Risk:** medium — this writes to the database.
**Blocks:** R3.

**Read `STATE.md` first. Read `README.md` §3, §4 and §8 before writing any code.**

---

## Why this task exists

The trial runs two arms over the same bars: a **blind** arm (existing behaviour, the
control) and an **aware** arm (regime-gated). If both arms write into `fact_trade_outcomes`
as it stands today, their trades pool into one undifferentiated set and the comparison —
the entire point of the week — is destroyed.

`fact_trade_outcomes` today:

```
outcome_id, timestamp, asset_id, strategy_id, granularity, trade_horizon,
is_winner, r_multiple, holding_bars, atr_sl_multiplier, atr_tp_multiplier,
entry_signal_type, exit_reason, created_at, is_oos, fold_id
```

Three things are missing for this trial:

1. **which arm produced the trade** — blind or aware
2. **which regime was in force at the decision bar**, and from which label source
3. **which run produced it**, so two executions of the same arm never silently merge

There is a fourth, larger gap you are **not** solving here: contract v2 exists to preserve
each strategy's own exits, and one row with a single `r_multiple` cannot represent a
three-leg scale-out. That is gap 3 in `CONTRACT_V2_AND_POSITION_ENGINE.md` §11.3 and it is
deliberately out of scope this week — but **design the new table so adding legs later does
not require rewriting it.** Leave the door open; do not walk through it.

---

## Hard constraints

1. **Do not alter `fact_trade_outcomes`.** Not a new column, not a default, nothing. It
   feeds the live attribution path and the blind arm is the control.
2. Create a **new table**. Name it `fact_regime_trial_outcomes`.
3. All DB access through `src/common/db.py`. Parameterized SQL only.
4. Writes must be **idempotent**: `INSERT … ON CONFLICT (…) DO UPDATE`. A re-run of the same
   arm and run id must not double-count.
5. **Snapshot before any destructive operation** and record it in `STATE.md`'s checkpoint
   table. There are no destructive operations expected in R1 — if you find yourself needing
   one, stop and mark BLOCKED.
6. Column naming follows house rules: lowercase, `fact_*` prefix, quote `"timestamp"`.

---

## Execution plan

### Step 1 — Write the migration

Location: follow whatever convention `src/sql/` or the existing migration scripts use.
Inspect first; do not invent a new migration system.

Required columns, on top of everything `fact_trade_outcomes` already carries:

| Column | Type | Notes |
|---|---|---|
| `arm` | `varchar` NOT NULL | `'blind'` or `'aware'`. Add a CHECK constraint — an unrecognised arm must fail closed, never default. |
| `regime_at_entry` | `varchar` NOT NULL | The label in force at the **decision bar**, not the fill bar. `UNKNOWN` is a valid value and must be storable. |
| `regime_source` | `varchar` NOT NULL | `'d1_trend'` or `'hmm_causal'`. Which instrument produced `regime_at_entry`. Never nullable — a label with no stated source is unusable. |
| `run_id` | `uuid` or `varchar` NOT NULL | One per execution of the runner. Two runs never merge. |
| `strategy_key` | `varchar` NOT NULL | The v2 **string** id (e.g. `kiss_h4`). The live path keys on int; this trial does not, and forcing an int id here would prejudge gap 2. |
| `mask_applied` | `jsonb` | The frozen mask this strategy ran under, stored **with the trade**. If a mask is ever changed, old rows still say what they actually ran. |
| `engine` | `varchar` NOT NULL | `'position_engine_v2'` or `'backtest_engine_v1'`. CHECK-constrained. The trial runs two strategy universes with **different exit models** — the 43 new `StrategyV2` strategies use their own declared exits, the legacy 9 use a uniform ATR 1:3 harness. Pooling them would compare two different things. See `README.md` §9. |

Keep `is_oos` and `fold_id`, populated from `src/system1/validation/walk_forward.py` — **the
same module, not an equivalent one.** Two fold implementations is how OOS stops being OOS
(gap 4).

Primary key / conflict target: `(run_id, strategy_key, asset_id, granularity, "timestamp", arm)`.

**Forward-compatibility for legs:** add `leg_index int NOT NULL DEFAULT 0` and
`is_terminal_leg boolean NOT NULL DEFAULT true`. Today every trade writes one row with
`leg_index=0, is_terminal_leg=true`. When scale-outs arrive the table already holds them
without a migration. Do not build leg logic now — just leave the columns.

### Step 2 — Apply it and record the checkpoint

Before applying, append a row to `STATE.md`'s checkpoint table (table name, row count
before — zero, it is new — and how to undo, which is `DROP TABLE`).

Apply. Verify the table exists with the expected columns and constraints.

### Step 3 — A writer module

`src/regime_aware/outcomes.py`. Pure-function assembly separated from I/O, matching house
style. It must:

- accept a completed trade plus its decision-bar regime and arm
- refuse to write if `regime_source` is missing or `arm` is not one of the two allowed values
- be idempotent on re-run

### Step 4 — Tests

In `src/regime_aware/tests/`. At minimum:

1. Writing the same trade twice produces one row, not two.
2. An unrecognised `arm` value is **rejected**, not defaulted.
3. A missing `regime_source` is rejected.
4. `UNKNOWN` is accepted as a regime value and round-trips.
5. Two different `run_id`s keep their rows separate.
6. `is_oos` / `fold_id` come from `walk_forward.py` — assert the module identity, not just
   the values.

### Step 5 — Append to STATE.md

Row count, table name, test count, and anything the next agent needs.

---

## Definition of done

- [ ] `fact_regime_trial_outcomes` exists with every column above and the CHECK constraints
- [ ] `fact_trade_outcomes` is **byte-identical to before** — verify and state the row count
- [ ] `src/regime_aware/outcomes.py` writes idempotently
- [ ] Tests above pass; state the count
- [ ] `STATE.md` updated with checkpoint + log rows
- [ ] Nothing outside `src/regime_aware/` and the migration location was touched

## What the reviewer will check

- That the CHECK constraint on `arm` actually **fails closed** — Claude will try to insert
  `arm='blnid'` and expect an error, not a silent row.
- That `is_oos`/`fold_id` import from `src/system1/validation/walk_forward.py` and not a
  local reimplementation.
- That `fact_trade_outcomes` was genuinely untouched.

---

## Failure log

Append root causes here as they are found. Correct the plan above in place.

| Timestamp | Step | What went wrong | Root cause | Fix applied |
|---|---|---|---|---|
| | | | | |
