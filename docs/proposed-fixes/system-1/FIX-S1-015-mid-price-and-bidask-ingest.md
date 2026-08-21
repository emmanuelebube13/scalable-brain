# FIX-S1-015 — Mid price and Bid/Ask ingest

**Raised:** 2026-08-21
**Severity:** high — W1 data contained bid prices in the mid columns; H1/H4/D1 had thousands of missing bid quotes.
**Decision taken:** System-1 `multi_timeframe_ingest` becomes the canonical writer, refactored to explicitly fetch and persist `MBA` (mid, bid, ask) candles.

---

## 1. The finding

`fact_market_prices` has mid columns (`"Open"`, `high`, `low`, `"Close"`) and bid/ask columns (`bid_open…bid_close`, `ask_open…ask_close`).
The System-1 ingest path (`src/ingestion/multi_timeframe_ingest.py`) was broken in two ways:
1. Because the request sent `price=BA`, the OANDA response contained `bid` and `ask` keys but no `mid` key. `_normalize_candle` silently fell back to `bid`, writing bid prices into the mid columns (biased low by roughly half the spread). This affected 5,375 W1 rows.
2. The `upsert_bars_with_lineage` function inserted 12 columns but none of them were `bid_*`/`ask_*`, resulting in NULL values. This caused 7,020 NULLs in the midweek window from May to July 2026.

Additionally, H1 was missing from the `DEFAULT_GRANULARITIES` list in the System-1 ingest, despite being the primary modeling frame.

---

## 2. The fix

1. **System-1 Canonicalization:** Decided that `multi_timeframe_ingest.py` is the canonical ingest writer. The layer0 loader is retained as import-only for helpers. The Saturday cron (`shell/cron_oanda_ingest_saturday.sh`) was updated to invoke the System-1 writer.
2. **Fetch MBA:** `src/layer0/ingest_data/ingest_oanda_prices.py` was updated so `fetch_candles_window` and `fetch_candles_with_retry` accept a `price` parameter, allowing the System-1 writer to request `"MBA"`.
3. **Strict Mid Parsing:** `_normalize_candle` no longer falls back. If `mid` is absent, it returns `None` and logs an error. It now explicitly parses `mid`, `bid`, and `ask` blocks.
4. **Bid/Ask Upsert:** `upsert_bars_with_lineage` now includes the 8 `bid_*` and `ask_*` columns in the `INSERT` and `ON CONFLICT DO UPDATE SET` clauses.
5. **Data Quality Gates:** Added `NEGATIVE_SPREAD`, `MID_OUTSIDE_SPREAD`, and `ABSURD_SPREAD` checks to `src/ingestion/dq.py`.
6. **H1 Granularity:** Added `"H1"` to `DEFAULT_GRANULARITIES`.

---

## 3. Repair Data

Implementation complete. `DO UPDATE SET` gracefully applied to missing data without full resync. 5,375 W1 rows and 7,020 midweek NULLs repaired.

- Repaired W1 data across EUR_USD, GBP_USD, USD_JPY, AUD_USD, and USD_CAD.
- Repaired the 2026-05-03 → 2026-07-03 NULL-bid window for D1, H4, and H1.
- Null count for `bid_close` dropped to 0.

---

## 4. Verification

- Dry run completed successfully with `EUR_USD` H1.
- Added comprehensive tests in `test_dq.py`.
- `pytest src/ingestion -v` and `pytest src/layer0/tests/ -v` pass.
- `black src/` and `mypy src/` complete cleanly.
- Database query verifies non-NULL bid/ask and accurate `"Close"` price matching `mid.c`.
