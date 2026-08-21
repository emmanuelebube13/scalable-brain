# Pre-registration — cross-sectional currency momentum, portfolio-level

Written **before** the first run against real data, per
`docs/design/STRATEGY_EXPERIMENT_STANDARD.md`. Nothing below is edited after seeing a
result; findings go in `RESULT.md` alongside it.

Date: 2026-08-21

## What is being measured

The mechanism `currency_momentum_factor` declares but the single-pair harness cannot
reach: rank currencies by trailing 252-bar spot return against USD, long the top
tercile, short the bottom, rebalance on the first bar of each calendar month.

Implemented in `src/portfolio/` by calling that module's own fixture-pinned
`currency_momentum()` and `net_tercile_weights()` unchanged. Universe is the five
pairs already in `dim_asset` — EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD — on D1,
2005-12-31 to 2026-08-19 (6,043 bars).

## Parameters, fixed in advance

| Parameter | Value | Source |
|---|---|---|
| Lookback | 252 D1 bars | the module's `LOOKBACK_BARS`; not tuned here |
| Rebalance | first bar of a new calendar month | the module's NOTE 2 (truncation-stable) |
| Weighting | net tercile, ±1/3 | `net_tercile_weights`, verbatim |
| Vol scaling | reported both with and without | pre-declared as two arms, not a sweep |
| Cost | 0 and 2 bp of turnover | 2 bp brackets the measured 1.8–2.9 pip spreads |

**No other variants will be run.** No alternative lookbacks, no threshold sweeps, no
pair subsets. If a variant is tried later it is a new experiment with its own
registration and its own multiple-comparison accounting.

## Known handicap, stated up front

Five currencies is a degenerate cross-section. `net_tercile_weights` on a 5-currency
universe puts the median currency at exactly 0.0, leaving **four active legs** — two
long, two short. Published cross-sectional currency momentum uses far wider universes,
and the effect is a breadth effect. This run is therefore expected to *understate* the
mechanism, and a weak result cannot by itself condemn it.

## What I expect (recorded before running)

- Most likely: **Sharpe 0.0 to 0.4**, PF 1.0 to 1.2. Directionally positive but nowhere
  near the gates, consistent with a real-but-thin effect measured at insufficient breadth.
- Costs should barely register — monthly rebalancing on four legs is low turnover.
- Vol scaling should help modestly; the legs have similar volatility, so there is less
  for it to fix than in a multi-asset portfolio.

## Decision rules, fixed in advance

| Outcome | Reading | Action |
|---|---|---|
| Sharpe > 0.8 **and** PF > 1.5 | Would clear the gates | **Do not celebrate.** Four legs cannot plausibly produce this; audit for a leak before reporting |
| Sharpe 0.3 – 0.8 | Consistent with the published effect at reduced breadth | Supports breadth as the binding constraint; argues for widening the universe |
| Sharpe 0.0 – 0.3 | Weak, as expected for four legs | Inconclusive on the mechanism; breadth decision unchanged |
| Sharpe ≈ 0 to −0.3 | No detectable cross-sectional effect here | Mechanism unsupported at this breadth |
| Sharpe < −0.3 | Suspicious | Investigate for a sign or mapping error before reporting, despite the passing sign tests |

## The comparison that matters

The crippled single-pair version scored **PF 0.89, Sharpe −0.42** over 300 trades
(`results/reports/strategy_ranking_20260817T012843Z.json`). The portfolio version
should beat that. If it does not, one of the two implementations is wrong and that
becomes the finding.

## Validity precondition

`src/portfolio/tests/` must pass, including `test_planted_trend_is_detected`. Without a
working positive control a null result is uninterpretable. Status at time of writing:
**15/15 passing**.
