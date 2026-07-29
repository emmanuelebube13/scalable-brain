# APPLY — S3-002 and S3-004 on Computer 3 / the VM

**Read this whole file before running anything.** These changes alter how real-money
position sizes are computed. Apply them in a session where you can watch the first few
sizing decisions.

The reference arithmetic is `fx_units.py` in this folder; the tests pin every expected
number. Port the two functions into the System-3 sizing module — do not import this file
into production, it is a specification, not a library.

---

## Before you start

```bash
# 1. Snapshot the files you are about to change.
cp <s3>/oanda_executor.py  <s3>/oanda_executor.py.bak-$(date +%Y%m%d)
cp <s3>/live_pipeline.py   <s3>/live_pipeline.py.bak-$(date +%Y%m%d)

# 2. Record the current behaviour so you can compare afterwards.
#    Note the units the sizer produces for one USD_JPY signal — you should see it change
#    by ~150x. If it does not, the patch did not take effect.
```

You need one input the current code does not have: **the quote-currency → account-currency
rate for each instrument.** For a USD account:

| Instrument | Quote | `quote_to_account_rate` |
|---|---|---|
| EUR_USD, GBP_USD, AUD_USD | USD | `1.0` |
| USD_JPY | JPY | `1 / USDJPY_price` |
| USD_CAD | CAD | `1 / USDCAD_price` |
| a EUR_GBP-style cross | GBP | `GBPUSD_price` |

**This rate must be fetched live, not hardcoded.** If it is unavailable, the sizer must
**refuse to size** (default-safe posture: missing ⇒ REJECT). Do not fall back to `1.0` —
that reinstates exactly the bug being fixed.

---

## S3-004 — risk cap in account currency

**File:** `oanda_executor.py`, `calculate_position_size`, step 6 (was line ~246).

```python
# BEFORE — units of (account ccy) / (quote ccy per unit): only correct if quote == account
units_decimal = risk_capital / sl_distance

# AFTER
if quote_to_account_rate is None or quote_to_account_rate <= 0:
    raise ValueError(f"no quote->account rate for {instrument}; refusing to size")
risk_per_unit_account = sl_distance * quote_to_account_rate
units_decimal = risk_capital / risk_per_unit_account
```

Also fix the pip display (was line ~402), which hardcodes 4-decimal pips:

```python
# BEFORE
pip_distance = sizing.sl_distance * Decimal('10000')
# AFTER  (pip_size = 0.01 for JPY-quoted, 0.0001 otherwise)
pip_distance = sizing.sl_distance / pip_size(instrument)
```

Keep `ROUND_DOWN` — realised risk must never exceed the cap.

### Apply and test

```bash
cd <s3-repo>
pytest <your sizing tests> -v
python - <<'PY'   # smoke: USD_JPY must now size ~150x larger
from decimal import Decimal
# ... call calculate_position_size for USD_JPY, SL 0.30, rate 1/150
# expect ~100,000 units, NOT 666
PY
```

---

## S3-002 — exposure as a fraction of equity

**File:** `live_pipeline.py`, `evaluate_correlation_gate` (was lines ~1108-1121).

```python
# BEFORE — a COUNT compared against a percentage via a magic *10
total_exposure = len(open_positions)
if total_exposure >= MAX_TOTAL_EXPOSURE_PCT * 10:      # >= 2.5 -> fires at the 3rd position
    ... exposure_pct=total_exposure / 10               # 2 positions -> "0.2" regardless of size

# AFTER
notional = sum(
    Decimal(p["units"]) * Decimal(p["entry_price"]) * quote_to_account_rate(p["instrument"])
    for p in open_positions
)
exposure_pct = notional / account_equity
if exposure_pct > MAX_TOTAL_EXPOSURE_PCT:
    ... reject with the true fraction
if MAX_CONCURRENT_POSITIONS is not None and len(open_positions) >= MAX_CONCURRENT_POSITIONS:
    ... reject on the count cap, named honestly
```

Add `MAX_CONCURRENT_POSITIONS = 3` alongside `MAX_TOTAL_EXPOSURE_PCT` so behaviour is never
*weaker* than today — today's effective rule is "reject the 3rd position".

**Blocker you will hit:** `prepare_broker_order` returns `"units": None`
(`live_pipeline.py:1282`), so size never reaches this gate. The exposure fix cannot work
until `units` and `entry_price` are actually carried on the position dicts. Fix that first
or the new gate divides by nothing.

---

## Rollback

```bash
cp <s3>/oanda_executor.py.bak-<date> <s3>/oanda_executor.py
cp <s3>/live_pipeline.py.bak-<date>  <s3>/live_pipeline.py
# restart the service, confirm sizing returns to the previous magnitudes
```

Rolling back restores the unit bugs. Prefer fixing forward unless sizing is visibly wrong.

---

## Order of operations

1. Apply **S3-004** first — it is self-contained arithmetic and independently testable.
2. Verify one live-shaped USD_JPY sizing by hand before letting it place anything.
3. Then plumb `units`/`entry_price` through to the exposure gate.
4. Then apply **S3-002**.
5. Address the **S3-006 lockout** (see `S3-006-ROOT-CAUSE.md`) before re-enabling the gate.

Do not apply both at once. If sizing changes by 150x and exposure logic changes in the same
deploy, you will not know which one moved the numbers.
