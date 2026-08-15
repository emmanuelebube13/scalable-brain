# EXEC-012 — Trade-Close Tracking for Producer-Originated Trades (Agent Prompt)

**Run on: this machine, repo `system2/system-2-execution-engine`. Priority: CRITICAL —
do this before the next trading window opens (Sunday 20:00 UTC / 17:00 Atlantic).**

## The incident that motivates this (2026-07-15/16)

Six live trades were opened by the full pipeline on 2026-07-15. All six were closed
BROKER-SIDE by their stop-loss orders during the day. **None of the closes flowed back
to System 3.** For ~20 hours S3's `trade_journal` showed 6 open positions and
`ams_open_positions` was populated while the broker was flat; the reconciler correctly
alerted `open-position set mismatch … broker={}` every snapshot, but it is detect-only.
The ledger was repaired by hand from broker records on 2026-07-16 (journal rows 1–6,
`exit_reason='stop_loss[backfilled-from-broker-2026-07-16]'`).

Consequences while broken: S3's exposure layers count phantom opens (would have
throttled/blocked Sunday's trading at `max_open_positions=8`), the loss-streak /
consecutive-losses risk inputs never update, Task 15 never recomputes
`strategy_performance` from real closes, and the stage system can never accumulate the
50 closed trades it needs to graduate.

## Root cause

`ExecutionRuntime.startup_reconcile()` adopts broker open trades into the
`PositionManager` **only at engine startup**. Trades submitted during the session
(via `OutboundConsumer` → `adapter.submit`) are **never registered** with the position
manager, so:
1. the manager's close-detection loop (`evaluate_all`) never watches them;
2. no close/exit FillEvent is ever emitted to `ams-inbound`;
3. S2's duplicate-instrument backup guard sees zero open positions (which is also how
   two concurrent EUR_USD shorts got through on 2026-07-15).

## Task

Make broker-side closes (SL/TP/manual) of session-opened trades flow back to System 3
as the close events its post-trade processor already understands, WITHOUT modifying
System 3 or the Bridge (hard rule), and with minimal, surgical changes to System 2.

### Approach (suggested — verify against the actual code before committing)

1. **Register on fill:** in the wiring in `execution/lifecycle.py` (`build_from_secrets`),
   after a successful submit+fill, construct the same `ManagedTrade` that
   `startup_reconcile`'s `reconcile_fn` would build and `position_manager.register()` it.
   The consumer already exposes an `emit_fn(order, constructed, fill)` hook — extend the
   lambda there; do NOT modify `OutboundConsumer` itself.
2. **Detect closes:** `PositionManager.evaluate_all(prices)` runs every tick with
   `price_source_fn`. Verify it detects broker-closed trades (poll
   `adapter.transport.get_open_trades()` or per-trade GET) — if it only manages
   trailing stops, add a lightweight `sync_with_broker()` sweep (compare registered
   trade ids vs broker open-trade ids; on missing → fetch the closed trade's
   realizedPL/closePrice/closeTime).
3. **Emit the close event:** publish the close as a FillEvent (via the existing
   `FillProducer`) in the exact FLAT shape System 3's `classify_inbound` expects — read
   `system3/ams/src/ams/service/consumers.py` + the FillEvent contract
   (`system3/ams/contracts/v1/FillEvent.schema.json`) FIRST; note the bridge translates
   `ams-inbound` → `ams-inbound.ams`, so publish exactly what today's open-fill path
   publishes (same envelope/shape), with the close semantics S3's post-trade processor
   uses to close a journal row (look at how `ams.posttrade.processor` distinguishes
   open vs close fills).
4. **Backfill tool:** add `tools/backfill_closes.py` (S2 repo) that replays broker
   closed-trades since a timestamp into the same event path — so any future gap can be
   repaired by rerunning it instead of hand-SQL.
5. **Tests:** unit tests with a fake adapter/broker for: register-on-fill, close
   detection, close-event emission, no duplicate close events (idempotency on broker
   trade id), and the duplicate-instrument guard now seeing session trades.

### Constraints

- Do not modify System 3 or the Bridge. Do not break the 198 passing S2 tests.
- Fail-open: close-tracking errors must never block new trading; log + retry.
- The close event must be idempotent (S3 dedups fills on `broker_order_id`).

### Verification

- Sim: open a fake trade, "close" it at the fake broker, assert a close FillEvent is
  published and a second sweep publishes nothing.
- Live (practice): after deploy + engine restart, place/close one small manual trade on
  the practice account and watch S3's journal row close within one sweep;
  reconciler stays "no divergence".
