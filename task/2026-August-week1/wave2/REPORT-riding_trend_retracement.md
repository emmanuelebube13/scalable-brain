# REPORT-riding_trend_retracement

## Implemented
A multi-timeframe trend continuation strategy. It uses the D1 chart (specifically a 50 EMA and MACD > 0 condition) to define the macro trend, and looks for temporary retracements on the H4 chart into a dynamic support zone (the H4 50 EMA). If price touches the H4 50 EMA while the D1 trend remains intact, it enters at market in the direction of the macro trend. The stop loss is a tight fixed 50 pips, and it targets a massive 4.0R (200 pips).

## Deviations
None. The multi-timeframe construction was implemented rigorously. D1 data is causally merged into the H4 simulation frame using `merge_asof` to guarantee that the H4 entry bar only ever sees the D1 EMA and MACD states from the previously closed daily bar, preventing lookahead bias.

## Uncertainties
- **Infrequent Setup**: Requiring price to be above a D1 EMA *and* pulling back to touch an H4 EMA creates a very specific geometric constraint. If the trend is too strong, the H4 EMA is never touched; if too weak, the D1 EMA fails. This resulted in an extremely low trade count.
- **Stop Geometry**: A fixed 50-pip stop across all pairs completely ignores individual pair volatility (ADR).

## Coverage
- **Pairs requested**: EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD
- **Pairs declared**: EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD
- **Pairs missing**: None
- **Pairs skipped by harness**: None. All 5 pairs were run.

## Verdict
FAIL (0.57 PF). The strategy fired only 40 OOS trades across 5 pairs over 10 years, which is barely enough to evaluate. However, the performance on those 40 trades was highly negative (20% win rate, -0.55 Sharpe). The fixed 50-pip stop is likely too tight for H4 swing trades, causing the strategy to get chopped out by intraday noise before the macro trend can resume towards the ambitious 200-pip target.
