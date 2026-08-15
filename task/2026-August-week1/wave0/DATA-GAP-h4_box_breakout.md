# DATA-GAP-h4_box_breakout

## Recommendation
**Implement now with reduced coverage, and queue the three missing JPY crosses for
ingestion alongside the Wave-1 batch.** Two of the five requested pairs (GBP_JPY, EUR_JPY)
are already Wave-1 additions — pending, not gaps — and they are the two most liquid and
most volatile JPY crosses, i.e. the pairs where the strategy's premise (weekly
range-expansion on volatile JPY crosses) is strongest. The remaining three (AUD_JPY,
CHF_JPY, CAD_JPY) are standard OANDA v20 instruments obtainable with the exact ingest
procedure Wave 1 is already running; there is no reason to defer or drop the strategy.
Caveat: with **zero** of the five pairs live today, the strategy is untestable until at
least the GBP_JPY/EUR_JPY backfill completes — schedule this strategy's Wave-2 run after
that backfill is verified.

## What is missing
1. **Pairs:** AUD_JPY, CHF_JPY, CAD_JPY — all granularities (H1 for fill resolution,
   H4 for decisions). Not in `dim_asset` (only 5 pairs live) and **not** in the Wave-1
   addition list (GBP_JPY · EUR_JPY · NZD_USD · USD_CHF · EUR_GBP · EUR_AUD · AUD_NZD ·
   EUR_CAD — note Wave-1 adds USD_CHF and the CAD *majors*, not these JPY crosses).
2. **Secondary (minor): historical spread series** for JPY crosses. The source triggers
   at "box + 10–20 pips + spread"; no spread data exists in `fact_market_prices`. The spec
   uses the 1.0-pip cost-model constant as a declared proxy (SPEC §8/§10 row 2). This is a
   flagged proxy, not a blocker, and does not require new ingestion to proceed.

## Why the strategy needs it
CSV `target_pairs`: **"GBP/JPY | EUR/JPY | AUD/JPY | CHF/JPY | CAD/JPY"** — the strategy is
*defined* as a JPY-cross system; the recommendation reasoning states the edge is
"opening-week range resolution on volatile JPY crosses". Running it on substitute pairs
(e.g. the live USD_JPY) would measure a different instrument set than the strategy
documents; running it on 2 of 5 pairs measures the strategy on its two strongest cells but
drops the AUD/CAD/CHF funding-currency diversification the basket implies.

## How it could be obtained
**OANDA v20 REST — cheapest, already built.** AUD_JPY, CHF_JPY, and CAD_JPY are all
standard OANDA instruments; the existing `multi_timeframe_ingest` pipeline handles them
with zero code changes. The spread series is *not* worth obtaining: historical OANDA
spread is not served by the candles endpoint, tick-level pricing would be a different
vendor (e.g. Dukascopy tick data, free with registration, or TrueFX, free) and a schema
change — disproportionate for a 1-pip-scale buffer term; keep the declared proxy.

## Recommended integration
Per the Wave-1 procedure (CONTRACT_V2 §7):
1. Insert three `dim_asset` rows (`market_type='Forex'`, `is_active=true`) for
   AUD_JPY, CHF_JPY, CAD_JPY.
2. `python -m src.system1.ingestion.multi_timeframe_ingest --symbol AUD_JPY` (and likewise
   CHF_JPY, CAD_JPY). Resumable (`ON CONFLICT`, resumes from `MAX(timestamp)`); ~130k H1
   bars/pair to 2006 — run overnight with the Wave-1 batch.
3. Verify with the coverage query before declaring done; the Wave-2 harness already skips
   pairs with insufficient history, so a partial backfill degrades gracefully.
No schema change needed. The strategy spec (SPEC-h4_box_breakout.md §2) already declares
the pairs; no spec edit is required when data lands.

## Impact if we proceed without it
The backtest measures the strategy on **GBP_JPY + EUR_JPY only** (once their Wave-1
backfill lands). That is still informative: these are the highest-volatility,
highest-liquidity JPY crosses and the natural home of the claimed edge, so a failure here
is a strong verdict against the strategy everywhere. What is lost: (a) 60% of the intended
basket, so pooled trade counts drop ~3/5 and per-cell diversification across funding
currencies (AUD, CAD, CHF behave differently under risk-on/risk-off) is untested; (b) any
verdict is exposed to GBP- and EUR-specific idiosyncrasy. Conclusion: proceed on two
pairs, publish per-cell verdicts, and treat the three missing crosses as an ingest task,
not a research blocker.
