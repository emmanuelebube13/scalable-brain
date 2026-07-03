# AMS-001 — AMS Database Schema

- **Task ID**: AMS-001
- **System**: System 3 — Account Management
- **Priority**: P0-Critical
- **Estimated Effort**: 2d
- **Prerequisites**: FND-004
- **External Dependencies**:
  - **Canonical datastore (FND-004)** — the ratified engine (SQL Server 2022 `ForexBrainDB` vs PostgreSQL/TimescaleDB). *Why:* DDL types, identity columns, and `NOW()`/`SYSUTCDATETIME()` defaults differ; the schema must be authored against the ratified engine. The AMS design assumes Postgres; the active primary is SQL Server.
  - **Backup/DR (FND-006)** — backup + tested restore covers these tables. *Why:* AMS tables are the system of record for risk and audit.

## Objective
Create the AMS schema (`AMS_Account_State`, `AMS_Decision_Log`, `AMS_Circuit_Breaker_Log`, `trade_journal`, `equity_curve`, `daily_summary`, `regime_exposure`, `strategy_performance`, `risk_state`) with indexes and retention.

## Current State
**New.** No AMS tables exist. `ForexBrainDB` holds the existing `Fact_*`/`Dim_*` tables; `Fact_Signals` is the signal source referenced by `AMS_Decision_Log.signal_id`, `Fact_Macro_Events` feeds time-based rules, and `Fact_Live_Trades` is Layer 4's existing trade log (distinct from the richer AMS `trade_journal`). Risk thresholds today live as constants in `src/layer4_executor/live_pipeline.py` and `src/layer7/oanda_executor.py`, not in a table.

## Target State
Nine AMS tables exist in the canonical DB with primary keys, indexes for the gate's hot read paths, UTC-aware timestamps, and a documented retention/backup policy. Types are portable (decimal/integer/varchar/timestamp/text) so the schema is identical in intent whether FND-004 chooses SQL Server or Postgres. A single seed row exists in `AMS_Account_State` (mode=`DEMO`, sub_state=`ACTIVE`).

## Technical Specification

### Engine portability note
Use a single migration file under `src/sql/migrations/` (per repo convention). Where the doc shows `SERIAL`/`NOW()` (Postgres), the SQL Server equivalent is `INT IDENTITY(1,1)` / `SYSUTCDATETIME()`. All timestamps are **UTC**.

### Table: `AMS_Account_State` (current account truth; one row per managed account)
| Column | Type | Notes |
|--------|------|-------|
| account_id | PK identity | |
| mode | VARCHAR(20) | DEMO, MICRO_LIVE, SMALL_LIVE, FULL_LIVE |
| sub_state | VARCHAR(20) | ACTIVE, CAUTION, PAUSED, CIRCUIT_BROKEN, RECOVERY |
| broker_account_id | VARCHAR(50) | OANDA account id |
| base_currency | VARCHAR(3) | USD |
| starting_balance | DECIMAL(15,2) | |
| current_balance | DECIMAL(15,2) | |
| current_equity | DECIMAL(15,2) | |
| peak_equity | DECIMAL(15,2) | monotonic; basis for drawdown |
| current_drawdown_pct | DECIMAL(5,2) | (peak−equity)/peak ×100 |
| daily_pnl | DECIMAL(15,2) | realized today (UTC) |
| daily_start_equity | DECIMAL(15,2) | equity at UTC-day open |
| weekly_pnl | DECIMAL(15,2) | |
| weekly_start_equity | DECIMAL(15,2) | |
| consecutive_wins | INTEGER | |
| consecutive_losses | INTEGER | resets on any win |
| total_trades_today | INTEGER | |
| max_risk_per_trade_pct | DECIMAL(5,2) | effective cap for current mode |
| circuit_break_reason | VARCHAR(255) | NULL unless broken |
| last_updated | TIMESTAMP | default UTC now |

### Table: `AMS_Decision_Log` (every gate decision; append-only)
| Column | Type | Notes |
|--------|------|-------|
| decision_id | PK identity | |
| timestamp | TIMESTAMP | UTC |
| signal_id | INTEGER | FK to `Fact_Signals` |
| regime_at_decision | VARCHAR(50) | |
| strategy_name | VARCHAR(100) | |
| pair | VARCHAR(10) | |
| direction | VARCHAR(4) | LONG/SHORT |
| xgboost_score | DECIMAL(4,3) | Layer 3 score |
| decision | VARCHAR(10) | APPROVED, REDUCED, DELAYED, REJECTED |
| rejection_reason | VARCHAR(255) | NULL if approved |
| suggested_size | DECIMAL(10,5) | lots, pre-gate |
| approved_size | DECIMAL(10,5) | lots, post-gate |
| account_balance | DECIMAL(15,2) | snapshot |
| account_drawdown_pct | DECIMAL(5,2) | snapshot |
| consecutive_losses | INTEGER | snapshot |
| daily_pnl | DECIMAL(15,2) | snapshot |
| gate_failed | VARCHAR(2) | which gate (A–J), NULL if approved |

### Table: `AMS_Circuit_Breaker_Log` (every breaker event + override; append-only)
| Column | Type | Notes |
|--------|------|-------|
| breaker_id | PK identity | |
| triggered_at | TIMESTAMP | UTC |
| reset_at | TIMESTAMP | NULL until reset |
| trigger_type | VARCHAR(50) | SOFT_STOP, DAILY_LIMIT, WEEKLY_LIMIT, MAX_DRAWDOWN, CONSECUTIVE_LOSS, MARGIN_PROXIMITY, CORRELATION_SHOCK, VOLATILITY_SPIKE, MANUAL |
| trigger_value | DECIMAL(10,2) | actual value |
| threshold | DECIMAL(10,2) | configured threshold |
| action_taken | TEXT | what was closed/stopped |
| reset_by | VARCHAR(50) | username or "auto" |
| notes | TEXT | mandatory for manual override/reset |

### Table: `trade_journal` (full per-trade record; all history) — columns mirror proposed design §3.3A
`journal_id` PK; `trade_id` VARCHAR(40); `timestamp` TIMESTAMP UTC; `pair`; `direction`; `strategy`; `regime_at_entry`; `entry_price` DECIMAL(12,5); `stop_loss` DECIMAL(12,5); `take_profit` DECIMAL(12,5); `position_size` DECIMAL(10,5); `risk_amount_usd` DECIMAL(15,2); `risk_percent` DECIMAL(5,2); `expected_rr` DECIMAL(6,2); `expected_duration_hours` INTEGER; `account_balance_at_entry` DECIMAL(15,2); `account_equity_at_entry` DECIMAL(15,2); `margin_used_percent` DECIMAL(5,2); `consecutive_loss_count_at_entry` INTEGER; `daily_pnl_at_entry` DECIMAL(15,2); `drawdown_at_entry` DECIMAL(5,2); `exit_price` DECIMAL(12,5) NULL; `exit_time` TIMESTAMP NULL; `realized_pnl_usd` DECIMAL(15,2) NULL; `exit_reason` VARCHAR(40) NULL; `actual_duration_hours` DECIMAL(8,2) NULL; `slippage_pips` DECIMAL(6,2) NULL; `broker_order_id` VARCHAR(50) NULL; `decision_id` INTEGER NULL (FK `AMS_Decision_Log`).

### Table: `equity_curve` (all history)
`point_id` PK; `timestamp` TIMESTAMP UTC; `balance` DECIMAL(15,2); `equity` DECIMAL(15,2); `drawdown_pct` DECIMAL(5,2); `peak_equity` DECIMAL(15,2).

### Table: `daily_summary` (all history)
`summary_date` DATE PK (UTC); `realized_pnl` DECIMAL(15,2); `trades_count` INTEGER; `wins` INTEGER; `losses` INTEGER; `win_rate` DECIMAL(5,2); `max_drawdown_pct` DECIMAL(5,2); `start_equity` DECIMAL(15,2); `end_equity` DECIMAL(15,2).

### Table: `regime_exposure` (last 365 days)
`row_id` PK; `as_of_date` DATE; `regime_label` VARCHAR(50); `time_in_regime_hours` DECIMAL(10,2); `realized_pnl` DECIMAL(15,2); `trades_count` INTEGER; `win_rate` DECIMAL(5,2).

### Table: `strategy_performance` (last 365 days) — read by Gate Layer F
`row_id` PK; `as_of_date` DATE; `strategy_name` VARCHAR(100); `regime_label` VARCHAR(50); `trades_count` INTEGER; `win_rate` DECIMAL(5,2); `avg_win` DECIMAL(15,2); `avg_loss` DECIMAL(15,2); `win_loss_ratio` DECIMAL(8,4); `rolling_sharpe_30d` DECIMAL(8,4); `max_drawdown_pct` DECIMAL(5,2); `expectancy` DECIMAL(15,2); `backtest_win_rate` DECIMAL(5,2); `backtest_sharpe` DECIMAL(8,4); `is_quarantined` BIT/BOOLEAN.

### Table: `risk_state` (current only) — fast-read snapshot for the gate
`risk_state_id` PK; `as_of` TIMESTAMP UTC; `active_breakers` TEXT (JSON list); `daily_loss_budget_remaining_pct` DECIMAL(5,2); `drawdown_multiplier` DECIMAL(4,2); `consecutive_loss_multiplier` DECIMAL(4,2); `stage_multiplier` DECIMAL(4,2); `cooling_until` TIMESTAMP NULL; `notes` TEXT.

### Indexes
- `AMS_Decision_Log`: index on `(timestamp)`, `(signal_id)`, `(decision)`, `(strategy_name, regime_at_decision)`.
- `AMS_Circuit_Breaker_Log`: index on `(triggered_at)`, `(trigger_type)`, partial/filtered on `reset_at IS NULL` (active breakers).
- `trade_journal`: index on `(timestamp)`, `(strategy, regime_at_entry)`, unique on `(broker_order_id)` (idempotent fills), index on `(exit_time)`.
- `equity_curve`: index on `(timestamp)`.
- `strategy_performance`: unique on `(as_of_date, strategy_name, regime_label)`.

### Retention / backup (ties to FND-006)
- All-history (no purge): `trade_journal`, `equity_curve`, `daily_summary`, `AMS_Decision_Log`, `AMS_Circuit_Breaker_Log`. (Decision/breaker logs are audit records — never auto-deleted.)
- Rolling 365-day: `regime_exposure`, `strategy_performance` (a scheduled job trims older rows).
- Current-only: `AMS_Account_State` (one row/account), `risk_state` (one row).
- Backup: included in FND-006 daily backup; restore tested into a clean DB. Encryption at rest per the chosen engine.

## Testing & Validation
- DDL applies cleanly on the FND-004 engine; rolling back the migration drops only AMS tables.
- Insert/read fixtures for each table; verify PK/identity and UTC defaults.
- Idempotency: inserting two fills with the same `broker_order_id` violates the unique index (proves AMS-007 can dedupe).
- Index presence/usage check: an `AMS_Decision_Log` lookup by `signal_id` and a `strategy_performance` lookup by `(strategy, regime)` use the index (these are gate hot paths — must be O(log n)).
- Retention job dry-run trims only > 365-day `regime_exposure`/`strategy_performance` rows and never touches audit logs.
- Restore test (with FND-006): backup → restore into clean env → row counts match.

## Rollback Plan
The schema is **additive** — it creates only new `AMS_*` and lowercase AMS tables and does not alter existing `Fact_*`/`Dim_*`. Rollback = run the down-migration to drop the nine tables; no existing data is touched. Until AMS-002 connects, the tables are inert.

## Acceptance Criteria
- [ ] All nine tables exist on the FND-004-ratified engine with the documented columns and UTC timestamp defaults.
- [ ] All listed indexes and the `trade_journal.broker_order_id` unique constraint exist.
- [ ] A seed `AMS_Account_State` row (DEMO / ACTIVE) is present.
- [ ] Retention policy is documented and a trim dry-run leaves audit logs intact.
- [ ] Migration is reversible and is covered by the FND-006 backup + a tested restore.

## Notes & Risks
- **FND-004 churn** is the top risk; keep types portable and avoid engine-specific features in the contract. If FND-004 picks Postgres, the AMS design's assumptions hold directly; if SQL Server, swap identity/timestamp syntax only.
- `signal_id` FK targets `Fact_Signals`; if FND-004 splits time-series to TimescaleDB, ensure the FK target still resolves or degrade to a soft reference.
- Keep `trade_journal` richer than the existing `Fact_Live_Trades` (which lacks fill/slippage columns per CLAUDE.md) — AMS owns the full record; do not retrofit `Fact_Live_Trades`.
