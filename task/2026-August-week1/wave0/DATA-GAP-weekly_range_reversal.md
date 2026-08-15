# DATA-GAP-weekly_range_reversal

## Recommendation
**Implement now with reduced coverage — and add GBP_CAD to the Wave-1 ingestion list as a ninth pair.** The strategy is fully testable today on `GBP_USD` plus the four other live majors (the author explicitly generalises to "other ranging major/minor pairs"), so the missing pair must not block the build. But GBP_CAD is the author's *headline* instrument, it is unambiguously Forex (no XAU-style exclusion applies), and it costs exactly one `dim_asset` row plus one resumable OANDA ingest command — the cheapest possible gap to close. Deferring the whole strategy for one pair would waste a clean, mechanical spec; dropping GBP_CAD permanently would discard the cell the author actually traded.

## What is missing
- **Pair:** `GBP_CAD` (GBPCAD), all granularities (this strategy needs H1 only).
- Not in the live 5-pair universe (`EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD`) and — unlike 8 other named pairs — **not in the Wave-1 addition list** (`GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD`). This is an oversight in the Wave-1 demand extraction, not a deliberate exclusion.
- No granularity or external-feed gap: the strategy needs only H1 OHLCV (CCI, rolling 336-bar range, pip size — all derivable).

## Why the strategy needs it
The CSV `target_pairs` field names it first: **`GBPCAD|GBPUSD|Other ranging major/minor pairs`**. The author's system was demonstrated on GBPCAD — a high-ATR cross famous for multi-week ranges, which is precisely the regime the hypothesis (§1 of the SPEC) depends on. GBPUSD is the named fallback; "other ranging pairs" maps to the rest of the universe but is an interpolation, not the author's evidence base.

## How it could be obtained
**OANDA v20 REST — the cheapest path, already built.** GBP_CAD is a standard OANDA instrument; the existing `multi_timeframe_ingest` pipeline needs no code change, only a `dim_asset` row and one command. Expected backfill: ~130k H1 bars to 2006, overnight at practice rate limits, resumable via `ON CONFLICT ("timestamp", asset_id, granularity)` — identical in every respect to the 8 pairs already scheduled. No vendor, licence, or cost considerations arise.

## Recommended integration
1. Insert `dim_asset` row: `symbol='GBP_CAD'`, `market_type='Forex'`, `is_active=true` (next free `asset_id`, currently 6+ depending on Wave-1 ordering).
2. `python -m src.system1.ingestion.multi_timeframe_ingest --symbol GBP_CAD` (H1 suffices for this strategy; H4/D1/W1 come free with the standard job and serve the rest of the fleet).
3. Verify with the standard coverage query before declaring done, per CONTRACT_V2 §7.
4. No schema change. Pip convention: GBP_CAD is a CAD-quote pair at 0.0001 — confirm `calculate_pips()`/`get_pip_value()` handle it identically to USD_CAD (already live), which they should by construction.
5. Add `GBP_CAD` to `pairs_available` in SPEC-weekly_range_reversal §2 marked **pending**, alongside the Wave-1 list.

## Impact if we proceed without it
The backtest would measure the strategy on `GBP_USD`, `EUR_USD`, `USD_JPY`, `AUD_USD`, `USD_CAD` (plus pending Wave-1 pairs) — 5–13 cells instead of 6–14. That is still fully informative about the *rules*: the hypothesis is a generic range-reversion claim, not a GBPCAD-specific one, and five live pairs give an adequate pooled sample. What is lost is (a) the single cell with the strongest a-priori regime fit (GBPCAD's ranging reputation is why the author chose it), creating mild adverse-selection risk in the pooled verdict — if the strategy passes without its best pair, the verdict is if anything conservative; (b) fidelity to the source, since the author's own demonstrations are unverifiable. Net: proceed without it now; ingest GBP_CAD overnight and re-run the cell when it lands — the marginal cost of both actions is near zero.
