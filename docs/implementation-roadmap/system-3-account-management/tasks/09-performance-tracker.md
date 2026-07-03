# AMS-009 — Performance Tracker

- **Task ID**: AMS-009
- **System**: System 3 — Account Management
- **Priority**: P1-High
- **Estimated Effort**: 3d
- **Prerequisites**: AMS-007
- **External Dependencies**:
  - **DB (AMS-001)** — read `trade_journal`/`equity_curve`; write `daily_summary`, `regime_exposure`, `strategy_performance`. *Why:* metrics are derived from the journal and feed Gate Layer F and the deployment manager.
  - **Layer 5 telemetry (EXEC-009)** — reads these metrics for dashboards. *Why:* observability without duplicating decision logic.

## Objective
Build the performance tracker (equity curve, rolling 30-day Sharpe/Calmar, win/loss journal, per-strategy & per-regime attribution, duration analytics).

## Current State
**New.** No live performance analytics exist. `equity_curve`/`trade_journal` are populated by AMS-007 but nothing computes Sharpe/Calmar/attribution. Layer 0 produces backtest metrics; this is the *live* counterpart.

## Target State
A batch/periodic analytics job (and on-close incremental updates) that computes, from `trade_journal`/`equity_curve`: the equity curve, rolling 30-day Sharpe and Calmar, win/loss journal stats, per-strategy and per-regime attribution (win rate, avg win/loss, win-loss ratio, expectancy, max DD), and trade-duration analytics (actual vs expected). It writes `daily_summary`, `regime_exposure`, and `strategy_performance` — the last of which is **read by Gate Layer F (AMS-005)** and the deployment manager (AMS-012) and decay auditor (AMS-010).

## Technical Specification

### Metrics (formulas)
- **Equity curve**: from `equity_curve` points (already appended by AMS-007); compute running peak + drawdown.
- **Rolling 30-day Sharpe**: `mean(daily_returns_30d) / std(daily_returns_30d)` (annualized as configured); alert threshold < 0.5 (review).
- **Calmar**: `annualized_return / max_drawdown`; alert < 1.0 (reduce size).
- **Per-trade expectancy**: `(win% × avg_win) − (loss% × avg_loss)`; alert < 0 (stop strategy).
- **Win/loss journal**: counts, win rate, avg win, avg loss, win-loss ratio, largest win/loss, by overall / strategy / regime / pair.
- **Duration analytics**: actual hold (`exit_time − timestamp`) vs `expected_duration_hours`; flag systematic over/under-holding.
- **Slippage analytics**: from `slippage_pips` (entry expected vs actual).

### Writes
- `daily_summary` (one row/UTC-day): realized P&L, trades, wins/losses, win rate, max DD, start/end equity. Written at the UTC-day rollover (coordinated with AMS-007) and at the 21:00 UTC daily-summary report time.
- `strategy_performance` (per `as_of_date × strategy × regime`): trades_count, win_rate, avg_win, avg_loss, win_loss_ratio, rolling_sharpe_30d, max_drawdown_pct, expectancy, plus `backtest_win_rate`/`backtest_sharpe` carried for AMS-010, and `is_quarantined`. **Insufficient sample → leave win_rate NULL** so Gate Layer F's "no data → 0.1% demo" path triggers (never fabricate stats).
- `regime_exposure` (per `as_of_date × regime`): time-in-regime, realized P&L, trades, win rate.

### Cadence & footprint
- Incremental on each CLOSE (cheap rolling updates) + a periodic full recompute (e.g. nightly) for correctness. Use pandas over bounded windows; keep memory small for Computer 3 (process by date range, not the full history at once).

### Periodic reports (data side; delivery via AMS-011)
- Daily Summary (21:00 UTC), Weekly Report (Sunday 20:00 UTC), Monthly Deep Dive — compute the figures here; AMS-011 formats and sends.

## Testing & Validation
- Unit: Sharpe/Calmar/expectancy on a fixed return series match hand-computed values.
- Attribution: a fixture of mixed trades produces correct per-strategy and per-regime win rates / expectancy.
- No-data guard: a strategy×regime with < min sample leaves win_rate NULL (verify Gate F then uses the 0.1% path).
- Duration/slippage: known trades produce correct actual-vs-expected and slippage figures.
- Idempotency: re-running the batch for a date produces identical `daily_summary`/`strategy_performance` rows (upsert, no dupes).
- Footprint: full recompute over a year of fixtures stays within Computer-3 memory budget.

## Rollback Plan
Read-mostly and additive — it only derives metrics into tables consumed downstream. Rollback = disable the job; Gate Layer F then sees stale/empty `strategy_performance` and falls back to the 0.1% demo-size path (safe). No source data (`trade_journal`/`equity_curve`) is mutated.

## Acceptance Criteria
- [ ] Computes equity curve, rolling 30-day Sharpe, Calmar, expectancy, and win/loss stats matching hand-computed fixtures.
- [ ] Writes per-strategy×regime `strategy_performance` consumed by Gate Layer F, leaving win_rate NULL on insufficient sample.
- [ ] Writes `daily_summary` and `regime_exposure`; produces the figures for daily/weekly/monthly reports.
- [ ] Duration and slippage analytics are produced per trade.
- [ ] Batch is idempotent and fits the Computer-3 footprint.

## Notes & Risks
- `strategy_performance` is now on the gate's hot path indirectly (Layer F reads it); ensure the write cadence keeps it fresh enough that sizing reflects recent live performance, but never blocks the gate.
- Keep live metrics strictly separate from Layer 0 backtest metrics; AMS-010 compares the two — conflating them would hide decay.
- Annualization factor and "30-day" window definitions must be config-driven and documented so Sharpe is comparable across reports.
