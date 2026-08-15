# DATA-GAP-smash_days

## Recommendation
**Implement now with reduced coverage.** The strategy is fully specified and testable today on the 5 live pairs (AUD_USD, USD_CAD, EUR_USD, GBP_USD, USD_JPY), and coverage rises to 13 cells automatically as the 8 Wave-1 pair additions land. The two explicitly named pairs that are NOT in the Wave-1 plan (GBP_NZD, NZD_CHF) and the unnamed balance of the author's "28 leading pairs" should be treated as an optional later expansion, not a blocker: both named pairs are standard OANDA v20 instruments obtainable through the existing ingest pipeline with zero new engineering. Notably, running on the reduced universe has a genuine methodological upside — the OP himself warns that the setup double-counts correlated AUD/NZD themes when run across 28 pairs, and the current universe contains far fewer AUD/NZD crosses, so the reduced-coverage backtest is less exposed to the strategy's own known concentration defect. Do not defer; do not drop.

## What is missing
1. **Pairs:** GBP_NZD and NZD_CHF — explicitly named in `target_pairs` ("e.g. GBP/NZD | NZD/CHF | AUD/USD | USD/CAD") but absent from both the 5 live pairs and the 8 Wave-1 additions (GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD). Beyond these, the author runs the setup across "28 leading forex pairs"; only 13 of the conventional 28 majors/crosses are on the current plan, leaving roughly 15 further crosses (e.g. GBP_AUD, GBP_CAD, NZD_JPY, NZD_CAD, CHF_JPY, AUD_CHF, AUD_CAD, EUR_NZD, EUR_CHF, GBP_CHF …) uncovered.
2. **Granularity:** none. D1 is live and current (to 2026-08-06); H1 for fill resolution is current (to 2026-08-07).
3. **External series (secondary):** an economic-calendar / event feed, needed for the author's "avoids trading during extreme volatility/event risk" filter. No calendar, news, or sentiment data exists in the system. This filter has been **dropped** from the spec under the no-invented-data rule (SPEC §8, §10 #4) rather than proxied.

## Why the strategy needs it
- Pairs — `target_pairs`, verbatim: *"28 leading forex pairs (e.g. GBP/NZD | NZD/CHF | AUD/USD | USD/CAD)"*. A ~1–3 signals/month/pair setup is pair-count-hungry: on 5 pairs the pooled trade count may be thin for the gates; the author's design assumes breadth across 28 instruments.
- Calendar — `risk_management`, verbatim: *"avoids trading during extreme volatility/event risk"*. Without an event feed, signals that fire into known binary events (central-bank decisions, CPI) are taken in the backtest that the author would have skipped.

## How it could be obtained
1. **GBP_NZD, NZD_CHF (and any further crosses):** OANDA v20 REST — cheapest path, already built. Both are standard OANDA instruments on the practice feed the existing ingester already polls. Procedure is identical to the Wave-1 additions: insert `dim_asset` rows, run the resumable multi-timeframe ingest overnight.
2. **Economic calendar:** not obtainable from existing data and not derivable from OHLCV without changing the filter's meaning (a volatility proxy screens *realized* volatility, not *scheduled event* risk). If ever required, a third-party calendar API (e.g. Trading Economics or Finnhub economic-calendar endpoints; licence/cost per vendor, typically a paid tier for historical depth back to 2006) would be needed. **Recommendation: do not procure.** The filter is discretionary risk hygiene, not part of the edge; its absence is disclosed in the spec and biases the backtest toward *more* trades in event windows — visible, conservative-direction, and acceptable for a research verdict.
3. The remaining ~15 unnamed crosses: same OANDA route as (1), but low priority — the 13-cell universe already covers the most liquid pairs and avoids redundant AUD/NZD theme overlap.

## Recommended integration
For GBP_NZD and NZD_CHF, if approved:
1. Insert `dim_asset` rows: `symbol='GBP_NZD'`, `market_type='Forex'`, `is_active=true`; same for `NZD_CHF`.
2. Run: `python -m src.system1.ingestion.multi_timeframe_ingest --symbol GBP_NZD` (and likewise `NZD_CHF`) — the ingest is resumable (`ON CONFLICT ("timestamp", asset_id, granularity)`); expect ~130k H1 bars per pair of overnight backfill to 2006.
3. No schema change required. The smash_days spec already declares pairs via metadata; the harness skips pairs with insufficient history, so the strategy runs today and simply gains cells as pairs land. No strategy-code change will be needed.

## Impact if we proceed without it
- **Pairs:** the backtest measures the smash-day edge on the 5–13 most liquid USD-centric pairs instead of 28. That is still fully informative for the go/no-go question — the hypothesis (5-day exhaustion snapback) is not pair-specific, and EUR_USD/GBP_USD/USD_JPY are the deepest markets where such an edge should show first if it exists. What is lost is breadth-smoothing of the pooled result and the two explicitly named pairs; per-cell verdicts will make any pair-dependence visible. Trade-count risk is mitigated by ~20 years of D1 history (~5,900 bars/pair) and by the Wave-1 additions roughly tripling cell count.
- **Calendar filter:** the backtest takes signals into event windows that the author would skip. Direction of bias: more trades, likely slightly worse average outcome (event-window entries have gap-prone next sessions, and F3/F6 resolve those gaps adversely) — i.e. conservative for qualification purposes. Disclosed in SPEC §8 and §10 #4.
