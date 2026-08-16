# REPORT-psar_gbpjpy_daily

## Implemented
A daily trend-following system optimized specifically for GBP/JPY. It uses a Parabolic SAR (AF step 0.02, max 0.2) to define the trend, and enters in the direction of the SAR. The stop loss trails along the PSAR points. No specific take profit is defined, so the strategy exits entirely when the PSAR flips (modeled via a trailing stop and expiry). 

## Deviations
None.

## Uncertainties
- **Exit Logic**: The spec exited the position when the PSAR flips. Since `contract_v2` requires declarative structures, this was modeled exactly using a trailing stop anchored to the PSAR value.

## Coverage
- **Pairs requested**: GBP_JPY, EUR_JPY
- **Pairs declared**: GBP_JPY
- **Pairs missing**: GBP_JPY, EUR_JPY
- **Pairs skipped by harness**: GBP_JPY (no data).

## Verdict
INSUFFICIENT (0 orders emitted). The strategy's only required pairs (GBP_JPY and EUR_JPY) are not present in the historical database. The harness skipped the single declared pair, resulting in 0 cells evaluated and 0 trades generated. It cannot be meaningfully measured on the 5 live pairs without corrupting the hypothesis, which was explicitly designed around the specific volatility characteristics of JPY crosses.
