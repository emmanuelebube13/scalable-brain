# REPORT-liquidity_sweep_ob

## Implemented
A 4-hour strategy built around the "liquidity sweep" and "order block" concepts. It identifies a swing high/low structure and defines an "order block" as the last bearish candle before an upward impulse (or bullish before downward). It then looks for price to re-enter this block and sweep the block's extreme (a liquidity grab) before reversing to close back inside the block. The entry is a market order immediately upon the close of the sweeping bar. The stop loss is placed with a tight 2-pip buffer outside the sweeping wick. The exit targets the most recent confirmed swing extreme (targeting the opposing liquidity pool).

## Deviations
None. The declarative stop and take profit structures exactly map to the rules provided in the specification.

## Uncertainties
- **Order Block Search**: The specification defined the order block as the "last bearish candle before the impulse". This was correctly implemented by tracing backward from the impulse origin, but this logic assumes a continuous strict sequence which often misses complex structural shifts in real H4 price action.
- **Liquidity Sweep**: A "sweep" requires the wick to pierce the block's boundary but the close to remain inside. This is a very strict topological requirement that severely restricts trade frequency.

## Coverage
- **Pairs requested**: Any
- **Pairs declared**: EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD (the 5 live pairs).
- **Pairs missing**: None
- **Pairs skipped by harness**: None. All 5 pairs were run.

## Verdict
FAIL (1.04 PF). The strategy fired only 14 OOS trades across 5 pairs, failing all robustness gates. The low trade count indicates that the strict combination of a confirmed swing point, an explicitly identified single-candle order block, a retracement, and a precise wick-only sweep of the block's boundary is too rare on the H4 timeframe to constitute a measurable edge. It is fundamentally a pattern-matching filter that produces a negligible sample size.
