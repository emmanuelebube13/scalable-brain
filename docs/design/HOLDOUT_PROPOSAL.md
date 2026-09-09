# Proposal — a never-touched holdout period, in addition to walk-forward OOS

**Raised by owner, 2026-09-08. Status: assessed, viable, not yet decided.**

Proposal: reserve market data from a cut date (proposed **2023-01-01**) that is never used for
training or for iterating on strategies, and evaluate on it.

---

## 1. The problem this actually solves, and it is real

Today "OOS" means: `entry_time >= series_start + 36 months`. Everything after the initial training
window. In practice that is roughly **2009 → 2026 — most of history.**

It is out-of-sample in the *fold* sense. It is **not untouched**. That same span has been
evaluated on every vetting run, every gate change, every strategy iteration, across 51+ strategies
× 4 regimes × 3 granularities, repeatedly, for months.

That is a multiple-comparisons problem with an effective search space nobody has counted. It is
the most likely explanation for cells qualifying on **5, 13 and 20 trades with PF 13.58, 8.28 and
6.76 and max drawdowns of 0.02%** — those are what winning-by-search looks like, and no gate in
`gates.py` can detect it, because the gates see one cell at a time.

A genuinely untouched holdout is the standard remedy. **The instinct is correct.**

## 2. Is there enough data? Yes — measured

`position_engine_v2` population, 2026-09-08:

| granularity | pre-2023 | **post-2023** | current "OOS" |
|---|---|---|---|
| D1 | 2,210 | **1,400** | 2,624 |
| H1 | 11,296 | **6,504** | 12,335 |
| H4 | 10,220 | **5,891** | 11,269 |
| **all** | 23,726 | **13,795** | 26,228 |

- The holdout would be **36.8%** of all v2 trades.
- **31 of 41** v2 strategies have ≥30 post-2023 trades.

That is a healthy holdout — larger than expected, and enough to measure most of the fleet.

## 3. Recommendation: add it, do not replace OOS with it

**Do not** replace walk-forward OOS. Two reasons:

1. **The gates need trades.** PF, Sharpe, MaxDD and recovery on 3.7 years alone would give thinner
   samples than today — and thin samples are the problem being solved, not the solution.
2. **A holdout consulted routinely is not a holdout.** If every vetting run reads 2023+, it is
   mined exactly like the current OOS and is worthless within a few months.

**Use two stages instead:**

| stage | data | role |
|---|---|---|
| **1. Selection** | walk-forward OOS, ending **2022-12-31** | the gates, as today, on a closed span. Iterate freely here. |
| **2. Confirmation** | **2023-01-01 → present** | a strategy that already passed stage 1 is checked once on data never used to choose it |

Stage 2 is not a gate to be tuned. It answers one question: *does the thing we selected still work
where we have never looked?*

## 4. The discipline that makes it work — and the failure mode

**The holdout is a consumable resource. Every look spends some of it.**

Rules, without which this is theatre:

- **Look once per decision.** Not per run. Not per iteration.
- **Record every look** — date, what was tested, the result — in an append-only register. The
  register is what makes the multiple-comparison count knowable instead of guessed.
- **Never iterate against it.** The moment a strategy is modified *because* of a holdout result,
  the holdout is training data for that strategy and is spent.
- **Never let it become a gate with a threshold someone tunes.** That is the same mining, one
  level up.
- **Re-cut it on a schedule, not on demand.** When it is exhausted, advance the cut date — with the
  new date recorded and the old holdout retired into the training span. On demand means whenever
  the answer is inconvenient.

**Honest cost:** 2023+ is also the most recent, most regime-relevant data, and it would no longer
train the gatekeeper or the HMM. That is a real loss and should be accepted knowingly, not
discovered later.

## 5. Interaction with current work

- **Not part of Work Order 03.** That one fixes the diurnal contamination. This is a change to how
  the whole system decides, and it should not ride along inside another change.
- **It would make the WO-03 verdict trustworthy.** The proposed map's one qualified cell
  (`holy_grail_pullback@D1@Trending-Down`, 10 trades) is precisely the kind of result a holdout
  check exists to accept or kill. Today there is no way to tell which it is.
- **`is_oos` already exists** on `fact_trade_outcomes`, so a `is_holdout` column alongside it is
  additive and cheap. The walk-forward design in `validation/walk_forward.py` stays untouched;
  only its end date moves.

## 6. Open questions for the owner

1. **Cut date.** 2023-01-01 gives 13,795 trades. A later cut preserves more training data but
   thins the holdout. 2023-01-01 looks well-judged.
2. **Does the gatekeeper also stop training on 2023+?** Consistency says yes. Cost: the gatekeeper
   loses its most recent data, and it is already in trouble (§ the degeneracy work order).
3. **What happens when a strategy passes stage 1 and fails stage 2?** Rejected outright, or
   recorded and re-examined? Decide *before* the first failure, not after — deciding afterwards is
   how a holdout gets rationalised away.
