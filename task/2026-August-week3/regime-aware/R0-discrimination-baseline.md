# R0 — Discrimination baseline

**Engineer:** Gemini Pro · **Reviewer:** Claude
**Estimated time:** 1–2 hours · **Risk:** none — read-only, no writes anywhere.
**Blocking:** No. See "What a null result means" below.

**Read `STATE.md` first. Read `README.md` §3 and §4.**

---

## Why this task exists

Before gating strategies by regime, measure whether regime carries any information about
their outcomes at all. This is the cheapest possible check and it sets the expectation for
everything after it.

Prior evidence, so you know what you are testing against:

- **Finding B**: `n_discriminating: 0 of 10` on the legacy ten, re-tested 2026-08-14 against
  the corrected labels. Among the nine clean strategies the max win-rate spread was 0.0567,
  against a 0.10 bar.
- That was measured on the **legacy ten**, which are mostly range and mean-reversion
  strategies, using an omnibus spread across all four HMM states.
- **The 43 new v2 strategies have never been measured for this.**

So this is not re-running a settled question. It is asking it of a fleet that was never
tested, with an instrument (D1 trend) that was not the one that produced finding B.

---

## What a null result means

**It does not stop the trial.** The owner has decided explicitly: the build continues
regardless of what R0 finds, because the first week's goal is to see the system work end to
end, not to prove the edge.

What R0 changes is **what we claim**. If nothing discriminates, the week is a plumbing
exercise and the documentation in R5 must say so plainly. If something does discriminate,
we have a pre-registered reason to expect the aware arm to differ, recorded *before* R3
runs — which is worth considerably more than noticing it afterwards.

Record the result either way. Do not soften it.

---

## Hard constraints

1. **Read-only.** No writes to any table. No new tables.
2. Output goes to `results/regime_aware/R0/` as JSON plus a short markdown summary.
3. Only ever read `regime_causal`. Never `regime_smoothed`.
4. Reuse `src/system1/attribution/discrimination.py` if it fits. Do not reimplement a
   metric that already exists — that mistake produced a 1650% drawdown figure once already.

---

## Execution plan

### Step 1 — Inventory

Establish what you are measuring. `python -m src.layer0.strategies.v2_harness --list`
enumerates the discovered v2 strategies (43 as of 2026-08-16). Cross-check against
`results/research/` for which have evaluation reports with pooled trades.

Record the count in `STATE.md`. If it is not 43, say what changed.

### Step 2 — Attach regime to each strategy's OOS trades

For each strategy's most recent `v2_evaluation_*.json`, take the OOS trades and attach the
regime in force at the **decision bar** (not the fill bar), under both instruments:

- `d1_trend` — via `src/regime_aware/context.py::build_trend_labels`
- `hmm_causal` — via `fact_market_regime_v2.regime_causal`

The point-in-time join must not leak: the label attached to a trade must be one that existed
before the decision. `src/system1/attribution/attribute.py` already does this join correctly
— read it and follow the same discipline.

### Step 3 — Measure discrimination, two ways

**(a) The omnibus test, for continuity with finding B.** Max spread in win rate across
regimes, per strategy, per label source. Bar: 0.10.

**(b) The directional test — this is the one that matters for our hypothesis.** Finding B's
omnibus spread is a weak instrument for the question we are actually asking. Our hypothesis
is not "outcomes vary by regime"; it is "trend-following strategies do better in trending
regimes." That is one-sided and family-specific, so it has far more power.

For each strategy, using the family declared in R2 — **if R2 has not run yet, use the
strategy's own declared metadata or its filename family, and record which you used** —
compute mean R and win rate inside its hypothesised-favourable regimes versus outside, with
a bootstrap CI on the difference.

Report both. Do not report only whichever is more encouraging.

### Step 4 — Concentration check

For every result that looks positive, report the **per-pair breakdown**. A "discriminating"
strategy whose entire effect sits in one pair is the T3 artifact repeating. State the pair
composition of every favourable cell explicitly.

This check is not optional and it is the reason this task exists at all.

### Step 5 — Write up and append to STATE.md

`results/regime_aware/R0/SUMMARY.md`: how many strategies discriminate under each test and
each label source, the concentration findings, and one paragraph of plain-English verdict.

---

## Definition of done

- [ ] Every discovered v2 strategy with pooled OOS trades is covered, or its exclusion is stated
- [ ] Both label sources measured
- [ ] Both the omnibus and the directional test reported
- [ ] Per-pair breakdown given for every favourable result
- [ ] `SUMMARY.md` states the verdict plainly, including if it is "nothing discriminates"
- [ ] Nothing was written to any database table
- [ ] `STATE.md` updated

## What the reviewer will check

- That the regime join is point-in-time and uses `regime_causal`.
- That per-pair breakdowns are present for **every** positive result, not a sample.
- That a null result, if found, is stated plainly rather than buried in hedging.

---

## Failure log

| Timestamp | Step | What went wrong | Root cause | Fix applied |
|---|---|---|---|---|
| | | | | |
