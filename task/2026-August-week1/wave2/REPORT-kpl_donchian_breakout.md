# REPORT: kpl_donchian_breakout

## Implemented
- A daily (D1) trend-following system based on Donchian channel breakouts.
- The `warmup_bars` correctly uses the maximum of `DONCHIAN_PERIOD` (20) and `ATR_PERIOD` (14).
- The `generate_orders` function iterates over the bars, calculating `donchian_channel` (returning lower, middle, upper) and extracting `dcu_s` (shifted upper channel) and `dcl_s` (shifted lower channel).
- LONG condition: The current bar closes above the upper channel of the previous bar (`C_t > dcu_t`), while the previous bar closed below or equal to it.
- SHORT condition: The current bar closes below the lower channel of the previous bar (`C_t < dcl_t`), while the previous bar closed above or equal to it.
- Both entries use Market orders (`entry="market"`) with a stop placed 2 ATR from the close (`stop_price = C_t +/- 2.0 * atr_t`).
- The stop employs a volatility-based trailing stop via `trail_atr_multiple=2.0`.

## Deviations
- N/A.

## Uncertainties
- Discovered and corrected a potential bug where the subagent originally unpacked the Donchian channel results incorrectly. `indicators.donchian_channel` returns `(upper, middle, lower)`, so the correct unpacking `dcu, _, dcl = donchian_channel(...)` was implemented.

## Fixture rationale
- Shrunk `DONCHIAN_PERIOD` and `ATR_PERIOD` to 2.
- Created hand-crafted OHLC data (25 bars) with precise structural moves that yield exactly 2 orders (1 LONG, 1 SHORT).
- The setup creates artificial constraints to force false conditions in the initial bars and only validate when exactly met on specific indices (index 6 for LONG, 16 for SHORT).
- Verified stop distances with pytest tolerance assertions correctly scaled to match the hand-calculated ATR structure.
