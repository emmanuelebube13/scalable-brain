# R2b — The contract-v2 regime gate

**Engineer:** Gemini Pro · **Reviewer:** Claude
**Estimated time:** 3–4 hours · **Risk:** low — new code, nothing existing changes.
**Needs:** R2 (frozen masks). **Blocks:** R3.

**Read `STATE.md` first. Read `README.md` §4 and §9. Read `src/layer0/strategies/contract_v2.py`
and `position_engine.py` before writing anything.**

---

## Why this task exists

`src/regime_aware/` is built on the **legacy v1 engine** — deliberately, and its
`__init__.py` explains why. Every strategy in `src/regime_aware/strategies/` subclasses a
legacy v1 class (`RegimeAwareDonchianH4(TrendDonchian_H4_Only)` and so on).

**The 43 new strategies are `StrategyV2` subclasses.** They run on `PositionEngine` with
their own declared exits. The existing regime-aware framework cannot execute them.

Pushing them down to the v1 engine is not the answer: the v1 path applies a uniform ATR
1:3 harness through `engine_adapter`, which throws away each strategy's declared exits —
the exact thing contract v2 exists to preserve, and which the owner has decided to keep. It
would also inherit the T6 ATR case-mismatch (`engine_adapter` writes `df["atr"]`,
`StrategyBase` reads `df["ATR"]`).

So the gate moves to the v2 layer. This task builds it.

---

## Why this is simpler than the v1 port

The v1 regime-aware ports needed `ParamBlock` and `resolve_at` because they change
*parameters* per regime — different channel periods, different ADX thresholds, different
ATR multiples. Resolving that without restarting indicators at regime boundaries is the
hard part, and `contract.py` solves it.

**We are not doing that.** Per `README.md` §4 the intervention this week is a gate only:
`enabled` true or false, nothing else varies. A `StrategyV2` emits `OrderIntent`s; the gate
drops the ones whose decision bar sits in a disabled regime. That is a filter over a list.

No indicator resolution problem, because indicators were already computed once over the
continuous frame by the strategy itself, before any gating happens. Nothing is recomputed
per regime. Nothing restarts at a boundary.

**Do not import `ParamBlock` into this path.** If a future week adds per-regime parameters
to v2 strategies, that is a different design conversation with a different overfitting
profile. Keep this one a filter.

---

## Hard constraints

1. **Do not modify any strategy in `src/layer0/strategies/research/`.** The 43 are the
   subject of the experiment; editing them destroys the control.
2. **Do not modify `contract_v2.py`, `position_engine.py`, or `v2_harness.py`.** Wrap, do
   not alter. If you believe one of them must change, stop and mark BLOCKED.
3. The gate reads regime at the **decision bar** (`OrderIntent.decision_bar`), never the
   fill bar.
4. `UNKNOWN` → filtered out. Always.
5. Only `regime_causal`. Never `regime_smoothed`.
6. Gating suppresses **entries only**. An intent that was allowed through still exits under
   the strategy's own declared rules — `PositionEngine` handles that and you do not
   intervene.
7. New code lives in `src/regime_aware/v2/`. Do not scatter it.

---

## Execution plan

### Step 1 — Read the two contracts

`contract_v2.py` (`StrategyV2`, `OrderIntent`, `closed_context_frame`,
`assert_no_lookahead_v2`) and `position_engine.py`. Understand what an `OrderIntent`
carries and when `decision_bar` is stamped, before writing a filter over them.

Note `assert_no_lookahead_v2` exists here — the v1 regime-aware package had to carry its own
truncation-based causality test because that assertion was unavailable. On the v2 path you
get it for free. Use it.

### Step 2 — The regime series resolver

`src/regime_aware/v2/labels.py`. Given a pair, a granularity and a frame index, return the
label per bar under a stated `regime_source`:

- `d1_trend` — via `src/regime_aware/context.py::build_trend_labels` (reuse it, do not
  reimplement)
- `hmm_causal` — via `fact_market_regime_v2.regime_causal`

Joined backward onto the frame so bar *t* carries a label derived strictly from before *t*.
`context.py::attach_regime` already does this correctly — reuse it.

### Step 3 — The gate

`src/regime_aware/v2/gate.py`. A wrapper implementing `StrategyV2` that holds an inner
strategy plus a mask:

- delegates `metadata` and `warmup_bars` to the inner strategy
- `generate_orders(frames)` calls the inner strategy, then **filters** the yielded intents:
  keep an intent only if the mask enables the label at its `decision_bar`
- emits nothing else, changes nothing else — no re-sizing, no re-stopping, no re-ordering

The wrapper must satisfy `assert_no_lookahead_v2` on its own. Filtering by a label that is
itself causal cannot introduce look-ahead, but assert it rather than reason about it.

### Step 4 — Record what was filtered

The gate must expose, per run, how many intents it dropped and in which regimes. R3 needs
this and so does the trial write-up. A gate that silently drops everything and a gate that
drops nothing look identical from the trade table alone.

### Step 5 — Tests

In `src/regime_aware/v2/tests/`:

1. **Identity.** All-permissive mask ⇒ the filtered intent list is `==` the unfiltered one.
   Not "equivalent" — the same objects, same order, same count.
2. **Full suppression.** All-disabled mask ⇒ zero intents, and the strategy produces zero
   trades rather than erroring.
3. **Decision bar, not fill bar.** Construct an intent whose decision bar and fill bar fall
   in different regimes; assert the decision bar's label governs.
4. `UNKNOWN` is always filtered, including when every named regime is enabled.
5. The wrapper passes `assert_no_lookahead_v2`.
6. Warm-up bars, where no label exists yet, are `UNKNOWN` and therefore filtered.
7. Delegation: `metadata` and `warmup_bars` match the inner strategy exactly.

### Step 6 — Smoke-run against real strategies

Pick three of the 43, one per family, and run the gate end to end through `v2_harness`'s
machinery. Confirm trade counts fall (gating should reduce them), that the identity test
holds with an all-permissive mask, and record the drop counts in `STATE.md`.

### Step 7 — Append to STATE.md

---

## Definition of done

- [ ] `src/regime_aware/v2/` with `labels.py` and `gate.py`
- [ ] All seven tests pass; state the count
- [ ] Identity test proven with an all-permissive mask on at least three real strategies
- [ ] Filter counts exposed per run
- [ ] `contract_v2.py`, `position_engine.py`, `v2_harness.py` and all 43 strategies
      **unmodified** — verify and state this
- [ ] No `ParamBlock` import on this path
- [ ] `STATE.md` updated

## What the reviewer will check

- **Claude runs the identity test personally.** All-permissive must give byte-identical
  intents. This is the v2 equivalent of the equivalence test and it is the load-bearing one.
- That `decision_bar` governs, by tracing an intent whose decision and fill bars straddle a
  regime change.
- That nothing in the 43 strategies was edited — `git diff` on that directory must be empty.
- That the drop counts are real and not zero-by-accident.

---

## Failure log

| Timestamp | Step | What went wrong | Root cause | Fix applied |
|---|---|---|---|---|
| | | | | |
