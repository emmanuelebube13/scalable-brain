# Work Order 05 — A never-touched holdout period

**Rationale and measurements: `docs/design/HOLDOUT_PROPOSAL.md`. Read it first — it explains why
this exists and records the numbers this order relies on.**

**Runs LAST.** After WO-03 (labels settled, trading restored) and after WO-04 Phase 1. It changes
how the system decides, and it must not ride along inside another change.

---

## 1. What this fixes

Today "OOS" means `entry_time >= series_start + 36 months` — roughly **2009 → 2026, most of
history**. It is out-of-sample in the *fold* sense but it has been evaluated on every vetting run,
every gate change and every strategy iteration, across 51+ strategies × 4 regimes × 3
granularities, for months.

That is an uncounted multiple-comparisons problem, and it is the most likely explanation for cells
qualifying on **5, 13 and 20 trades with PF 13.58 / 8.28 / 6.76 and max drawdowns of 0.02%**. No
gate in `gates.py` can detect it — the gates see one cell at a time, never the search behind it.

## 2. Design — two stages, not a replacement

**Walk-forward OOS is NOT replaced.** Measured viability, `position_engine_v2`:

| granularity | pre-2023 | post-2023 |
|---|---|---|
| D1 | 2,210 | 1,400 |
| H1 | 11,296 | 6,504 |
| H4 | 10,220 | 5,891 |
| **all** | 23,726 | **13,795** (36.8%) |

31 of 41 v2 strategies have ≥30 post-2023 trades.

| stage | data | role |
|---|---|---|
| **1 — Selection** | walk-forward OOS, ending **2022-12-31** | the gates, exactly as today, on a closed span. Iterate freely. |
| **2 — Confirmation** | **2023-01-01 → present** | a cell that already passed stage 1 is checked **once**, on data never used to select it |

Stage 2 is **not** a gate with a tunable threshold. It answers one question: *does the thing we
selected still work where we have never looked?*

## 3. Outcomes

1. `fact_trade_outcomes` carries an **`is_holdout`** column alongside `is_oos`. Additive; the
   walk-forward design in `validation/walk_forward.py` is untouched, only its end date moves.
2. `HOLDOUT_CUT_DATE = "2023-01-01"` is a single named constant. **Nothing anywhere hardcodes the
   date** — the same rule that produced three disagreeing `REGIME_MODEL_VERSION` copies.
3. Stage-1 metrics are computed on OOS trades **strictly before** the cut. A stage-1 metric that
   silently includes holdout trades makes the whole exercise pointless — this must be enforced in
   code and covered by a test, not left to convention.
4. Stage 2 is a **separate, explicitly-invoked report**. It must not run as part of routine
   vetting, and `vet.py` must not read holdout data at all.
5. An append-only **look register** — `results/state/holdout_register.jsonl` — recording every
   stage-2 evaluation: date, what was tested, cells examined, result, who asked. This is what
   makes the multiple-comparison count knowable rather than guessed.

## 4. The discipline — the point of failure

**The holdout is a consumable resource. Every look spends some of it.** Encode what can be
encoded; document the rest:

- **Look once per decision**, not per run, not per iteration.
- **Never iterate against it.** Modifying a strategy *because* of a holdout result makes the
  holdout training data for that strategy, and it is spent.
- **Never turn it into a tunable gate.** That is the same mining, one level up.
- **Re-cut on a schedule, not on demand.** When exhausted, advance the cut date, record the new
  one, retire the old holdout into the training span. On demand means "whenever the answer is
  inconvenient."

Build the register so that violating these is *visible*, not impossible — a guard that blocks a
legitimate look will simply be bypassed.

## 5. Constraints

- **Do not change any vetting gate threshold.** This work order changes *which trades* the gates
  see, never the gates.
- **Do not run a stage-2 evaluation as part of this work order.** Build the mechanism, verify it
  on synthetic or clearly-labelled dry-run data, and stop. **The first real look is an owner
  decision** — and it is the one that spends the resource.
- Do not touch the map, `designate.py`, or the freeze.
- The 17,583 orphaned rows (strategies 7/8/9) are in scope only to the extent of reporting how
  many fall after the cut. Do not run `--reconcile`.

## 6. Owner decisions needed before Phase 2 of this order

Answer these **before** the first look, not after. Deciding afterwards is how a holdout gets
rationalised away.

1. **Does the gatekeeper also stop training on post-cut data?** Consistency says yes; the cost is
   that it loses its most recent data while already in trouble (WO-04).
2. **A cell passes stage 1 and fails stage 2 — rejected outright, or recorded and re-examined?**
3. **Does the HMM stop training on post-cut data?** It still gates promotion.

## 7. Review gates

| after | invoke | for |
|---|---|---|
| §3.1–3.3 | `db-guardian` | the additive column and the strictly-before-cut predicate |
| §3.3 | `leakage-hunter` | **the critical one** — that no stage-1 path can see a post-cut trade |
| §3.4–3.5 | `measurement-reviewer` | that the two-stage design measures what it claims |
| before close | `devils-advocate` | argue that this is theatre, and answer the argument |

## 8. Deliverables

**`audit/reports/work_order_05.md`** — query output, not prose:

1. Trade counts either side of the cut, per granularity, per engine.
2. Strategies with <30 post-cut trades — i.e. those stage 2 cannot meaningfully evaluate.
3. Proof that stage-1 metrics changed as expected when the OOS window closed at 2022-12-31, and
   by how much per cell.
4. How many of the 17,583 orphaned rows fall after the cut.

**`SUMMARY-05.md`** — one page: what changed, what is now true, what each agent found, what you
could not do, **what you did not check**.

## 9. Standing rules

- Claims carry evidence inline. Verification means running it.
- **State what you did not check.**
- If a constraint conflicts with an outcome, stop and report — do not choose.
