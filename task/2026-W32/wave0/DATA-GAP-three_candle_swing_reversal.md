# DATA-GAP-three_candle_swing_reversal

## Recommendation
**Implement now with reduced coverage.** The strategy is fully testable today on D1 with EUR_USD, USD_CAD, USD_JPY (live) plus NZD_USD (Wave-1 pending, not a gap). D1 is the source's own primary timeframe and the spec's conservative choice, so the H12 gap costs nothing. GBP_CAD and GBP_NZD are cheap, standard OANDA additions — recommend adding them to the Wave-1 pair batch since they are named only by this strategy and would otherwise be silently dropped. XAU_USD: **drop permanently** — it is excluded by policy (not Forex; pip/margin conventions assume FX) and no workaround should be built.

## What is missing
1. **H12 granularity** — named in `timeframes` ("D1 primary|H12|H4 confirmation"). Not in the allowed set {H1, H4, D1, W1}; not present in `fact_market_prices`.
2. **GBP_CAD** — named in `target_pairs`; not among the 5 live pairs and NOT in the Wave-1 addition list (GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD).
3. **GBP_NZD** — same status as GBP_CAD.
4. **XAU_USD** — named in `target_pairs`; deliberately excluded by policy (DATA_AVAILABILITY.md: "not Forex; `calculate_pips()` and margin conventions assume FX").

## Why the strategy needs it
- `timeframes`: "D1 primary|H12|H4 confirmation|H1 only in direction of D1 trend" — H12 is one of the author's traded frames; the thread trades the pattern on H4/H12/D1.
- `target_pairs`: "EURUSD|NZDUSD|USDCAD|USDJPY|GBPCAD|GBPNZD|XAUUSD" — GBP-cross and gold coverage is part of the author's claimed opportunity set.

## How it could be obtained
1. **H12 — derivable from existing data, no new ingest.** Resample H4 (or H1) bars, grouped on the OANDA day boundary (D1 bars open at 21:00 UTC). Each H12 bar = 3 consecutive H4 bars (or 12 H1 bars): `Open` = open of first child bar, `High` = max of child highs, `Low` = min of child lows, `Close` = close of last child bar, `Volume` = sum of child tick counts. H12 bars stamped 21:00Z (covering 21:00→09:00) and 09:00Z (09:00→21:00). The H4 frame is already aligned to the same 21:00Z day boundary, so grouping is unambiguous — verify by asserting every group's first child timestamp mod 12h ∈ {21:00Z, 09:00Z}. Cost: a pure transform; no rate limits, no vendor. If Wave 2 wants the H12 variant, the resampler belongs in the strategy's own module or the research loader, NOT in shared ingestion (granularity allow-list is H1/H4/D1/W1).
2. **GBP_CAD, GBP_NZD — standard OANDA v20 REST ingest (cheapest; pipeline already built).** Both are ordinary OANDA-tradable FX crosses. Insert `dim_asset` rows (`market_type='Forex'`, `is_active=true`), then `python -m src.system1.ingestion.multi_timeframe_ingest --symbol GBP_CAD` (and `GBP_NZD`). Resumable (`ON CONFLICT` + resume from `MAX(timestamp)`); expect ~130k H1 bars each back to 2006 — one overnight job for both. They were simply not ranked into the Wave-1 batch (each is named by only this one strategy).
3. **XAU_USD — obtainable from OANDA (XAU_USD is a standard v20 instrument) but excluded by policy.** Supporting it would require pip-value and margin conventions that the system explicitly does not implement for metals. Do not half-support; record as a permanent exclusion.

## Recommended integration
- **Now (Wave 2):** run the strategy on EUR_USD, USD_CAD, USD_JPY, NZD_USD (pending) at D1 only. No ingest needed.
- **Optional pair extension:** two `dim_asset` inserts (`GBP_CAD`, `GBP_NZD`, `market_type='Forex'`, `is_active=true`) + two overnight ingest commands as above; verify with the standard coverage query before enabling.
- **Optional H12 variant (only if the D1 result is promising):** private resampling function in the strategy module per the derivation above; no schema change, no allow-list change. Treat H12 as a reporting variant, not a second qualification path.
- **XAU_USD:** none. Document exclusion in the strategy report.

## Impact if we proceed without it
- **Pairs:** coverage is 4 of 7 requested (57%). The two missing GBP crosses are the author's highest-volatility named instruments, so the backtest will under-represent the strategy's behaviour in fast, wide-ranging markets; results will be biased toward the behaviour on EUR_USD/USD_CAD/USD_JPY/NZD_USD. Still informative: D1 counter-trend reversal mechanics do not depend on the specific cross, and the pooled verdict remains a fair test of the pattern itself.
- **H12:** none for the declared D1 spec. The H12 variant would roughly double signal frequency versus D1 (two bars per day instead of one); without it we simply test the coarser, slower version — which is the conservative reading anyway.
- **XAU_USD:** gold's trend/volatility character differs materially from FX, but the exclusion is policy, not oversight; the report should state that one of the author's named instruments was untestable by design.
