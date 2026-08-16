# REPORT-smart_money_swing

## Implemented
A multi-timeframe swing strategy that uses weekly trend (EMA50 vs EMA200) and daily momentum (RSI > 50) as high-timeframe filters, executing on H4 price action. The entry mechanism is a "smart money" setup: it enters on the close of an H4 bar if it breaks above the highest high of the prior 9 bars (for longs), aligning with the HTF trend. The stop loss is anchored structurally to the lowest low of the 9-bar setup window, and exits are taken in halves at 1R and 2R.

## Deviations
None. All indicators, timeframes, and structural constraints map exactly to the provided specification. The strategy gracefully bypasses the engine's `TRAILING_LEG_UNSUPPORTED` limitation because it does not use a fractional trailing runner; instead, it uses a fixed 2-part exit (TP1, TP2) with a trailing StopRule, which is fully supported.

## Uncertainties
- **MTF Construction**: Calculating the W1 EMA cross and D1 RSI from within an H4 simulation frame requires exact causal grouping. We map the most recently closed W1 and D1 values using `merge_asof` to guarantee zero look-ahead bias during evaluation.

## Coverage
- **Pairs requested**: EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD
- **Pairs declared**: EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD
- **Pairs missing**: None
- **Pairs skipped by harness**: None. All 5 pairs were run.

## Verdict
FAIL (0.92 PF). The strategy fired 1246 OOS trades across 5 pairs. Despite rigorous multi-timeframe confirmation rules designed to ensure trades only fire in the direction of the "smart money" macro trend, the strategy exhibits negative expectancy. Buying H4 breakouts at the exact moment they exceed the 9-bar local extreme often results in buying the top of a micro-swing, causing immediate stop-outs as the market retraces back to its mean.
