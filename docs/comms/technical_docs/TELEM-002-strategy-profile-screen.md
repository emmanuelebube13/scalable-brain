# TELEM-002 — "Strategy" Screen on the Telemetry Dashboard (Agent Prompt)

> **STATUS UPDATE 2026-07-16: a v1 of this screen is ALREADY LIVE.** Built as screen
> 07 "Strategy" (`telemetry-dashboard/src/screens/Strategy.jsx`), fed by a `strategy`
> payload in `bridge/telemetry_publisher.py` (60s refresh; cloud: in the snapshot;
> local dev: mirrored to `public/strategy.json` — that file is deliberately EXCLUDED
> from the Cloud Run static dir, it would bypass the token). Panels 1–6 below exist
> in basic form. Running this prompt now means ENHANCING v1 — notably: S1 catalog
> descriptions once S1-EXPORT-002 lands, trades/day-in-window stat, per-pair live
> stats, equity-by-strategy — not rebuilding it. Read Strategy.jsx first.

**Run on: this machine.** Touches: `telemetry-dashboard/` (React/Vite),
`bridge/telemetry_publisher.py`, `cloud/telemetry-web/` (redeploy). Read
`deployment-guide/09-LIVE-SIGNAL-PIPELINE.md` and the dashboard conventions in
`telemetry-dashboard/src/` first (theming rules: CSS custom properties in
`index.css` only; light default + dark toggle; mobile drawer shell — see
`memory: telemetry-web-hosting` notes replicated in DEPLOY.md).

## Goal

A new dashboard screen **"Strategy"** answering, at a glance, the operator's
questions: what strategy is running, why it qualified, on which pairs/regimes, what
trading style it is, how often it trades, and whether live performance tracks the
backtest. Works on both local dev and the hosted Cloud Run site.

## Data sources (in order of authority)

1. **Active model set** (`system2/.../state/model-cache/active/`):
   `regime_strategy_map.json` (serializer v1.0.0: `regimes → [{strategy_id, variant,
   rank, metrics{profit_factor, sharpe, win_rate, max_drawdown, recovery_factor,
   trade_count, oos_months}}]`, plus `gates`, `ranking_rule`, `rejection_summary`,
   `validation_design`), `strategy_weights.json`, `champion_manifest.json`
   (`dynamic_thresholds`, `oos_uplift`), `model_metadata.json`.
2. **S3 DB** (`system3/ams/state/db/ams.db`, read-only): `trade_journal` (live trades:
   pair, regime_at_entry, direction, realized_pnl, entry/exit times → live WR,
   expectancy, avg hold, frequency), `strategy_performance`, `stage_history`,
   `equity_curve`, `daily_summary`.
3. **S2 config** (`.env.system2`): `SIGNAL_INSTRUMENTS` vs `TRADEABLE_INSTRUMENTS`.
4. **Optional enrichment** when `gs://…/system1/analytics/latest.json` exists
   (S1-EXPORT-002): catalog descriptions + frequency stats. Degrade gracefully
   (render "pending System 1 export") when absent.

## Plumbing

Follow the existing pattern end-to-end: add a `strategy` payload to
`bridge/telemetry_publisher.py`'s snapshot (it already mirrors six endpoints; add a
seventh source that reads the files/DB above directly — keep reads cheap, refresh this
payload at most every 60 s, not 5 s), then render from the snapshot in cloud mode and
from a local aggregation in dev mode (`src/connection.js` handles both). Redeploy
Cloud Run per `cloud/telemetry-web/DEPLOY.md` (same TELEMETRY_TOKEN).

## Screen content (panels)

1. **Strategy card** — name (`Range_Stochastic_Divergence`), family/description (from
   S1 export when present), qualified variants + regimes, portfolio weights, the
   ranking rule and gates with pass values; "68 of 72 candidate variants rejected"
   from `rejection_summary` (integrity signal).
2. **Backtest metrics grid** — per regime×granularity cell: PF, Sharpe, WR, MaxDD,
   RF, trade count, OOS months (straight from the map's `metrics`).
3. **Coverage map** — 8 watchlist pairs × status: TRADEABLE (EUR_USD, GBP_USD,
   AUD_USD) / blocked-S2-allowlist (NZD_USD) / blocked-no-conversion-rate (crosses),
   derived live from the configs, not hard-coded.
4. **Trading style card** — derived, not hard-coded: granularity, SL/TP ATR multiples,
   max hold (S3 `risk_config.json` `time_rules`), weekly window rendered in BOTH UTC
   and the browser's local timezone, "flat weekends", "no High-Vol entries" from
   `empty_regimes`.
5. **Live vs backtest** — from `trade_journal`: live trade count, WR, avg R (realized
   pnl / risk_amount), avg hold, trades/day-in-window; side-by-side with the backtest
   priors per regime; a small "sample too small (<30)" badge until n≥30.
6. **Stage progress** — current stage from `ams_account_state`/`stage_history` +
   progress toward advancement (trades done /50, win rate vs 45%, weeks, breakers) —
   this is the operator's "is it working" meter (question 5).

## Rules

- Read the `dataviz` conventions already used by the dashboard (existing screens);
  reuse the validated palette tokens; tabular-nums for metric grids.
- Never block the dashboard on a missing source — every panel renders a specific
  "unavailable: <why>" state.
- No secrets in the snapshot (it's served through the token-gated Cloud Run app, but
  keep account ids/keys out anyway).
- Update `telemetry-dashboard-v1` docs/DEPLOY.md; bump the Cloud Run revision.

## Verification

Local `npm run dev` renders all six panels from live files; hosted site shows the same
after redeploy (headless check like the 07-14 verification); kill S3 → panels 5–6 show
their unavailable state while the rest still render.
