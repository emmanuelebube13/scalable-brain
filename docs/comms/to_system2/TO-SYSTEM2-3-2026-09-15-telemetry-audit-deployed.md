# TO SYSTEM 2/3 — telemetry audit deployed across dashboard, VM and publisher (2026-09-15)

**From:** System 1 (Computer 1), acting with owner approval
**Status:** DEPLOYED and verified live. This is a record, not a request — plus two follow-ups for you at the end.

## What changed and where

All work is on branch `telemetry-audit-2026-09-15` in each repo, pushed. The VM was
deployed by direct file copy (backup first — see Rollback) because `/opt/scalablebrain`
is not a git checkout.

### scalablebrain-umbrella (dashboard, Cloud Run rev 00089–00091)
- Overview: ACCOUNT & MARGIN banner + six static tiles consolidated into one interactive
  row (FINANCIALS / POSITIONS · UNRL P&L / SYSTEM HEALTH) with Dialog drill-downs.
  GATE-2 lifetime tile moved into the System Health drill-down with an explicit
  dead-producer-window caveat. Unrealized P&L colour now derives from the value's sign.
- AVG CONFIDENCE retitled **AVG GATEKEEPER SCORE**, "shadow — not enforced" on the label.
- Gate-1 Outcome Mix redesigned: segmented bar + count legend; RATE BLOCKED badge and
  `shadow.label_as` verbatim semantics preserved (D1 rules intact).
- New **daily signal conversion** donut + endpoint `GET /api/v1/signals/daily-conversion`
  (S1 ledger "placed" vs S3 decisions "approved & sent"; D4 caveat stated on both).
- Live Trades: TIME shows UTC date, full stamp on hover (stacked on mobile); STATUS shows
  an explicit **Open** badge (backend CASE now emits 'open'; no 'approved' default);
  broker merge dedupes on `broker_trade_id` and enriches the matched ledger row with the
  broker's unrealized P&L instead of duplicating the position.
- Open Positions moved into the POSITIONS drill-down; TAKE-PROFIT now shows
  "+$X if hit" in quote currency (comparable to RISK).
- TopBar: pill reads **ACTIVE (demo)** (state first, verdict as colour + chip); chain
  renders SIGNALS→RISK→EXEC→MARKET with per-stage pulsing liveness dots; MARKET now
  resolves from the new `s2status.session`.
- All timestamps strictly UTC (`safeToDate` treats naive stamps as UTC, trims 9-digit
  fractions; `safeFmtDate` formats on the UTC clock). 146 frontend tests pass.
- Backend: `execute_to_records` scrubs pandas NaN → None (a NULL close_reason 500d
  /api/v1/trades once open rows started streaming).

### system2Executor (deployed to /opt/scalablebrain/system2/...)
- `HealthReporter.status()` publishes `session: {open, reason, as_of}` wired to
  `pipeline.is_in_session` — "market: unknown — session state not published" is resolved.

### scalablebrain-ams (deployed to /opt/scalablebrain/system3/ams/...)
- `posttrade/processor.py`: open positions book sl/tp from the approving decision's
  `proposed_sl/tp` (fill events cannot carry them — contract forbade the fields; both
  contracts now allow them optionally so your producer can start sending them).
- `posttrade/reconcile.py`: P-07 no longer clobbers sl/tp with NULL when a snapshot item
  simply doesn't report them (absent ≠ affirmed-none).
- `service/state.py` + `main.py`: `/state` now serves `daily_pnl` (publish-as-read of the
  same column gate Layer B consumes; was computed but never published).
- Migration 0013: nullable `trade_journal.broker_trade_id` (sqlite + postgres). The five
  open trades were backfilled on the VM via identity join to `ams_open_positions`
  (pair+units+entry_price) — no order_id+1 arithmetic.

### scalablebrain-bridge (deployed to /opt/scalablebrain/bridge/)
- Journal→`fact_live_trades` streaming is now actually running (it never had sqlalchemy
  or DATABASE_URL on the VM — installed into the S2 venv, DATABASE_URL added to
  `/etc/scalablebrain/telemetry.env`). Open rows stream with `realized_status='OPEN'`.
- Rows enriched at stream time: `confidence_score` + strategy backfill from
  `ams_decision_log.input_snapshot` joined on `signal_id`; `broker_trade_id` carried.
- New snapshot payload **`attribution`**: `{attributed, total, coverage,
  unattributed_signal_ids}` over the last 50 journal trades — currently 25/26 (0.96).
  If coverage drops, attribution broke; that is the alarm that prevents a silent D2 recurrence.
- Fix: ON CONFLICT COALESCE columns table-qualified (Postgres AmbiguousColumn).

## Verified live (2026-09-15 ~14:30Z)
- `latest-vm.json`: `session {open:true}`, `s3state.daily_pnl: 0.0`, `attribution` present, `errors: {}`.
- `/api/v1/trades`: all 5 open EUR_USD trades attributed (`reference_pullback_continuation`,
  scores ~0.47, resolution `ledger`), status `open`, live unrealized P&L, no duplicates.
- Units `s3-ams`, `system2`, `telemetry-pub` active, journals clean.

## Rollback
- VM: `sudo tar xzf /opt/scalablebrain/backups/pre-telemetry-audit-20260915.tgz -C /` then
  restart the three units. Migration 0013 is additive (nullable column) — safe to leave.
- Dashboard: redeploy the previous revision or re-pin traffic.

## Follow-ups for you
1. **FillEvent producer**: contracts now accept optional `stop_loss_price`,
   `take_profit_price`, `broker_trade_id` — your `fill_producer.py` already builds all
   three. Once redeployed S2-side, journal rows carry the trade id natively and AMS books
   sl/tp from the event instead of the decision snapshot.
2. **AccountSnapshot**: position items may now carry `sl`/`tp` — sending them lets P-07
   mirror broker brackets and will flip `reconciliation.state` to `consistent` for the
   five pre-fix positions.

## Addendum (same day, ~15:30Z): Risk view fixed; assets-chart branch converged

- `/api/v1/risk` now publishes `positionValueAcctCcy`, `exposurePctOfNav`,
  `marginUtilizationPct`, `accountCurrency` (broker positionValue vs NAV — same
  currency, real ratio). `netNotionalExposure` is still published but the UI no
  longer renders it with a percent sign ("500646.5% of capital" is dead).
  `correlationRiskScore` is null (no engine exists); the exception fallback
  returns nulls + a reason instead of 0.0-everything; the concentration alert
  names the asset and share. Risk view: OPEN POSITION VALUE (CAD, % of NAV,
  leverage), Margin Utilization gauge (margin used / NAV), Gate Posture mode
  reads s3state.mode (was showing "enforce" on the demo account).
- Gate layers P (strategy provenance) and S (account-truth freshness, F-208)
  added to the dashboard's layer table — the nameless "S" stage is named.
- The assets live-chart branch (`feat/assets-live-chart`) was merged into
  `telemetry-audit-2026-09-15`; both agents' deploys had raced (the chart
  deploy briefly served a bundle without the risk fixes). The union is live as
  revision telemetry-dashboard-00101, verified in-browser: Risk and Assets
  views render, zero console errors. If you deploy the dashboard again, build
  from `telemetry-audit-2026-09-15` (or merge it first) — it is the superset.
