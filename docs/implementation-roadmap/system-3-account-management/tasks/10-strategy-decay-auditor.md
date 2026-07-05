# AMS-010 — Strategy-Decay Auditor (Layer 6)

- **Task ID**: AMS-010
- **System**: System 3 — Account Management
- **Priority**: P1-High
- **Estimated Effort**: 3d
- **Prerequisites**: AMS-009
- **External Dependencies**:
  - **DB (AMS-001)** — read `strategy_performance`/`trade_journal`; write `is_quarantined` + decay events. *Why:* compare live vs backtest and quarantine failing strategies.
  - **Backtest baselines (Layer 0 / object storage FND-001)** — backtest win rate/Sharpe per strategy×regime. *Why:* the divergence baseline.
  - **Notification (AMS-011)** — flag/quarantine alerts. *Why:* the operator must know when a strategy is benched.

## Objective
Embed the Layer 6 auditor as strategy-decay detection (live vs backtest divergence > 20% → flag/quarantine) with reconciliation of trade outcomes.

## Current State
The existing Layer 6 (`src/layer6_auditor/trade_auditor.py`) reconciles unresolved `Fact_Live_Trades` outcomes post-hoc but does **not** detect strategy decay vs backtest. This task embeds and extends that role inside System 3 against the live `trade_journal` and `strategy_performance`.

## Target State
A periodic auditor that: (1) reconciles trade outcomes (ensures every closed trade has a resolved win/loss/P&L in `trade_journal`, patching from broker data where needed), and (2) compares live rolling metrics to the backtest baseline per strategy×regime; when live performance diverges **> 20% below** backtest, it **flags** the strategy and, on sustained divergence, **quarantines** it (`strategy_performance.is_quarantined = true`) so Gate Layer F rejects it. Quarantine and clearance are logged and notified.

## Technical Specification

### Reconciliation (carry-over of Layer 6 role)
- For each closed `trade_journal` row missing realized outcome, resolve from broker transaction data relayed by System 2 (and cross-check `Fact_Live_Trades`). Log any unresolved trade for manual review. This keeps `strategy_performance` (AMS-009) trustworthy.

### Decay detection
- Inputs per strategy×regime: live `win_rate`, `rolling_sharpe_30d`, `expectancy`, `win_loss_ratio` (from `strategy_performance`); baselines `backtest_win_rate`, `backtest_sharpe`.
- **Minimum live sample** before judging: ≥ 20 live/demo trades (per proposed design §7.6). Below that, no decay action (Gate F's no-data path already keeps size at 0.1%).
- **Divergence test**: relative shortfall of a metric vs its baseline. Live diverges > 20% below backtest →
  - **FLAG** (first/transient breach): record a decay event, notify, keep trading but Gate F's measured-win-rate sizing already reduces it.
  - **QUARANTINE** (sustained breach over N evaluation windows): set `is_quarantined=true` → Gate Layer F treats the strategy as REJECT for that regime; notify CRITICAL.
- Secondary checks (proposed design §7.6): live win rate within ±10% of backtest; live avg win/loss within ±15%. Outside these → flag.
- **Clearance**: a quarantined strategy clears only after a manual review or a configured recovery window with live metrics back within tolerance; clearance is logged + notified.

### Pseudo-code
```
for (strategy, regime) in active_combos:
    sp = strategy_performance[strategy, regime]
    if sp.trades_count < 20: continue
    shortfall = (sp.backtest_win_rate - sp.win_rate) / sp.backtest_win_rate
    if shortfall > 0.20:
        if breaches_sustained(strategy, regime): quarantine(); notify(CRITICAL)
        else: flag(); notify(HIGH)
    elif within_tolerance(sp): maybe_clear(strategy, regime)
    log_decay_event(...)
```

### Storage
- Reuse `strategy_performance.is_quarantined`; record decay events (timestamp, strategy, regime, metric, live, backtest, shortfall, action) — either a dedicated `strategy_decay_log` table or as structured entries. Keep an audit trail.

### Retrain trigger (advisory)
- Per proposed design §7.7, surface a retrain recommendation when rolling 14-day Sharpe < 0.3 or after any circuit breaker; emitted as a notification/flag to System 1 (this task does **not** retrain — it signals).

## Testing & Validation
- Unit: a strategy with live win rate 20%+ below backtest over sustained windows gets quarantined; a one-off dip only flags.
- Sample guard: < 20 trades → no decay action.
- Reconciliation: an unresolved closed trade is resolved from broker data; a truly unresolvable one is flagged for manual review, not silently dropped.
- Quarantine effect: a quarantined strategy×regime is rejected by Gate Layer F (joint test with AMS-005).
- Clearance: recovered metrics clear quarantine only via the configured path; logged + notified.
- Idempotency: re-running the auditor doesn't double-log or thrash quarantine state.

## Rollback Plan
Detection is advisory-by-default behind a flag (`AMS_DECAY_ENFORCE`). With enforcement off, it flags + notifies but does not set `is_quarantined`, so the gate is unaffected. Rollback = disable enforcement (or clear all quarantines via AMS-014). Reconciliation is read/patch only and never deletes journal history.

## Acceptance Criteria
- [ ] Reconciles closed-trade outcomes so `strategy_performance` is trustworthy; unresolved trades are surfaced, not dropped.
- [ ] Detects > 20%-below-backtest divergence per strategy×regime with a ≥20-trade minimum sample.
- [ ] Sustained divergence quarantines the strategy (Gate F then rejects it); transient divergence only flags.
- [ ] Quarantine, clearance, and retrain recommendations are logged and notified.
- [ ] Enforcement is flag-gated and idempotent.

## Notes & Risks
- Backtest baselines must be the *same* strategy/regime definitions as live, or divergence is meaningless; pin the baseline source to the promoted Layer 0 artifacts (FND-001).
- Quarantining is powerful — a noisy detector could bench a good strategy on variance; require sustained breach + minimum sample, and make clearance easy via AMS-014.
- This complements, not replaces, the existing `Fact_Live_Trades` reconciliation; ensure no double-resolution conflict.
