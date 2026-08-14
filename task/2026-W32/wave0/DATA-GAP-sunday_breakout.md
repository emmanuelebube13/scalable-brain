# DATA-GAP-sunday_breakout

## Recommendation

**Implement now with reduced coverage.** Run the strategy on GBP_USD immediately (all required granularities exist back to 2006). Treat EUR_JPY as a declared-but-skippable cell until the Wave 1 backfill is verified, and cap any analysis window at the last date for which weekly ATR is honestly knowable from the stale W1 feed (see below) unless the Wave 1 W1 refresh lands first. Neither gap blocks the build; both cap its coverage.

## What is missing

1. **EUR_JPY price data.** One of the two pairs the strategy names. `dim_asset` currently holds only EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD. EUR_JPY is on the Wave 1 addition list, but its backfill is "an overnight operator job and may not be complete when Wave 2 runs" (DATA_AVAILABILITY.md).
2. **Current W1 bars.** W1's last bar is 2026-06-12, stale ~8 weeks against H1/H4/D1 data that runs to 2026-08-07. The refresh is pending (Wave 1, agent G).

## Why the strategy needs it

- CSV `target_pairs`: **"GBP/USD | EUR/JPY"** — half the requested coverage is EUR/JPY, and the source author traded exactly these two pairs live (GBP/USD primary, EUR/JPY with a variant rule set; see SPEC §10.7).
- CSV `data_requirements`: **"weekly ATR(14)"** — the take-profit distance is ½ × weekly ATR(14) (CSV `exit_logic`). The ATR is computed from W1 bars, causally aligned so that only fully completed weeks enter (SPEC §3). With W1 ending 2026-06-12, every trading week after mid-June 2026 lacks the completed W1 bars its decision requires; signals in the last ~8 weeks of H1/H4 history cannot compute an honest TP level and must be dropped, not proxied with stale ATR values.

## How it could be obtained

- **EUR_JPY:** the Wave 1 procedure already specified in the contract (Part F): insert the `dim_asset` row (`market_type='Forex'`, `is_active=true`), then `python -m src.system1.ingestion.multi_timeframe_ingest --symbol EUR_JPY`. Ingest is resumable; ~130k H1 bars back to 2006 against OANDA practice rate limits; overnight job. Verify with the coverage query before enabling the cell.
- **W1 refresh:** `python -m src.system1.ingestion.multi_timeframe_ingest --granularity W1`, plus the already-mandated investigation of why the Saturday cron stalled. Both items are Wave 1 scope; nothing new is being requested here — this note exists so the dependency is visible on this strategy's critical path.

## Recommended integration (concrete)

1. Declare `pairs = [GBP_USD, EUR_JPY]` in the strategy metadata exactly as the CSV requests; rely on the documented harness behaviour of skipping pairs with insufficient history rather than failing.
2. Before any run, compute the ATR-knowability horizon: the latest decision bar allowed is the last Sunday candle whose preceding 14 completed W1 bars all exist. With W1 at 2026-06-12, the analysis window ends in mid-June 2026; do not pad with stale ATR values (that would silently change the TP distance and inflate/deflate r-multiples).
3. When Wave 1 reports EUR_JPY coverage verified and W1 refreshed, re-run with no spec change — the spec is already written for both pairs and current W1.
4. In the report, state per-cell coverage explicitly: which pairs ran, and the date range actually evaluated versus requested.

## Impact if we proceed without it

- **EUR_JPY absent:** results cover GBP_USD only — the pair the author primarily traded, so the core hypothesis is still tested. Lost: the second cell, any cross-pair dispersion read (Contract Part G), and validation of the author's two-pair live claim. Acceptable for Wave 2; must be labelled single-pair in the report.
- **W1 stale:** the evaluation window loses its most recent ~8 weeks. For a walk-forward backtest spanning 2006–2026 this trims only the tail of the final fold; material impact is low, but the fold report must flag the truncation (F11-style) rather than presenting a shortened window as full coverage. If the strategy were ever considered for live/paper forwarding, stale W1 would be a hard blocker — the TP distance would be computed from 2-month-old volatility.
- **No silent proxies:** no substitute pair (e.g., GBP_JPY as "close to EUR/JPY") and no ATR substitution (e.g., D1 ATR × √5) is permitted; both would change the strategy being measured.
