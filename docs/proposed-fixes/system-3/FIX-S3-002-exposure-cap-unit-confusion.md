# FIX-S3-002 — "25% portfolio exposure" cap is a position *count*, not a notional fraction

**Severity:** P1 (a documented risk limit means something entirely different from its name)
**Status:** Proposed
**Author:** Claude (System-3 risk-engine audit)
**Date raised:** 2026-06-26
**Scope:** `src/layer4_executor/live_pipeline.py` — `MAX_TOTAL_EXPOSURE_PCT`,
`evaluate_correlation_gate`
**Category:** (1) unit/dimensional bug · (4) degenerate output
**Risk to live trading:** The "max 25% exposure" guard does not measure exposure; it never looks at
position size or notional, so it cannot protect against over-concentration by capital.

---

## 1. Executive summary

CLAUDE.md and the constant name advertise a portfolio guard of "max 25% exposure"
(`MAX_TOTAL_EXPOSURE_PCT = 0.25 # 25% of portfolio`). The implementation never computes a fraction of
capital. It counts *how many position dicts* are in `open_positions` and compares that integer to
`0.25 * 10 = 2.5`. So the rule actually means **"reject the 3rd concurrent position,"** independent of
each position's size, notional, or risk. The magic `* 10` and the reported `exposure_pct =
total_exposure / 10` are a fabricated unit bridge: 2 positions are reported as "0.2" exposure
regardless of whether they risk \$10 or \$10,000.

---

## 2. Evidence

```
live_pipeline.py:124   MAX_TOTAL_EXPOSURE_PCT = 0.25  # 25% of portfolio
...
live_pipeline.py:1051  total_exposure = len(open_positions)          # a COUNT of positions
live_pipeline.py:1052  if total_exposure >= MAX_TOTAL_EXPOSURE_PCT * 10:   # >= 2.5  → fires at 3 positions
live_pipeline.py:1055      exposure_pct=total_exposure / 10,         # 2 positions reported as 0.2
```
`total_exposure` is `len(open_positions)` — a count. It is multiplied against a percentage threshold
via an unexplained `* 10`, and the "exposure_pct" surfaced in `CorrelationResult` /
`fact_live_trades` is `count / 10`. Nowhere in the module is any position's `units`, notional, or
`risk_capital` summed; `prepare_broker_order` even returns `"units": None` (live_pipeline.py:1282),
so size never reaches this gate. The threshold is therefore dimensionally a count, mislabelled as a
percent. Changing `MAX_TOTAL_EXPOSURE_PCT` from 0.25 to, say, 0.40 would silently change the limit
from "3rd position" to "5th position," not from 25% to 40% of capital.

Combined with `MAX_POSITIONS_PER_ASSET = 1` (live_pipeline.py:123) and FIX-S3-001 (the list is empty
in practice), the effective behavior is "at most 2 distinct-asset positions per *single run*, by
count" — never a capital-based cap.

---

## 3. Root cause

A percentage-named constant is wired into an integer count comparison through an arbitrary scale
factor (`* 10`, `/ 10`) instead of computing exposure as `sum(position_notional) / account_equity`.
The gate was specified in capital terms but implemented in cardinality terms.

## 4. Proposed fix

- Make exposure a real fraction: track each open position's notional (`units * entry_price`, in
  account currency — see FIX-S3-004 for the currency conversion) and compute
  `exposure_pct = sum(notional) / account_equity`. Reject when `exposure_pct > MAX_TOTAL_EXPOSURE_PCT`.
- Keep a *separate*, explicitly named `MAX_CONCURRENT_POSITIONS` integer if a count cap is also
  desired — do not overload one constant to mean both.
- Remove the `* 10` / `/ 10` magic numbers; report the true fraction.

## 5. Validation plan

- Unit test: two positions of known notional against a known equity must yield the exact
  `exposure_pct`; assert rejection when it crosses 0.25. Today the value is `count/10` regardless of
  size, so this test cannot pass against the current code.
- Replay/backtest: confirm `exposure_pct` distribution is continuous in [0,1] and tracks summed
  notional, not a step function of position count.

## 6. Rollout / risk

Pure logic change in one gate; additive once position notional is available (it must come from the
broker sizing result, `PositionSizeResult.units * entry_price`). No order-placement change. Ship with
the count cap retained as a named constant so behavior is never *weaker* than today.

## 7. One-paragraph summary

`MAX_TOTAL_EXPOSURE_PCT = 0.25` is documented as "25% of portfolio," but `evaluate_correlation_gate`
implements it as `len(open_positions) >= 0.25 * 10`, i.e. "block the 3rd position," and reports
`exposure_pct = count / 10`. No position size, notional, or risk is ever summed (the broker order even
carries `units: None`), so the guard cannot limit capital exposure and the constant's percentage units
are fictional. Fix: compute exposure as summed notional ÷ account equity and reject above the real
fraction; if a count cap is also wanted, give it its own explicitly named constant instead of
overloading a percentage with a `* 10` fudge.
