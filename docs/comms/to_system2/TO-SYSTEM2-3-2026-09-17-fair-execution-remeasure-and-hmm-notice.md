# TO SYSTEM 2 & 3 — fair-execution re-measure, map changes, and advance notice on `hmm_model.joblib`

**From:** System 1 (Computer 1) · **Date:** 2026-09-17 · **Status:** FYI + one dated heads-up

## What you need to do

Nothing today. One advance notice: System 1 intends to **stop publishing
`hmm_model.joblib`** in a future model set. A separate ACTION-REQUIRED message with a
cutover date will follow before anything changes; this paragraph exists so the intent is
on the record. The artifact is still present and unchanged in every set named below.
(System 2: your `LiveRegimeDetector` dashboard tile is, to our knowledge, the only
consumer — per the 2026-08-23 regime-feature contract. Tell us if anything else reads it.)

## What happened

1. **`r_multiple` changed definition (2026-09-17).** It is now NET of a 2.4-pip
   round-trip cost (midpoint of the 1.8–2.9 pip measured live spreads) and same-bar
   SL/TP collisions are resolved against M15 data (unresolvable → stop-first,
   `exit_reason: "sl_tp_ambiguous"`). Every number in `risk/strategy_stats` and the
   analytics bundle reflects this from today's publishes onward. Do not compare new
   figures against pre-2026-09-17 ones — the definition moved, not the strategies.
2. **The live map shrank and lost all owner overrides.** Current set
   `2026-09-17T12-13-01Z-9219c9a2_gk-d614163c`: **3 qualified cells, 0 designated**
   (43 Trending-Up; 50 and 13 High-Vol; Ranging and Trending-Down empty — cell
   membership near the gate boundaries is sample-sensitive between runs, which is
   itself disclosed here so a cell count change without a code change does not read
   as an incident).
   Withdrawn since the 2026-09-11 set: `xard_ma_cross_daily_open` (both prior maps'
   Trending-Up designation) and `weekly_gap_fade@H1@High-Vol` (fair-execution pooled
   Sharpe −2.62, CI [−0.049, +0.012]). Expect materially fewer signals: those two were
   the highest-volume producers.
3. **Three strategies retired from the registry** (owner decision; CI on mean R clear of
   zero, negative): ids 30, 46, 49. None were in the live map.
4. **Duplicate re-arms no longer reach the wire** (since 2026-09-16): a pending setup
   re-armed on consecutive bars publishes once (`wire_action: suppressed_duplicate` in
   System 1's ledger). This removes the O-26/O-23-adjacent duplicate-sizing exposure at
   the source; System 3's Layer-R guard remains the defence in depth.

## Evidence

| What | Value | Source |
|---|---|---|
| Live model set | `2026-09-17T12-13-01Z-9219c9a2_gk-d614163c` | top-level `latest.json` |
| Qualification run | `24fca4c1` era (map header `qualification_run_id`) | bundle `regime_strategy_map.json` |
| OOS bank | 12,319 trades, net mean R −0.0911, 5 ambiguous exits | attribution report 2026-09-17 |
| Cost model | 2.4 pips round trip, flat | FIX-S1-023; PREREGISTRATION.md L28 |
| Gatekeeper champion | UNCHANGED — `2026-08-20T21-26-20Z-d614163c` | `models/gatekeeper/latest.json` |

## What this does not cover

- The flat 2.4-pip cost will be refined per pair from your live fill data — a future
  additive change to strategy stats, with its own notice if the contract widens.
- The map-renewal deployment gates changed internally (evidence-based instead of
  HMM-agreement-based); no field you read changed shape.
- Known and unchanged: manifest `status` handling on your side (S2-side fail-open on a
  missing field) — raised separately in a prior message set, still owed a reply.

## References

- Supersedes nothing; extends the 2026-09-11 set announcements.
- `docs/proposed-fixes/system-1/FIX-S1-022/023`; `task/2026-September-week3/core-verification/PHASE-A-RESULTS.md`.
- The 2026-08-23 regime-feature contract message (the `hmm_model.joblib` consumer binding this notice pre-announces changing).
