# FIX-S3-004 — 2% risk cap is computed in quote currency, not account currency (wrong for JPY/CAD pairs)

**Severity:** P1 (the hard risk cap is off by the exchange rate for 2 of 5 live assets — under/over-sizing)
**Status:** Proposed
**Author:** Claude (System-3 risk-engine audit)
**Date raised:** 2026-06-26
**Scope:** `src/layer7/oanda_executor.py` — `calculate_position_size` (units from `risk_capital /
sl_distance`)
**Category:** (1) unit/dimensional bug
**Risk to live trading:** For non-USD-quoted instruments the realized dollar risk diverges sharply
from the intended \$200 / 2% — USD_JPY is risked ~150× too small; the cap silently means different
things per pair.

---

## 1. Executive summary

Position size is `units = risk_capital / sl_distance`, where `risk_capital` is in **account-currency
dollars** (\$200 cap) but `sl_distance` is a **price difference in the instrument's quote currency**.
The product `units × sl_distance` — the actual loss if the stop is hit — is therefore in **quote
currency, not USD**. The code treats it as dollars. For USD-quoted pairs (EUR_USD, GBP_USD, AUD_USD)
quote = USD and it happens to be right. For **USD_JPY** (quote = JPY) and **USD_CAD** (quote = CAD) —
2 of the 5 assets in `dim_asset` — the "\$200 risk" is actually 200 JPY (~\$1.33) or 200 CAD (~\$147),
so the hard 2% cap is violated by the FX rate.

---

## 2. Evidence

```
oanda_executor.py:59-60  MAX_RISK_DOLLARS = $200          # account-currency dollars
oanda_executor.py:236-239  sl_distance = entry_price - sl_price   # PRICE units = QUOTE currency / unit
oanda_executor.py:246  units_decimal = risk_capital / sl_distance
```
The intended invariant is "loss at stop = units × sl_distance ≤ \$200." But `units × sl_distance` has
units of (quote currency per unit) × units = **quote currency**, not account currency. The conversion
factor `quote→USD` is missing.

Live asset universe (`dim_asset`): EUR_USD, GBP_USD, **USD_JPY**, AUD_USD, **USD_CAD**.

Worked example — **USD_JPY** at ~150.00, ATR ≈ 0.30 JPY, SL = 1×ATR ⇒ `sl_distance = 0.30` (JPY):
- `units = 200 / 0.30 = 666` units.
- Actual loss at stop = `666 × 0.30 = 200` **JPY** = 200 / 150 ≈ **\$1.33**, not \$200.
- The position is ~150× *under*-risked versus the intended 2%. (For pairs where the conversion went
  the other way, it would *over*-risk.)

**USD_CAD** at ~1.36: "\$200" is 200 CAD ≈ \$147 — a ~1.36× error. Only the three USD-quoted pairs are
coincidentally correct.

A related cosmetic symptom confirms the unit blindness: `pip_distance = sizing.sl_distance *
Decimal('10000')` (oanda_executor.py:402) hardcodes the 4-decimal pip factor, which is wrong (×100)
for JPY pairs — the module assumes every instrument is a 4-decimal USD-quoted pair.

---

## 3. Root cause

The sizing formula omits the quote-currency-to-account-currency conversion (and, for cross/▮JPY pairs,
the pip/point value). It implicitly assumes every instrument is quoted in the account currency (USD),
which holds for 3 of 5 live pairs and silently fails for the rest.

## 4. Proposed fix

- Convert risk to the instrument's quote currency before dividing, or convert the per-unit loss to
  account currency before comparing to the cap:
  `units = risk_capital_account_ccy / (sl_distance_quote × quote_to_account_rate)`.
  For USD_JPY, `quote_to_account_rate = 1 / USD_JPY`; for USD-quoted pairs it is 1.0. OANDA's
  `pricing`/`instrument` endpoints expose the conversion (`unitsAvailable`/home-currency conversion
  factors) — use them rather than hardcoding.
- Drive `pip_distance`/precision from instrument metadata (JPY pairs: 2-3 decimals) instead of a fixed
  `×10000`.
- Add an assertion/test that realized loss-at-stop (in account currency) ≤ `MAX_RISK_DOLLARS` for a
  basket including a JPY-quoted and a non-USD-quoted pair.

## 5. Validation plan

- Unit test the sizer for EUR_USD, USD_JPY, USD_CAD with known rates and assert the account-currency
  risk equals \$200 (±1 unit rounding) for all three. Today USD_JPY/USD_CAD fail.
- Cross-check against OANDA's reported margin/position value for a dry-run order.

## 6. Rollout / risk

Requires a quote→home-currency rate at sizing time (one extra pricing fetch, already available via the
OANDA client). Additive; can ship log-only (log corrected vs current units side-by-side) before
switching. Affects only sizing magnitude, not direction or gating.

## 7. One-paragraph summary

`units = risk_capital / sl_distance` mixes account-currency dollars (the \$200 cap) with a quote-
currency price distance, so the real loss-at-stop (`units × sl_distance`) is in the *quote* currency.
For the 3 USD-quoted pairs it's coincidentally right, but for USD_JPY the "\$200 cap" is 200 JPY
(~\$1.33, ~150× under-risk) and for USD_CAD ~\$147 — both live assets. The fix is to multiply
`sl_distance` by the quote→home-currency rate (1.0 for USD-quoted, 1/USD_JPY for JPY-quoted, etc.)
before computing units, and to derive pip/precision from instrument metadata instead of a hardcoded
×10000.
