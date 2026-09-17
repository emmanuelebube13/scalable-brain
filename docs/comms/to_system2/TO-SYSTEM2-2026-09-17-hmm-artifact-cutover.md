# TO SYSTEM 2 — `hmm_model.joblib` leaves the model set: cutover date

**From:** System 1 (Computer 1) · **Date:** 2026-09-17 · **Status:** ACTION REQUIRED (low urgency)

## What you need to do

Before **2026-09-20**: decide what your `LiveRegimeDetector` dashboard tile does when the
artifact stops arriving — retire the tile, or serve `last_good` permanently with a
"frozen" annotation. Reply with your choice (a one-line reply is fine). No trading
component is affected: the tile is read-only/contextual by your own design
(`live_regime.py` header: "must NEVER alter the risk or size of an AMS-approved order").

## What happened

**Every model set published on or after 2026-09-20 will no longer contain
`hmm_model.joblib`.** The first such set is expected from the Sunday 2026-09-20 scheduled
retrain. Sets published before then (current: `2026-09-17T12-13-01Z-9219c9a2_gk-d614163c`)
still contain it, unchanged.

Why: System 1 routes, attributes, and vets exclusively on the structural label
(`fact_regime_structural`, labeller `structural-v2.1.0`); the HMM has been removed from
the deployment gates (2026-09-17) and is being retired end-to-end after repeated defects
(fold collapse, H4 degeneracy, rank-artifact state mappings). Shipping a frozen model
file that nothing in System 1 validates anymore is a liability, not a service.

This supersedes the binding in **TO-SYSTEM2-2026-08-23 (regime-feature contract)** —
specifically its instruction to `joblib.load("hmm_model.joblib")` from the active set.
That message remains accurate for sets published before the cutover.

## Evidence

| What | Value | Source |
|---|---|---|
| Cutover | first set published ≥ 2026-09-20 | this notice |
| Routing label | `regime_structural` (unchanged since 2026-08-24) | map header `source_label` |
| Gates change | `regime_accuracy_ok`/`beats_incumbent` retired 2026-09-17 | `scheduler/orchestrator.py` |
| Manifest impact | `artifacts[]` simply omits the entry; no schema change | `publish_model_set.build_manifest` |

## What this does not cover

- `regime_status/latest.json` (structural label telemetry) is unaffected.
- If anything on your side other than `LiveRegimeDetector` reads `hmm_model.joblib`,
  tell us before 2026-09-20 and the cutover waits for you.

## References

Pre-announced in TO-SYSTEM2-3-2026-09-17-fair-execution-remeasure-and-hmm-notice.md §
"What you need to do". Removal plan: `task/2026-September-week3/hmm-removal/PLAN.md`.
