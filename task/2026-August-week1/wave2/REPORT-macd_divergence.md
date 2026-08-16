# REPORT-macd_divergence

## Implemented
A single-timeframe H4 divergence strategy using the MACD line and confirmed price swing lows/highs. It enters at market (fill on open) when a divergence is confirmed and price breaks the confirmation bar's extreme. The stop is structural, placed at the divergence swing low/high itself. A single take-profit leg is set at the next confirmed swing resistance/support level.

## Deviations
None. The code matches the conservative reading of the spec exactly.

## Uncertainties
- **Entry bar timing:** The source does not define the exact entry bar. Chosen to require 5-bar confirmation of the swing plus a trigger close, which is conservative but introduces a minimum 7-bar lag.
- **MACD confirmation:** MACD is sampled at the two price swing bars rather than waiting for MACD to form its own confirmed swings, which would add even more lag.
- **Both MACD extrema sign:** Required both MACD lows to be < 0 for longs (bearish momentum) and > 0 for shorts, enforcing a stricter setup.
- **Opposite signal exit:** Contract v2 cannot express "close open position if an opposite signal forms". Open trades run to stop or TP.

## Coverage
- **Pairs requested:** "Any currency pair"
- **Pairs declared:** EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD (the 5 live pairs).
- **Pairs missing:** None explicitly requested.
- **Pairs skipped by harness:** None. All 5 declared pairs were evaluated.

## Verdict
FAIL (1.096 PF). The strategy fired 441 OOS trades across the 5 pairs but failed to clear the gates, primarily due to a low profit factor (1.10 < 1.50) and low Sharpe (0.16 < 0.80). The significant confirmation lag (7+ H4 bars) likely cedes too much of the initial reversal impulse to achieve the required expectancy.
