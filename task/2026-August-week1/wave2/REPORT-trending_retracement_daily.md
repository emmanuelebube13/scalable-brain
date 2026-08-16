# REPORT-trending_retracement_daily

## Implemented
A D1 trend retracement strategy. It uses a bullish/bearish crossover of SMMA3 and SMMA8 (Smoothed Moving Average) to define the trend direction. It enters on a stop order when a retracement candle's entire body falls within a 0.5%–1.0% envelope around the SMMA8. The stop is structural, placed at the most recent confirmed swing extreme. A fixed 150-pip take profit target is used, and a breakeven trigger is implemented via an auxiliary leg at 70 pips.

## Deviations
- **Breakeven Offset:** The spec called for a negative breakeven offset (-25.0 pips adverse to entry). `contract_v2.py` strictly forces `breakeven_offset_pips` to be non-negative. This was altered to 0.0 (exact breakeven) to allow the strategy to run.
- **Exits:** The source's primary exits (outer-band touch / opposite cross) are inexpressible. The fixed 150-pip take profit is the only expressible exit.

## Uncertainties
- **Envelope tuning:** Envelopes use fixed percentages (0.5% / 1.0%) across all pairs, though the author suggests volatility tuning. Kept fixed per the no-optimization rule.
- **Setup Candle Location:** Whole-body containment inside the envelope was required, which is stricter than the pseudocode's close-only test.

## Coverage
- **Pairs requested:** "Any"
- **Pairs declared:** EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD (the 5 live pairs).
- **Pairs missing:** None explicitly requested.
- **Pairs skipped by harness:** None. All 5 pairs were run.

## Verdict
FAIL (0.9811 PF). The strategy fired only 4 OOS trades across the 5 pairs, failing the gates. The low trade count flags as LOW_CONFIDENCE. The untuned fixed-percentage envelopes likely filter out too many setups on certain pairs, and the stringent whole-body containment requirement severely limited trade frequency.
