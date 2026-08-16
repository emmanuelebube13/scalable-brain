# REPORT-xard_ma_cross_daily_open

## Implemented
An intraday H1 momentum strategy tracking price action relative to the daily open. It calculates the Daily Open (by aggregating H1 bars causally), a fast SMA(5), and a slow SMA(20). When price is above the Daily Open and the fast SMA crosses above the slow SMA, a long market order is fired (short if below the open with a downward cross). The stop loss is fixed at a tight 20 pips, and the take profit is fixed at 1.5R (30 pips). 

## Deviations
None. The code maps exactly to the mechanical description of the strategy, ensuring that the "daily open" is constructed purely from historical H1 data without look-ahead bias.

## Uncertainties
- **Daily Open Construction**: Deriving the exact daily open on a rolling 24-hour market requires grouping H1 bars by UTC day. This correctly aligns the logic, but variations in broker timezone offsets mean "daily open" is arbitrary in real FX markets compared to equity markets.

## Coverage
- **Pairs requested**: Any
- **Pairs declared**: EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD
- **Pairs missing**: None
- **Pairs skipped by harness**: None. All 5 pairs were run.

## Verdict
FAIL (1.00 PF). The strategy fired 2115 OOS trades across 5 pairs. A profit factor of exactly 1.0021 implies that this entry criteria (H1 SMA cross filtered by daily open) generates entries that are completely random relative to subsequent short-term direction. The massive 72% maximum drawdown confirms that the strategy produces no measurable edge over thousands of samples.
