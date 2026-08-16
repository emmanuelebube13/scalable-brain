# Strategy Experiment Standard

**Status:** proposed, 2026-08-15 · **Derived from:** `task/2026-August-week2/deliverables/T3-regime-aware/`
**Applies to:** any claim that a strategy, variant, filter or context signal is better than what it replaces — including all 51 incoming strategies.

---

## Why this exists

Between 2026-08-02 and 2026-08-15 this system produced four results that looked like edges and
were not:

| claim | what it actually was |
|---|---|
| `Range_Stochastic_Divergence`, PF 1.92 across four live cells | look-ahead — a centred rolling window |
| Regime map with 4 qualifying cells | derived from those contaminated outcomes |
| "72 cells tested" | 16 were byte-identical photocopies of other cells |
| Regime-aware arm, PF 0.85 → 1.24, **p = 0.0428** | pair selection; the regime label proxied for "is this USD_JPY" |

Every one passed the checks in force at the time. Each was caught by a check added afterwards.
This document is those checks, written down before the next batch of strategies arrives — so
they are entry requirements rather than post-mortems.

**The governing principle:** a result must survive being *tried to be broken* before it is
believed. The gates in `src/system1/vetting/gates.py` test whether a strategy performed. These
rules test whether the measurement means anything.

---

## The eight rules

### 1. Equivalence before comparison

Any new implementation of an existing strategy — a port, a refactor, a wrapper — must reproduce
the original **trade for trade** (entry time, direction, entry price, stop, target, exit reason,
r-multiple) when configured to be a no-op, *before* any A/B built on it is believed.

> Without this you cannot tell whether a difference came from the intervention or from the port.
> Reference: `src/regime_aware/tests/test_equivalence.py`.

### 2. Parameters fixed in advance, and written down

Every parameter of an intervention must be chosen from stated reasoning **before** the run, and
the reasoning committed alongside the values. Adjusting parameters after seeing output creates a
new variant — name it and re-test it; do not edit the original.

> Reference: the block-by-block rationale in `src/regime_aware/strategies/donchian_vcp.py`.
> An untraceable parameter is indistinguishable from a fitted one.

### 3. Per-pair decomposition is mandatory

No pooled number is believed without its per-pair breakdown. **A cell drawing more than 70% of
its trades from a single pair is flagged and does not count as a multi-pair result.**

> This is the rule that caught the confound. `hmm_aware` drew 90% of its trades from USD_JPY;
> the pooled PF of 1.24 was indistinguishable from "trade the blind strategy on USD_JPY only."

### 4. Check the context variable for degeneracy first

Before conditioning on any context signal — regime, session, volatility bucket — report its
distribution **per instrument**. A signal taking one value for more than 90% of an instrument's
bars carries no information for that instrument, and conditioning on it silently becomes
instrument selection.

> The HMM labels are 92–98% `Ranging` for EUR_USD, GBP_USD, AUD_USD and USD_CAD, and at H4 those
> four pairs have **exactly zero** `Trending-Up` bars across 28,000+ bars each.

### 5. Report a confidence interval, not a point estimate

Every profit factor is reported with a 95% bootstrap interval. **A cell whose interval includes
1.0 has not demonstrated that it makes money**, whatever its point estimate.

> Applied to the T3 study, this invalidated every attractive cell — PF 1.48 came with [0.95, 2.22].
> The only interval excluding 1.0 belonged to a *losing* cell, PF 0.76 [0.62, 0.91].

**Implied sample size.** Interval width falls roughly with √n. Observed here: n=209 → width 0.84;
n=799 → width 0.29. Resolving a PF of 1.5 from 1.0 with confidence therefore needs on the order
of **800–1000 OOS trades per cell**. Cells in the low hundreds cannot settle the question, no
matter how good they look. The production `min_n = 20` shrinkage guard is far below this and
should be read as a floor against absurdity, not as evidence of sufficiency.

### 6. Significance is necessary, not sufficient

Report a permutation test against the baseline (reuse `gatekeeper/thresholds.oos_uplift_test`).
Then ask what else differs between the two populations. **A significant result that fails rules
3–5 is a significant artifact.**

> `hmm_aware` returned p = 0.0428. The populations genuinely differ — one excludes four losing
> pairs. The test was right; the interpretation would have been wrong.

### 7. Apply the selection discount to anything found by looking

A cell discovered by inspecting results carries a large, now-measured penalty:

> **1.96 → 0.89.** The MTF experiment's best cell (PF 1.96, one of 36, chosen after looking)
> became PF 0.89 overall when the same idea was applied uniformly with parameters fixed in
> advance.

A promising cell found by inspection is a **hypothesis**, never a result. It must be re-run
pre-registered and uniformly before it counts.

### 8. Experiments are isolated and archivable

An experiment lives in its own package, opens the database **read-only**
(`SET default_transaction_read_only = on`), writes only under `results/<experiment>/`, and
modifies nothing outside its folder. Rejecting it must be a zip-and-delete that leaves the
production system bit-identical.

> Enforced, not promised: `test_database_itself_refuses_a_write` asserts PostgreSQL rejects the
> write, and a source scan forbids write verbs in the package.

---

## Checklist

Before any "X is better than Y" claim is accepted:

- [ ] Equivalence test passes under null parameters
- [ ] Parameters and reasoning committed before the run
- [ ] Per-pair table included; no cell >70% one pair (or flagged)
- [ ] Context variable's per-instrument distribution reported; no >90% degeneracy
- [ ] Profit factor reported with 95% bootstrap CI; CI excludes 1.0
- [ ] Permutation test vs baseline reported, **and** rules 3–5 pass
- [ ] If found by inspection: re-run pre-registered and uniform
- [ ] Experiment read-only, self-contained, archivable

## Two known measurement gaps

1. **`r_multiple` excludes spread.** Slippage is in the fill price, but the 1-pip spread is
   subtracted only from dollar PnL (`core_engine/backtest_engine.py:120`). Every r-based metric
   in this repo is therefore *optimistic*. Report gross and net until this is unified.
2. **Repeated looks erode the OOS window.** The walk-forward OOS period has now been examined
   many times. Before promotion, a final holdout that has never been inspected should be opened
   exactly once.

## Reference implementation

`src/regime_aware/` implements all eight rules end to end and is the template to copy.

```bash
python -m pytest src/regime_aware/tests/ -q      # the guarantees
python -m src.regime_aware.runner --lookback-years 10
```
