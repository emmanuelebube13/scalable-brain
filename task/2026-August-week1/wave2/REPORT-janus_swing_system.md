# REPORT: janus_swing_system

## Implemented
- Daily (D1) granularity swing trading system.
- The entry is triggered by a retracement to the midpoint of the signal bar.
- LONG conditions: `at_support` (price close to recent swing low), `three_down` (3 consecutive lower closes), and `bullish_straight` (strong bullish bar closing in upper half, opened in lower half).
- SHORT conditions: `at_resistance` (price close to recent swing high), `three_up` (3 consecutive higher closes), and `bearish_straight` (strong bearish bar closing in lower half, opened in upper half).
- `OrderIntent` uses a limit entry at the exact midpoint (`mid_t = (H_t + L_t) / 2.0`), with stops placed 5 pips beyond the signal bar's extreme.
- Exit is a pure trailing stop based on the pip distance of the initial risk.
- Spacing mechanism implemented (`(i - last_emission_idx) >= 4`) to prevent clustering of signals.

## Deviations
- None.

## Uncertainties
- Used `SWING_PERIOD = 5` and `n=1` in `last_n_confirmed_lows` and `last_n_confirmed_highs` to match the concept of a "recent swing low/high".

## Fixture rationale
- The hand-built bars (30 total) trace out the precise setup for both LONG and SHORT.
- The indicator was scaled (`SWING_PERIOD = 1`) to make the test compact.
- The LONG setup triggers at bar 12 with a `buy_limit` exactly at the midpoint of bar 12 (1.1930).
- The SHORT setup triggers at bar 24 with a `sell_limit` exactly at the midpoint of bar 24 (1.2070).
- The test verifies that all orders, limits, stops, and trailing exits trigger with precise expected values.
