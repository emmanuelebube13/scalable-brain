# P0 — The unified strategy registry

**Engineer:** Gemini Pro · **Reviewer:** Claude
**Est:** 4–6 h · **Risk:** medium — writes to `dim_strategy`, which the whole live path keys on.
**Blocks:** everything.

**Read `STATE.md`, then `README.md` §2 and §3.**

---

## Why

Three universes, three discovery mechanisms, no shared identity:

| universe | discovery | id type | count |
|---|---|---|---|
| legacy | `get_all_strategies()` — a literal list at `qualify_strategies.py:439` | `int` 1..10 | 10 |
| v2 research | `v2_harness.discover()` | `str` (`"kiss_h4"`) | 43 |
| regime-aware ports | `src/regime_aware/strategies/` | `str` | 9 |

Every downstream table keys on `int`. Every research strategy has a `str`. Until one view
spans all three with stable integer ids, nothing else in this folder can be built.

---

## Hard constraints

1. **Existing ids 1..10 never change.** `fact_trade_outcomes` has 55,756 rows referencing
   them and `fact_strategy_regime_attribution` derives from those. Renumbering silently
   re-labels history.
2. **Id allocation is permanent and recorded.** Once a string key gets an int, that pairing
   is immutable. FIX-S1-004 is the standing warning — a duplicate id silently collapsed a
   strategy's weight once already.
3. **Allocation is idempotent.** Re-running must not mint a second id for the same key.
4. `strategy_key` (the string) remains the human-facing identifier. The int is plumbing.
5. Do not delete or rewrite `get_all_strategies()` yet — P1 still calls it. Add beside it.

---

## Execution plan

### Step 1 — Extend `dim_strategy`

Add, with a migration in `src/sql/migrations/`:

| column | purpose |
|---|---|
| `strategy_key` | the string id; **UNIQUE**, nullable only for the legacy 10 until backfilled |
| `universe` | `'legacy'` / `'v2_research'` / `'regime_aware_port'`. CHECK-constrained, fails closed |
| `engine` | `'backtest_engine_v1'` / `'position_engine_v2'` — which engine produces its trades |
| `primary_granularity` | H1 / H4 / D1 / W1 |
| `family` | from `src/regime_aware/families.py`, nullable |
| `registered_at_utc` | when the id was allocated |

Backfill `strategy_key` for the legacy 10 from their existing `strategy_name`.

### Step 2 — The allocator

`src/system1/registry/allocate.py`:

```python
def ensure_strategy_id(strategy_key: str, *, universe: str, engine: str,
                       primary_granularity: str, family: str | None) -> int
```

- returns the existing id if `strategy_key` is already present (idempotent)
- otherwise allocates `max(strategy_id) + 1` inside a transaction with the row locked, so
  two concurrent callers cannot collide
- refuses an unknown `universe` or `engine` rather than defaulting

### Step 3 — The unified view

`src/system1/registry/catalog.py`:

```python
def all_strategies() -> list[StrategyRecord]   # every universe, id + key + engine + metadata
def by_id(strategy_id: int) -> StrategyRecord
def by_key(strategy_key: str) -> StrategyRecord
def instantiate(record) -> object              # returns a runnable strategy object
```

`instantiate` dispatches on `universe`: legacy classes from the literal list, v2 via
`v2_harness.discover()`, ports via their module's `build_regime_aware()`. **This is the
only place that knows how the three universes differ.** Everything downstream takes a
`StrategyRecord`.

### Step 4 — Register the fleet

A CLI that walks all three universes and allocates ids:

```
python -m src.system1.registry.allocate --dry-run   # print what would be allocated
python -m src.system1.registry.allocate             # allocate
```

Print a table: key → id → universe → engine. Record the counts in `STATE.md`.

### Step 5 — Tests

1. Legacy ids 1..10 unchanged after a full allocation run — assert each by name.
2. Allocation is idempotent: run twice, same ids, no new rows.
3. A duplicate `strategy_key` is rejected by the UNIQUE constraint (prove by attempting it).
4. Unknown `universe` / `engine` rejected, not defaulted.
5. `instantiate()` returns a runnable object for one strategy of each universe.
6. `by_id` / `by_key` round-trip.
7. Concurrent allocation of the same new key yields one id, not two.

### Step 6 — Append to `STATE.md`

---

## Definition of done

- [ ] `dim_strategy` extended; legacy 10 backfilled and **verified unchanged**
- [ ] All 62 strategies (10 + 43 + 9) hold stable ids; state the actual count
- [ ] `catalog.all_strategies()` returns them all; `instantiate()` works per universe
- [ ] Tests above pass; state the count
- [ ] `fact_trade_outcomes` row count unchanged — state it before and after
- [ ] `STATE.md` updated with the key→id table

## Reviewer will check

- That ids 1..10 still map to the same names — by querying, not by reading the code.
- That the UNIQUE constraint on `strategy_key` actually fires.
- That allocation run twice produces zero new rows.

---

## Failure log

| Timestamp | Step | What went wrong | Root cause | Fix |
|---|---|---|---|---|
| | | | | |
