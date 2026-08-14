# DATA-GAP-nzdjpy_median_ma_retrace

## Recommendation

**Defer the backtest until NZD_JPY data lands; implement the Wave-2 spec now; drop the strategy rather than proxy it if the ingest is declined.** Reasoning, in order:

1. **"Implement now with reduced coverage" is impossible here.** The strategy names exactly one pair, and that pair is missing. Reduced coverage equals zero pairs equals no backtest at all. The spec itself is complete and Wave-2-ready (no interpretive decisions remain), so the code can be written in Wave 2 regardless; only the run is blocked.
2. **Deferral is cheap.** NZD_JPY is a standard OANDA v20 instrument and the ingest pipeline already exists; adding it is one `dim_asset` row plus one more symbol on the already-planned overnight Wave-1 backfill job (~130k H1 bars). Marginal cost is near zero.
3. **Drop is the fallback, and it is a live option.** The CSV itself carries the warnings: curve-fit to a single pair, reward:risk below 1:1 (0.4% TP vs 0.5% SL) resting on an unverified high win rate, and supporting evidence that exists only as chart images. If the operator judges one extra overnight symbol not worth the maintenance surface for a single MODERATE-conviction strategy, dropping loses little. What must **not** happen is silent substitution of NZD_USD or GBP_JPY (SPEC §10 #7) — a proxy backtest would measure a different strategy and attribute the result to this one.

## What is missing

- **Pair:** NZD_JPY (`target_pairs` reads, verbatim: `NZD/JPY`). It is absent from the 5 live `dim_asset` pairs **and** absent from the 8 Wave-1 additions — a genuine gap, not a pending item.
- **Granularity:** H1 only — the standard granularity the pipeline already produces; nothing exotic.
- **External series:** none. The strategy needs H1 OHLC only (median price and session clock are derivable from OHLCV + timestamps). No rates, calendar, COT, or real-volume requirement exists in this row.

## Why the strategy needs it

- `target_pairs`: `NZD/JPY`
- `data_requirements`: `H1 OHLCV | MA(5) and MA(50) computed on median price (H+L)/2 | round-hour timestamp filter 07:00-13:00 London`

The strategy is single-pair by design ("single-pair specialization", `risk_management` field); the pair is not one ingredient among several, it is the entire instrument universe.

## How it could be obtained

- **OANDA v20 REST (cheapest, already built):** NZD_JPY is a standard OANDA instrument on the same practice feed the existing pairs come from. The Wave-1 pair-addition procedure applies unchanged — this is the recommended path.
- **Another vendor:** unnecessary; no licence or cost case to make while OANDA serves the pair.
- **Derivable from existing data:** **No.** A synthetic NZD_JPY cross built as NZD_USD × USD_JPY would require NZD_USD (itself only Wave-1 pending) and would produce a synthetic series whose spreads, gaps, and timestamp alignment do not match a real tradable cross; fills and the round-hour session behaviour would be fabricated. Rejected explicitly.

## Recommended integration

Identical to the Wave-1 pair procedure (CONTRACT §7):

1. Insert `dim_asset` row: symbol `NZD_JPY`, `market_type='Forex'`, `is_active=true`.
2. Backfill: `python -m src.system1.ingestion.multi_timeframe_ingest --symbol NZD_JPY` (H1 suffices for this strategy; H4/D1 come along with the standard job). Resumable (`ON CONFLICT` + resume from `MAX(timestamp)`); expect ~130k H1 bars back to 2006 — fold it into the same overnight run as the eight Wave-1 pairs.
3. Verify coverage with the standard coverage query before Wave 2 runs the strategy; the harness skips pairs with insufficient history rather than failing, so a half-landed backfill degrades gracefully to "no result" rather than a wrong one.
4. JPY pip convention check: `calculate_pips()` / `get_pip_value()` must use the 0.01 JPY pip for NZD_JPY. USD_JPY is live, so the JPY convention presumably already exists — Wave 1 should assert it explicitly for the new cross rather than assume.

## Impact if we proceed without it

There is **no partial backtest**: the strategy has one pair, so without NZD_JPY it simply does not run, and the correct outcome is an empty result with this gap note attached — not a proxy result. The informative-loss calculation is: we forgo testing whether a session-filtered median-MA retrace signal on a thin JPY cross can sustain the ~57–58% net win rate its negative-RR bracket demands (SPEC §11). Given the strategy's self-declared curve-fit risk and image-only evidence, that is a tolerable loss.

One caveat that survives **even if the data lands** (also flagged in SPEC §8 and §10 #6): the mandated cost model (F10: 1.0-pip spread, 0.5-pip entry slippage) is the only spread series that exists, and real NZD/JPY retail spreads are typically 1.5–3 pips. Against a ~35-pip TP, each understated spread pip is ~3% of the target. Results for this pair will carry an optimistic cost bias that must be stated in the report; it cannot be fixed at strategy level because F10's constants are mandated for cross-strategy comparability.
