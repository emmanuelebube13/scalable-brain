# System 1 — "The Brain": Executive Overview, First Principles, and Audit Map

**Document date:** 2026-07-24
**Scope:** System 1 only (Computer 1 — the offline model-building factory)
**Repository:** `/home/emmanuel/Documents/Scalable_Brain/scalable-brain`
**Purpose:** Business-process orientation prior to a defect audit, with emphasis on
business rules. Every technical or industry term is defined inline on first use, and
again in the Glossary (Section 9).
**Basis:** Direct reading of `src/system1/` runtime code and the live state artifacts in
`results/state/` as of 2026-07-24. Where this document states a live number, it was read
from an artifact, not from prior documentation.

---

## Table of Contents

1. [What System 1 Is](#1-what-system-1-is)
2. [The Business Process — Executive Summary](#2-the-business-process--executive-summary)
3. [The Business Process — Stage by Stage](#3-the-business-process--stage-by-stage)
4. [First Principles — The Four Axioms](#4-first-principles--the-four-axioms)
5. [The Economic Logic](#5-the-economic-logic)
6. [Current Live State (Verified 2026-07-24)](#6-current-live-state-verified-2026-07-24)
7. [Audit Map — Where the Business Rules Live](#7-audit-map--where-the-business-rules-live)
8. [Seed Observations for the Audit](#8-seed-observations-for-the-audit)
9. [Glossary](#9-glossary)

---

## 1. What System 1 Is

System 1 is an **offline model factory**. "Offline" here means it runs on a schedule
against historical data, not in reaction to live market events. It never places a trade,
never sizes a position, and never contacts the broker for execution purposes (it does
contact the broker to *download price history*, which is a read-only operation).

Its entire job is to answer one question on a repeating cycle:

> *Which strategies have a proven mathematical edge, under which market conditions, and
> how much confidence do we assign to each one?*

It publishes that answer as a **versioned, checksummed artifact** to cloud object storage.
Systems 2 (execution) and 3 (risk and account management) consume that artifact.

- **Edge** — a statistically demonstrable tendency for a strategy to produce positive
  expected return, as opposed to a pattern that appears profitable by chance.
- **Artifact** — a file (or set of files) produced by a pipeline run and stored
  immutably, e.g. a trained model plus its metadata.
- **Checksummed** — accompanied by a cryptographic hash (SHA256) of its contents, so any
  corruption in transit or storage is detectable.

### The three-system topology

| System | Host | Role |
|--------|------|------|
| **System 1 — The Brain** | Computer 1 (this repository) | Ingest → features → regimes → attribution → vetting → gatekeeper → publish |
| System 2 — The Hand | Another computer | Execution only: consumes approved orders, fills them on OANDA, manages open positions |
| System 3 — The Guardian | Another computer | Risk gating, account state machine, circuit breakers, position sizing |

The separation is deliberate and load-bearing. **System 1 does not know whether it is
live.** It produces the same output whether real capital is deployed or not. This means a
bug in System 1 cannot directly cause an unintended trade — it can only cause a *bad
recommendation*, which the downstream systems are independently responsible for
rejecting.

**Inviolable principles inherited from the platform design:**

1. **Preservation over profit** — avoiding ruin ranks above maximising return.
2. **No downstream recomputation** — System 3 never re-scores a signal, System 2 never
   re-sizes a position, System 1 never knows if it is live. Each system trusts the
   upstream contract rather than second-guessing it.
3. **Default-safe posture** — missing, stale, or errored input results in REJECT, never
   in a permissive guess.
4. **Deterministic and auditable** — the same inputs produce byte-identical outputs, and
   every decision leaves a written record.

---

## 2. The Business Process — Executive Summary

System 1 is a **funnel that converts raw price ticks into a capital allocation policy**.

The funnel is nine stages. Each stage has at least one *business rule* — a hard condition
that, if violated, stops the run rather than allowing degraded output to proceed.

| # | Stage | Business question answered | Rule that can stop the run |
|---|-------|---------------------------|----------------------------|
| 001 | **Ingest** | "Do we have clean, complete market data?" | Data-quality gates on gaps and staleness |
| 002 | **Features** | "What was knowable at each bar?" | Trailing-only computation, deterministic output — no look-ahead |
| 003 | **Regime** | "What kind of market was it?" | Hidden Markov Model must reach ≥0.70 holdout accuracy, or fall back to K-Means |
| 004 | **Attribution** | "Which strategy made money in which market condition?" | Metrics computed on out-of-sample trades only; sanity bounds (drawdown ≤ 100%, \|Sharpe\| ≤ 10) abort the run |
| 005 | **Vetting** | "Which combinations are good enough to trade?" | Six hard gates: PF ≥ 1.5, Sharpe ≥ 0.8, MaxDD ≤ 25%, WinRate ≥ 40%, Recovery ≥ 3.0, OOS ≥ 60 months |
| 005b | **Weighting** | "How much capital does each qualifier receive?" | Softmax allocation with a 5% floor; weights **must** sum to 1.0 or the run aborts |
| 006 | **Gatekeeper** | "Given a specific signal, should we actually take it?" | Machine-learning model must show bootstrap-significant out-of-sample uplift; its approval rate must fall within [5%, 60%] or it refuses to ship |
| 007 | **Publish** | "Is the artifact intact, and is it better than what is currently live?" | Upload → SHA256 verify → **only then** flip the pointer; must beat the incumbent |
| 009 | **Orchestrate** | "Should we retrain at all, and may this candidate go live?" | Four deployment gates, an exclusive lock, and a 6-hour cooldown |

### The business loop, in plain language

> Every hour, a scheduled job asks *"is there a reason to rebuild the model?"* The valid
> reasons are: it is Sunday 00:00 UTC; or live Sharpe over the last 14 days dropped below
> 0.3; or regime-classification accuracy fell below 0.70; or a circuit breaker fired
> downstream.
>
> If no reason fires — which is the case in the overwhelming majority of hourly checks —
> the job writes `no_trigger_or_cooldown` to a log and exits without doing any work.
>
> If a reason does fire, the job takes an exclusive on-disk lock (so two rebuilds can
> never run at once), then rebuilds: regimes → attribution → vetting → gatekeeper. The
> result is a **candidate**. The candidate is then submitted to four deployment gates.
>
> Only if **all four gates pass** is the new bundle published and the live pointer moved
> to it. Otherwise the previous model (the **incumbent**) remains live, and the failure is
> recorded with the specific gate that blocked it.

- **Candidate** — a newly built model awaiting approval to go live.
- **Incumbent** — the model currently live and being consumed downstream.
- **Circuit breaker** — an automatic safety mechanism that halts trading when a
  predefined loss or anomaly threshold is breached.

---

## 3. The Business Process — Stage by Stage

### MODEL-001 — Ingestion
**Module:** `src/system1/ingestion/multi_timeframe_ingest.py`, `dq.py`
**Output:** `fact_market_prices` table

Downloads historical price bars from OANDA's v20 REST API across multiple timeframes and
writes them to PostgreSQL. Runs weekly (Saturday cron) so that the retrain has fresh data.

- **Bar** (or **candle**) — a summary of price movement over a fixed time interval,
  recorded as Open, High, Low, Close (OHLC).
- **Timeframe / granularity** — the length of one bar. This system uses H1 (1 hour), H4
  (4 hours), and D1 (1 day).
- **REST API** — a web interface for requesting data over HTTP.
- **Data-quality (DQ) gates** — automated checks for missing bars, duplicated
  timestamps, stale data, and impossible values (e.g. High < Low). Failures block the
  data from entering the pipeline.

**Business rule:** bad or incomplete data must not silently enter the pipeline, because
every downstream metric inherits its errors.

---

### MODEL-002 — Feature Store
**Module:** `src/system1/features/feature_pipeline.py`, `definitions.py`
**Output:** versioned Parquet files under `feature-store/{version}/`

Converts raw price bars into **features** — derived numerical descriptions of market state
such as volatility and trend strength.

- **Feature** — an input variable to a model, computed from raw data.
- **Feature store** — a versioned repository of computed features, so that a model
  trained last month can be reproduced exactly using the same feature definitions.
- **Parquet** — a columnar file format, efficient for large analytical datasets.
- **Trailing-only** — computed using only data at or before the current bar.
- **Look-ahead bias** — the error of using information that would not have been available
  at decision time. It is the single most common cause of backtests that look excellent
  and fail live.

**Business rule:** every feature must be trailing-only and deterministic (identical inputs
produce byte-identical outputs). This is what makes the eventual performance claims
defensible.

---

### MODEL-003 — Regime Classification
**Module:** `src/system1/regime/hmm_regime.py`, `mapping.py`
**Output:** `fact_market_regime_v2` table, `models/hmm_model.joblib`

Labels every historical bar with one of four **market regimes**: Trending-Up,
Trending-Down, Ranging, or High-Vol.

- **Regime** — a persistent market condition. The premise is that strategies do not have
  a single fixed edge; they perform differently depending on whether the market is
  trending, range-bound, or volatile.
- **Hidden Markov Model (HMM)** — a statistical model that assumes an unobservable
  ("hidden") state drives the observable data, and that the state changes over time with
  fixed transition probabilities. Here the hidden state is the regime.
- **Gaussian HMM** — an HMM in which each hidden state emits observations drawn from a
  normal (Gaussian) distribution.
- **K-Means** — a simpler clustering algorithm that groups data points into *k* clusters
  by proximity. Used here as a fallback when the HMM underperforms.
- **Holdout accuracy** — classification accuracy measured on data deliberately withheld
  from training.

This stage emits **two different labels per bar**, and the distinction is critical:

| Label | How computed | Safe to use for? |
|-------|--------------|------------------|
| `regime_smoothed` | Forward-backward algorithm over the **full history** | **Reporting only.** It uses future bars to refine a past label. |
| `regime_causal` | Walk-forward, **filtered forward-only** | Training and evaluation. Only uses information available at that bar. |

- **Forward-backward algorithm** — an HMM inference method that makes two passes over the
  data (one forward in time, one backward) to produce the best possible estimate of each
  hidden state. Because the backward pass uses future data, its output must never be used
  as a model input.
- **Filtered estimate** — an HMM state estimate using only data up to and including the
  current bar. This is the honest, causally valid version.
- **Causal** — depending only on past and present, never future.
- **Warm-up period** — the initial stretch of data where the model has not yet seen
  enough history to produce a valid estimate. These bars are labelled NULL, and trades
  occurring in them are tagged UNKNOWN rather than guessed.

**Business rule:** HMM must reach ≥0.70 holdout accuracy; below that it degrades to
K-Means rather than shipping an unreliable regime model. Training and evaluation consume
`regime_causal` exclusively.

---

### MODEL-004 — Attribution
**Module:** `src/system1/attribution/attribute.py`, `metrics.py`, `discrimination.py`
**Output:** `fact_strategy_regime_attribution` table

Joins each historical trade to the regime that was in force at the moment of entry, then
computes performance metrics for every **cell**.

- **Cell** — one combination of (strategy × regime × granularity). With 10 strategies and
  4 regimes, this produces up to 80 cells. A cell is the atomic unit of qualification: the
  system does not judge a strategy in isolation, only a strategy *in a specific market
  condition at a specific timeframe*.
- **Variant** — a (strategy, granularity) pair, e.g. `Range_Stochastic_Divergence@H1`. Two
  variants of one strategy are treated as genuinely different qualifiers.
- **Attribution** — assigning observed performance to its causal conditions.
- **Point-in-time join** — matching each trade to the most recent regime label that
  existed *at or before* the trade's entry time. Implemented via `merge_asof` with
  `direction="backward"`.

Performance is measured in **R-multiples**:

- **R-multiple** — profit or loss expressed as a multiple of the amount risked on that
  trade. A trade that made twice what it risked is +2R; one that hit its stop-loss is −1R.
  This normalises across position sizes and instruments, making trades directly
  comparable.

The metrics computed per cell:

| Metric | Definition |
|--------|-----------|
| **Win rate** | Fraction of trades that were profitable. |
| **Profit factor (PF)** | Gross profit ÷ gross loss. Above 1.0 means profitable; 1.5 means £1.50 earned per £1.00 lost. |
| **Sharpe ratio** | Mean return ÷ standard deviation of returns, annualised. Measures return *per unit of risk*. Higher is better; roughly, above 1.0 is good and above 2.0 is excellent. |
| **Maximum drawdown (MaxDD)** | The largest peak-to-trough decline in the equity curve, as a fraction of the peak. Measures worst-case pain. |
| **Recovery factor** | Total return ÷ maximum drawdown. Answers "how much did we earn per unit of worst-case pain?" |
| **Expectancy** | Average R per trade. |
| **Average R** | Average win size ÷ average loss size. |

- **Equity curve** — the running value of the account over time.
- **Annualised** — scaled so figures over different time periods are comparable on a
  yearly basis. Sharpe here is annualised by the *realised trade frequency* (trades per
  year), not by bar frequency. This distinction matters: annualising a per-trade return
  series by bar frequency inflates Sharpe by roughly √(bars per year ÷ trades per year) —
  a previously identified and fixed defect.
- **Fixed-fractional / compounding capital model** — R-multiples are converted into an
  equity curve by risking a fixed percentage of current equity per trade (default 1%) and
  compounding the result. This makes drawdown a genuine bounded fraction in [0, 1) rather
  than an unbounded R figure, and makes recovery factor a unit-consistent return% ÷
  drawdown% ratio.

**Out-of-sample discipline (the core of this stage):**

- **In-sample (IS)** — data the model was trained on.
- **Out-of-sample (OOS)** — data the model has never seen, held back to test whether the
  edge is real or merely memorised.
- **Walk-forward validation** — repeatedly train on a growing window of past data, then
  test on the immediately following unseen window. Here: minimum 36 months training,
  6-month steps, 6-month test windows, anchored (expanding, not sliding).
- **Fold** — one train/test split in that sequence.

**Every gate metric is computed on OOS trades only.** `oos_months` measures the union span
of the OOS windows in which the cell actually traded — not the calendar span of all its
trades. If the database lacks the `is_oos` column, all trades are treated as in-sample,
which makes every cell fail the OOS gate. That is the deliberate safe direction.

**Thin-sample handling:**

- **Bayesian shrinkage** — when a cell has few trades (n < 20), its metrics are blended
  toward the broader strategy-level average, in proportion to how thin the sample is. This
  prevents a 3-trade cell with a lucky run from appearing world-class.
- **`low_confidence` flag** — any cell that required shrinkage is stamped with this flag,
  which is an **unconditional rejection** at the vetting stage.

**Sanity bounds:** drawdown > 100% or |Sharpe| > 10 are physically impossible. They
indicate a *measurement bug*, not a great strategy, and the run aborts rather than shipping
corrupt attribution. (Exception: cells with fewer than 20 OOS trades have the value clamped
and logged instead of aborting, since they are already rejected by the low-confidence rule.)

**Business rule:** performance claims are only valid if measured out-of-sample, on causally
valid labels, with thin samples discounted.

---

### MODEL-005 — Vetting and Weighting
**Module:** `src/system1/vetting/vet.py`, `gates.py`
**Output:** `regime_strategy_map.json`, `strategy_weights.json`

#### 5a. The qualification gates

Each cell must clear **all six** thresholds. There is no scoring compromise — a single
failure disqualifies the cell.

| Gate | Threshold | Business meaning |
|------|-----------|------------------|
| Profit factor | ≥ 1.50 | Must earn at least £1.50 per £1.00 lost |
| Sharpe ratio | ≥ 0.80 | Return must be meaningful relative to its volatility |
| Max drawdown | ≤ 25% | Worst-case decline must be survivable |
| Win rate | ≥ 40% | Must not depend on rare outsized wins |
| Recovery factor | ≥ 3.00 | Must earn at least 3× its worst drawdown |
| OOS months | ≥ 60 | Must have five years of genuine out-of-sample evidence |
| `low_confidence` | must be false | Thin-sample cells rejected unconditionally |

#### 5b. Ranking

Qualifying cells are ranked by a **composite score**:

```
0.5 × Sharpe  +  0.3 × ProfitFactor  +  0.2 × RecoveryFactor  −  MaxDrawdown
```

Ties break on trade count (descending), then drawdown (ascending).

#### 5c. Capital weighting

- **Softmax** — a function that converts a set of scores into positive values summing to
  1.0, where higher scores receive proportionally more. Used here so that a bigger measured
  edge earns more capital.
- **Temperature** — a parameter controlling how sharply softmax concentrates. Higher
  temperature produces flatter allocation; lower concentrates on the top scorer. Currently
  1.0.
- **Minimum-weight floor** — a guaranteed minimum allocation (currently 5%) for every
  qualified variant, so no qualifier is starved to effectively zero.
- **Water-filling** — the algorithm used to apply the floor: pin any weight that would
  fall below the floor to exactly the floor, then redistribute the remaining mass among the
  unpinned weights in proportion to their original magnitude. Repeat until stable. This
  preserves the relative ranking of the non-floored variants.
- **Starvation** — the failure mode this design exists to prevent: an earlier
  normalisation approach drove the lowest-ranked qualifier to ~1e-8 weight regardless of
  its merit, effectively deleting a strategy that had passed every gate.

**Business rule (hard post-condition):** every non-empty regime's weights must sum to
1.0 ± 1e-6. If they do not, the run raises `WeightsNotNormalized` and refuses to publish. A
degenerate weight map must never reach the systems that size positions from it.

---

### MODEL-006 — The ML Gatekeeper
**Module:** `src/system1/gatekeeper/train.py`, `thresholds.py`, `promote.py`
**Output:** `champion_model.pkl` + manifest

Vetting decides *which strategies are allowed to trade at all*. The gatekeeper is a second,
finer filter that decides *whether to take this specific signal right now*.

- **Gatekeeper** — a binary classifier that scores each candidate trade and vetoes those
  below a threshold.
- **XGBoost** — a gradient-boosted decision-tree algorithm; a strong general-purpose
  classifier for tabular data.
- **Classifier** — a model that predicts a category. Here: will this trade win, yes or no.
- **Binary label** — the target being predicted. Here `is_winner` (1 or 0).

**Inputs:** ATR, ADX, the four causal regime probabilities, plus one-hot encoded causal
regime, strategy ID, and entry signal type — with three derived interaction features.

- **ATR (Average True Range)** — a volatility indicator: the average size of recent price
  ranges.
- **ADX (Average Directional Index)** — a trend-strength indicator; high values mean a
  strong trend regardless of direction.
- **One-hot encoding** — representing a categorical value as a set of binary columns, one
  per possible category, so a model can consume it numerically.
- **Standardisation (StandardScaler)** — rescaling numeric features to zero mean and unit
  variance, so features on different scales contribute comparably.
- **Grid search / hyperparameter tuning** — systematically trying combinations of model
  settings (tree depth, learning rate, etc.) and keeping the best.
- **Class weighting (`scale_pos_weight`)** — compensating for imbalanced classes. Winners
  are only ~38% of trades, so without this the model would be biased toward predicting
  "loss."

**Threshold calibration:**

- **Threshold** — the model score above which a signal is approved. Calibrated *per
  regime*, so the bar for approval can differ between a trending and a ranging market.
- **Turnover / approval rate** — the fraction of signals the gatekeeper approves. Bounded
  to [5%, 60%].
- **Degenerate model** — one that approves nearly nothing or nearly everything. Either is
  useless: it adds no information. Outside the turnover band, the trainer raises
  `GatekeeperRefused` and ships nothing.

**Proof of value — OOS uplift:**

- **Uplift** — the difference in mean R-multiple between the trades the gatekeeper
  approved and those it rejected, measured out-of-sample. Positive uplift means it is
  genuinely separating good trades from bad.
- **Bootstrap / permutation test** — a statistical method that repeatedly reshuffles the
  group labels (approved vs rejected) to build a distribution of uplift *under the
  assumption that the gatekeeper has no skill*. Currently 20,000 permutations.
- **p-value** — the probability of observing an uplift at least this large purely by
  chance. Below 0.05 is conventionally "significant."
- **Statistically significant** — unlikely to be an accident of the sample.

**Business rule:** the gatekeeper must demonstrate positive *and* statistically significant
OOS uplift, and must operate inside the turnover band. Otherwise it refuses to produce a
bundle at all.

- **Dry-run mode** — writes `models/proposed_champion_*` and never touches the live
  champion. This is the default invocation, honouring the platform's log-only-by-default
  rule.

---

### MODEL-007 — Serialization and Publishing
**Module:** `src/system1/serializer/serialize.py`, `publish_gatekeeper.py`
**Output:** versioned bundle in Google Cloud Storage

- **Serialization** — converting an in-memory model into a file that can be stored and
  later reloaded.
- **Bundle** — the complete published package: model file(s), metadata, and checksums.
- **Object storage** — cloud file storage addressed by key (e.g. Google Cloud Storage).
- **Immutable versioned prefix** — each publish writes to its own folder named by
  timestamp plus a random suffix, and that folder is never overwritten. Rolling back means
  moving a pointer, not restoring deleted files.
- **Pointer / `latest.json`** — a small file naming which version is currently live.
  Consumers read the pointer, then fetch that version.
- **Atomic pointer flip** — updating the pointer in a single indivisible operation, so a
  consumer reading concurrently sees either the old version or the new one, never a
  half-written state.

**The publish ordering is the business rule.** It runs in exactly this sequence:

1. Compute SHA256 for every artifact locally.
2. Write `model_metadata.json` and `checksums.sha256`.
3. Upload all files to `{prefix}/{version}/`.
4. **Round-trip verify** every uploaded object's SHA256 against the local value.
   Any mismatch → delete the partial version, abort, **pointer untouched**.
5. **Only now** flip `latest.json` atomically.
6. Trim to the last 5 versions (best-effort; never fails an already-completed publish).

A superseded pointer is archived to `previous.json` as a rollback breadcrumb.

**Additional guards:**
- **Secret scanning** — text artifacts are scanned for API keys, bearer tokens, and
  password patterns before upload, so credentials cannot leak into a published bundle.
- **Empty-map refusal** — if the regime map contains zero qualifying strategies, publish
  is refused outright.
- **Beats-incumbent gate** (gatekeeper publisher) — a worse model cannot take the live
  pointer.

**Business rule:** a corrupt or unverified upload must never become live. Verification
strictly precedes the pointer flip.

---

### MODEL-008 — Queue Producer
**Module:** `src/system1/queue_producer/producer.py`
**Output:** messages on `Scored_Signal_Queue`

Publishes scored signals to a message queue for downstream consumption.

- **Message queue** — an intermediary that decouples producer and consumer, so neither
  needs the other to be online simultaneously.
- **Schema validation** — checking each message against a declared structure before
  sending, so malformed messages never enter the queue.
- **Idempotent** — safe to repeat. Sending the same message twice has the same effect as
  sending it once, which matters because networks retry.
- **Backpressure** — slowing or blocking the producer when the queue is full, rather than
  dropping messages.
- **Dead-letter queue (DLQ)** — where messages that repeatedly fail processing are
  diverted for inspection, instead of being lost or retried forever.

> **Known gap:** `QUEUE_PROVIDER` is currently set to `local`, meaning scored signals land
> in `results/state/queue/` on this machine — which System 3, running on a different
> computer, cannot read. Migration to Google Cloud Pub/Sub is an open task.

---

### MODEL-009 — The Retrain Orchestrator
**Module:** `src/system1/scheduler/orchestrator.py`, `triggers.py`
**Output:** `retrain_state.json`, `retrain_log_*.json`

This is the control plane — the only component authorised to make a model live.

#### Triggers (when a retrain is allowed to start)

| Trigger | Condition |
|---------|-----------|
| Scheduled | Sunday 00:00 UTC |
| Performance degradation | 14-day live Sharpe < 0.30 |
| Model degradation | Regime accuracy < 0.70 |
| Emergency | Circuit breaker fired downstream |

A missing or `None` metric **does not** fire a trigger — absent telemetry must not cause a
spurious rebuild.

#### Safety mechanisms

- **Single-flight lock** — an exclusive on-disk lock created with `O_EXCL` (a filesystem
  flag meaning "fail if this file already exists"), making the creation atomic. Two
  concurrent retrains are therefore impossible.
- **Cooldown / debounce** — a minimum 6-hour interval between retrains, preventing a
  flapping metric from triggering repeated rebuilds.

#### The four deployment gates

All four must pass for the candidate to be promoted:

| Gate | Condition | Failure behaviour |
|------|-----------|-------------------|
| `regime_accuracy_ok` | Candidate regime accuracy ≥ 0.70 | Blocks |
| `non_empty_map` | At least one qualifying strategy | Blocks |
| `oos_uplift_ok` | Gatekeeper uplift ≥ MIN_UPLIFT (currently 0.0) **and** statistically significant | **Fails closed** — a missing result blocks promotion unless an operator explicitly passes `--allow-missing-uplift` |
| `beats_incumbent` | Candidate regime accuracy ≥ incumbent's | **Fails open** on the first-ever publish (nothing to beat), but the absolute gates still bind |

- **Fail closed** — when information is missing, deny. The safe default for a gate.
- **Fail open** — when information is missing, allow. Used only where denial would make
  the system unbootstrappable (there is genuinely no incumbent on the first run).
- **Promotion** — the act of making a candidate the live model.

The incumbent is read from the **storage backend**, not from a local file. This matters:
when the producer published to cloud storage but the consumer read a local file, the two
diverged, and `beats_incumbent` silently stopped binding. Reading both through the same
backend keeps producer and consumer consistent.

**Business rule:** the orchestrator is the **single governed writer** of the champion
bundle. A second promotion path must never be added — it would create a route to live
capital that bypasses these gates.

---

## 4. First Principles — The Four Axioms

Every mechanism above derives from four axioms. This is the frame to use when judging
whether any given line of code is correct: *which axiom does this serve, and does it
actually serve it?*

### Axiom 1 — A backtest is not evidence. Only out-of-sample survival is.

- **Backtest** — simulating a strategy over historical data.
- **Overfitting** — tuning a model so closely to historical data that it captures noise
  rather than signal, producing excellent backtests and poor live results.

**Therefore:** trades are split by expanding-window walk-forward folds (36-month minimum
training, 6-month steps, 6-month OOS windows). Every gate metric is computed *only* on
trades flagged `is_oos`. `oos_months` measures the union span of OOS windows the cell
actually traded in. If the OOS column is absent from the database, everything is treated as
in-sample and everything fails — deliberately the safe direction.

### Axiom 2 — A label that used future information is a lie.

- **Data leakage** — information from the future contaminating a model's training or
  evaluation, producing performance that cannot be reproduced live.

**Therefore:** the regime model emits both a smoothed label (full-history, reporting only)
and a causal label (walk-forward, filtered forward-only). Attribution and the gatekeeper
consume **only** the causal one, joined point-in-time so that the regime bar timestamp is ≤
the trade entry time. Warm-up bars are NULL, and trades before the first valid label are
tagged UNKNOWN rather than guessed.

Both conditions are required and neither is sufficient alone: joining on `bar_time ≤ entry`
using a *smoothed* label is still leakage, because the label's value itself encodes future
information even though its timestamp does not.

### Axiom 3 — Small samples produce fake edges.

**Therefore:** Bayesian shrinkage blends cells with fewer than 20 trades toward the
strategy-level global, and every shrunk cell is stamped `low_confidence`, which is an
unconditional rejection at vetting.

Separately — and this is a distinct concern — hard sanity bounds exist to catch
*measurement bugs*, not bad strategies. A drawdown above 100% or a Sharpe above 10 is not a
remarkable strategy; it means the arithmetic is wrong. The run aborts rather than shipping.

### Axiom 4 — Default-safe. Missing, stale, or errored ⇒ reject.

**Therefore:**
- Promotion-capable stages default to dry-run / log-only.
- The uplift gate fails closed when the result is missing; there is no silent `None ⇒
  pass`.
- The pointer flips only after checksum verification, so a corrupt upload leaves the
  previous model live.
- An exclusive lock makes concurrent retrains impossible.
- The incumbent is read from the authoritative storage backend, not a local cache.
- A weight map that does not sum to 1.0 raises rather than publishes.

---

## 5. The Economic Logic

Beneath the engineering, the financial thesis is:

> **Capital is allocated by conditional edge, not average edge.**

A strategy is not "good" in the abstract. It is good *in Ranging conditions, on the H1
timeframe*. Everything follows from treating the (strategy × regime × granularity) cell,
rather than the strategy, as the unit of judgement:

- **Regime** is the conditioning variable — the thing performance is measured *given*.
- **The six vetting gates** are the qualification filter — the minimum standard of proof.
- **Softmax weights** are the allocation function — converting measured edge into capital
  share.
- **The ML gatekeeper** is a final per-signal veto layered on top of all of it.

**Position sizing is deliberately absent from System 1.** The system emits a *weight* (a
relative share), never a *size* (an absolute amount of capital). Sizing requires knowledge
of current account equity, open exposure, and risk limits — all of which belong to System 3.
Keeping weight and size separate is what makes the boundary between the systems clean and
enforceable.

- **Kelly criterion** — a formula for the mathematically optimal fraction of capital to
  risk given a known edge. **Quarter-Kelly** means risking one quarter of that amount, a
  common practice because full Kelly is extremely volatile and highly sensitive to
  estimation error in the edge. The platform's stated philosophy is quarter-Kelly with a 2%
  risk cap; the metrics module's 1% default risk fraction is aligned with this.

---

## 6. Current Live State (Verified 2026-07-24)

Read directly from `results/state/` on 2026-07-24.

**Last promotion:**
```
last_run_utc   : 2026-07-19T00:00:01Z
last_decision  : promoted
last_bundle    : 2026-07-19T00-28-32Z-87628c72
```

**Qualification run:** `b678e2de-e35f-4f5b-9998-2d96612a49f9` (generated 2026-07-19T00:22:48Z)

**Qualified cells — 4 of ~80 candidates:**

| Regime | Variant | PF | Sharpe | Win rate | MaxDD | Recovery | Trades | OOS months |
|--------|---------|-----|--------|----------|-------|----------|--------|------------|
| Trending-Up | `Range_Stochastic_Divergence@H1` | 1.84 | 1.01 | 64.6% | 4.0% | 5.91 | 79 | 83.8 |
| Trending-Down | `Range_Stochastic_Divergence@H1` | 3.24 | 2.58 | 76.9% | 3.0% | 26.05 | 117 | 77.8 |
| Ranging | `Range_Stochastic_Divergence@H1` | 2.94 | 3.80 | 73.1% | 4.7% | 75.83 | 335 | 83.8 |
| Ranging | `Range_Stochastic_Divergence@H4` | 3.06 | 1.74 | 73.3% | 2.1% | 15.91 | 60 | 78.1 |

**Capital weights:**
```
Trending-Up    : Range_Stochastic_Divergence@H1  1.00
Trending-Down  : Range_Stochastic_Divergence@H1  1.00
Ranging        : Range_Stochastic_Divergence@H1  0.95
                 Range_Stochastic_Divergence@H4  0.05
```

**Empty regimes:** `High-Vol` — no strategy qualifies, so the system has **no coverage** in
volatile conditions.

**Rejection tally (cells failing each gate; a cell can fail several):**
```
profit_factor  : 72      win_rate       : 47
sharpe         : 72      oos_months     :  8
recovery       : 72      low_confidence :  3
max_drawdown   : 53
```

**Operational cadence:** the hourly orchestrator is running and behaving as designed —
the three most recent logs (07:00, 06:00, 05:00 on 2026-07-24) all record
`no_trigger_or_cooldown` with no work performed.

**Interpretation for the business:** the gates are doing their job — they are rejecting
approximately 95% of candidates. But the surviving population is a **single strategy**. The
entire live model is `Range_Stochastic_Divergence`, ~95% of it at H1. This is a
concentration exposure, not a diversified portfolio.

- **Concentration risk** — the exposure that arises when performance depends on a single
  source. If this one strategy's edge decays, there is nothing behind it.

---

## 7. Audit Map — Where the Business Rules Live

| Rule class | File / anchor | Why it is a risk surface |
|------------|---------------|--------------------------|
| Qualification thresholds | `src/system1/vetting/gates.py:18` (`GATES`) | The six gate values and the composite ranking formula |
| Capital allocation | `src/system1/vetting/gates.py:127` (`normalized_weights`) | Softmax, temperature, floor, water-filling |
| Sum-to-1 invariant | `src/system1/vetting/vet.py:103` (`_assert_weights_normalized`) | The last guard before a sizing artifact ships |
| Metric definitions | `src/system1/attribution/metrics.py` | Sharpe annualisation, equity curve, recovery, shrinkage |
| OOS discipline | `src/system1/validation/walk_forward.py`; `attribution/attribute.py:167` | The core "is this real" machinery |
| Causal labelling | `src/system1/attribution/attribute.py:105` (`_load_regimes`) | The leakage boundary |
| Regime model + dual labels | `src/system1/regime/hmm_regime.py` | Where smoothed and causal labels are produced |
| Gatekeeper training | `src/system1/gatekeeper/train.py` | Fold construction, threshold calibration, degeneracy refusal |
| Uplift statistics | `src/system1/gatekeeper/thresholds.py:44` (`oos_uplift_test`) | The permutation test that constitutes the proof of edge |
| Promotion authority | `src/system1/scheduler/orchestrator.py:117` (`deployment_gates`) | The four gates; the only path to live |
| Trigger policy | `src/system1/scheduler/triggers.py` | When the loop may fire |
| Artifact integrity | `src/system1/serializer/serialize.py`; `publish_gatekeeper.py` | Verify-before-flip contract, secret scan, retention |

---

## 8. Seed Observations for the Audit

These emerged from reading the code and are recorded as **candidates for investigation**,
not confirmed defects. Each requires verification before being treated as a finding.

### 8.1 The live gatekeeper may be stale relative to the live strategy map

`models/champion_model.pkl` is dated **2026-07-05**. `models/proposed_champion_model.pkl` is
dated **2026-07-18**. The orchestrator invokes the gatekeeper only with `dry_run=True`
(`orchestrator.py:178`) in order to harvest an uplift figure for the `oos_uplift_ok` gate —
it never promotes the resulting model. `_default_promote` publishes only the regime and
weights bundle.

**Implication:** the model that vetoes individual live signals and the map that selects
which strategies may trade appear to originate from different training runs, roughly two
weeks apart. Whether this violates an intended invariant — bundle coherence — needs
confirming against the design specification.

### 8.2 `beats_incumbent` compares only regime accuracy

At `orchestrator.py:161`, the head-to-head comparison is made solely on
`regime_accuracy`. A candidate with worse strategy quality, worse gatekeeper uplift, and
fewer qualifying cells would still promote provided its HMM holdout accuracy merely ties the
incumbent's.

**Implication:** "better" is defined by a metric that measures the regime classifier, not
the profitability of the resulting allocation policy. This is a weak definition of
improvement for a gate whose stated purpose is preventing regression.

### 8.3 The 5% weight floor is load-bearing, not incidental

`Range_Stochastic_Divergence@H4` in the Ranging regime carries a weight of exactly `0.05` —
the configured `MIN_WEIGHT`. It received the floor, not an earned allocation.

**Implication:** the fix that replaced starvation-at-1e-8 with a floor did resolve the
starvation defect, but the floor is now the binding constraint on real capital deployment
for that variant. Whether 5% is the correct policy figure, as opposed to an
engineering-convenient default, is a business decision that should be recorded as such.

### 8.4 Context for the audit: two known open findings

Carried forward from `docs/SYSTEM1_ANALYSIS_2026-07-01.md` and prior investigation, and
relevant to interpreting anything found:

- **Regimes do not discriminate.** A discrimination run reported 0 of 10 strategies showing
  a meaningful win-rate spread across regimes (maximum spread 0.075, against a 0.10 bar).
  The regime→strategy mapping has not been demonstrated to be a source of edge. Since regime
  is the conditioning variable on which the entire economic thesis rests, this is the most
  consequential open question in System 1.
- **D1 regimes fall back to K-Means.** The HMM did not clear the 0.70 accuracy floor at the
  daily timeframe. The fallback is working as designed; the point is not to describe D1
  regimes as HMM-derived.

---

## 9. Glossary

Alphabetical. Terms are defined as used in this system, not in full generality.

**ADX (Average Directional Index)** — A technical indicator measuring trend strength
regardless of direction. High values indicate a strong trend.

**Annualisation** — Rescaling a metric so figures covering different periods are comparable
on a yearly basis. Sharpe here is annualised by realised trade frequency, not bar frequency.

**Artifact** — A file or set of files produced by a pipeline run and stored for later
consumption.

**Atomic operation** — An operation that either completes fully or not at all, with no
observable intermediate state. Used here for the pointer flip and the lock file.

**ATR (Average True Range)** — A volatility indicator: the average size of recent price
ranges.

**Attribution** — Assigning observed performance to the conditions under which it occurred.

**Backpressure** — Slowing or blocking a producer when a queue is full, rather than
dropping messages.

**Backtest** — A simulation of a strategy over historical data.

**Bar (candle)** — A summary of price movement over a fixed interval: Open, High, Low,
Close.

**Bayesian shrinkage** — Blending a small-sample estimate toward a broader average, in
proportion to how thin the sample is, to reduce the influence of noise.

**Bootstrap** — A resampling technique that estimates the distribution of a statistic by
repeatedly resampling the observed data.

**Bundle** — The complete published package: model files, metadata, and checksums.

**Candidate** — A newly built model awaiting approval to go live.

**Causal** — Depending only on past and present information, never future.

**Cell** — One (strategy × regime × granularity) combination; the atomic unit of
qualification in this system.

**Champion** — The model currently designated live. Contrast **challenger** — a candidate
attempting to displace it.

**Checksum** — A hash of a file's contents used to detect corruption. This system uses
SHA256.

**Circuit breaker** — An automatic mechanism that halts trading when a predefined loss or
anomaly threshold is breached.

**Classifier** — A model predicting a category. Here: will this trade win, yes or no.

**Class weighting (`scale_pos_weight`)** — Compensating for imbalanced classes so a model
does not simply predict the majority outcome.

**Composite score** — The weighted combination of metrics used to rank qualifying cells:
`0.5×Sharpe + 0.3×PF + 0.2×Recovery − MaxDD`.

**Compounding** — Reinvesting gains so that returns accrue on a growing base.

**Concentration risk** — Exposure arising when performance depends on a single source.

**Cooldown (debounce)** — A minimum interval between repeated actions, preventing a
flapping condition from triggering repeatedly. Here 6 hours between retrains.

**Data leakage** — Future information contaminating training or evaluation, producing
performance that cannot be reproduced live.

**Dead-letter queue (DLQ)** — Where messages that repeatedly fail processing are diverted
for inspection.

**Degenerate model** — One that approves nearly everything or nearly nothing, and therefore
adds no information.

**Deterministic** — Producing identical output from identical input, every time.

**Drawdown** — A decline from a peak in the equity curve. See **maximum drawdown**.

**Dry-run** — Executing a process without its irreversible effects, to inspect what it
would do. Here it writes `proposed_*` artifacts and never touches the live champion.

**Edge** — A statistically demonstrable tendency toward positive expected return.

**Equity curve** — The running value of an account over time.

**Expectancy** — Average profit or loss per trade, here in R-multiples.

**Expanding window** — A validation scheme in which the training set grows with each fold
(as opposed to a sliding window of fixed size). Also called *anchored*.

**Fail closed** — When required information is missing, deny. The safe default for a gate.

**Fail open** — When required information is missing, allow. Used only where denial would
make a system unbootstrappable.

**Feature** — An input variable to a model, derived from raw data.

**Feature store** — A versioned repository of computed features, enabling exact
reproduction of past training runs.

**Filtered estimate** — A state estimate using only data up to and including the current
observation. The causally valid counterpart to a smoothed estimate.

**FinBERT** — A BERT-family language model fine-tuned for financial text sentiment. Present
in this repository as an auxiliary component, not yet integrated as a gate or feature.

**Fold** — One train/test split in a walk-forward validation sequence.

**Forward-backward algorithm** — An HMM inference method making both a forward and a
backward pass over the data. Its output uses future information and must never be a model
input.

**Gate** — A hard pass/fail condition. In this system, gates block rather than penalise.

**Gatekeeper** — The ML classifier that vetoes individual signals below a score threshold.

**Granularity (timeframe)** — Bar length. This system uses H1 (1 hour), H4 (4 hours), D1
(1 day).

**Grid search** — Systematically evaluating combinations of model hyperparameters and
retaining the best.

**Hidden Markov Model (HMM)** — A model assuming an unobservable state drives observable
data, with fixed probabilities of transitioning between states. Here the hidden state is
the market regime.

**Holdout** — Data deliberately withheld from training, used to measure genuine
performance.

**Hyperparameter** — A model setting chosen before training (tree depth, learning rate),
as opposed to a parameter learned during it.

**Hypertable** — A TimescaleDB construct: a table automatically partitioned by time for
efficient time-series queries.

**Idempotent** — Safe to repeat; performing the operation twice has the same effect as
once.

**Immutable** — Never modified after creation. Published bundle versions are immutable;
rollback moves a pointer rather than restoring files.

**In-sample (IS)** — Data the model was trained on.

**Incumbent** — The model currently live and being consumed downstream.

**Kelly criterion** — A formula for the mathematically optimal fraction of capital to risk
given a known edge. **Quarter-Kelly** risks one quarter of that, because full Kelly is
highly volatile and very sensitive to error in the estimated edge.

**K-Means** — A clustering algorithm grouping data into *k* clusters by proximity. Used
here as the regime fallback when the HMM fails its accuracy gate.

**Log-only mode** — Producing the report of what would happen without applying the change.

**Look-ahead bias** — Using information unavailable at the actual decision time. The most
common cause of backtests that succeed and live trading that fails.

**Low-confidence flag** — A stamp on any cell whose metrics required shrinkage, causing
unconditional rejection at vetting.

**Maximum drawdown (MaxDD)** — The largest peak-to-trough decline in the equity curve, as a
fraction of the peak. The system's measure of worst-case pain.

**merge_asof** — A pandas operation joining two time-ordered tables by nearest preceding
key. The mechanism of the point-in-time join.

**MLflow** — An experiment-tracking system recording parameters, metrics, and artifacts for
each run.

**Object storage** — Cloud file storage addressed by key. Here Google Cloud Storage (GCS).

**One-hot encoding** — Representing a categorical value as a set of binary columns, one per
category.

**Optuna** — A hyperparameter optimisation library.

**Out-of-sample (OOS)** — Data the model has never seen, held back to test whether an edge
is real rather than memorised.

**Overfitting** — Fitting noise rather than signal, producing excellent backtests and poor
live results.

**Parquet** — A columnar file format efficient for large analytical datasets.

**Permutation test** — A statistical test that repeatedly reshuffles group labels to build
the distribution of a statistic under the null hypothesis of no difference.

**Pip** — The smallest conventional price increment in a currency pair; the standard unit
for quoting spread and slippage in forex.

**Point-in-time join** — Matching a record to the most recent reference value that existed
at or before its timestamp. Prevents retrospective information contaminating the join.

**Pointer (`latest.json`)** — A small file naming which published version is currently
live.

**Profit factor (PF)** — Gross profit ÷ gross loss. Above 1.0 is profitable.

**Promotion** — Making a candidate the live model.

**p-value** — The probability of observing a result at least as extreme as the one measured
if the null hypothesis (no real effect) were true. Below 0.05 is conventionally
"significant."

**Pub/Sub** — Google Cloud's publish/subscribe message queue service.

**Qualification run** — One complete attribution-and-vetting cycle, identified by a UUID
carried on every row and artifact it produces, for lineage.

**Recovery factor** — Total return ÷ maximum drawdown. Return earned per unit of worst-case
pain.

**Regime** — A persistent market condition. This system uses four: Trending-Up,
Trending-Down, Ranging, High-Vol.

**REST API** — A web interface for requesting data over HTTP.

**R-multiple** — Profit or loss expressed as a multiple of the amount risked. A trade
hitting its stop-loss is −1R; one earning twice its risk is +2R. Normalises across position
sizes and instruments.

**Schema validation** — Checking data against a declared structure before accepting it.

**Serialization** — Converting an in-memory object into a storable file.

**SHA256** — A cryptographic hash function producing a 256-bit fingerprint of a file's
contents.

**Sharpe ratio** — Mean return ÷ standard deviation of returns, annualised. Return per unit
of risk. Broadly, above 1.0 is good and above 2.0 is excellent.

**Single-flight lock** — A mechanism ensuring only one instance of a process runs at a
time. Implemented here with the `O_EXCL` filesystem flag, which makes creation atomic.

**Slippage** — The difference between the expected fill price and the actual one. Modelled
at 0.5 pip on entry in the backtests that produced this system's trade outcomes.

**Smoothed estimate** — A state estimate refined using the full data series including
future observations. Valid for reporting, invalid as a model input.

**Softmax** — A function converting scores into positive values summing to 1.0, with higher
scores receiving proportionally more. The capital allocation function here.

**Spread** — The difference between bid and ask price; a transaction cost. Modelled at 1.0
pip in this system's backtests.

**Standardisation (StandardScaler)** — Rescaling numeric features to zero mean and unit
variance.

**Starvation** — A qualified strategy receiving effectively zero capital due to a
normalisation defect. The failure mode the weight floor exists to prevent.

**Statistical significance** — Unlikely to have arisen by chance in the observed sample.

**Temperature** — A softmax parameter controlling concentration. Higher values flatten the
allocation; lower values concentrate it on the top scorer.

**Threshold** — The model score above which the gatekeeper approves a signal. Calibrated
per regime.

**TimescaleDB** — A PostgreSQL extension for time-series data, providing hypertables and
compression.

**Turnover (approval rate)** — The fraction of candidate signals the gatekeeper approves.
Bounded here to [5%, 60%].

**Uplift** — The difference in mean return between approved and rejected trades, measured
out-of-sample. The gatekeeper's proof of value.

**Variant** — A (strategy, granularity) pair, treated as a distinct qualifier with its own
score and weight.

**Vetting** — Applying the qualification gates to determine which cells may trade.

**Walk-forward validation** — Repeatedly training on a growing window of past data and
testing on the immediately following unseen window. The system's primary defence against
overfitting.

**Warm-up period** — Initial data where a model cannot yet produce a valid estimate. Such
bars are NULL and trades within them are tagged UNKNOWN.

**Water-filling** — The algorithm applying the minimum-weight floor: pin weights below the
floor to exactly the floor, redistribute the remainder proportionally among the rest,
repeat until stable.

**Win rate** — The fraction of trades that were profitable.

**XGBoost** — A gradient-boosted decision-tree algorithm; the gatekeeper's model type.

---

## Appendix — Operating Commands

```bash
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain
source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate

python -m src.system1.features.feature_pipeline --version 1.0.0   # MODEL-002
python -m src.system1.regime.hmm_regime                           # MODEL-003
python -m src.system1.attribution.attribute                       # MODEL-004
python -m src.system1.vetting.vet                                 # MODEL-005 (log-only)
python -m src.system1.vetting.vet --live                          # MODEL-005 (writes state)
python -m src.system1.gatekeeper.train --dry-run                  # MODEL-006 (proposed only)
python -m src.system1.serializer.serialize                        # MODEL-007
python -m src.system1.serializer.publish_gatekeeper --dry-run     # MODEL-007 (gatekeeper)
python -m src.system1.scheduler.orchestrator                      # MODEL-009 (evaluate triggers)
python -m src.system1.scheduler.orchestrator --force              # MODEL-009 (force retrain)

pytest src/system1 -v                                             # the suite that matters
```

**Scheduled operation (crontab):**
```
0 * * * *  shell/cron_system1_retrain.sh        # hourly trigger evaluation
0 0 * * 6  shell/cron_oanda_ingest_saturday.sh  # weekly price ingest
```

---

*Prepared as orientation for a business-rule defect audit of System 1. Statements of live
state were verified against artifacts on 2026-07-24; statements about intended behaviour
were read from the runtime source. Section 8 records candidates for investigation, not
confirmed findings.*
