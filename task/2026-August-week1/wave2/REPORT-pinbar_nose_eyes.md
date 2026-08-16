# REPORT-pinbar_nose_eyes

## Implemented
A single-timeframe H4 pinbar reversal strategy. It identifies a 2-bar pattern (left eye and nose) where the nose opens/closes inside the left eye's body but its extreme protrudes significantly beyond the left eye. Trades are taken only at mandatory structural S/R (confirmed swing levels). Entries are via stop orders placed beyond the nose's extreme, valid for 3 bars. A single take-profit leg is set just beyond the left eye's extreme.

## Deviations
- **S/R Filter:** The spec's "Ideally at strong support/resistance" was implemented as a mandatory filter using the last confirmed H4 swing level to remove subjectivity.

## Uncertainties
- **Entry style:** Chosen the conservative stop-entry beyond the nose, skipping the aggressive right-eye retreat entry.
- **Stop placement:** Stop is placed behind the confirmed S/R level or the nose point, whichever is safer, rather than just tightly behind the nose.
- **TP target:** Only the conservative TP target (left eye extreme) is used. The "next strong S/R" TP is skipped as discretionary.
- **Timeframe:** Evaluated on H4 as the primary timeframe per source consensus, instead of D1/W1 which would be too thin.
- **Two-sided pending overlap:** A buy_stop and a later sell_stop can coexist up to 3 bars, meaning chop could produce rapid reversal trades. No OCO mechanism is available to prevent this.

## Coverage
- **Pairs requested:** "Any currency pair"
- **Pairs declared:** EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD (the 5 live pairs).
- **Pairs missing:** None explicitly requested.
- **Pairs skipped by harness:** None.

## Verdict
FAIL (0.9226 PF). The strategy fired 14 OOS trades across the 5 pairs, failing the profit factor and Sharpe gates. The low trade count flags as LOW_CONFIDENCE, likely due to the strictness of requiring both a precise pinbar formation and alignment with a confirmed structural S/R level simultaneously.
