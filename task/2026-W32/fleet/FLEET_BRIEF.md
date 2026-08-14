# Fleet brief — 51-strategy research build

**Date:** 2026-08-09 · **Target:** implement `forex_swing_strategies.csv` (51 strategies)
against the System-1 research sandbox, faithfully enough that the verdicts mean something.

This file is context for *you* (the operator). The paste-ready prompts are the `WAVE*.md`
files. Send them in order; the gates between waves are real.

---

## The sequencing rule

> **Parallelise the leaves. Centralise the trunk.**

Fifty agents writing fifty strategies against a frozen interface is excellent. Ten agents
writing ten parts of one execution engine produces ten incompatible fill conventions, and
reconciling them costs more than writing it once.

So: **one** spec (written — `docs/design/CONTRACT_V2_AND_POSITION_ENGINE.md`), **one small
team** builds the engine, **then** the big fleet writes strategies against something that
already works.

If you invert waves 1 and 2 you get 51 files written against an interface that does not
exist, all needing rework. That is the failure mode this ordering exists to prevent.

---

## The three waves

| Wave | Agents | Depends on | Output | Send |
|---|--:|---|---|---|
| **0 — Spec extraction** | ~51 (1/strategy) | nothing | `SPEC-<id>.md` per strategy + gap notes | **now**, in parallel with Wave 1 |
| **1 — Engine build** | 6–8 | the design doc | `contract_v2.py`, `position_engine.py`, `causal_structure.py`, tests | **now** |
| **2 — Strategy authoring** | ~51 (1/strategy) | Waves 0 **and** 1, both reviewed | 51 strategy modules + golden fixtures | **only after I sign off Wave 1** |

Wave 0 and Wave 1 are independent and run concurrently. Wave 2 is gated on both.

**Why Wave 0 exists:** the CSV rows are prose written by traders. "Place a buy stop 2 pips +
spread above the SECOND consecutive higher high" contains at least four decisions an
implementer must make (which swing detector? confirmed when? spread at decision or fill? what
if a third higher high forms first?). Making those decisions *once, explicitly, in a
reviewable document* — before any code — is what turns Wave 2 from interpretation into
translation. It is also the single best use of a large agent fleet, because the 51 rows are
genuinely independent.

---

## The one instruction that makes review possible

**Every strategy in Wave 2 ships with a golden fixture:** 30–50 hand-specified OHLC bars plus
the exact expected order intent — entry type and level, stop level, every exit leg — and a
test that asserts the strategy produces it.

Without fixtures, "review 51 strategy files" means reading logic with no ground truth, which
is precisely where errors survive. With fixtures, review becomes checking whether the fixture
encodes the CSV row correctly — a far more reliable operation, and one that catches the
interpretation errors that matter.

**A Wave-2 deliverable without a passing golden fixture is not accepted.** Say this in the
prompt, and hold to it.

---

## Standing rules for every agent, every wave

1. **Never edit** `core_engine/backtest_engine.py`, `contract.py`, `engine_adapter.py`,
   `promote.py`, `registry.py`, or anything under `src/system1/`. Additive files only.
2. **Never import** `indicators.detect_swing_points` — it is look-ahead (`center=True`).
   Use `causal_structure.confirmed_swing_points`. This is not a style note: it is the exact
   bug that contaminated the only strategy in production.
3. **Never reimplement** a gate threshold or a metric. Import from `system1/vetting/gates.py`
   and `system1/attribution/metrics.py`.
4. **No look-ahead.** Every strategy must pass `assert_no_lookahead_v2`. Prohibited:
   `shift(-n)`, `rolling(..., center=True)`, `.iloc[i+1:]`, any whole-series normalisation
   (`(x - x.mean()) / x.std()` over the full frame), `resample` without a causal offset.
5. **State uncertainty, do not resolve it silently.** If the CSV row is ambiguous, pick the
   *more conservative* reading, implement that, and record the ambiguity and the alternative
   in the deliverable. A documented conservative choice is good work. A silent optimistic
   guess is the thing that makes backtests lie.
6. **Type hints everywhere; mypy clean; black formatted.**
7. **One agent, one strategy.** Do not refactor shared code in Wave 2 — if two strategies
   need the same helper, both declare it and the reviewer consolidates.

---

## What "faithful" means, and where it stops

Be straight with the fleet about this, because agents left to guess will overclaim:

- **Achievable:** pending stop/limit entries, three-leg scale-outs, breakeven-on-TP2,
  trailing stops, D1-filter/H4-entry structure, W1 frames. ~90% fidelity to the documented
  strategies.
- **Not achievable from bar data:** the intrabar path. When one bar's range covers both the
  stop and a target, no data says which came first. The engine always assumes the stop
  (convention F5). Resolving D1 strategies on H1 bars shrinks this gap substantially — and
  every strategy is run both ways so the residual is *measured and published*, not hidden.
- **Out of scope entirely:** position sizing (System 3's job), parameter optimisation,
  regime conditioning, and anything touching the live model.

---

## Expected outcomes — set these expectations now

- The **9 W1 strategies** will fail on trade count. 36 months of training ≈ 156 W1 bars.
  This is arithmetic, not a defect. Implement them anyway; report them honestly.
- Most of the 51 will **fail the gates** (PF≥1.5, Sharpe≥0.8, MaxDD≤25%, WinRate≥40%,
  Recovery≥3.0, OOS≥60mo). The T6 pilot — a reasonable strategy — came back PF 0.94,
  Sharpe −0.66. **A well-documented rejection is a successful run.** The purpose of this
  exercise is to find the two or three that survive, not to make 51 pass.
- The CSV's own grading is a prior worth respecting: **42 MODERATE, 5 HIGHLY_RECOMMENDED,
  4 EXPERIMENTAL**. Run the gates on the 5 HIGHLY_RECOMMENDED first to shake out the
  pipeline before committing compute to all 51.

---

## Operator checklist

- [ ] Send Wave 0 and Wave 1 prompts, with the files listed in `UPLOAD_MANIFEST.md`
- [ ] Bring Wave 1 output back here for review (engine correctness, the 12 acceptance tests)
- [ ] Bring Wave 0 output back here for review (spec fidelity, gap notes)
- [ ] **Gate:** only after both reviews pass, send Wave 2
- [ ] Bring Wave 2 output back here for review (51 files + fixtures)
- [ ] I wire it in and give you the run commands
- [ ] You run: data enablement first (pairs backfill overnight), then gates in waves
