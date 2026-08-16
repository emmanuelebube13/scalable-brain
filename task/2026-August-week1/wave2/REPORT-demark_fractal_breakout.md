# REPORT-demark_fractal_breakout

## Implemented
A purely mechanical H4 trend-following breakout strategy. It buys when the price breaks above a confirmed DeMark swing high (LevDP=2) and sells when the price breaks below a confirmed DeMark swing low. Crucially, the strategy enforces an additional 1-bar confirmation lag beyond the natural causality of the fractal, meaning a swing that occurs at bar `k` is only actionable at bar `k+3`. The strategy uses pending stop orders with a small entry buffer. Stops are placed behind the most recent confirmed opposite-side fractal with a buffer. Exits are managed purely by a 1.5x ATR(14) trailing stop.

## Deviations
- **Pip calculation bug (FIXED):** The original implementation erroneously converted the fixed pip buffers (4-pip entry buffer, 3-pip stop buffer, plus spread proxy) using the `metadata.pairs[0]` (EUR_USD) rate of `0.0001` for all pairs. For USD_JPY, which trades around ~110.00 and has a pip value of `0.01`, this resulted in applying buffers of ~0.0005 instead of ~0.05. This effectively ran the USD_JPY pairs with exactly zero buffer on entries and stops. This was fixed on 2026-08-16 by dynamically inferring the pip size from the price magnitude.

## Uncertainties
- **Fractional Trailing Legs:** The position engine explicitly rejects `ExitLeg(kind="trailing")` if `fraction < 1.0` (`TRAILING_LEG_UNSUPPORTED`). The strategy avoids this rejection because it uses `fraction=1.0` (trailing the entire position at once).

## Coverage
- **Pairs requested**: Any
- **Pairs declared**: EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD
- **Pairs missing**: None
- **Pairs skipped by harness**: None

## Verdict
FAIL (0.97 PF, Sharpe -0.18). After fixing the critical pip calculation bug, the strategy completely lost its edge on USD_JPY. The initial 2026-08-16 artifact reported a stellar passing cell on USD_JPY (PF 1.51, Sharpe 1.11, 610 trades) which was flagged as the single strongest result in the entire fleet. The follow-up investigation revealed that this was purely an artifact of running USD_JPY with a 100x tighter buffer (essentially 0 pips) due to the EUR_USD pip cross-contamination. 

Once the correct `0.01` pip size was applied, the USD_JPY cell reverted to the fleet's baseline failure profile. The strategy generated 2961 OOS trades across the 5 pairs and failed every single gate. The single passing cell was a bug, and the strategy carries no genuine edge.
