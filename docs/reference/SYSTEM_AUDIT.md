# Scalable-Brain — System Audit Specification

**Version:** 1.0
**Purpose:** Independently verify that the system's reported behaviour matches its actual behaviour.
**Status:** Baseline run not yet performed.

---

## 0. Why this exists

Every claim about this system that has been checked closely has turned out to differ from
the description:

- "30 years of data" was data from 2005 onward.
- "Costs are handled" rested on an argument that spread is excluded by R-multiple
  construction — which excludes it from measurement, not from reality.
- "Six strategies passed vetting" was mostly cells with 5 to 11 out-of-sample trades.
- The D1 timestamp convention was described in two mutually contradictory ways in the
  same paragraph.

None of this implies carelessness. It is what happens in any system with enough moving
parts and no independent check. But it means decisions are currently being made on a
picture that has been wrong every time it was inspected closely.

The purpose of this audit is not to improve the system. It is to make the system's
self-reports trustworthy, so that future improvements can be evaluated at all. Until
that holds, a good change and a bad change look identical from the outside.

### Operating principles

1. **The audit reports. It does not remediate.** No check may modify code, data, config
   or database state. Any check that cannot run read-only is out of scope.
2. **Silence is not a pass.** A check that cannot be executed reports `INCONCLUSIVE` with
   a reason. It never reports `PASS`. An audit that quietly skips its hardest check is
   worse than no audit, because it manufactures confidence.
3. **Evidence, not assertion.** Every finding cites a file and line range, a query, or a
   computed figure. "Looks correct" is not a finding.
4. **Measure, don't infer.** Where a property can be tested empirically against real data,
   test it. Do not conclude a shift is correct by reading the shift; conclude it by
   checking whether a label was knowable before the bar it was applied to.

---

## 1. Layout and scheduling

```
audit/
  SYSTEM_AUDIT.md              <- this file (the spec)
  run_audit.py                 <- runner: executes checks, emits reports
  checks/
    a_lookahead.py
    b_costs.py
    c_gate.py
    d_regime_columns.py
    e_live_vs_backtest.py
    f_data_quality.py
  baseline/
    baseline.json              <- first full run, frozen; the reference point
  reports/
    YYYY-MM-DD_HHMM/
      findings.json            <- machine-readable, diffable
      report.md                <- human summary
      artifacts/               <- plots, sample rows, failing records
  state/
    last_full_run.json
    open_findings.json         <- findings not yet resolved, with age
```

### Two modes

**FULL** — every check in this document. Expensive (simulations, full backtest re-runs).
Run once now to establish baseline, then monthly, and always before any material change
to the labeller, gate, cost model or execution path.

**SENTINEL** — the fast subset marked `[S]` below. Cheap, read-mostly, no re-simulation.
Run daily or hourly alongside the existing signal cron. Its job is to detect drift and
regressions between full runs, not to reason.

```bash
# crontab
0 3 * * *   cd $REPO && python src/audit/run_audit.py --mode sentinel
0 4 1 * *   cd $REPO && python src/audit/run_audit.py --mode full
```

### Severity

| Level | Meaning | Response |
|---|---|---|
| **P0** | Results are invalid, or live trading is unsafe | Halt trading. Nothing else proceeds until resolved. |
| **P1** | Results are materially biased but system is safe | Freeze strategy promotion. Fix before any vetting decision is trusted. |
| **P2** | Correctness risk, not currently causing known harm | Ticket it. Fix within the cycle. |
| **P3** | Hygiene, clarity, future-trap | Backlog. |

Any **P0** in SENTINEL mode should page, not email.

---

## A. Lookahead and causality

**Highest priority. If the backtest can see the future, every other number in the system
is meaningless and nothing below this section is worth reading.**

### A1 — D1 bar timestamp semantics `[S]` — P0

The reported convention contains a contradiction. It was stated that the D1 timestamp
marks the *open* of the new daily bar, and also that a bar covering Sunday 5PM to Monday
5PM NY carries the `Monday 22:00 UTC` stamp. Both cannot be true. If 22:00 UTC is 5PM NY,
that stamp is the bar's **close**. If the stamp genuinely marks the **open**, then
`shift(1)` is insufficient and every intraday signal is being fed a label derived from up
to a full day of its own future.

**Test empirically. Do not read the code and conclude.**

1. Pick one instrument and one D1 bar with timestamp `T`.
2. Pull all H1 bars in `[T-24h, T)` and in `[T, T+24h)`.
3. Compute `max(high)`, `min(low)`, `first(open)`, `last(close)` for each window.
4. Determine which window reproduces the D1 bar's OHLC.

- Reproduced by `[T-24h, T)` → timestamp marks **close**. `shift(1)` is correct.
- Reproduced by `[T, T+24h)` → timestamp marks **open**. **P0 lookahead confirmed.**

Repeat across at least 20 bars, 5 instruments, and both DST regimes.

**Report:** which window matches, per instrument, with the actual OHLC figures.

### A2 — End-to-end label knowability `[S]` — P0

Take one intraday signal from the backtest. Trace its regime label back to the exact wall-clock
instant that label first became computable from data that had closed.

**Report:** signal bar time, label value, label knowable-at time, and the delta. Delta must
be strictly positive (label knowable *before* signal bar). Any zero or negative delta is P0.

### A3 — DST boundary integrity — P1

Is the 22:00 UTC boundary fixed or DST-adjusted? A fixed stamp is 5PM EST but 6PM EDT.

**Report:** for the DST transition weeks in at least 4 different years, the number of H1
bars composing each D1 bar. Anything other than the expected count means bars are being
built from misaligned windows twice a year.

### A4 — `merge_asof` direction and tolerance `[S]` — P0

Confirm `merge_asof` uses `direction='backward'` and has an explicit `tolerance`. Backward
merge with no tolerance will happily carry a stale label across an arbitrarily long gap —
including across a data outage.

**Report:** the exact call with its arguments, and the maximum observed label age in hours
across the full history. Flag any label older than 48 hours attached to a live signal.

### A5 — Warmup mask scope — P1

Confirm `label.iloc[:VOL_ZSCORE_WINDOW] = UNKNOWN` is applied **per instrument**, not
across a concatenated frame. If applied to a stacked multi-instrument DataFrame, only the
first instrument is masked and every other instrument trades on invalid warmup labels.

**Report:** the grouping context of the mask, plus a count of non-UNKNOWN labels appearing
within the first 252 bars of each instrument. Expected: zero, for every instrument.

### A6 — Indicator leakage into features — P1

Even with labels masked, confirm no raw indicator value (ADX, EMA50, EMA200, ATR%,
z-score) computed during the warmup window reaches the Gatekeeper feature vector or any
vetting input.

**Report:** every feature derived from the labeller's intermediates, and its first valid
index per instrument.

### A7 — Target/label alignment in the Gatekeeper — P0

Separate from regime timing: confirm the Gatekeeper's training target is not computable
from its own feature vector, and that no feature is constructed from data after the
prediction timestamp.

**Report:** feature list with the computation window of each, relative to prediction time.

---

## B. Cost model

### B1 — What price do fills actually use — P1

Read `BacktestConfig` (`src/layer0/core_engine/backtest_engine.py`) and
`position_engine.py` (around lines 119–123).

Determine, precisely: does a trade enter at bid, ask, or mid? Exit at bid, ask, or mid?
Is spread deducted from the realized R, or only from a separately-tracked P&L figure that
the vetting gate never reads?

The claim under test is that R-multiples are "spread-free by construction" and therefore
immune to spread assumptions. R-multiples exclude spread from *measurement*, not from
*reality*. You enter at the ask and exit at the bid; that round trip comes out of realized
R. If fills are mid-to-mid, every trade's R is overstated by approximately
`spread / stop_distance`.

**Report:** the fill price rule, quoted with line numbers, and whether spread reaches R.

### B2 — Magnitude of any omitted cost — P1

If B1 shows spread is not in R, quantify it. For each granularity (H1, H4, D1), compute
the median stop distance in pips, then `spread / median_stop` as a percentage of R.

**Report:** a table of granularity, median stop, omitted cost as % of R. Indicative
expectation: an H1 strategy with a 12-pip stop loses roughly 8% of every R; an H4 strategy
with a 30-pip stop roughly 3%.

### B3 — Cost sensitivity re-run — P1

Re-run the full vetting population with full round-trip spread deducted from R, at
1×, 2× and 3× the current 1.0 pip assumption.

**Report:** survivor count at each level, and the shift in the PF distribution
(10/25/50/75/90/95th percentiles). Baseline for comparison: median PF 0.89, p75 1.03,
p95 1.79, 6 survivors.

### B4 — Historical spread realism — P2

A flat 1.0 pip across 2005–present is optimistic for the early years; retail EURUSD was
routinely 2–3 pips in 2005–2008 and crosses were wider.

**Report:** whether any era-varying or instrument-varying spread schedule exists. If not,
re-run B3 with a schedule that widens pre-2010 and widens crosses relative to majors.

### B5 — Slippage model realism — P2

Confirm the 0.5 pip adverse slippage is applied on both entry and exit, and check whether
it is conditioned on anything. Constant slippage understates cost around news and rollover,
which is disproportionately where stop-driven strategies get filled.

**Report:** where slippage is applied, and whether it varies by time-of-day, volatility, or
order type.

### B6 — Swap / rollover — P2

**Report:** whether overnight financing is modelled at all. For any strategy holding
positions across the 5PM NY rollover, an unmodelled swap is a persistent unmodelled drift.

---

## C. Vetting gate integrity

### C1 — Full gate logic — P1

**Report:** every threshold in `vet.py`, in order, with line numbers. Explicitly state
whether a minimum-sample floor exists at any point.

The reported survivors were `kiss_h4` (72 trades), `Range_Stoch` (20, 9 trades),
`reference_pullback` (11), `double_bottom` (7), `pinbar` (5), against a population median
of 78 trades per cell. Five of six survivors sit far below the median n. That is the
signature of a gate selecting *for* small samples rather than screening them out.

### C2 — The true denominator — P1

58 strategies × 4 regimes × 3 granularities = 696. The reported figure is 197 "valid" cells.

**Report:** how many cells were evaluated, how many were excluded, the exclusion rule, and
whether exclusion depends on any performance quantity. If cells are dropped for reasons
correlated with outcome, the surviving population is already selected before the gate runs.

### C3 — Shrinkage behaviour — P1

**Report:** the exact shrinkage formula, its prior, and its posterior effect on PF at
n = 5, 7, 11, 20, 72, 200. If a cell with 7 trades can still clear a PF 1.5 gate after
shrinkage, the shrinkage is not doing the job it was introduced to do.

### C4 — Null simulation `[FULL only]` — P1

**The central test of whether the six survivors mean anything.**

1. Preserve the empirical distribution of realized R-multiples and the per-cell sample
   sizes exactly as observed.
2. Break the alignment between strategy-regime cells and outcomes — permute or bootstrap
   R-multiples across cells so no cell has any real edge.
3. Run the *actual* gate, unmodified, over this simulated population.
4. Repeat ≥ 500 times.

**Report:** the distribution of survivor counts under the null; `P(survivors ≥ 6)`; and
separately `P(≥ 5 survivors with n < 15)`. Compare with the observed result.

Interpretation: if the null routinely produces ~6 survivors, the regime-strategy map is
noise, and the correct conclusion is that the strategy bank — not the labeller — is the
binding constraint.

### C5 — Block-shuffled regime labels `[FULL only]` — P1

Distinct from C4. Here, keep the strategies and their real trades intact, but shuffle the
regime labels in blocks that preserve the observed run-length distribution (per instrument),
destroying only the alignment between regime and price. Re-run vetting.

**Report:** survivor count and PF distribution under shuffled labels vs. real labels. If
the real labels do not clearly beat shuffled ones, the labeller adds overfitting surface
without adding information.

### C6 — Multiple-testing control — P1

**Report:** whether any FWER or FDR correction, or a Deflated Sharpe adjustment, exists
anywhere in the pipeline, and the number of independent trials it accounts for.

Note the structural issue: walk-forward computes metrics out-of-sample, but the survivors
are then *selected* using those out-of-sample metrics across ~200 cells. Selection on OOS
converts OOS into training data. Shrinkage addresses thin samples; it does not address
200-way selection.

### C7 — Untouched holdout — P1

**Report:** whether any period of data has never been seen by any selection decision,
its date range, and how it is enforced. If none exists, say so plainly.

### C8 — Walk-forward hygiene — P2

**Report:** fold boundaries, embargo length, and whether the embargo exceeds the longest
lookback in the system (252 bars). An embargo shorter than the longest feature lookback
leaks train data into test.

---

## D. Regime column unification

### D1 — Column inventory `[S]` — P2

**Report:** the full schema of `fact_market_regime_v2`; which columns are populated for
the most recent bar per instrument; and the NULL rate of each column over the last 30 days.

### D2 — Consumer map — P1

Enumerate every consumer of regime data: `vet.py`, Gatekeeper feature construction, live
routing in `src/signals/run.py`, attribution, `regime_strategy_map.json` generation, and
any notebook or ad-hoc query.

**Report:** a table of consumer → column read → is that column ever NULL at the edge.

Two things named "regime" currently live in the same database: the structural labeller
(live path) and the HMM (historical batch writes). Anything reading the table without
knowing which column it grabbed is silently mixing definitions.

### D3 — NULL-at-edge rule `[S]` — P0

**Rule: nothing that touches a live decision may read a column that is ever NULL for the
latest bar.**

This is the exact failure that previously caused the producer to stall silently — the HMM's
`regime_causal` exists only inside completed walk-forward folds, so the newest row returned
`None` for every instrument and the system reported "No signals generated."

**Report:** any live-path consumer violating this rule. Any violation is P0.

### D4 — Gatekeeper feature provenance — P1

**Report:** the current champion Gatekeeper's full input vector, with the source column of
each feature. Confirm it was retrained on `regime_structural` (reported live since
2026-08-24) and that no residual HMM-derived feature (`prob_causal_*`) remains.

### D5 — HMM isolation — P3

**Report:** whether HMM output is named in a way that makes it impossible to mistake for
the live label (e.g. `regime_hmm_research`), and whether its non-causality at the edge is
documented at the schema level rather than only in a docstring.

Note on direction: the HMM cannot label the newest bar without a completed fold. That is
how it is fit, not a bug to be tuned out. Unification therefore means retiring the HMM
from anything feeding a decision — not promoting it. Its one genuine advantage, resistance
to flicker, is obtainable deterministically via hysteresis and minimum dwell time.

### D6 — Label reproducibility `[S]` — P2

Recompute structural labels from raw prices for the last 90 days and diff against stored
labels.

**Report:** mismatch count and any mismatched rows. Non-zero means the stored label and the
labeller have diverged — a silent config drift or a backfill that overwrote history.

### D7 — Label immutability — P2

**Report:** whether historical labels are ever recomputed or backfilled in place, and
whether an append-only record exists of what the label *was* at decision time. If labels
are mutable, backtests are being run against a history that live trading never saw.

### D8 — Chatter reproduction — P2

Independently reproduce the run-length quantiles and 4×4 transition matrix.

Reported D1 figures for reference: Trending-Up median run 12 days, Trending-Down 10,
Ranging 4, High-Vol 3 with p25 = 1; diagonal 0.943 / 0.940 / 0.844 / 0.782; ~10% daily
flip probability between High-Vol and Ranging.

**Report:** these statistics computed both on raw D1 labels **and** on labels after
`merge_asof` propagation to H1 and H4. The propagated version is the one that actually
gates trades and is the version that matters.

---

## E. Live vs backtest reconciliation

**The single best available truth-check, and to date unexamined.**

### E1 — Live track record inventory — P1

**Report:** start date of live/paper trading, number of live trades, instruments, and
which strategies were live over which windows.

### E2 — Trade-level replay — P0

Re-run the backtest over the exact live window, restricted to the live universe and the
strategies that were actually enabled.

**Report:** the count of live trades, backtest trades, and matched pairs. For matched
pairs, the distribution of differences in entry time, entry price, exit price and realized R.

A large population of backtest trades with no live counterpart means the backtest is taking
trades the live system cannot. The reverse means live is trading something the backtest
does not model. Either is P0 — it means the two systems are not the same system.

### E3 — Performance gap `[S]` — P1

**Report:** live vs backtest Sharpe, PF, hit rate, average R and max drawdown over the same
window, with a confidence interval on the gap.

Live consistently worse than backtest by more than costs explain is the classic signature
of lookahead or over-fitting. Quantify the gap before theorising about it.

### E4 — Regime agreement `[S]` — P1

For every bar in the live window, compare the regime label the live system used at the time
against the label the backtest assigns to that same bar today.

**Report:** agreement rate per instrument, and every disagreement with its date. Anything
below 100% means backtest and live disagree about the state of the world, and every vetting
decision made from backtest labels is describing a different system than the one trading.

### E5 — Gatekeeper live vs training distribution `[S]` — P1

**Report:** feature-by-feature distribution comparison (PSI or KS) between the Gatekeeper's
training data and its live inference inputs over the last 30 days. Flag any feature with
material drift. This is where the previous HMM-feature failure would have been caught early.

### E6 — Execution reality — P2

**Report:** realized slippage vs modelled 0.5 pip, realized spread at fill times vs the
1.0 pip assumption, rejected/requoted orders, and any live fill that the model would not
have produced.

---

## F. Data quality

### F1 — Coverage and gaps `[S]` — P2

**Report:** per instrument — first bar, last bar, expected vs actual bar count per year,
and every gap exceeding one session. Note that the database floor is 2004-12-31 22:00 UTC;
any figure describing the history as longer than that is wrong.

### F2 — Weekend and holiday handling — P2

**Report:** how the Friday-to-Sunday gap is treated in D1 aggregation and in indicator
calculation; whether Sunday partial bars exist and whether they are included; and the
treatment of major holidays where the FX session is thin or closed.

### F3 — Bad ticks and outliers — P2

**Report:** count of bars where `high < low`, `close` outside `[low, high]`, zero range,
zero volume, or a single-bar return beyond ~8 sigma. List the worst 50 with dates.

### F4 — Duplicates and monotonicity `[S]` — P2

**Report:** duplicate `(instrument, timestamp)` rows, and any non-monotonic timestamp
sequence.

### F5 — Timezone consistency — P1

**Report:** whether every timestamp in every table is stored in UTC with an explicit
timezone, and whether any table stores naive local time. Mixed conventions across tables
joined by timestamp is a silent misalignment.

### F6 — Instrument universe stability — P2

**Report:** instruments added or removed over the history, and whether any backtest ran
over a universe that would not have been available at the time.

### F7 — Revision detection `[S]` — P2

Snapshot a rolling window of raw prices on each run and diff against the previous snapshot.

**Report:** any historical bar whose OHLC changed since the last audit. Vendor revisions to
past prices silently invalidate stored labels and backtest results.

---

## G. Report format

### `findings.json`

```json
{
  "run_id": "2026-09-05_0300",
  "mode": "full",
  "git_sha": "...",
  "started_at": "...",
  "completed_at": "...",
  "findings": [
    {
      "id": "A1",
      "title": "D1 bar timestamp semantics",
      "severity": "P0",
      "status": "PASS | FAIL | INCONCLUSIVE",
      "verdict": "one sentence, plain language",
      "evidence": {
        "files": ["src/regime/structural.py:118-124"],
        "query": "...",
        "figures": {"...": "..."}
      },
      "delta_vs_baseline": "unchanged | new | resolved | worsened",
      "notes": "..."
    }
  ],
  "summary": {
    "P0": {"pass": 0, "fail": 0, "inconclusive": 0},
    "P1": {"pass": 0, "fail": 0, "inconclusive": 0},
    "P2": {"pass": 0, "fail": 0, "inconclusive": 0},
    "P3": {"pass": 0, "fail": 0, "inconclusive": 0}
  }
}
```

### `report.md`

Ordered by severity, worst first. Each finding: verdict in one plain sentence, then
evidence, then what it implies for decisions currently pending. Explicitly list every
`INCONCLUSIVE` check and why it could not run — that list is itself a finding.

### Diffing

Every run is diffed against `baseline/baseline.json` and against the previous run. New P0
or P1 findings, and any check that moved from PASS to FAIL or INCONCLUSIVE, appear at the
top of the report.

---

## H. Sequencing for the first run

Run in this order and stop at the first P0. There is no value in refining a cost model
inside a backtest that can see the future.

1. **A1, A2, A4** — lookahead. If any fails, halt and fix; everything else is void.
2. **D3** — NULL-at-edge on the live path. Safety.
3. **B1, B2** — is spread in R. Determines whether any reported PF means anything.
4. **C1, C2, C4** — is the vetting gate selecting noise.
5. **E2, E3, E4** — does live match backtest.
6. **F1–F7** — data quality sweep.
7. Everything remaining.

---

## I. What this audit deliberately does not do

It does not evaluate whether the regime taxonomy is well-designed, propose a replacement
labeller, tune thresholds, or assess strategy quality. Those are downstream questions, and
they cannot be answered honestly until the measurement apparatus is trustworthy.

The output of this audit is a decision: whether the current numbers can be believed. Only
after that is settled does redesign work make sense.