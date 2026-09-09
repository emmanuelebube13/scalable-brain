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
| WO-05 — holdout | `audit/reports/work_order_05.md` | not yet written |

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
