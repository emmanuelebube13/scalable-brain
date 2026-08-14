# DATA-GAP-mtf_swing_weekly_pivots

## Recommendation

**Implement now with reduced coverage (FX majors only).** The gap is incidental, not structural: every entry/exit rule in the source is defined on FX price action, the four explicitly named pairs (EURUSD, GBPUSD, USDJPY, AUDUSD) are all live in `fact_market_prices`, and USD_CAD covers the generic "FX majors" clause. Only the trailing "liquid indices" phrase is unfulfillable, and no rule depends on it. Deferring or dropping the strategy over this would discard a fully testable FX strategy for a catch-all instrument class the author never specified.

## What is missing

- **Instrument class: liquid stock/CFD indices** (e.g. US500, NAS100-type instruments — the source does not name specific ones). No index instrument exists in `dim_asset`; the five assets are all Forex, and the Wave-1 additions (GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD) are also all Forex.
- Nothing else: no granularity gap (H4 decision frame, D1 context, H1 fill resolution are all current), no external series gap (no rates/calendar/COT/VIX used), and no W1 dependency — the weekly pivot levels were dropped as non-load-bearing (SPEC §10 #3), so the stale W1 series is moot for this strategy.

## Why the strategy needs it

Only via the `target_pairs` field: `EURUSD|GBPUSD|USDJPY|AUDUSD|FX majors and liquid indices`. No entry, exit, or filter rule references any index; the phrase is a coverage wish, not a logic input.

## How it could be obtained

- **OANDA v20 REST (cheapest, already built):** OANDA practice accounts carry CFD indices (e.g. `SPX500_USD`, `NAS100_USD`, `US30_USD`). The existing `multi_timeframe_ingest` could fetch them with no new vendor code.
- **Caveat (the real blocker):** this project's pip-value, margin, and `calculate_pips()` conventions assume FX pairs (the same reason `XAU_USD` was deliberately excluded). Index CFDs have different pip/point definitions and contract sizes, so ingesting the prices is trivial but making the cost model and r-multiple arithmetic correct for them is a small design task, not a data task.

## Recommended integration

If index coverage is ever wanted: insert `dim_asset` rows with `market_type='IndexCFD'` (a new type — do **not** reuse `'Forex'`), extend `get_pip_value()`/`calculate_pips()` with per-instrument point definitions, then run `python -m src.system1.ingestion.multi_timeframe_ingest --symbol SPX500_USD` (etc.) per instrument. Until that convention work is scheduled, do nothing — the strategy is unaffected.

## Impact if we proceed without it

The backtest measures the strategy on five FX majors instead of "FX majors plus indices". All entry/exit logic is identical; the only loss is cross-asset-class diversification of the sample (fewer cells, and all cells share FX-specific regime behaviour such as central-bank-driven trends). That is still fully informative about the strategy's documented edge — the trend/pullback hypothesis is stated on FX charts in the source — and per-cell verdicts will honestly show FX-only coverage. If the strategy qualifies on FX, a later index extension is a pure data/convention task with no re-specification needed.
