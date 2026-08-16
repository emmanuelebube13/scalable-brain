# REPORT-pinbar_key_level_50pct

## Implemented
A daily reversion strategy that trades pinbars forming exactly at confirmed key swing support/resistance levels. The setup requires a "textbook" pinbar (wick >= 67% of range, body <= 33% of range) whose extreme piercing point is within a tight 0.25 × ATR14 band of a confirmed causal swing level (5-bar lag). A 50% retracement entry (a limit order placed at the midpoint of the pinbar's wick) is used to drastically improve the reward-to-risk ratio. The stop is anchored to the pinbar extreme. The trade is only taken if the implied reward-to-risk ratio (targeting the opposing swing level) is at least 2:1.

## Deviations
None. The implementation precisely models the strict pinbar geometry, the causal support/resistance extraction, and the 50% wick limit entry as defined in the spec.

## Uncertainties
- **Confluence Tightness**: The source requested pinbars "at key levels". The spec mechanized this as being within `0.25 * ATR14` of the exact swing level. This is a very strict proximity requirement that filters out "near misses".
- **Limit Entry Expiry**: The 50% retracement limit order was set to expire after 1 bar (the next daily bar). If price runs away without retracing to the wick's 50% level the next day, the trade is missed.

## Coverage
- **Pairs requested**: Any
- **Pairs declared**: EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD (the 5 live pairs).
- **Pairs missing**: None
- **Pairs skipped by harness**: None. All 5 pairs were run.

## Verdict
FAIL (0.76 PF). The strategy fired 53 OOS trades across 5 pairs. By requiring a 50% wick retracement limit entry, the strategy minimizes risk and maximizes reward *when filled*, but it suffers from severe adverse selection: the limit orders that actually get filled are disproportionately the ones where price is continuing right through the level to stop the trader out. A 15.1% win rate is the mechanical result of this adverse selection, destroying the 2:1 R:R advantage.
