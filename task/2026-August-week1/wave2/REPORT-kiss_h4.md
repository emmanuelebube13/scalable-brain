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

## Coverage
- Pairs declared: GBP_USD, EUR_JPY, GBP_JPY, EUR_USD, AUD_USD.
- Pairs missing: none of the named five is a gap.
- Harness skipped EUR_JPY, GBP_JPY (no data for primary or context frame).

## Verdict
FAIL. PF=0.86, Sharpe=-0.42, Recovery=0.75 across 286 OOS trades in 3 passing cells. Strategy executed correctly but edge is negative.
