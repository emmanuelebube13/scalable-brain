# REPORT: inside_bar_pinbar_combo

## Implemented
- The strategy logic strictly follows the specification for a two-bar exhaustion sequence (inside bar followed by a pin bar).
- Bullish setup requires closing below EMA50, bearish setup requires closing above EMA50.
- All limit orders are set up properly: `buy_limit` is placed below the current bar's close, and `sell_limit` is placed above the current bar's close.
- Support and resistance levels use the `last_n_confirmed_highs` and `last_n_confirmed_lows` functions, checking for recency up to 250 bars and at a max distance of `0.25 * ATR(14)`.
- TP is set at the nearest opposing confirmed swing level, and the order is skipped if no TP level is available. 

## Deviations
- None. The code faithfully applies the detailed criteria established in the specification.

## Uncertainties
- No major ambiguities encountered beyond those already addressed in the specification.

## Fixture rationale
- The hand-built bars (34 bars total) set up a clear environment to warm up the EMA(5), ATR(5), and swing confirmation (period=2) mechanics, scaled down for the fixture scope.
- They simulate a solid downtrend and a bounce, establishing a confirmed swing low (support) and swing high (resistance).
- A valid bullish pin bar setup is produced at bar 19 touching the established support, generating a single `buy_limit` order with TP1 set exactly at the previous swing high.
- Afterwards, a bearish pin bar setup is produced at bar 28 touching the established resistance, generating a `sell_limit` order with TP1 set exactly at the previous swing low.
- These bars test both long and short order logic under the exact condition bounds required by the strict inequalities (e.g. 60% tail rejection limit).
