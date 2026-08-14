# DATA-GAP-currency_momentum_factor

**Strategy:** Quantpedia Currency Momentum Factor (12-month cross-sectional) — row 43 of forex_swing_strategies.csv
**Companion spec:** `SPEC-currency_momentum_factor.md`

## Recommendation

**Implement now with reduced coverage — this gap is NOT blocking.**

The core signal (trailing 12-month return per currency vs USD) is computable entirely from
OHLCV data that already exists. What is missing is **breadth**, not the signal: the
documented strategy ranks 10–20 currencies, while the DB has 5 non-USD currencies today and
at most 7 after the Wave-1 backfills. On today's 5-currency universe the top-3/bottom-3 rule
is degenerate (it collapses to long-2/short-2 with the median currency flat — see SPEC §2
and §10 row 2), so results before Wave-1 completes should be read as a thin-universe
approximation, not as a test of the documented factor. Do not defer: the strategy is
implementable, the degeneracy is fully declared in the spec, and the walk-forward harness
already skips pairs with insufficient history. Do not drop: this is one of the few
academically anchored rows in the CSV (Menkhoff, Sarno, Schmeling & Schrimpf). If a
decision-maker wants the *documented* factor rather than a 7-currency sketch, the fix is
ordinary OANDA pair ingestion (below) — a scheduling decision, not a purchase.

## What is missing

1. **Universe breadth (the real gap).** The CSV requests a "Universe of 10-20 currencies vs
   USD (majors + liquid minors)". Available/planned USD pairs cover only: EUR, GBP, JPY,
   AUD, CAD (live) + NZD, CHF (Wave 1) = **7 currencies maximum**. Reaching even the low end
   of 10 requires additional USD pairs with **no Wave-1 plan**, e.g. USD_DKK, USD_NOK,
   USD_SEK, USD_SGD, USD_MXN, USD_HKD (any three of which reach 10). (The Wave-1 cross pairs
   GBP_JPY, EUR_JPY, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD add no new currency-vs-USD series
   and are irrelevant here.)
2. **"Total return" carry component (minor, accepted deviation).** The signal as documented
   is a 12-month *total* return (spot + interest differential). No rate or forward data
   exists in the DB ("Non-price data — none of it exists", DATA_AVAILABILITY.md), so the
   spec uses spot return only (SPEC §10 row 3). For 12-month G10 horizons the spot component
   dominates; the ranking is largely, not perfectly, preserved.
3. **Overnight cash rates (cosmetic, out of scope).** Listed in the CSV's data requirements
   for "cash not used as margin invested at overnight rates". The r-multiple backtest does
   no sizing and models no margin or cash balance, so this component cannot appear in any
   reported metric. Not ingested (SPEC §10 row 8).

## Why the strategy needs it

Verbatim from the CSV:

- `target_pairs`: "Universe of 10-20 currencies vs USD (majors + liquid minors)"
- `data_requirements`: "OHLCV daily FX spot or futures prices vs USD|overnight cash rates"
- `risk_management`: "Equal-weighted legs; cash not used as margin invested at overnight
  rates; diversification across 10-20 instruments; documented max drawdown -45.87%"

The diversification is not decoration: a cross-sectional factor's Sharpe comes from holding
many independent legs so idiosyncratic currency noise cancels. At 5–7 currencies the
published 0.30 Sharpe / 7.61% p.a. profile is not what is being measured.

## How it could be obtained

- **Additional USD pairs:** OANDA v20 REST — the cheapest path, and the ingestion pipeline
  already exists. OANDA practice supports USD/NOK, USD/SEK, USD/SGD, USD/MXN, USD/HKD;
  USD/DKK availability should be confirmed against the broker feed before promising it.
  Same procedure as the Wave-1 additions: insert `dim_asset` rows, then
  `python -m src.system1.ingestion.multi_timeframe_ingest --symbol <PAIR>` (resumable,
  overnight backfill ~130k H1 bars/pair to 2006).
- **Carry component of total return (optional):** 3-month rates per currency from FRED
  (free, programmatic; e.g. `DGS3MO` for USD and OECD/national series for the rest) — same
  schema as proposed in `DATA-GAP-usd_carry_basket.md` (`fact_macro_rates`). Only worth
  building if the carry strategy's ingestion proceeds anyway; do not build it for this
  strategy alone.
- **Overnight cash rates for margin yield:** FRED, free — but there is nothing to wire it
  to in an r-multiple backtest. Only relevant if a capital-weighted equity simulation is
  ever commissioned.

## Recommended integration

1. Now: nothing. Implement `SPEC-currency_momentum_factor.md` as written; the harness
   degrades gracefully (skips pairs with insufficient history).
2. Wave-1 completion: verify NZD_USD and USD_CHF D1 coverage (≥ 253 closed D1 bars) so the
   universe reaches 7 currencies and the top-3/bottom-3 rule becomes non-degenerate.
3. Optional breadth upgrade (new decision, not Wave 1): pick three additional USD pairs
   (suggest USD_NOK, USD_SEK, USD_SGD for liquidity and G10/liquid-minor mix), insert
   `dim_asset` rows (`market_type='Forex'`, `is_active=true`), run the standard ingest
   command per pair overnight, verify with the coverage query. No schema change is needed —
   the spec's universe `U(t)` is declared mechanically from whichever pairs pass the
   data-sufficiency gate, so new pairs are picked up automatically once they have 253 D1
   bars (~12 months after their backfill start of 2006, i.e. immediately for full backfills).
4. Only if the carry component is wanted: land the `fact_macro_rates` ingestion from the
   usd_carry_basket gap document, then extend `mom_c` to `spot_return + (r_c − r_US)`; this
   is a spec revision, not a Wave-2 implementer decision.

## Impact if we proceed without it

The backtest measures a **5-currency (later 7-currency) cross-sectional momentum sketch**
instead of the documented 10–20-currency factor. Specifically:

- On 5 currencies the tercile rule is degenerate: ranks 1–2 long, 4–5 short, rank 3 flat —
  ~83% of the universe is always positioned, so the cross-sectional selection (the actual
  anomaly) is barely exercised; results will look like plain multi-pair trend-following.
- Diversification is 2–3× thinner than documented, so portfolio-level statistics (Sharpe,
  drawdown) will be materially worse than the published 0.30 / −45.87% and per-pair
  concentration higher. A pooled pass would not validate the documented factor; a pooled
  fail would not refute it.
- The signal ranking itself is otherwise honest: spot return is OHLCV-derived and causal;
  omitting the carry component perturbs ranks only at the margin for G10 pairs.

**Verdict: still informative** as a pilot of the anomaly's post-2010 survival on the majors
— which is exactly what the CSV's own reasoning asks for ("requires modern re-testing") —
provided every report carries the thin-universe caveat and does not inherit the published
10–20-currency performance claims.
