# DATA-GAP-double_bottom_measured_move

## Recommendation

**Implement now with reduced coverage; add AUD_CAD to the Wave-1 overnight backfill as a cheap opportunistic extra, but do not block Wave 2 on it.** Reasoning, in order:

1. **AUD_CAD is a documented example, not the instrument universe.** The strategy's `target_pairs` is "FX pairs - majors and crosses (GBP/JPY|AUD/CAD examples on page)" — the pair universe is generic; GBP/JPY and AUD/CAD are the page's two worked chart examples. The backtest is fully informative on the 13-pair universe (5 live + 8 Wave-1 pending, which already includes GBP_JPY, the other documented example).
2. **Adding it is near-free if the operator chooses to.** AUD_CAD is a standard OANDA v20 instrument on the same practice feed; it is one more `dim_asset` row and one more symbol on the already-planned overnight Wave-1 ingest (~130k H1 bars). The only reason it is a gap at all is that the CSV's aggregate demand table ranked it below the cut — only this row names it.
3. **Do not proxy it.** No synthetic AUD_CAD built from AUD_USD × USD_CAD, and no silent substitution of AUD_USD or USD_CAD alone. A proxy backtest would measure a different series (fabricated spreads, gaps, and session alignment) and attribute the result to this strategy. If the operator declines the extra ingest, proceed on 13 pairs and record AUD_CAD as untested — a stated omission, not a fabricated cell.

## What is missing

- **Pair:** AUD_CAD. Absent from the 5 live `dim_asset` pairs AND absent from the 8 Wave-1 additions (GBP_JPY · EUR_JPY · NZD_USD · USD_CHF · EUR_GBP · EUR_AUD · AUD_NZD · EUR_CAD) — a genuine gap, not a pending item.
- **Granularity:** D1 for decisions, H1 for fill resolution — the standard granularities the pipeline already produces; nothing exotic.
- **External series:** none. The row's `data_requirements` is "OHLCV only (swing-point pattern recognition)". No rates, calendar, COT, or real-volume requirement.

## Why the strategy needs it

- `target_pairs` (verbatim): `FX pairs - majors and crosses (GBP/JPY|AUD/CAD examples on page)`
- `risk_management` (verbatim): `... worked examples: GBP/JPY +774 pips, AUD/CAD +597 pips`

AUD/CAD carries one of the only two concrete performance datapoints the source offers (the +597-pip worked example). Without the pair, that example cannot be reproduced or refuted on our own data — the only pair-level evidence check this row allows is halved. The strategy itself, however, is pair-generic; nothing in the entry, exit, or filter logic is AUD/CAD-specific.

## How it could be obtained

- **OANDA v20 REST (cheapest, already built):** AUD_CAD is a standard OANDA instrument. The Wave-1 pair-addition procedure applies unchanged — recommended path if the operator wants the example pair covered.
- **Another vendor:** unnecessary; no licence or cost case to make while OANDA serves the pair.
- **Derivable from existing data:** **No** — explicitly rejected. AUD/CAD ≈ AUD_USD × USD_CAD is arithmetically constructible from two live pairs, but the synthetic series would have fabricated spreads (sum of two legs' spreads), misaligned gaps and session boundaries, and no real fillable quotes; every fill, stop, and measured-move outcome on it would be invented. Rejected per the no-invented-data rule.

## Recommended integration

Identical to the Wave-1 pair procedure (CONTRACT §7):

1. Insert `dim_asset` row: symbol `AUD_CAD`, `market_type='Forex'`, `is_active=true`.
2. Backfill: `python -m src.system1.ingestion.multi_timeframe_ingest --symbol AUD_CAD` — fold into the same overnight run as the eight Wave-1 pairs. Resumable (`ON CONFLICT` + resume from `MAX(timestamp)`); expect ~130k H1 bars back to 2006.
3. Verify with the standard coverage query before Wave 2 runs; the harness skips pairs with insufficient history rather than failing, so a half-landed backfill degrades gracefully to "no result".
4. Pip convention check: assert `calculate_pips()` / `get_pip_value()` handle AUD_CAD with the standard 4-decimal (0.0001) pip — no JPY involvement, so this should be the default path, but Wave 1 should assert it for the new row rather than assume.

## Impact if we proceed without it

The strategy runs on 13 pairs instead of 14; the backtest measures the same rules on a slightly smaller cross-section. **The loss is evidential, not structural:** we forgo the ability to reproduce the source's +597-pip AUD/CAD worked example on our own data, which is one of only two concrete claims in the row (the GBP/JPY +774-pip example remains testable once the Wave-1 GBP_JPY backfill lands). Given the strategy's pair-generic logic and the fact that the author's conviction rests on worked examples rather than a statistical sample anyway, proceeding without AUD_CAD is still informative — the pooled 13-pair OOS gates are the verdict that matters, and one additional mid-liquidity cross would not change a pooled pass/fail except at the margin. If the ingest is declined, the report must list AUD_CAD as an untested documented-example pair, not silently drop it from the requested-universe accounting.
