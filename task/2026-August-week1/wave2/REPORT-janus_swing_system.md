# REPORT: janus_swing_system

## Implemented
- The strategy logic strictly follows the specification for the Forex Swing System.
- It identifies D1 entry setups using a "straight bar" confirmation after 3 strictly consecutive counter-trend days.
- It mechanically requires the signal bar to touch within 10 pips of the most recent confirmed swing low/high (using period=5 and 5-bar lag).
- The re-emission guard (1 signal per 4 D1 bars per pair) is correctly implemented.
- The trailing exit leg correctly trails at exactly the initial risk distance in pips.

## Deviations
- None. The code accurately applies the structural conditions, indicator states, and exit rules.

## Uncertainties
- Discretionary S/R level selection was mechanized as a 10-pip band around a 5-bar-stale confirmed swing point, which drastically restricts the number of trades.

## Coverage
- Pairs declared: EUR_USD, EUR_CAD, EUR_AUD, EUR_JPY, AUD_USD, AUD_NZD, USD_CAD, GBP_USD, GBP_JPY, USD_JPY, NZD_USD.
- Pairs missing: none.
- Harness skipped EUR_CAD, EUR_AUD, EUR_JPY, AUD_NZD, GBP_JPY, NZD_USD (no data for primary or context frame).

## Verdict
INSUFFICIENT. 6 OOS trades across 5 cells. The strictness of the mechanized S/R check + trend precondition resulted in too few trades to establish a statistical edge.
