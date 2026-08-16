# REPORT-long_wick_pinbar_8ema

## Implemented
A daily trend-following strategy that looks for pullbacks into the 8 EMA that are rejected via a long-wick pinbar. The trend is defined by the 8 EMA being above/below the 16 EMA, and the 8 EMA sloping in the trend direction over 2 bars. The pinbar must touch or cross the 8 EMA, and its wick must represent at least 2/3 of the entire candle range. Entries are placed as stop orders slightly past the high/low of the pinbar to confirm continuation. Stops are placed behind the pinbar's extreme with a 2-pip buffer. The exit is a fixed 2:1 Reward:Risk target.

## Deviations
None. The code exactly translates the mechanical specification described in the source.

## Uncertainties
- **EMA Trend Definition**: The source requested "8 EMA and 16 EMA sloped". The spec interpreted this as `EMA8[t] > EMA8[t-2]` for an uptrend.
- **Pinbar Geometry**: The source lacked precise ratios. The spec defined a "long wick" as the wick being ≥ 2/3 of the total High-Low range.
- **Entry Method**: The source stated "enter when price breaks pinbar high/low". This was implemented correctly as a `buy_stop` or `sell_stop` order placed at the pinbar's extreme + 2 pips, expiring if not triggered within the next daily bar.

## Coverage
- **Pairs requested**: EUR_USD, GBP_USD, AUD_USD (as specified in the prompt/spec).
- **Pairs declared**: EUR_USD, GBP_USD, AUD_USD
- **Pairs missing**: None
- **Pairs skipped by harness**: None. All 3 pairs were run.

## Verdict
FAIL (0.9296 PF). The strategy fired 98 OOS trades across the 3 pairs, failing the PF, Sharpe, and Win Rate gates. The 2:1 fixed reward/risk ratio on strict daily pinbars simply did not clear the hurdle, as daily pinbars at the 8 EMA frequently see price continue past the pinbar's extreme before reversing to stop out the trader, yielding a negative expectancy.
