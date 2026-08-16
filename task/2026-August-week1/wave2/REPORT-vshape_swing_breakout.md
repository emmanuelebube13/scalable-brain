# REPORT-vshape_swing_breakout

## Implemented
A primary H4 breakout strategy that triggers after a V-shaped flush and recovery. A setup is valid for 20 bars after a confirmed swing establishes the "V". It enters at market when a large candle closes decisively beyond the flush origin, accompanied by a tick volume surge. The initial stop is set behind the V-swing extreme (with a 1.0-pip buffer), and the position trails via a 3.0×ATR trail leg evaluated on H4 closes.

## Deviations
- **Swing Detection:** The CSV pseudocode used a look-ahead `rolling(11, center=True)`. This was replaced by `causal_structure.confirmed_swing_points(period=5)`, enforcing a 5-bar lag.
- **V-Shape Formalization:** The source's qualitative "V-shape" requirement was mechanized into thresholds: a 1.5×ATR14 flush followed by a 1.0×ATR14 rebound within the 5-bar confirmation window.
- **Volume proxy:** The OANDA tick count is used for the volume surge condition (`Volume[t] > SMA20(Volume)[t]`), which the author sanctions.

## Uncertainties
- **Stop width:** The wider of the two source-documented stops ("beyond the V-swing extreme") was selected, making it more conservative.
- **Exit method:** The author suggested exiting at the "next major S/R", which was rejected as an unparameterized discretionary rule. A 3.0×ATR trail was implemented instead.

## Coverage
- **Pairs requested:** "All forex majors and minors"
- **Pairs declared:** EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD (the 5 live pairs).
- **Pairs missing:** None.
- **Pairs skipped by harness:** None. All 5 pairs were run.

## Verdict
FAIL (0.9095 PF). The strategy fired a healthy 2369 OOS trades across 5 pairs but failed significantly on PF (0.91), Sharpe (-0.58), and Max Drawdown (42.66%). The combination of a wide initial stop and an ATR trail giving back open profit likely contributed to the poor expectancy, while the false-breakout filters failed to prevent substantial drawdown.
