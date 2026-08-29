# src/vetting/ — gates, selection, and the owner override

Full procedure: the `run-vetting` skill. This file is the constraints only.

## Integrity is checked before the gates, and is not a gate

`INTEGRITY_DISQUALIFIED` is evaluated in `vet.py` **before** the performance gates, in a
separate `integrity_fail` category. The distinction is load-bearing:

> A gate failure means "could pass later by improving." An integrity failure cannot.

`Range_Stochastic_Divergence` (strategy 10) reads the future via `rolling(center=True)` and
emits **zero** causal signals — but its attribution rows still show PF 1.92, because they
derive from the look-ahead backtest. **Regenerating the map without the integrity bar
re-qualifies it.** Never remove that bar to see what happens.

## The gates — OOS trades only

PF ≥ 1.5 · Sharpe ≥ 0.8 · MaxDD ≤ 25% · WinRate ≥ 40% · Recovery ≥ 3.0 · **OOS ≥ 12 months**

- The OOS gate was lowered from 60 to 12 **by owner decision, 2026-08-21**. Deliberate. Tests
  still asserting 60 are stale — fix the tests, do not revert the behaviour.
- **There is no minimum-trade-count gate.** `trade_count` is only a ranking tie-break, so a
  cell can pass everything on a small sample. Sample adequacy is the reviewer's job.
- When a threshold appears in a message string, **read it from the constant**. A hardcoded
  `< 60mo` in a rejection reason once sent a downstream agent investigating a working gate.

## `designate.py` is an owner override

It places a **gate-failing** strategy into the map with a written reason, and refuses
`INTEGRITY_DISQUALIFIED` ids. `selection_basis: "designated"` propagates all the way into the
signal message and **must be disclosed** in anything describing the live model set.

Known latent defect: `vet.py` can publish qualified strategies with **empty exits**. Check
exits are populated before believing a new qualifier.

## Standing finding

**Regimes do not discriminate** — `n_discriminating: 0 of 10`, max win-rate spread 0.0567
against a 0.10 bar, re-tested against honest labels (kappa 0.83+). A qualifying regime cell
is not evidence that regimes work. The Trending-Up H4 cell is 100% USD_JPY.

## Defaults

`vet` without `--live` writes `results/reports/proposed_*` and touches nothing live. Run it
first, read it, then go live.
