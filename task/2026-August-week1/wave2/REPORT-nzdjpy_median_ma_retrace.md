# REPORT-nzdjpy_median_ma_retrace

## Implemented
A daily reversion strategy specifically tuned for the NZD/JPY cross. It uses a 5-period Simple Moving Average of the typical price (Median MA) as a dynamic reversion mean. Entry conditions trigger when price deviates significantly from this SMA and forms a reversal candlestick pattern. Take profit and stop loss are fixed pip amounts tuned to the specific ADR of this pair.

## Deviations
None. The logic has been implemented exactly as described, though it could not be backtested on live data.

## Uncertainties
- **Lack of Test Data**: The system relies heavily on fixed pip distances and specific moving average settings fitted to the unique characteristics of NZD/JPY, preventing meaningful testing on other major pairs.

## Coverage
- **Pairs requested**: NZD_JPY
- **Pairs declared**: NZD_JPY
- **Pairs missing**: NZD_JPY
- **Pairs skipped by harness**: NZD_JPY (no data available).

## Verdict
INSUFFICIENT (0 orders emitted). The strategy's only requested pair is NZD_JPY, which is not available in the provided historical dataframe. The harness correctly skipped the pair, resulting in 0 cells evaluated. We deliberately chose not to substitute another pair (like EUR_USD or USD_JPY), as doing so would invalidate the hypothesis and report meaningless, mis-parameterized results.
