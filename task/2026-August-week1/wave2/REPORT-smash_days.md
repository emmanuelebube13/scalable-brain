# REPORT-smash_days

## Implemented
A short-only D1 smash-up day strategy. The decision bar must close above the previous day's close and above the highs of the preceding 5 days. It emits a sell_stop at the decision bar's low, valid for 1 bar (the following session), with a structural stop at the decision bar's high. Positions are exited unconditionally at the close of the 5th session.

## Deviations
- Exit: The P&L-conditional exit ("first profitable Close after 5 or more sessions held") was dropped as inexpressible. A pure 5-session time exit is used instead.

## Uncertainties
- **Longs:** The spec text indicated shorts are primary, though the pseudocode mentioned a mirror for longs. Kept as short-only to match the conservative reading.
- **Event Risk Filter:** The spec mentions avoiding "extreme volatility/event risk", but this was dropped entirely as there is no event data available.
- **Cross-Pair Exposure Limit:** The spec limits concurrent exposure to avoid AUD/NZD double-counting. Dropped as contract v2 has no cross-pair coordination channel.

## Coverage
- **Pairs requested:** "28 leading forex pairs"
- **Pairs declared (available):** AUD_USD, USD_CAD, EUR_USD, GBP_USD, USD_JPY
- **Pairs missing:** GBP_NZD, NZD_CHF, and the rest of the 28 pairs.
- **Pairs skipped by harness:** None. All 5 had sufficient data, but the strategy fired extremely rarely.

## Verdict
INSUFFICIENT (2 OOS trades). The strategy only produced 2 OOS trades across the 5 available pairs over 10 years, which is insufficient for measurement. This is likely due to the restrictive entry condition combined with the limited pair universe.
