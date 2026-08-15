# T1 — Reconnect the Feedback Loop · Executive Summary

**2026-07-29 · System 1 (The Brain)**

## What was broken

For five weeks — from **23 June to 29 July** — System 1 was learning from results that had
stopped arriving.

The program that records how each strategy's trades actually turned out
(`fact_trade_outcomes`) crashed every time it started. It had been broken by an earlier
folder reorganisation: a single missing file turned the strategy library into something
Python could no longer load. Nothing anywhere raised an alarm. The retrain kept running on
schedule, kept passing its gates, and kept publishing models — all judged against trade
results frozen in June.

Worse, the error message pointed at the wrong thing. The code caught the real failure,
threw it away, and reported an unrelated one instead. That is why a one-file problem went
five weeks without being found.

## What was done

- **Repaired the load chain.** Three separate breaks, all left by the same reorganisation:
  a missing package file, strategy modules pointing at folders that had moved, and a
  1,460-line duplicate copy of an old file that was still being executed.
- **Rebuilt the trade record.** 134,407 trades across a full ten-year window, from 100
  backtests. **1,059 trades over 4 weeks** were recovered from the dead period.
- **Made this class of failure loud.** Nine load-shims across the codebase now report the
  *real* error instead of hiding it. Turning that on immediately exposed a second, separate
  breakage nobody knew about — which is the point. **42 new automated tests** now fail
  noisily if the strategy library ever breaks this way again.
- **Re-ran the analysis on honest data** in log-only mode. Nothing was promoted; no live
  model was touched.

## What is now true

- Trade outcomes are current through **24 July 2026** (the last market close), rebuilt today.
- The full pipeline loads and evaluates cleanly: **215 automated tests pass** (42 new, 173
  existing).
- A future break of this kind **crashes visibly** instead of silently freezing the feedback
  loop.

## What this means for the model — the honest answer

Re-running the analysis on fresh data produced **almost exactly the same result** as the
stale data: the same four qualifying strategy/regime combinations, the same single strategy,
with metric changes in the second decimal place. Five missing weeks against a seven-year
evaluation window simply did not move the numbers.

So: the process failure was real and serious — the system was flying blind and would not
have noticed genuine deterioration — but **the damage to the current model was small**. T3's
promotion review should expect its evidence to *confirm* the existing model rather than
overturn it.

Two known problems are unchanged and remain the real concerns: the entire live model is
still **one strategy** (`Range_Stochastic_Divergence`), and the **High-Volatility regime
still has no qualifying strategy at all**.

## What this unblocks

T3 can now assemble its promotion evidence from genuinely current trade results rather than
a June snapshot. T4 can now define what "fresh" means for the outcomes table, because the
table is finally moving again.

## One thing worth your attention

The rebuild program deletes the entire outcomes table before it starts rebuilding, and
commits that deletion immediately. If it is interrupted — power cut, credit limit, crash —
the live table is left **empty**. It was run here with a manual backup taken first, but that
safety depends on someone remembering. Making that operation safe is recommended for W32.
