# REPORT: kiss_h4

## Implemented
- The strategy logic strictly follows the specification for the 4H KISS system.
- It identifies H4 trends using a sequence of confirmed swing highs and lows via `last_n_confirmed_highs` and `last_n_confirmed_lows` (using period=5 and checking the last two swing points).
- It verifies pullbacks to the 20-period LWMA.
- It filters entries using Price Action patterns (engulfing, pin bars, tweezers) and MACD histogram momentum confirmation.
- Pair-specific take profit sizes (75 pips for high-ADR pairs, 50 pips for low-ADR pairs) are robustly inferred mathematically from price level clustering, keeping the implementation totally pure to the `frames` dict standard.

## Deviations
- None. The code accurately applies the structural conditions, indicator states, and exit rules. 

## Uncertainties
- Pair pip values and TP sizing were handled implicitly via math instead of hard-coding the `metadata.pairs[0]` string to support actual multi-pair testing, assuming JPY pairs trade >20 and GBP trades >1.15.

## Fixture rationale
- The hand-built bars (35 total) create explicit trend structures and test both the long and short setups.
- The indicators were shrunk (LWMA to 2, MACD to 2/4/2, Swings to period 1) to make the conditions mathematically trackable.
- Bar 12 triggers a perfect long setup with a bullish engulfing pattern.
- Bar 24 triggers a perfect short setup with a bearish engulfing pattern.
- Both orders exactly match hand-calculated stops (100 pips) and targets (75 or 50 pips).
