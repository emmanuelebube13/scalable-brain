# REPORT: kpl_donchian_breakout

## Implemented
- The strategy logic implements a classic 20-day Donchian channel breakout on the D1 timeframe.
- It enters at market upon a close outside the channel (shifted by 1 bar to avoid reading the current bar's high/low).
- A 2x ATR(14) initial stop and close-anchored trailing stop overlay were implemented per the CSV's recommendation, as the original script lacked a stop.

## Deviations
- The always-in-market (stop-and-reverse) behavior of the original was mechanically decomposed into fresh market entries on crossover events only. This avoids inexpressible order overlap under the v2 contract, though it misses trend resumption after a stop-out.

## Uncertainties
- The stop overlay (2x ATR) is the single most important risk parameter but is not of the original author's choosing, injecting an uncertainty into whether the strategy's failure belongs to the breakout logic or the stop tightness.

## Coverage
- Pairs declared: EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD, GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD.
- Pairs missing: none.
- Harness skipped GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD (no data for primary or context frame).

## Verdict
FAIL. PF=0.86, Sharpe=-0.43, Recovery=N/A across 359 OOS trades in 5 passing cells. The strategy operated correctly as a mechanical breakout but failed to establish a positive edge over the evaluation window.
