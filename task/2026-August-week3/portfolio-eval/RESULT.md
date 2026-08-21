# Result — cross-sectional currency momentum, portfolio-level

Companion to `PREREGISTRATION.md` in this folder, which was written and fixed before
this run. Nothing in the registration was edited afterwards.

Run: 2026-08-21 · `python -m src.portfolio.run_momentum`
Raw output: `results/reports/portfolio_momentum_20260821.json`

## Validity precondition — met

`src/portfolio/tests/` — **15/15 passing**, including `test_planted_trend_is_detected`.
The evaluator scores a world built so momentum must work at Sharpe > 0.5, and scores a
random-walk world inside ±0.5. A null result below is therefore interpretable: the
instrument can see an edge when one is present, and does not manufacture one from noise.

## The numbers

Universe EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD · D1 · 6,043 bars
2005-12-31 → 2026-08-19 · 239 monthly rebalances (2006-10-01 → 2026-08-02)

| vol scaled | cost | Sharpe | PF | MaxDD | Ann. return | OOS Sharpe | OOS PF |
|---|---|---|---|---|---|---|---|
| no | 0 | 0.066 | 1.013 | 18.6% | 0.21% | −0.120 | 0.978 |
| no | 2 bp | 0.047 | 1.009 | 20.3% | 0.11% | −0.143 | 0.974 |
| yes | 0 | 0.088 | 1.017 | 18.0% | 0.32% | −0.126 | 0.977 |
| yes | 2 bp | 0.053 | 1.010 | 20.6% | 0.14% | −0.166 | 0.970 |

## Reading, against the pre-registered rules

Full sample lands in the **"Sharpe 0.0 – 0.3 — weak, as expected for four legs"** band.
Walk-forward OOS lands in **"≈0 to −0.3 — no detectable cross-sectional effect here"**.
Neither triggers the audit-for-a-leak rule, and neither triggers the sign-error rule.

The honest summary: **no edge at this breadth.** An annualized return of 0.1–0.3% against
an 18–20% maximum drawdown is indistinguishable from zero. It is not a disaster and not
a discovery.

Two predictions in the registration held:

- Costs barely register. 2 bp of turnover moves Sharpe by about 0.02–0.04, as expected
  for four legs rebalanced monthly.
- Vol scaling helps marginally (+0.02 Sharpe) and does not rescue anything, as expected
  when the legs have similar volatility.

## The comparison that mattered

| | PF | Sharpe |
|---|---|---|
| Single-pair crippled version (`strategy_ranking_20260817T012843Z.json`, 300 trades) | 0.89 | **−0.42** |
| This portfolio version, full sample | 1.01 | **+0.07** |

The portfolio version beats the crippled one, which is what the registration said must
happen. That confirms the crippling was real — scoring a cross-sectional strategy one
pair at a time genuinely destroyed information — and it removes the alternative
explanation that one of the two implementations is simply wrong.

It also means the −0.42 on file **should not be read as a verdict on the mechanism.** It
was a verdict on a mutilated version of it.

## What this does and does not settle

**Settles:** the mechanism, measured properly, is flat on five currencies. The
single-pair verdict was an artefact. The measurement gap named in
`N5-fleet-completion/SUMMARY.md` finding #5 is now closed for weight-schedule strategies.

**Does not settle:** whether cross-sectional currency momentum works. Five currencies
leave four active legs — `net_tercile_weights` sends the median currency to exactly 0.0
— and the published effect is a breadth effect. This run was pre-declared as expected to
understate it, and it did. A flat result at four legs is weak evidence about the
mechanism at twenty.

## What is now cheap that was not before

The evaluator is universe-agnostic: `build_bundle(pairs)` takes any list of symbols in
`dim_asset`. The 68 FX pairs, 21 metals and 34 index CFDs available on the account are
each one row in `dim_asset` and one ingest run away from being measurable here. That is
the experiment this result argues for, and it is now a data question rather than an
engineering one.

## Caveats a reader should carry

1. **Bar-level profit factor is not trade-level profit factor.** A continuously held
   portfolio has no trades; the 1.01 here is not comparable to the 1.5 gate, which is
   defined on per-trade r-multiples. Comparing them directly is an error.
2. **Costs are modelled as a flat 2 bp of turnover**, not from the per-bar bid/ask now
   known to be in `fact_market_prices`. Wiring real spreads in is
   `task/2026-August-week3/ingest-mba/` and would make this stricter, not looser.
3. **Financing is not modelled.** A monthly-rebalanced currency portfolio earns or pays
   carry, and the account's financing rates run from +1.8% to −3.83% annualized. For a
   strategy held this long that term is not negligible and its absence is a real gap.
4. The walk-forward OOS mask is reported for comparability with the rest of System 1,
   but this strategy has **no fitted parameters** — the lookback and tercile rule are
   pre-registered from the source — so the full sample is already out-of-sample in the
   sense that matters.
