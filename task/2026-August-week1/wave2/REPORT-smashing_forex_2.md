# REPORT-smashing_forex_2

## Implemented
A daily trend-following system. It checks the slope of the EMA50 over 3 bars to define the trend direction, requires the CCI50 to agree, and demands a "fresh signal" (the condition must not have been true on the prior bar) to avoid entering late. It places a market order with a 30-pip fixed stop loss and a fixed 2.5R (75 pip) take profit.

## Deviations
Because `contract_v2` and the position engine do not currently support fractional trailing legs (rejected via `TRAILING_LEG_UNSUPPORTED`), the specified 200-pip trailing runner (which was intended for 50% of the position) had to be dropped entirely to allow the strategy to run. The entire position (100% fraction) now exits at the fixed TP1 target.

## Uncertainties
- **Fresh Signal Logic**: The spec explicitly requires that the entry signal condition was false on the previous bar. This restricts entry frequency to exact crossover bars.
- **Engine Limitation**: The inability to express fractional trailing stops means the strategy's intended "fat right tail" from the runner is entirely missing from this backtest.

## Coverage
- **Pairs requested**: EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD
- **Pairs declared**: EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD
- **Pairs missing**: None
- **Pairs skipped by harness**: None. All 5 pairs were run.

## Verdict
FAIL (0.50 PF). The strategy fired 1911 OOS trades across 5 pairs. Even acknowledging the missing trailing runner, a Profit Factor of 0.50 on the fixed target leg is highly negative expectancy. The tight "just beyond EMA" stop combined with the 2.5R target results in severe whipsaw losses. The system produced a 100% max drawdown, destroying the account.
