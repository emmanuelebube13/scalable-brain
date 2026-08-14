# DATA-GAP-ma_crossover_swing

## Recommendation

**Implement now with reduced coverage** — run the strategy on the three live FX pairs it names (EUR_USD, GBP_USD, USD_JPY) and record XAU_USD as excluded. XAU_USD is a **deliberate policy exclusion, not a missing feed**: gold is not Forex, and the system's pip-value, margin, and `calculate_pips()` conventions all assume FX pairs (CONTRACT §7; DATA_AVAILABILITY). Adding it would require changes to shared infrastructure far beyond this strategy, and the strategy loses nothing essential without it — it is explicitly "asset-agnostic" MA-cross logic that three liquid majors exercise fully. Do not defer and do not drop.

## What is missing

- **Pair:** XAU_USD (spot gold vs USD) — named in the row's `target_pairs`. No granularity of XAU_USD exists in `fact_market_prices`, and none is planned in Wave 1.
- Everything else the strategy needs (D1/H4/H1 OHLCV for the three FX pairs, EMA/SMA/MACD/ATR inputs) is present and current.

## Why the strategy needs it

The CSV's `target_pairs` field reads: `EURUSD|GBPUSD|USDJPY|XAUUSD|asset-agnostic, applies to FX majors`. Gold is one of four explicitly named instruments — the author's published demo traded equities/ETFs and metals-style instruments, so XAUUSD was part of the intended validation universe. However, the immediately following clause ("asset-agnostic, applies to FX majors") shows the author regards the logic as instrument-independent; gold is illustrative, not load-bearing.

## How it could be obtained

- **Not obtainable under current conventions** — this is the honest answer. OANDA v20 REST *does* serve XAU_USD candles (the ingest path already built could fetch it at zero development cost), but the exclusion is a system-design decision, not a data-access problem: `calculate_pips()`, pip values, and margin assumptions in the shared codebase are hard-coded to FX conventions. Half-supporting gold would silently mis-price every trade.
- To support it properly (a future initiative, not this wave): add a `market_type='Metals'` asset class with metal-specific `pip_size`/`pip_value` (e.g. 0.01 or 0.1 USD per ounce conventions) and margin handling, insert a `dim_asset` row, then run the standard ingest: `python -m src.system1.ingestion.multi_timeframe_ingest --symbol XAU_USD`. That is a shared-infrastructure change with its own review, and should not be smuggled in as a side effect of one research strategy.

## Recommended integration

None for Wave 1/2. Declare `pairs_available = [EUR_USD, GBP_USD, USD_JPY]` in the strategy metadata and note the XAU_USD exclusion in the report header, so the coverage gap is visible rather than silent. If a metals asset class is ever built, this strategy requires no spec change to pick it up — its logic is instrument-agnostic.

## Impact if we proceed without it

The backtest measures the MA-cross-with-confirmation edge on three FX majors only. That is still fully informative for the strategy's stated hypothesis: the logic has no gold-specific component (no session, no safe-haven flow, no DXY input), and EUR_USD / GBP_USD / USD_JPY span the major USD regimes. The only loss is breadth of evidence — a pass on three FX pairs is weaker corroboration of the "asset-agnostic" claim than a pass on three pairs plus gold would have been, and the report should say exactly that rather than over-claiming instrument independence.
