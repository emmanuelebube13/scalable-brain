# REPORT-outside_hma_klinger

## Implemented
An H4 price action strategy that trades "outside bars" (engulfing range) occurring in the direction of the trend, defined by a Hull Moving Average (27). It also incorporates a volume filter using the Klinger Volume Oscillator (KVO), which must confirm the direction (KVO > 0 for longs, KVO < 0 for shorts). It enters at market upon the close of the outside bar. The stop loss is fixed to 1.5 ATR(14) behind the entry, and the take profit is a fixed 2.0R (3.0 ATR).

## Deviations
None. The code faithfully implements the custom Hull MA and the complex EMA-based logic of the Klinger Volume Oscillator using tick volume as a proxy for real volume.

## Uncertainties
- **Tick Volume Proxy**: In decentralized FX markets, true volume does not exist. The KVO was calculated using broker tick volume, which is a standard but imperfect proxy for market activity.
- **Hull MA Implementation**: Hull MA requires calculating a WMA of price, a WMA of price with half the period, and then a WMA of the difference with the square root of the period. This was meticulously derived into native pandas/numpy logic.

## Coverage
- **Pairs requested**: EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD
- **Pairs declared**: EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD
- **Pairs missing**: None
- **Pairs skipped by harness**: None. All 5 pairs were run.

## Verdict
FAIL (0.85 PF). The strategy fired 1291 OOS trades across 5 pairs, failing the gates with a highly negative Sharpe ratio (-1.07) and a 56% drawdown. While an outside bar is a strong momentum signal, jumping in *after* the close of a massive H4 engulfing bar often means entering right at the local exhaustion point, leading to high stop-out rates before a 2.0R continuation can materialize. The HMA and KVO filters were insufficient to protect against this structural mean-reversion pull.
