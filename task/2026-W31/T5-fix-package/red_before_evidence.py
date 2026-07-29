"""Run the SAME risk invariants against the UNPATCHED formulas.

Every check here is one the corrected code passes. Against the legacy formulas
they fail — that is the red-before evidence. Output is captured in RED-BEFORE.txt.
"""
from decimal import Decimal
from fx_units import (Instrument, OpenPosition, LEGACY_exposure_pct,
                      LEGACY_position_size_units, LEGACY_pip_distance,
                      realised_risk_account_ccy, portfolio_exposure_pct)

RISK_USD, EQUITY = Decimal("200"), Decimal("10000")
EUR_USD = Instrument("EUR_USD", 4, Decimal("1.0"))
USD_JPY = Instrument("USD_JPY", 2, Decimal("1") / Decimal("150"))
USD_CAD = Instrument("USD_CAD", 4, Decimal("1") / Decimal("1.36"))
EUR_GBP = Instrument("EUR_GBP", 4, Decimal("1.27"))

fails = 0
def check(name, ok, detail):
    global fails
    if not ok: fails += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}\n         {detail}")

print("INVARIANT 1 — realised risk at stop must equal the USD 200 cap (+/- rounding)")
for inst, sl in ((EUR_USD, Decimal("0.0050")), (USD_JPY, Decimal("0.30")),
                 (USD_CAD, Decimal("0.0040")), (EUR_GBP, Decimal("0.0040"))):
    u = LEGACY_position_size_units(risk_capital_account_ccy=RISK_USD, sl_distance_quote_ccy=sl)
    r = realised_risk_account_ccy(units=u, sl_distance_quote_ccy=sl, instrument=inst)
    ok = abs(r - RISK_USD) <= Decimal("1")
    check(f"{inst.name}: legacy units={u:,}", ok,
          f"realised risk = USD {r:.2f}  (intended 200.00, error {(r/RISK_USD - 1)*100:+.1f}%)")

print("\nINVARIANT 2 — reported exposure must track notional, not position count")
small = [OpenPosition(EUR_USD, 1_000, Decimal("1.10"))] * 2
massive = [OpenPosition(EUR_USD, 100_000, Decimal("1.10"))] * 2
ls, lm = LEGACY_exposure_pct(small), LEGACY_exposure_pct(massive)
check("size-sensitivity", ls != lm,
      f"$1,100 book -> {ls}   |   $110,000 book -> {lm}   (identical: exposure ignores size)")
check("2200% book is rejected", lm > Decimal("0.25"),
      f"true exposure = {portfolio_exposure_pct(massive, EQUITY):.2f}x equity, "
      f"legacy reports {lm} and APPROVES")

print("\nINVARIANT 3 — pip distance must respect the instrument's pip size")
check("USD_JPY 0.30 -> 30 pips", LEGACY_pip_distance(Decimal("0.30")) == Decimal("30"),
      f"legacy reports {LEGACY_pip_distance(Decimal('0.30'))} pips (100x too many)")

print(f"\n{fails} invariant(s) FAILED against the unpatched code.")
raise SystemExit(1 if fails else 0)
