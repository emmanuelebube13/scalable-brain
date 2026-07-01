# FIX-S1-002 — "OOS ≥ 60 months" gate measures in-sample span, not true out-of-sample

**Severity:** P1 (overstates confidence in qualified strategies; not impossible-number-producing)
**Status:** VERIFIED (log-only) — OOS gate now fires (`oos_fail` 0→8); gate-can-fire regressions (overfit fails OOS, low-oos rejected) + independent re-verify (39 tests green, pure walk-forward calendar math reviewed, no bugs); proposed map regenerated, live map untouched, pending promotion sign-off
**Author:** Claude (surfaced while implementing FIX-S1-001)
**Date raised:** 2026-06-26

> **Implementation note (2026-06-30):** Implemented on branch `fix/s1-002-true-oos` (Option A,
> walk-forward folds) — stacked on the Verified FIX-S1-004. New reusable component
> `src/system1/validation/walk_forward.py` (`generate_folds`/`assign_oos`/`oos_month_span`, locked
> design: anchor = per-granularity min entry_time, `min_train=36mo`, `step=6mo`, `oos_window=6mo`,
> anchored) — built reusable because FIX-S1-005 shares it. Schema: additive `is_oos`/`fold_id` on
> `fact_trade_outcomes` (`ADD COLUMN IF NOT EXISTS` + index, idempotent), backfilled in place from
> existing `entry_time`s (split: **93,458 OOS / 41,062 in-sample, no NULLs**). `attribute.py` now
> computes every gate metric on the **OOS subset only**; `oos_months` = `oos_month_span` of the OOS
> windows the cell traded; old full-span field retained reporting-only as `in_sample_span_months`
> (lives in the parquet/report — not a DB column, dropped by the schema-aware writer). A
> `validation_design` lineage block is written into the regime map (contract loosened additively).
>
> **Pre-existing defect exposed + fixed (owner-approved):** the FIX-S1-001 sanity guard
> (`|Sharpe|<=10`) hard-aborted MODEL-004 on a thin starved-regime cell (strategy 10 / High-Vol / H4,
> 2–4 OOS trades, |Sharpe|≈4269 — a small-sample artifact, not corrupt math). The guard is identical
> to baseline and would abort a baseline re-run too; run `5bfa38bc` predates it being on the live
> path. Fix: cells with `trade_count < N_MIN (20)` clamp the unstable metric to the sanity bound and
> continue (they are `low_confidence` → unconditionally rejected downstream); the hard abort is
> retained for `>= N_MIN` cells (real corrupt math). Regression tests cover both branches.
>
> **Log-only re-run (run `d5004493`, NO promotion):** `oos_months` distribution min 18 / max 84 /
> median 83 (was uniformly ~117–120); **11/80 cells now below the 60-mo OOS gate**;
> `rejection_summary.oos_fail` **0 → 8** (the gate is no longer inert). The qualifying set is
> unchanged (Range_Stochastic_Divergence@H1 in Trending-Up/Down/Ranging + @H4 in Ranging) — those
> cells survive genuine OOS scrutiny. High-Vol remains starved/empty. Tests: **95 passed** (full
> System-1 suite, incl. "overfit fails OOS", clamp, and guard-still-aborts); black clean; mypy = pre-
> existing noise only (no new error classes). Live `results/state/regime_strategy_map.json` untouched.
**Scope:** `src/system1/attribution/attribute.py` (`_cell_metrics` `oos_months`), MODEL-005 vetting gate,
`financial-metrics` skill (`oos_month_span`), MODEL-005/007 lineage.
**Affected pipeline:** MODEL-004 → MODEL-005 (vetting & regime map) → MODEL-007 (bundle to Computer 2).
**Risk to live trading:** None to fix; but the *current* behavior ships strategies that look more proven
than they are.

---

## 1. Executive summary

The qualification gate advertises **"Out-of-Sample coverage ≥ 60 months"** — meaning a strategy must
prove itself on data it *never saw during design/fitting* for at least 5 years. In reality the system
currently computes `oos_months` as the **calendar span of all the strategy's trades** — i.e. the full
in-sample history. So the gate that is supposed to be the strongest guard against overfitting is, today,
**not testing out-of-sample at all.** It does not create impossible numbers (so it is P1, not P0), but it
**inflates trust**: a curve-fit strategy can pass the OOS gate purely by having traded over a long
window. This matters because the whole project philosophy is *"no strategy touches live data until it
proves a mathematical edge."*

---

## 2. Evidence

In `src/system1/attribution/attribute.py`, `_cell_metrics` (the code's own comment is candid):

```python
# Calendar span of the cell's trades drives both the coverage proxy (oos_months) ...
# NOTE: backtests are full-history (not walk-forward folds), so oos_months is an
# in-sample coverage proxy, not true OOS.
span_days = (cell["entry_time"].max() - cell["entry_time"].min()).days
oos_months = round(span_days / 30.44, 2)
```

Then in `src/system1/vetting/gates.py` the gate treats that proxy as if it were real OOS:
```python
"oos_months": 60,
...
if cell.get("oos_months", 0) < GATES["oos_months"]:
    failures.append(f"OOS={cell['oos_months']}mo < 60mo")
```

Symptom in the corrected run: every qualifying cell reports `oos_months ≈ 117–120`, and the rejection
summary shows `oos_fail: 0` — **no strategy is ever rejected by the OOS gate.** A gate that never fires
is either trivially satisfied or not measuring what it claims. Here it is the former.

The `financial-metrics` skill even documents the *correct* intended method (`oos_month_span` over
walk-forward folds), so the spec is right — the implementation took a shortcut.

---

## 3. Root cause

The backtests that populate `fact_trade_outcomes` are **full-history single passes**, not walk-forward
(train-then-forward-test) runs. There are no fold boundaries recorded per trade, so the attribution stage
has nothing to distinguish "in-sample" trades from "out-of-sample" trades and falls back to total span.

---

## 4. Proposed solution (high level — needs design)

This is a larger change than FIX-S1-001 because it touches how strategies are *backtested*, not just how
metrics are computed. Two options, in increasing rigor:

**Option A — Walk-forward folds at qualification (recommended).**
Re-run Layer 0 / qualification as **walk-forward**: repeatedly fit/select on an in-sample window, then
record trades on the *next* unseen window, rolling forward across history. Tag each trade in
`fact_trade_outcomes` with an `is_oos` flag (and/or `fold_id`). Then:
- `oos_months` = union span of OOS windows only (use the skill's `oos_month_span`).
- All gate metrics (PF/Sharpe/MaxDD/Recovery/WinRate) computed on **OOS trades only**.

**Option B — Holdout split (lighter, weaker).**
Reserve the most recent N years as a pure holdout never used in any selection; require the strategy to
clear gates on that holdout. Simpler, but one fixed split is less robust than rolling folds.

**Either way:** add a `fact_trade_outcomes.is_oos` (boolean) / `fold_id` column, teach attribution to
honor it, rename the metric honestly (`oos_months` only counts OOS), and record the validation design in
the map lineage so Computer 2 knows how the numbers were earned.

---

## 5. Validation plan

- Unit: `oos_month_span` merges overlapping folds correctly; metrics computed on OOS subset only.
- Property: a deliberately overfit strategy passes in-sample but **fails** OOS gates (regression test
  that this gate can actually fire).
- Re-run qualification log-only; expect the qualifying set to **shrink** vs. FIX-S1-001's map — that
  shrinkage is the point (it removes strategies that only looked good in-sample).

---

## 6. Rollout, risk, non-goals

- **Sequencing:** do this **after** FIX-S1-001 is promoted, so we change one thing at a time.
- **Risk:** none to live trading during the work; the corrected map stays authoritative.
- **Effort:** medium-large (re-architects the backtest pass + adds a column + re-runs history).
- **Non-goal:** changing the 60-month threshold value — keep the threshold, just make it *real*.

---

## 7. One-paragraph summary for a fast reviewer

The "5 years out-of-sample" gate is the system's main anti-overfitting guard, but it currently measures
the *full in-sample* trade span, so it never rejects anything (`oos_fail: 0`). Fix: re-run qualification
as walk-forward (or at least a reserved holdout), tag each trade as in- vs out-of-sample, and compute the
gate metrics on OOS trades only. Expect the qualifying strategy set to shrink — that shrinkage is exactly
the overfit risk we're currently blind to. Do it after FIX-S1-001 is promoted; no live-trading risk.
