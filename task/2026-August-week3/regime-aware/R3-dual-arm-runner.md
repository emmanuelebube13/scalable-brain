# R3 — Dual-arm runner

**Engineer:** Gemini Pro · **Reviewer:** Claude
**Estimated time:** 4–6 hours · **Risk:** medium — writes outcomes, and it is the task whose
correctness everything else depends on.
**Needs:** R1 (table), R2 (frozen masks) and R2b (the v2 gate) all DONE.

**Read `STATE.md` first. Read `README.md` in full. Read `src/regime_aware/contract.py`.**

---

## Why this task exists

This runs both arms over the same bars and writes their trades, separately tagged, into
`fact_regime_trial_outcomes`. It is the measurement apparatus. If it is subtly wrong,
every number produced this week is wrong in a way that looks fine.

---

## Two universes — you are running both

Per `README.md` §9, the trial covers two sets of strategies through two different
mechanisms. Do not attempt to unify them; they are separate paths on purpose.

| | **The 43 new strategies** — PRIMARY | **The legacy 9** — continuity |
|---|---|---|
| base | `StrategyV2` | v1 `Strategy` subclasses |
| engine | `PositionEngine` | `layer0.core_engine.BacktestEngine` |
| gated by | **R2b's intent filter** | existing `ParamBlock` / `resolve_at` |
| exits | strategy's own declared exits | uniform ATR 1:3 |
| lives in | `src/regime_aware/v2/` | `src/regime_aware/strategies/` |

**The 43 are the reason this trial exists.** If you run short of time or budget, cut the
legacy 9 and say so in `STATE.md`. Never the reverse.

Both write into the same `fact_regime_trial_outcomes` table from R1. Record which universe
produced each row — if R1's schema has no field for that, add one and note it in the
failure log; a pooled comparison across two different exit models would be meaningless.

---

## The one test that matters most

**Equivalence before comparison** (rule 1 of `STRATEGY_EXPERIMENT_STANDARD.md`). It takes a
different form on each path.

**On the v2 path (the 43):** an all-permissive mask filters zero intents, so the aware arm
must produce a **byte-identical** intent list and therefore identical trades. This is the
stronger form of the test — assert list identity, not metric similarity. R2b step 5 test 1
establishes it; re-assert it here on the full strategy set, not just the three smoke-tested
in R2b.

**On the v1 path (the legacy 9):** an all-identical `ParamBlock` set must reproduce the
blind twin **trade for trade** — same entry time, direction, entry price, stop, target, exit
reason, r-multiple. Not "similar", not "within tolerance on aggregate".
`src/regime_aware/tests/test_equivalence.py` already does this; read it and extend.

If either fails, the plumbing is changing outcomes by itself and no comparison built on it
means anything.

**Do not proceed past this.** If equivalence fails, mark FAILED in `STATE.md`, record the
root cause, and stop. A broken equivalence test is not a detail to fix later; it invalidates
everything downstream.

---

## Hard constraints

1. **The blind arm is unmodified existing behaviour.** It is the control. If you find
   yourself editing strategy logic to make the arms comparable, you have broken the control
   — stop and mark BLOCKED.
2. Indicators are computed **once over the full continuous frame** per distinct parameter
   value; each bar then selects its regime's column. Never slice the frame into regime
   segments and compute within them — a Donchian channel restarted at every boundary invents
   breakouts the real series never produced. `contract.py` explains this; follow it.
3. Regime is resolved at the **decision bar**, never the fill bar.
4. `UNKNOWN` → do not trade. Always.
5. Only `regime_causal`. Never `regime_smoothed`.
6. Disabling a regime suppresses **entries only**. Open positions still exit normally.
   Force-closing a position because the regime changed is a different intervention and
   would confound the comparison.
7. OOS folds come from `src/system1/validation/walk_forward.py` — that module, not a copy.

---

## Execution plan

### Step 1 — Equivalence gate, both paths

Run the all-permissive-mask check across **every** strategy R3 will cover — all 43 on the
v2 path, all 9 on the v1 path. Record pass/fail per strategy in `STATE.md`. **Any failure
stops the task.**

### Step 2 — The runner

Two entry points, one per universe. `src/regime_aware/runner.py` already exists and handles
the v1 path — read it before writing anything new; extend rather than replace if it fits.
The v2 path needs its own runner in `src/regime_aware/v2/`, built on R2b's gate and driving
`PositionEngine` the way `v2_harness.evaluate_cell` does. **Reuse `v2_harness`'s machinery
rather than reimplementing the fold attribution** — it already imports `_aggregate_cell` and
`evaluate_gates` rather than restating them, and that discipline is why its numbers are
trustworthy.

Each must, for each strategy × pair × granularity:

- resolve the regime series under the configured `regime_source` (`d1_trend` primary;
  `hmm_causal` also runnable for comparison)
- run the blind arm and the aware arm over the identical bar series
- emit trades tagged with `arm`, `regime_at_entry`, `regime_source`, `run_id`,
  `strategy_key`, `mask_applied`, plus `is_oos`/`fold_id`
- write through `src/regime_aware/outcomes.py` from R1

One `run_id` per invocation, generated once at the start.

### Step 3 — Guard against the known artifacts

Build these in as assertions that fail the run, not as things to check afterwards:

- **Pair concentration.** If an arm's trades collapse onto one pair while the blind arm's do
  not, flag it loudly in the output. This is the T3 artifact and it must be impossible to
  miss.
- **Trade starvation.** If the aware arm's trade count for a cell falls below a floor
  (suggest 30 OOS trades), mark that cell as unmeasurable rather than reporting a metric
  computed from a handful of trades. Gating *will* reduce trade counts — that is expected
  and is the point — but a PF computed from 6 trades is noise wearing a number's clothes.
- **Zero-trade cells.** A trend strategy gated to trending regimes may legitimately produce
  zero trades on some pair. Report it as zero, explicitly. Do not silently drop the cell.

### Step 4 — Run it

Both label sources. Record `run_id`, per-arm trade counts, and per-cell coverage in
`STATE.md`. Append after each strategy completes, not at the end — this run takes a while
and a rate limit mid-run must not lose the record of what already succeeded.

Snapshot/checkpoint before the first write, per `STATE.md`'s checkpoint table.

### Step 5 — Comparison report

`results/regime_aware/R3/`. Per strategy and pooled:

- blind vs aware: trade count, win rate, mean R, PF, Sharpe, max drawdown
- **bootstrap CI on the difference in mean R**, not just point estimates
- per-pair breakdown for every cell where the aware arm looks better
- how many cells were unmeasurable under the trade floor

State the number of comparisons made. With ~43 strategies × 2 label sources, some will look
good by chance alone; the report must say how many tests were run so the reader can weigh a
p-value properly.

### Step 6 — Append to STATE.md

---

## Definition of done

- [ ] Equivalence passes for every covered strategy on **both** paths, recorded per strategy
- [ ] All 43 v2 strategies covered, or each exclusion stated with a reason
- [ ] Each outcome row records which universe produced it
- [ ] Both arms ran over identical bars; trade counts recorded
- [ ] Outcomes written tagged and idempotent; re-running the same `run_id` adds no rows
- [ ] Concentration, starvation and zero-trade guards active and reported
- [ ] Comparison report with CIs on differences, not bare point estimates
- [ ] Number of comparisons stated
- [ ] `STATE.md` updated per strategy

## What the reviewer will check

- **Claude re-runs the equivalence test personally.** A reported pass that was never
  executed against the blind twin is the single failure that would invalidate the week.
- That regime is taken at the decision bar — Claude will trace one trade end to end.
- That disabling a regime suppressed entries only and did not close open positions.
- That per-pair breakdowns accompany every favourable result.
- That the trade floor was applied rather than mentioned.

---

## Failure log

| Timestamp | Step | What went wrong | Root cause | Fix applied |
|---|---|---|---|---|
| | | | | |
