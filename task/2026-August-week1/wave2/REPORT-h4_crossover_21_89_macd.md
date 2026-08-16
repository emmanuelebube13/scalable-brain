# REPORT-h4_crossover_21_89_macd

## Implemented
A multi-timeframe trend-following strategy that requires alignment between H4 and D1. It uses an EMA cross (21 and 89) on H4 as the primary signal, but filters it by requiring the D1 MACD histogram to agree with the direction (MACD > 0 for longs, MACD < 0 for shorts). It enters at market when both conditions align. Stop loss is placed at the recent swing extreme (plus a small buffer), and take profit is a fixed 1:1 risk-reward ratio.

## Deviations
None. The code maps exactly to the mechanical description of the strategy, ensuring that the D1 MACD is constructed using trailing-only data to prevent look-ahead bias when evaluating on H4.

## Uncertainties
- **MTF Construction**: Deriving the exact daily MACD value at a specific H4 bar close requires causal `merge_asof` alignment. This ensures that the H4 bar only sees the D1 MACD value from the *previously completed* daily bar.
- **Swing Stop**: The stop relies on a standard swing detection method (lag 5) rather than an arbitrary recent bar count, which delays the identification of the pivot but guarantees structural significance.

## Coverage
- **Pairs requested**: EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD
- **Pairs declared**: EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD
- **Pairs missing**: None
- **Pairs skipped by harness**: None. All 5 pairs were run.

## Verdict
FAIL (1.00 PF). The strategy fired 200 OOS trades across 5 pairs. A profit factor of exactly 1.0044 implies that this entry criteria (H4 EMA cross filtered by D1 MACD) generates entries that are completely random relative to subsequent short-term direction, yielding exactly a 50/50 win rate on a 1:1 target over a large sample.
