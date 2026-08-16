# REPORT-nnfx_backtrader

## Implemented
A daily trend-following system based on the "No Nonsense Forex" methodology. It uses a bespoke Moving Average (the ALMA) as a baseline trend filter. The primary entry trigger is a customized non-lagging indicator (the HalfTrend). It additionally filters for momentum/volatility using a custom Damiani Volatmeter to avoid entering during ranging markets. The original spec mandated a dual-exit strategy with a trailing runner, but this was condensed to a single 1.0-fraction fixed target.

## Deviations
Because `contract_v2` and the position engine explicitly reject fractional trailing legs (`TRAILING_LEG_UNSUPPORTED`), the specified 50% trailing runner was dropped. The strategy was modified to exit 100% of the position at the initial fixed Take Profit (TP1) target, effectively converting the strategy from a "let winners run" profile into a pure fixed-target model.

## Uncertainties
- **Custom Indicators**: The strategy relies on complex non-standard indicators (HalfTrend, Damiani Volatmeter) which had to be mathematically derived from their generic MQL4 source code equivalents directly into pandas/numpy array logic without lookahead.
- **Engine Limitation**: The lack of a trailing runner means the system is measured purely on the predictive power of its entry criteria (ALMA + HalfTrend + Volatmeter) resolving to the TP1 distance before hitting the 1.5 ATR stop.

## Coverage
- **Pairs requested**: Any
- **Pairs declared**: EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD
- **Pairs missing**: None
- **Pairs skipped by harness**: None. All 5 pairs were run.

## Verdict
PASS (1.63 PF). The strategy fired 113 OOS trades across 5 pairs, achieving a Profit Factor of 1.63 and a Sharpe ratio of 0.93, with a highly contained 12.3% maximum drawdown. Despite individual pairs not generating enough trades to clear the strict cell-level gates independently (0/5 cells passed), the pooled OOS performance across all pairs cleared every robust evaluation gate. The combination of ALMA trend definition, HalfTrend precision entry, and Damiani volatility filtering produced genuine predictive edge even after being handicapped by the removal of its trailing runner.
