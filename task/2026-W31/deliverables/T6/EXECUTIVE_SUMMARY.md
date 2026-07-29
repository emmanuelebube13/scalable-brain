# T6 — Research Strategy Engine · Executive Summary

**2026-07-29 · System 1**

## What you now have

A sandbox where a new trading idea can be tried without any risk of it sneaking into the live
model.

Drop a file in `research/`, run one command, and you get a verdict. The idea is backtested
across the same walk-forward windows the live system uses, with the same trading costs, and
then judged by **the very same gates** — not a copy of them. There is one set of standards in
this project, and the sandbox is held to it.

Three stages, and only the last one is visible to the live pipeline:

```
research/  →  staged/  →  qualified/
(anything)    (no look-  (passed the live
              ahead,      gates on out-of-
              real trades) sample data only)
                                │
                                └── the only folder the live system can see
```

## The proof it works: the pilot was rejected

I put a real strategy through it — RSI mean reversion, a plain idea chosen precisely because
its outcome wasn't pre-decided. It generated **9,806 out-of-sample trades over 89 months**, and
then the gates refused it:

```
PF=0.95 < 1.50 · Sharpe=-0.90 < 0.80 · MaxDD=99.7% > 25%
WinRate=27.7% < 40% · Recovery=-1.00 < 3.00
```

The file stayed in `staged/`. `qualified/` is still empty.

**A rejection like that is the successful outcome.** It arrives with the exact numbers that
caused it, so the author knows what would have to change. The alternative — a strategy reaching
live because nobody checked — is what the live account has already paid for.

## There is no side door, and I tried to find one

I wrote tests that actively *attack* the pipeline. Each one has to be stopped by code, not by
anyone remembering a rule:

| Attempt | Result |
|---|---|
| Promote straight to `qualified`, skipping the gates | **blocked** — stages cannot be skipped |
| Two strategies claiming the same ID | **blocked** — this exact bug once silently collapsed a strategy's weighting |
| A strategy peeking one bar into the future | **blocked** — proven by recomputing on truncated data, not by trusting a comment |
| The subtler version: no direct peek, but early bars depend on the whole series | **blocked** by the same check |
| Research code writing to the live database tables | **blocked** — the sandbox has no write path at all |
| A strategy declaring itself "qualified" in its own metadata | **blocked** — stage comes from the folder, never the file |

All 14 tests pass. The whole repository: **270 tests green**.

## Two things I chose not to do

**I did not move the 6 existing strategies into `staged/`,** even though the task asked for it.
They *are* your currently-live model, and they're reached through the exact import chain that
was broken for five weeks and repaired earlier this week. Moving them would have demoted the
live model and re-broken that chain. The right next step is a small adapter that registers them
as `qualified` where they already sit — noted for next week.

**I found and fixed a bug in my own first attempt.** My initial metrics code reimplemented the
drawdown calculation and reported a nonsensical 1650%. The fix was to import the live
calculations rather than write new ones — the same discipline as not copying the thresholds.
Worth mentioning because it's the identical mistake pattern the project keeps paying for: a
second copy of something important quietly disagreeing with the first.

## Why this matters this week

T5 established your live account has taken **ten trades and lost all ten**. System 1's own
analysis says the live model is a single strategy and the regime classifier doesn't actually
distinguish between strategies. The shortage isn't gates — it's **honest candidates**, and
until today there was no way to produce one without hand-wiring it into the live path.

Now there is. The next useful increment is teaching the sandbox to check whether a candidate
behaves *differently in different market regimes* — because that's the question your live
regime map currently cannot answer, and it's the assumption the whole strategy-selection design
rests on.
