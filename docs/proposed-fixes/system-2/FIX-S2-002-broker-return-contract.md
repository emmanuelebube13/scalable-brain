# FIX-S2-002 — Live OANDA fills are recorded as FAILED (broker adapter return-contract mismatch)

**Severity:** P0 (a real, capital-committing order is logged as a failure; position goes untracked)
**Status:** Proposed
**Author:** Claude (System-2 audit)
**Date raised:** 2026-06-26
**Scope:** `src/layer7/oanda_executor.py::execute_trade` ↔ `src/layer4_executor/live_pipeline.py::execute_broker_order` (+ post-exec logging, open-position tracking)
**Affected pipeline:** Layer 4 Stage 7 (broker execution) → Stage 8 (execution logging) → Layer 6 auditor
**Risk to live trading:** High — divergence between broker reality and system state.

---

## 1. Executive summary

The broker adapter and its Layer 4 caller disagree on the return shape. `execute_trade()`
returns the **raw OANDA response dict** (keys like `orderFillTransaction`) or `None`, but
`execute_broker_order()` reads keys `success`, `order_id`, `fill_price`, `fill_time`,
`slippage_pips` that **never exist** on that response. Consequence: a genuinely filled live
order is classified as a failure — no order id captured, no fill telemetry, the position is not
added to the open-position list, no alert email is sent, and the trade is logged "FAILED" —
while the position is actually live at OANDA. The dry-run path masks the bug because it returns
a correctly-shaped stub.

---

## 2. Evidence (code)

**Producer** (`oanda_executor.py:341-516`) — on a fill returns the OANDA SDK response:
```python
if response and 'orderFillTransaction' in response:
    ...
    return response          # raw dict: has 'orderFillTransaction', NOT 'success'/'order_id'
...
return None                  # on error / cancel returns None or the cancel response
```
It never returns a dict containing `success`, `order_id`, `fill_price`, `fill_time`, or
`slippage_pips`.

**Consumer** (`live_pipeline.py:1303-1323`):
```python
result = execute_trade(...)
if result and result.get("success"):                       # 'success' absent → None → falsy
    return True, result.get("order_id"), {...}
else:
    return False, None, {"error": result.get("error","Unknown")}   # taken on EVERY real fill
```
On a successful fill, `result` is a truthy dict but `result.get("success")` is `None` → the
`else` branch runs → `(False, None, {"error":"Unknown"})`.

**Downstream effect** (`live_pipeline.py:1684-1739`): because `success` is False, the pipeline
takes the failure branch — `update_post_execution_log(..., "FAILED", ...)`, sets
`veto_reason="Broker execution failed: Unknown"`, and **skips** `self.open_positions.append(...)`.
So the position that is live at the broker is invisible to the in-run correlation/exposure gate
(compounding FIX-S2-004) and to telemetry.

---

## 3. Root cause

`execute_trade` was written to return the SDK response for human/log inspection, while Layer 4
was written against an imagined normalized adapter contract
(`{success, order_id, fill_price, fill_time, slippage_pips}`). No adapter layer translates
between them, and the only integration that "passes" is the dry-run stub
(`execute_broker_order` returns `True, "DRY_RUN_001", {...}` directly), which is why this was
never caught.

---

## 4. Proposed fix

Make `execute_trade` (or a thin wrapper) return the normalized contract Layer 4 already expects:
```python
return {
  "success": True,
  "order_id": fill_tx["id"],
  "fill_price": float(fill_tx["price"]),
  "fill_time": fill_tx["time"],
  "slippage_pips": _pips(symbol, requested_entry, float(fill_tx["price"])),
}
```
and `{"success": False, "error": <reason>}` on cancel/exception. Compute `slippage_pips` with a
per-instrument pip factor (0.0001 majors, 0.01 JPY — see also FIX-S2-005 note). Add an
integration test that asserts a mocked OANDA fill response maps to `success=True` with a
populated `order_id`.

---

## 5. Validation plan

1. Unit-test `execute_broker_order` against a realistic mocked OANDA `orderFillTransaction`
   payload → assert `success=True`, non-null `order_id`, numeric `fill_price`.
2. Practice-account smoke test (single 1-unit order, explicit human approval): confirm the
   filled order is logged EXECUTED with the real order id, the email fires, and the position is
   appended to `open_positions`.
3. Assert the cancel/`V20Error` path maps to `success=False` with a non-"Unknown" error string.

---

## 6. Rollout / risk

Localized to the adapter return shape + one test; reversible. **Until fixed, the system's record
of what it executed is unreliable in live mode** — operators must reconcile against the OANDA
portal directly.

---

## 7. One-paragraph summary

`execute_trade()` returns the raw OANDA response dict (or `None`), but `execute_broker_order()`
inspects `.get("success")/.get("order_id")/.get("fill_price")` — keys that never exist on that
response — so every real fill falls into the failure branch: it is logged "FAILED", no order id
or fill price is captured, no alert is sent, and the live position is never added to the
open-position list. The dry-run stub hides the defect because it returns the right shape. Fix by
normalizing the adapter's return contract to `{success, order_id, fill_price, fill_time,
slippage_pips}` and adding a mocked-fill integration test.
