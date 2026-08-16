# REPORT-precision_swing

## Implemented
An H4 trend-following strategy using four independent lenses for confluence: price must be on the correct side of both EMA14 and EMA34, EMA14 must be on the correct side of EMA34, the Parabolic SAR (max AF=0.02) must agree, and a custom Detrended Price Oscillator (DPO) must be outside a 0.25×ATR14 flat-market band. Entries are at market when all conditions align (onset only). Stops are anchored exactly to the most recent confirmed swing extreme (5-bar confirmation lag). The exit is a fixed 1:1.25 reward-to-risk take profit.

## Deviations
- **Parabolic SAR:** The source used a "(0.02|0.02)" PSAR. This was strictly interpreted as AF start=0.02, step=0.02, max=0.02, meaning it never accelerates.
- **Exit Strategy:** The source mentioned an optional "exit when EMA or PSAR flips". This is a signal exit and cannot be modeled declaratively in contract v2, so the alternative fixed 1:1.25 TP was used.
- **Position Sizing:** The source's 1-2-3-5-8-13 martingale sizing sequence was explicitly rejected per system rules; a fixed `size_fraction = 1.0` was used.

## Uncertainties
- **Swing Stop Exactness:** The source specified placing the stop "below the previous swing low", which could imply a buffer. It was placed exactly at the confirmed swing level, which is the tightest and most conservative reading.
- **DPO Filter:** The spec mechanized the "DPO near zero" prose into a `0.25 × ATR14` band, as DPO is in price units and requires volatility scaling.

## Coverage
- **Pairs requested:** "Any"
- **Pairs declared:** EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD (the 5 live pairs).
- **Pairs missing:** None.
- **Pairs skipped by harness:** None. All 5 pairs were run.

## Verdict
FAIL (1.0446 PF). The strategy fired 543 OOS trades across the 5 pairs, failing the PF, Sharpe, and Max Drawdown (27.39%) gates. The confluence filters worked to find trades (over 500 signals is a robust sample), but the fixed 1:1.25 reward-to-risk exit on a trailing confirmed-swing stop simply could not produce a positive expectancy above costs.
