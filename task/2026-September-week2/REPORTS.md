# Reports for this week — where they live

Reports are **not** stored in this folder. Per `STRUCTURE.md`, `task/` holds work items and
`audit/reports/` holds their output. This file is the index so nothing has to be hunted for.

| report | path | status |
|---|---|---|
| WO-01 — structural writer restored; cost of a map rebuild | `audit/reports/work_order_01.md` | complete |
| WO-02 — summary written by the implementing agent | `task/2026-September-week2/regime-multi-timeframe/SUMMARY.md` | complete — **see the review below before relying on it** |
| **WO-02 REVIEW — corrections** | **`audit/reports/work_order_02_review.md`** | **complete, and load-bearing** |
| WO-03 — de-seasonalise, rebuild, resume trading | `audit/reports/work_order_03.md` | not yet written |
| WO-04 Phase 1 — gatekeeper diagnosis | `audit/reports/work_order_04_phase1.md` | not yet written |
| WO-04B — revert the leaky target; fixable-or-retire | `audit/reports/work_order_04b.md` | complete — **superseded on its central recommendation, see below** |
| WO-05 — holdout | `audit/reports/work_order_05.md` | not yet written |
| **Gatekeeper feature basis and trade geometry** | **`audit/reports/gatekeeper_feature_basis.md`** | **complete — supersedes WO-04B's verdict** |

## Read the feature-basis report before acting on WO-04B's verdict

WO-04B concluded *PARTIALLY FIXABLE (H1 only)* and recommended **retiring the gatekeeper for
H4 and D1**. Do not act on that. It was correct for the feature basis and the data it had, and
both have since changed:

- The basis it tested had **nothing transferable in it**. `atr_sl_multiplier` and
  `atr_tp_multiplier` were NULL in all 93,738 rows, so removing `strategy_id` left only market
  state. Those columns are now populated; the same folds then give a significant uplift with
  an AUC that exceeds the old `strategy_id` basis.
- **The per-granularity conclusion inverts.** On the rebuilt evidence H4 carries the edge
  (uplift 0.1405, p=0.00005) and H1 does not (p=0.4663) — the opposite of WO-04B. That
  comparison is confounded (basis and table changed together) and the report says so.
- The retrain is **still blocked**, but no longer for the reason WO-04B gives. See O-30.

One qualification runs the other way, and it is in §2.6: the new basis's strongest feature is
partly win-rate arithmetic, and the mean-R uplift it converts to fails in one of five folds.

## Read the WO-02 review before the WO-02 summary

`audit/reports/work_order_02_review.md` corrects **three of the four load-bearing claims** in
WO-02's summary. In short:

- The gatekeeper refusal does **not** show the structural regime is bad — the currently live
  champion fails the same check slightly *worse* (95.5% vs 95.1%) and was already trained on
  structural labels.
- "Only one strategy passed, on 10 trades" is wrong — four cells qualified, on 932, 160, 135 and
  10 trades.
- The before/after comparison is confounded: the label **and** the engine filter changed together,
  and the trade population fell 60% because of the engine, not the label.
- The finding that *was* right — H1 volatility is contaminated by time of day — is what Work
  Order 03 exists to fix.

Acting on the uncorrected summary would mean abandoning work that is largely sound.
