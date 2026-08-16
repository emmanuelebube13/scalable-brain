# REPORT-three_candle_swing_reversal

## Implemented
A daily reversion strategy based on a very strict 3-candle structural pattern. A valid swing high consists of a candle making a higher high than the prior candle, followed immediately by a candle making a lower high. A valid swing low is the inverse. The strategy trades on the close of the 3rd candle if the sequence forms a confirmed 3-candle extreme. A fixed 1.5R exit target is used, and the stop is placed precisely at the structural extreme (the High/Low of the middle candle) with no buffer.

## Deviations
None. The code maps exactly to the mechanical description of the 3-candle pattern.

## Uncertainties
- **Pattern Exactness**: The strategy demands exactly 3 candles forming the extreme (a one-bar up, one-bar down V-shape). Most swing points in Forex are more complex, requiring multiple bars to round off a top or bottom. This restricts the entry count severely.
- **Stop Buffer**: The specification stated placing the stop "at the high/low of the middle candle", which implies zero buffer. It was implemented exactly with 0 pips of buffer.

## Coverage
- **Pairs requested**: EUR_USD, USD_CAD, USD_JPY
- **Pairs declared**: EUR_USD, USD_CAD, USD_JPY
- **Pairs missing**: None
- **Pairs skipped by harness**: None. All 3 pairs were run.

## Verdict
FAIL (0.68 PF). The strategy fired only 12 OOS trades across 3 pairs, logging a LOW_CONFIDENCE failure. The strict requirement for a textbook 3-bar "V" top/bottom on daily charts is too rare, filtering out almost all potential setups. When it did trade, placing stops exactly on the extreme with zero buffer resulted in poor performance, as normal daily volatility frequently swept the unbuffered structural points before reversing.
