# Work Order 04 — Why the gatekeeper is a strategy lookup table

**Two phases. Phase 1 is read-only and runs NOW, in parallel with Work Order 03. Phase 2 waits
until WO-03's labels have settled.**

Read `audit/reports/work_order_02_review.md` first. It establishes that this defect is
**pre-existing and not caused by the regime work** — the currently live champion fails the same
check, slightly worse.

---

## 1. The defect

`src/gatekeeper/train.py` refuses to ship a model whose approval decisions are bimodal across
(strategy × regime) cells, because such a model reproduces the strategy selection MODEL-005 has
already done rather than gating on market state.

Measured, and this is the whole problem:

| model | degenerate cells | share |
|---|---|---|
| live champion (`models/champion_manifest.json`) | 84 of 88 | **95.5%** |
| WO-02 candidate | 77 of 81 | 95.1% |

Live champion distribution: **77 cells approve ≤0.05, 7 approve ≥0.95, 4 in between.**

From `check_cell_degeneracy`'s own docstring, measured on champion `gk-656f09e2` on 2026-08-02:
`strategy_id` one-hot carried **96.78%** of the model's gain importance; `regime_causal` carried
**0.21%**; all nine numeric features carried 2.65% combined. Downstream, System 2 traded the one
qualified strategy — which sat in the 100% group in every regime — and measured a live approval
rate of **0.9995** against a published `oos_approval_rate` of 0.3379.

**The gate is not gating.** It has not been for months, and it currently blocks any retrain.

## 2. What is NOT the cause

Do not spend time on these; they are already excluded by measurement:

- **Not the structural label.** The live champion already trains on `regime_structural` and is
  degenerate. Flipping selection onto structural did not cause this.
- **Not the WO-02 work.** The guard is pre-existing code (present in commit `5f48b76`); WO-02 did
  not add or tighten it.
- **Not a threshold that needs relaxing.** `MAX_DEGENERATE_CELL_SHARE` exists to catch exactly
  this. **Do not touch it, or `min_turnover_floor`, or the turnover band.** Widening a guard until
  a broken model fits through it is the failure mode this work order exists to prevent.

---

## PHASE 1 — Diagnosis `[read-only, runs now, parallel with WO-03]`

### Constraint: change nothing

No edits to `src/gatekeeper/`. No training runs that write a model. `--dry-run` only, and prefer
analysis over training. Phase 1's deliverable is a **finding**, not a fix.

You may read, query and compute. You may retrain *in memory* to measure feature importance, but
nothing may be written to `models/`.

### Questions to answer, with evidence

1. **Is `strategy_id` structurally able to dominate?** It is one-hot encoded across ~41–67
   strategies against nine numeric features and one categorical regime. Quantify the imbalance in
   the design matrix, not just the resulting gain importance.

2. **Is the label learnable from market state at all?** This is the question that matters most.
   The standing repo finding is that **regimes do not discriminate** — `discrimination` reports
   `n_discriminating: 0 of 10`, max win-rate spread 0.0567 against a 0.10 bar, re-tested against
   honest labels and it stood. If market state genuinely carries no information about trade
   outcome, then **no gatekeeper trained on market state can work**, and the model collapsing onto
   `strategy_id` is not a bug — it is the model correctly finding the only signal present.
   **Test this directly.** Train with `strategy_id` removed entirely and report what AUC / uplift
   survives. If the answer is "nothing", say so plainly.

3. **What do the nine numeric features actually carry?** Per-feature importance and per-feature
   univariate association with the outcome. 2.65% combined is close to nothing; establish whether
   that is because they are weak or because they are collinear with each other.

4. **Is the target well-posed?** What exactly is the model predicting, over what horizon, and is
   the positive class rate stable across strategies? A target whose base rate varies wildly by
   strategy makes `strategy_id` the optimal predictor by construction.

5. **Was the incumbent ever non-degenerate?** Check prior champion manifests for
   `shipped_approval_by_strategy_regime`. If every champion on record is degenerate, the gate has
   never worked and should be described that way rather than as a regression.

### Phase 1 deliverable

`audit/reports/work_order_04_phase1.md`. Query output, not prose. It must end with a verdict on
one question:

> **Is this a fixable model, or a gatekeeper that cannot work because its premise is false?**

Both answers are acceptable. "Retire the gatekeeper" is a legitimate finding and, given the
standing discrimination result, a live possibility. **Do not treat it as failure** — a component
that cannot work is worth knowing about, and it is currently blocking retrains.

### Review gate

`measurement-reviewer` on the finding — in particular on any claim that a feature does or does not
carry signal. `devils-advocate` on the verdict before it is written down.

---

## PHASE 2 — Remediation `[BLOCKED until WO-03 completes]`

### Why it is blocked

WO-03 changes the volatility baseline that produces the regime feature, and separately makes the
gatekeeper read labels from `fact_regime_structural` instead of recomputing them. Any fix
validated before those land is validated against inputs that are about to change.

### Scope, set by Phase 1's verdict

**If fixable:** implement the remedy Phase 1 identified, retrain, and demonstrate the degeneracy
share falls below `MAX_DEGENERATE_CELL_SHARE` **without altering the threshold**. Candidate
directions Phase 1 should have ranked — do not choose one before it does:
drop or regularise `strategy_id`; per-strategy calibration instead of one pooled model;
strengthen the numeric feature set; reframe the target.

**If not fixable:** produce a retirement proposal, not a workaround. It must state what replaces
the gate (shadow mode already means nothing is enforced — so possibly nothing), what happens to
`oos_uplift_ok` in the promotion gates, and what System 2/3 must be told. Retiring the gatekeeper
touches `S1_ARTIFACTS` and the published bundle, so it is a cross-system change.

### Constraints

- The orchestrator stays the **only** promotion path. Do not add a second.
- Dry-run only. Promotion is owner-gated.
- Do not relax any guard to get a model through.

---

## 3. Standing rules

- Claims carry their evidence inline. Verification means running it.
- **State what you did not check.**
- If a constraint conflicts with an outcome, stop and report — do not choose.
- Report failures faithfully, with the output.
