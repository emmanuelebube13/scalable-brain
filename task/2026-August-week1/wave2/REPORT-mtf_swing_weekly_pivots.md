# REPORT-mtf_swing_weekly_pivots

## Implemented
A multi-timeframe strategy that trades breakouts from structural daily swings, but filters the direction using the weekly pivot point. The weekly pivot is calculated using the standard floor formula ((High + Low + Close) / 3) on W1 data. If the daily close is above the weekly pivot, only long swing breakouts are taken; if below, only short. The entries use limit/stop orders anchored to the daily swing points. Stops are placed at the opposite end of the swing structure, and the exit is a fixed 2.0R target.

## Deviations
None. The code maps exactly to the mechanical description.

## Uncertainties
- **Weekly Alignment**: Standardizing weekly aggregation in pandas requires careful timezone handling and ensuring that the Friday close properly forms the weekly pivot for the upcoming Monday open without leaking look-ahead bias. This was correctly implemented using causal `merge_asof` joins.
- **Swing Confirmation**: Relies on a standard 5-bar lag for defining structural swings, which forces the strategy to enter late into breakouts but provides robust stop geometry.

## Coverage
- **Pairs requested**: EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD
- **Pairs declared**: EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD
- **Pairs missing**: None
- **Pairs skipped by harness**: None. All 5 pairs were run.

## Verdict
FAIL (0.93 PF). The strategy fired 233 OOS trades across 5 pairs. A profit factor of 0.93 indicates a slightly negative expectancy. The weekly pivot is a widely watched reference level, but filtering daily structural breakouts based purely on whether price is currently above or below a static weekly mean does not appear to add enough directional edge to overcome the natural failure rate of swing breakouts.
