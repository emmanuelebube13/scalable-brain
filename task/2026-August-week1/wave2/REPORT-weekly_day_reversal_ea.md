# REPORT-weekly_day_reversal_ea

## Implemented
A calendar-anomaly strategy targeting a reversal on Tuesdays. It enters at the Tuesday market open (Monday's daily close) if Monday was a directional day and its high-low range exceeded 1.5× its 14-day average daily range (ADR14). Entries are in the opposite direction to Monday's close. Stops are set at 0.5× ADR14 from the decision bar's close. The position is exited unconditionally 23 hours later (at 20:00 UTC Wednesday) via a time stop leg.

## Deviations
- **Take Profit disabled:** The contract requires static fractions summing to 1.0. A split-fraction encoding would distort the strategy's core logic (the 23-hour force-close). The TP was therefore disabled and the exit relies entirely on the 23-hour time stop, which captures the raw day-of-week effect.

## Uncertainties
- **Day of week:** Fixed to Tuesday per the "Turnaround Tuesday" anomaly documented by the author, rather than sweeping parameters.
- **Direction:** Fixed to reversal only, rejecting the continuation mode alternative to match the strategy's primary hypothesis.
- **ADR Formula:** Implemented the simple rolling mean of High-Low as specified in the source pseudocode, rather than the true range ATR.

## Coverage
- **Pairs requested:** FX majors
- **Pairs declared:** EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD (the 5 live pairs).
- **Pairs missing:** None explicitly missing in the FX group. The strategy framework mentions testing commodities/indices, which are out of scope.
- **Pairs skipped by harness:** None. All 5 declared pairs were run.

## Verdict
FAIL (1.0816 PF). The strategy fired 150 OOS trades across the 5 pairs, failing the PF and Sharpe gates. The 150 trades reflect the strict combination of a specific day of the week and a high volatility threshold. The expected reversal effect was too small to overcome costs and the tight 0.5× ADR stop.
