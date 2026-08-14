# DATA-GAP-h4_crossover_21_89_macd

## Recommendation

**Implement now with reduced coverage (10 of 12 pairs), and add the two CHF crosses via the standard Wave-1 ingest procedure when convenient — do not defer, do not drop.** The strategy is a generic trend-pullback system with no CHF-specific logic; GBP_CHF and EUR_CHF are simply 2 of 12 cells in a pooled test. Losing them trims dispersion coverage (and removes two historically range-prone, post-2015-floor-removal CHF series that would likely have been among the harder cells), but it does not change what the backtest measures or threaten validity. Both instruments are standard OANDA v20 symbols, so closing the gap is an overnight operator job identical in kind to the eight Wave-1 pair additions already planned — the cheapest possible fix on the menu.

## What is missing

- **Pairs (primary gap):** GBP_CHF and EUR_CHF, at H4 (signals), D1 (stop structure), and H1 (fill resolution). Neither exists in `dim_asset` (5 live pairs: EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD) and neither is in the Wave-1 addition list (GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD). Note: USD_CHF IS in the Wave-1 list and is **pending, not a gap**. The other seven named pairs (EURGBP, EURAUD, EURJPY, GBPJPY, USDCHF pending; EURUSD, GBPUSD, AUDUSD, USDCAD, USDJPY live) are covered.
- **Secondary items (not pair data; recorded here per the no-silent-proxy rule):**
  - No holiday/economic calendar feed exists. The source's "no trading on major US holidays" is implemented in the SPEC via a static, date-arithmetic US-federal-holiday list (derivable, flagged in SPEC §8 and §10 row 7). A real calendar feed would only refine this slightly; not worth obtaining on its own.
  - No fundamental/news data exists. The source's "~10-15 min daily fundamental check" is discretionary and non-mechanical; it is dropped with no proxy substituted.

## Why the strategy needs it

The CSV `target_pairs` field names twelve pairs verbatim: `EURUSD|GBPUSD|AUDUSD|USDCAD|EURGBP|EURAUD|EURJPY|GBPJPY|USDJPY|GBPCHF|USDCHF|EURCHF`. The author's documented hand-compiled backtest (Jan 2009 - Oct 2010) ran "across 12 pairs", so the CHF crosses are part of the evidence base the conviction rating rests on; dropping them means the modern re-test covers a strict subset of the author's sample.

## How it could be obtained

**OANDA v20 REST — cheapest, already built.** GBP_CHF and EUR_CHF are standard OANDA instruments on the same practice endpoint the existing `multi_timeframe_ingest` already pulls. No new vendor, no licence, no schema change beyond a `dim_asset` row. Backfill cost: ~130k H1 bars per pair to 2006, same as the Wave-1 pair jobs; run overnight against rate limits. (If OANDA history for these crosses proved thin pre-2010, Dukascopy tick data is the usual fallback vendor — but check OANDA coverage first; there is no reason to expect a problem for CHF crosses.)

## Recommended integration

1. Insert `dim_asset` rows: `(symbol='GBP_CHF', market_type='Forex', is_active=true)` and `(symbol='EUR_CHF', market_type='Forex', is_active=true)` — pip conventions are standard (0.0001), so `calculate_pips`/`get_pip_value` need no changes.
2. `python -m src.system1.ingestion.multi_timeframe_ingest --symbol GBP_CHF` then `--symbol EUR_CHF` (resumable via `ON CONFLICT`; overnight).
3. Verify with the coverage query (H1/H4/D1 to ~2006, current to ingest date) before enabling the cells.
4. No SPEC change is required: the strategy already declares both pairs; the harness skips pairs with insufficient history and picks them up automatically once the backfill lands.

## Impact if we proceed without it

The backtest runs on 10 cells (5 live + 5 Wave-1 pending) instead of 12. What is measured is unchanged in kind — pooled and per-cell r-multiples of the same mechanical system — just over fewer cells. Two honest caveats: (a) the author's 2009-2010 evidence base included these pairs, so pooled results are not directly comparable to the author's log on coverage grounds (they are already non-comparable on exit-rule grounds, see SPEC §10 row 5); (b) CHF crosses post-2015 are lower-volatility and range-prone, so the missing cells plausibly biased toward the harder end — proceeding without them, if anything, mildly flatters the pooled result, which the report should note. The result remains fully informative for a gate decision.
