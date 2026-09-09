# Work Order 04B — Revert the leaky target, then answer the gatekeeper question honestly

**Read `audit/reports/work_order_04_review.md` first.** It sets out why WO-04 is being reopened
and carries the measurements this order relies on.

**You did the right thing stopping at WO-05 and asking.** The three findings you raised are
correct — I verified all of them. This order answers your question, and adds one you did not ask,
which is the more serious of the two.

**Nothing here is operationally urgent.** The gatekeeper is in shadow mode, nothing is gated on
its score, the live map and model set are unaffected, and the system keeps trading throughout.

---

## STAGE A — Revert the target neutralization `[first, and not optional]`

### What is wrong

```python
strat_medians = frame.groupby("strategy_id")["r_multiple"].transform("median")
frame["is_winner"] = (frame["r_multiple"] > strat_medians).astype(int)
...
wf = _walk_forward(frame)          # split happens AFTER
```

The median is computed over the **whole frame** — every fold, all OOS, all holdout — before any
split. A 2019 trade's label depends on that strategy's 2026 trades. **That is target look-ahead.**

It also does not work:

| | value | required |
|---|---|---|
| degenerate cells | 49.4% | ≤50% — passed by 0.6pp |
| OOS uplift | 0.011245 | ≥ MIN_UPLIFT |
| significant | **False** (p=0.115) | must be True |

The degeneracy fell **by construction** — half of any strategy's trades beat its own median by
definition, so `strategy_id` was made uninformative arithmetically, not by the model finding
market state. And the model fails `oos_uplift_ok` regardless, so it could never be promoted.

### Outcomes

1. `frame["is_winner"]` is restored to its original definition. `git diff HEAD -- src/gatekeeper/train.py`
   should come back empty for that hunk.
2. Delete `models/proposed_champion_*` produced under the neutralized target — those artifacts
   describe a model trained on leaked labels and must not be mistaken for a candidate.
3. **Run `leakage-hunter` on the reverted trainer** and on any other label or feature transform in
   `train.py`. It was never run against the Phase 2 change; that gap is how this reached the
   owner.

### Constraint

**Do not replace one target redefinition with another.** If you believe the target is genuinely
mis-specified, that is a Stage B finding to be argued with evidence — not a change to make while
reverting.

---

## STAGE B — Answer the question WO-04 actually asked

WO-04 Phase 1 asked for a verdict on one thing, and it has not been delivered:

> **Is this a fixable model, or a gatekeeper that cannot work because its premise is false?**

### What the evidence says so far

- Un-neutralized, the model is ~95% degenerate — and so is the incumbent (95.5%), which predates
  the structural work entirely.
- `strategy_id` one-hot carried **96.78%** of gain importance; the regime feature **0.21%**; all
  nine numeric features **2.65%** combined.
- The standing repo finding is that regimes do not discriminate: `n_discriminating: 0 of 10`, max
  win-rate spread 0.0567 against a 0.10 bar, re-tested against honest labels and it held.
- The one attempt to make strategy identity uninformative produced an uplift of 0.011 at p=0.115
  — **not significant**, even with leaked labels helping it.

### The test that settles it

**Train with `strategy_id` removed entirely, on the honest target, and report what survives.**
AUC, OOS uplift, and its bootstrap significance. If nothing survives, market state carries no
information about trade outcome, and a gatekeeper conditioned on market state cannot work.

Run it per granularity as well as pooled — a null pooled result can hide a real one in a single
granularity, and the reverse.

### Both verdicts are acceptable

**If fixable:** implement the remedy, demonstrate degeneracy below the threshold **and** a
significant uplift, **without redefining the target and without touching any guard**.

**If not fixable:** write the retirement proposal. WO-04 §Phase 2 already specifies its contents:
what replaces the gate (shadow mode means possibly nothing), what happens to `oos_uplift_ok` in
the promotion gates, and what Systems 2/3 must be told — `hmm_model.joblib` and the gatekeeper
bundle are both in `S1_ARTIFACTS`, so retirement is a cross-system change.

**Retirement is not failure.** A component that cannot work is worth knowing about, and this one
currently blocks every retrain while gating nothing.

---

## STAGE C — Stop training on the holdout `[the owner's question, answered: yes]`

**Owner decision, 2026-09-09: both the gatekeeper and the HMM stop training on post-cut data.**

A holdout that the models have already trained on is not a holdout, and the first Stage-2 look
would be spent on nothing.

### Outcomes

1. `src/gatekeeper/train.py` excludes `is_holdout = True` rows from the training frame.
2. `src/regime/hmm_regime.py` does the same — it still gates promotion through
   `regime_accuracy_ok`, so its fit must respect the cut too.
3. The exclusion reads the `HOLDOUT_CUT_DATE` constant. **No date is hardcoded anywhere.**
4. Report the training-row count before and after for both, per granularity.

### Note the cost, do not hide it

Both models lose their most recent ~37% of data. For the gatekeeper this compounds a model
already in trouble. **Report the effect on uplift and accuracy rather than presenting the change
as free.**

---

## STAGE D — Correct the holdout boundary rule

A trade belongs to the holdout if **either its entry or its exit** falls after the cut. Classifying
on entry alone lets 2023 price action determine a Stage-1 outcome.

Measured magnitude, so you can size the work: **30 of 23,726 pre-cut trades = 0.126%** (D1 9,
H1 7, H4 14). Real, and small.

`fact_trade_outcomes` has no exit-time column; exit is derivable as
`timestamp + holding_bars × bar_duration`. If you add a stored exit timestamp, that is a schema
change — run `db-guardian`.

Also close the second half of the `leakage-hunter` finding: **the backfill SQL that bypasses the
cut logic.** Every path that writes `is_oos` or `is_holdout` must apply the same rule; a
backfill that sets them by a different route will silently disagree with the trainer.

---

## STAGE E — Record the holdout discipline

`devils-advocate`'s warning is half right, and the half that is right must be written down or it
will erode.

**Correct:** using post-cut data to validate *architecture* choices spends the holdout for that
purpose.

**Not applicable to what was done:** WO-03 and WO-04 chose architecture on **label statistics** —
diurnal spread, flicker, run length, label agreement. None is a strategy return. The holdout's
stated purpose is confirming *strategy selection*, and no strategy was selected on post-cut P&L.

Record in `results/state/holdout_register.jsonl`, as a standing constraint rather than a look:

> The holdout confirms **strategy selection**. It is never a benchmark for tuning system
> parameters, gates, or architecture. A decision informed by post-cut *returns* spends it; a
> measurement of post-cut *label statistics* does not.

---

## Constraints — all stages

- **Do not redefine the target to pass a guard.** That is what reopened this work order.
- **Do not touch** `MAX_DEGENERATE_CELL_SHARE`, `min_turnover_floor`, the turnover band, or any
  vetting gate.
- **Do not promote or publish.** Dry-run only. The orchestrator stays the only promotion path.
- **Do not run a Stage-2 holdout evaluation.** The first look is an owner decision and is not in
  this work order.
- Do not touch the live map or model set. They are unaffected and must stay that way.

## Gates

| after | invoke | why |
|---|---|---|
| A | **`leakage-hunter`** | **mandatory — the gap that let this through.** Any label or feature transform computed before the fold split |
| B | `measurement-reviewer` | the strategy_id-removed result, and any claim that signal does or does not survive |
| B | `devils-advocate` | before a retirement verdict is written down, and before a "fixed" verdict is believed |
| C | `leakage-hunter` | that no training path can still see a post-cut row |
| D | `db-guardian` | the boundary predicate and any schema change |
| before close | `structure-warden` | sweep |
| last | `auditor` | deliverables and claims |

## Deliverables

**`audit/reports/work_order_04b.md`** — query output, not prose:

1. `git diff` of the revert, and confirmation the neutralized artifacts are gone.
2. Degeneracy share and uplift (with p-value) for the honest target, un-neutralized.
3. The strategy_id-removed result: AUC, uplift, significance — pooled and per granularity.
4. Training-row counts before/after the holdout mask, gatekeeper and HMM, per granularity.
5. Trades reclassified by the entry-or-exit boundary rule.
6. What each gate returned.

**`SUMMARY-04B.md`** — one page, ending with the Stage B verdict in one sentence: **fixable, or
retire.**
