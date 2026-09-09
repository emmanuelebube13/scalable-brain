# Review of Work Order 04 and Work Order 05 Phase 1

**Reviewer:** Claude, 2026-09-09.
**Verdict on WO-04: NOT COMPLETE — the fix must be reverted before anything is built on it.**
**Verdict on WO-05 Phase 1: sound. Its three findings are correct; one is negligible in size.**

---

## 1. WO-04's "target neutralization" is target look-ahead

`src/gatekeeper/train.py`, `run()`:

```python
frame = build_frame()
frame = _derive_features(frame)

strat_medians = frame.groupby("strategy_id")["r_multiple"].transform("median")
frame["is_winner"] = (frame["r_multiple"] > strat_medians).astype(int)
...
wf = _walk_forward(frame)          # the split happens AFTER
```

**The median is computed across the entire frame — every fold, all OOS, all holdout — and only
then is the walk-forward split applied.** The label for a 2019 trade therefore depends on that
strategy's 2026 trades.

This is the defect class the repo has been fighting all year: information that reached a decision
before it existed. It is not a subtle instance. `leakage-hunter`'s standing check —
*"anything fitting outside its fold — scalers, feature selection, threshold tuning, imputation
statistics — leaks"* — covers a label transform computed on the full frame exactly.

## 2. It does not achieve what is claimed

**"Degeneracy cured" is true of the metric and false of the model.**

| measure | value | threshold |
|---|---|---|
| degenerate (strategy × regime) cells | **41 of 83 = 49.4%** | 50% allowed |
| OOS uplift | **0.011245** | ≥ `MIN_UPLIFT` |
| uplift p-value | **0.115094** | — |
| **significant** | **False** | must be True |

Three things follow.

**The degeneracy fell by construction, not by discovery.** Roughly half of any strategy's trades
beat that strategy's own median, by definition. The transform therefore forces every strategy to a
~50% base rate, which makes `strategy_id` uninformative about the target *as a matter of
arithmetic*. The metric had no choice but to improve. It is not evidence the model learned market
state — it is evidence the target was redefined until strategy identity stopped predicting it.

**It passed by 0.6 percentage points.** 49.4% against a 50% ceiling is not a cure; it is scraping
under a bar that was set to catch exactly this shape.

**The model still fails its own promotion gate.** `oos_uplift_ok` requires a non-negative,
bootstrap-**significant** uplift. At p=0.115 it is not significant, so `oos_uplift_ok` fails
closed and this model cannot be promoted regardless of the degeneracy number.

## 3. It also changes what an approval means

The gatekeeper no longer predicts "is this trade likely to win." It predicts "is this trade likely
to beat this strategy's median trade."

For a strategy whose median trade loses money, beating the median is still a loss. An approved
signal under this target is not a claim of profitability, and nothing downstream — System 2's
sizing, System 3's gates, the telemetry — knows that the meaning changed.

## 4. Against the work order's own constraints

WO-04 §2 stated: *"Do not touch `MAX_DEGENERATE_CELL_SHARE`, or `min_turnover_floor`, or the
turnover band. Widening a guard until a broken model fits through it is the failure mode this work
order exists to prevent."*

The guard was not widened. The **target was redefined until the model fitted through it**, using
leaked data. That is the same failure by a different route, and it is the one the constraint was
written to prevent.

WO-04 also offered a legitimate alternative outcome — *"'Retire the gatekeeper' is a legitimate
finding and, given the standing discrimination result, a live possibility. Do not treat it as
failure."* The measured evidence now points that way and it was not taken.

## 5. Process finding

`leakage-hunter` is reported as having run on WO-05 and to have found leaks there. There is no
evidence it was run against the WO-04 target change — which is where the actual leak is. WO-04's
gate table names `measurement-reviewer` and `devils-advocate` for Phase 1 but not
`leakage-hunter`, because Phase 1 was specified as read-only diagnosis. **Phase 2 changed the
training target and no leakage gate was specified for it.** That is a gap in the work order I
wrote, not only in the execution.

---

## 6. WO-05 Phase 1 — the three findings, verified

**Finding 1 — the gatekeeper trains on holdout data. CONFIRMED.**
`is_holdout` exists and is populated (33,967 of 93,616 rows). `src/gatekeeper/train.py` contains
no reference to it. Compounded by §1: the neutralized target's median is *also* computed over
holdout rows, so the holdout is contaminating both the features and the label.

**Finding 2 — exit-time look-ahead across the cut. CONFIRMED, and negligible.**
Measured, `position_engine_v2`, exit time derived as `timestamp + holding_bars × bar_duration`:

```
gran   pre-cut trades   exit after cut    share
D1              2,210                9   0.407%
H1             11,296                7   0.062%
H4             10,220               14   0.137%
ALL            23,726               30   0.126%
```

The mechanism is real and the boundary rule should be corrected — a trade belongs to the holdout
if **either** its entry or its exit falls after the cut. At 0.126% it is not a reason to hold
Phase 2.

**Finding 3 — "multiple-comparisons theatre". HALF RIGHT, and the distinction is load-bearing.**

The architecture decisions in WO-03 and WO-04 were made on **label statistics** — diurnal spread,
flicker rate, run length, label agreement. None of those is a strategy return. Measuring the
diurnal spread of a labelling rule over a span that includes 2023+ does **not** spend a holdout
whose purpose is to confirm *strategy selection*.

What *would* spend it: tuning a vetting gate against post-cut returns, or choosing which strategy
to ship by looking at post-cut P&L. Neither has happened.

The warning is still worth keeping, because the boundary is easy to cross without noticing. It
belongs in the holdout register as a standing constraint, not as a reason to stop.

---

## 7. Verdict and required order of work

**WO-04: NOT COMPLETE.** The target neutralization must be reverted. It is look-ahead, it cures
the guard by construction, and the resulting model fails its uplift gate anyway.

**WO-05 Phase 1: COMPLETE.** The holdout mechanism is built and its findings are correct. Phase 2
must not begin until the contamination in §1 and §6-Finding-1 is removed, or the first look will
be spent on a holdout that training has already seen.

Order, and the first item is not optional:

1. **Revert the target neutralization.**
2. Re-run the WO-04 Phase 1 diagnosis honestly against the real target, and reach the verdict the
   work order asked for: fixable, or retire.
3. Mask `is_holdout` in gatekeeper **and** HMM training.
4. Correct the holdout boundary rule to entry-or-exit.
5. Record the Finding-3 constraint in the holdout register.

Nothing here is urgent in the operational sense: the gatekeeper runs in shadow mode, nothing is
gated on its score, and the live map and model set are unaffected. **The system continues to
trade normally throughout.**
