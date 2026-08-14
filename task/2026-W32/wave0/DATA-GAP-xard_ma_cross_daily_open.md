# DATA-GAP-xard_ma_cross_daily_open

## Recommendation

**Implement now with reduced coverage (FX pairs only); do not chase XAU_USD.** Gold is one of the strategy's two named instrument classes, but XAU_USD is *deliberately excluded* from this platform — it is not Forex, and `calculate_pips()`, pip values, and margin conventions all assume FX pairs. Half-supporting gold would corrupt the r-multiple accounting that every gate consumes. The MA-cross + daily-open core of the strategy is instrument-agnostic, so the 13 FX pairs (5 live, 8 Wave-1 pending) give a fully informative backtest of the documented rules. Revisit gold only if and when the platform adopts a non-FX asset class with its own pip/margin conventions — that is a platform decision, not a strategy-level one.

## What is missing

- **Pair:** XAU_USD ("Gold"), named verbatim in `target_pairs` as `Majors and minors|Gold`.
- Not missing: any granularity (H1 suffices — the daily open and ADR are derivable from H1 bars at the 21:00 UTC boundary), and any external series (no rates/calendar/COT/volume requirements in this row).

## Why the strategy needs it

The CSV's `target_pairs` field reads: `Majors and minors|Gold`. The XARD system family was built and demonstrated by its author heavily on gold charts; gold is a first-class instrument in the source thread, not an incidental mention. Excluding it removes one of the two instrument classes the system was designed for.

## How it could be obtained

- **OANDA v20 REST (cheapest, already built):** XAU_USD is a standard OANDA instrument; the existing ingest pipeline could pull it with one additional symbol — the *data* is trivially obtainable.
- **The blocker is not data, it is conventions:** the platform's pip-value, margin, and r-multiple conventions assume FX (DATA_AVAILABILITY.md states XAU_USD is "excluded on purpose"). Supporting gold requires a `dim_asset` market_type decision ('Metals'), a pip-size convention for XAU (e.g. 0.1 or 0.01 per "pip"), and a margin model — changes to shared infrastructure that are out of scope for this strategy and must not be made as a side effect.
- **Derivable from existing data:** no. Gold prices cannot be synthesised from FX pairs.

## Recommended integration

None now. If the platform ever adopts metals:

1. Decide the pip/margin convention for XAU_USD (platform-level, System-3 input needed).
2. Insert `dim_asset` row: symbol `XAU_USD`, `market_type='Metals'`, `is_active=true`.
3. Backfill: `python -m src.system1.ingestion.multi_timeframe_ingest --symbol XAU_USD` (H1, H4, D1; resumable, ~130k H1 bars).
4. Note: gold's trading day/session break differs from the FX 21:00 UTC convention (gold has a daily settlement break ~21:00–22:00 UTC); the spec's 21:00 UTC day-boundary definition for the daily open and ADR would need a per-asset review before results on gold are comparable to the FX cells.

## Impact if we proceed without it

The backtest measures the strategy's documented MA-cross + daily-open rules on FX only. This is still informative: the entry/exit mechanics are price-series-agnostic, and 13 FX pairs provide a far larger statistical sample than one metal would. The loss is external validity for the author's original use case — if the system's edge was concentrated in gold's trend character (deep intraday trends, wide ADR), the FX result will understate (or simply misrepresent) the author's lived experience with the system. That caveat is stated in SPEC §11. Proceeding without gold is the correct trade: a clean 13-pair FX answer now beats a contaminated cross-asset answer built on FX-assumption accounting.
