# WAVE 1 — Contract v2 + position engine (paste this whole file as the prompt)

**Fleet size:** 6–8 agents with fixed roles. **Not** a free-for-all — this is one coherent
component and divergent conventions here poison all 51 downstream strategies.
**Depends on:** nothing. Runs concurrently with Wave 0.
**Output:** four new modules + a test suite, all additive.

---

## Uploaded files

- `CONTRACT_V2_AND_POSITION_ENGINE.md` — **the specification. It is authoritative.**
- `contract.py` — the v1 contract you extend (read; do not edit)
- `engine_adapter.py` — the existing uniform-ATR adapter (read; do not edit)
- `backtest_engine.py` — the incumbent engine (read for conventions; **never edit**)
- `multi_timeframe.py` — existing MTF engine to verify and wire, not replace
- `indicators.py` — the indicator inventory
- `promote.py`, `registry.py`, `research_data.py` — the surrounding sandbox
- `walk_forward.py`, `gates.py`, `metrics.py` — import from these; never reimplement
- `LOOKAHEAD_FINDINGS.md` — why `detect_swing_points` is banned

---

## Mission

Build the parallel, faithful execution path described in the spec. The existing T6 path stays
byte-for-byte intact and keeps passing its 15 tests. You are adding a second way to backtest,
not replacing the first.

Read §1 of the spec — the six inviolable constraints — before writing anything. They are
enforced by tests and by review.

---

## Roles

| Agent | Owns | Notes |
|---|---|---|
| **A — Contract** | `contract_v2.py` | Types, validation, `assert_no_lookahead_v2`, `SignalStrategyAdapter`. Finishes first; B and C depend on the types |
| **B — Engine** | `position_engine.py` | Fill conventions F1–F12, per-bar operation order, `BacktestResult`. **Single owner — do not split this file across agents** |
| **C — Causal structure** | `causal_structure.py` | `confirmed_swing_points`, `zigzag_swings`, `last_n_confirmed_highs`. Highest-risk module: 36 of 51 strategies depend on it |
| **D — MTF wiring** | alignment + `test_mtf_causality` | Verify `multi_timeframe.py`'s look-ahead claim empirically, then wire. If the claim is false, report it — do not quietly patch |
| **E — Harness** | walk-forward + per-cell reporting | Wire the engine into `walk_forward.py` folds; per-cell + pooled + dispersion (spec §8) |
| **F — Adversary** | attacks | Runs **after** A–E. Tries to break every guarantee. See below |
| **G — Enablement** | W1 + pairs | Spec §7. Independent of A–F; can finish early |

Agents A, B, C are the critical path. D, E depend on A and B. F runs last.

---

## The two things most likely to go wrong

**1. The v1-equivalence test.** A v1 strategy run through `SignalStrategyAdapter` and the new
engine MUST produce r-multiples identical to the T6 path to 1e-9 on a fixed fixture. If this
fails, the new engine has silently changed execution semantics and **every** result it ever
produces is incomparable to everything already in `results/research/`. Build this test
*first*, before the interesting features. Treat a failure as a stop-work condition.

**2. Causality.** Two independent places can leak the future:
- MTF alignment (spec §4): a D1 bar stamped at its open must not inform intraday decisions
  until it has closed. Off by one bar and every D1-filtered strategy is inflated.
- Swing points (spec §6): `indicators.detect_swing_points` uses `center=True` and is
  look-ahead. It contaminated `Range_Stochastic_Divergence`, the only strategy in
  production. Your replacement stamps swings at their **confirmation** bar and carries the
  level from the **occurrence** bar.

Both need tests that assert at the *boundary*, not on average. An average-case test passes
vacuously here — that is exactly how the production contamination survived qualification.

---

## Agent F — adversarial pass (run last, report before fixes)

Attempt each of these. Every one MUST be blocked by code, not by convention. Report each
with a `file:line` citation for the blocking mechanism.

1. A strategy using `shift(-1)` inside `generate_orders` → must fail `assert_no_lookahead_v2`
2. A strategy that fires so rarely the truncation probe covers no firing bar → the
   FIX-S1-013 vacuous-pass hole; the v1 contract already handles this (`contract.py:185-210`)
   and v2 MUST too
3. An `OrderIntent` with exit fractions summing to 1.5
4. A stop on the wrong side of entry for the direction
5. A pending `buy_stop` priced *below* the market at the decision bar (an instant fill
   disguised as a pending order)
6. A trailing stop that widens
7. A strategy reading the database from inside `generate_orders`
8. A strategy mutating the frames it is handed (and thereby the next strategy's data)
9. Promotion to `qualified` bypassing `vetting/gates.py`
10. A threshold literal (1.5, 0.8, 0.25, 0.4, 3.0, 60) hardcoded anywhere in the new modules
11. Two strategies sharing a `strategy_id` across different stages
12. A breakeven rule that moves the stop *before* the triggering leg fills

Where an attack succeeds, file it precisely; the owning agent fixes it; you re-run.

---

## Definition of done

- Four new modules: `contract_v2.py`, `position_engine.py`, `causal_structure.py`, plus the
  harness changes. All additive — `git status` shows **no modifications** to the files listed
  as read-only in spec §1.
- All 12 acceptance tests from spec §9 pass, with `test_v1_equivalence` first among them.
- The 15 existing T6 tests pass, unmodified.
- `mypy` clean on new modules; `black` formatted.
- W1 enabled and refreshed; the 8 new pairs' `dim_asset` rows written and the ingest command
  documented (running the backfill is the operator's job, not yours).
- A `WAVE1_REPORT.md` covering: the API as built (with any deviations from the spec and why),
  the v1-equivalence result, the MTF causality test at the boundary bar, all 12 attacks and
  their blocking `file:line`, and anything you could not do.

**Deviations from the spec are allowed but must be reported, never silent.** If the spec is
wrong somewhere, say so — it was written against a reading of the code, not against a running
build.
