# Dependencies & Prerequisites — System 3 (Account Management)

> Everything in this list must be provisioned (or a decision recorded) **before** the corresponding System 3 task can start or finish. System 3 is mostly **new**; it depends heavily on the foundational layer (FND-*) for its datastore, transport, secrets, host, and observability. Each entry states **what** and **why**.

## 1. Foundational tasks that gate System 3

| Item | What | Why | Gates |
|------|------|-----|-------|
| **Canonical datastore (FND-004)** | The ratified decision on SQL Server vs PostgreSQL/TimescaleDB for `ForexBrainDB` (the AMS design assumes Postgres; the active primary is SQL Server). | AMS tables (`AMS_Account_State`, `AMS_Decision_Log`, `AMS_Circuit_Breaker_Log`, `trade_journal`, `equity_curve`, `daily_summary`, `regime_exposure`, `strategy_performance`, `risk_state`) must be created against one canonical engine with portable types. | **AMS-001** (hard) |
| **Message queue (FND-002)** | Redis (recommended, AOF persistence, hosted on always-on Computer 3) or Postgres `LISTEN/NOTIFY` fallback, with documented contracts, backpressure, and staleness windows for `Scored_Signal_Queue`, `AMS_Outbound_Queue`, `AMS_Inbound_Queue`. | System 3 consumes scored signals and fill confirmations and publishes approved orders over these queues. | **AMS-002, AMS-003, AMS-007, AMS-008** |
| **Secrets management (FND-003)** | SOPS+age (or equivalent) holding the **Telegram bot token + operator chat ID**, **SMTP credentials**, and **DB credentials**, distributed per-host with least privilege. | System 3 sends notifications (Telegram/SMTP) and connects to the DB; no secret may live in code/config. FND-003 owns provisioning; AMS owns sending logic. | **AMS-002, AMS-011** |
| **Always-on host — Computer 3 (FND-002/005/008/010)** | A small VPS (1–2 vCPU / 1–2 GB) or Raspberry Pi 4/5 with reliable power + network, NTP-synced, on the private VPN. **No GPU.** | Hosts the always-on Guardian service and (optionally) Redis; must run 24/7 independent of the training box and meet the < 100 ms H1 latency budget. | **AMS-002** (deploy target) and all runtime tasks |
| **Observability/SLOs (FND-005)** | Lightweight logging/metrics shipping + alerting; the **< 100 ms decision-latency SLO** and a System-3-down alert. | System 3's reliability and latency must be monitored; if it is down, that fact must page the operator and Layer 4 must pause (EXEC-008). | **AMS-002** (health endpoint, structured logs), latency tests in AMS-003/005/008 |
| **Backup & DR (FND-006)** | Backup + tested restore for `ForexBrainDB`, including the AMS tables; retention aligned with each table. | Account state, journals, and audit logs are the system of record for risk and compliance; loss is unacceptable. | **AMS-001** (retention/backup notes) |
| **Inter-computer networking (FND-008)** | Tailscale/WireGuard VPN + TLS + NTP across the three hosts. | Cross-host queue/DB/API traffic must be private and encrypted; UTC-day budgets and staleness checks require clock sync. | All cross-host traffic from System 3 |

## 2. Cross-system dependencies (other agents' systems)

| Item | What | Why | Gates |
|------|------|-----|-------|
| **MODEL-008 (Layer 3 queue producer)** | Layer 3 writes scored signals to `Scored_Signal_Queue` with a defined message contract (signal id, pair, direction, strategy, regime, XGBoost score, proposed entry/SL/TP, timeframe). | This is System 3's **input**; the gate cannot run without it. | **AMS-003** |
| **EXEC-005 (Layer 4 fill producer)** | Layer 4 pushes fill/close confirmations to `AMS_Inbound_Queue` (broker order id, fill price/time, realized P&L on close, slippage, status). | Drives the post-trade processor that updates balance/equity/drawdown/counters and re-evaluates breakers. | **AMS-007** |
| **EXEC-004 (Layer 4 outbound consumer)** | Layer 4 reads approved orders from `AMS_Outbound_Queue`. | System 3's **output** consumer; defines the approved-order contract jointly with AMS-008. | **AMS-008** (contract) |
| **EXEC-008 (Layer 4 safety pause)** | Layer 4 pauses execution if `AMS_Outbound_Queue` is stale > 5 min or System 3 health fails. | Ensures the platform never trades without risk approval when the Guardian is down. | Cross-cutting safety; referenced by AMS-002/008 |
| **EXEC-009 (Layer 5 telemetry)** | Layer 5 reads AMS state (account state, decisions, breakers, performance) for the dashboard. | Read-only observability of System 3; AMS exposes a state/health read path. | AMS-002 (health), AMS-009 (metrics) |

## 3. External services & data feeds

| Item | What | Why | Used by |
|------|------|-----|---------|
| **Telegram bot** | Bot registered via @BotFather; token + operator chat ID stored in FND-003. | Real-time risk/operational alerts and mobile override entry point. | AMS-011, AMS-014 |
| **Email / SMTP sender** | Transactional SMTP relay with verified sender + credentials in FND-003. | Digests, weekly reports, and fallback when Telegram is unavailable. | AMS-011 |
| **OANDA v20 practice API (account-data endpoints)** | `/v3/accounts/{id}/summary`, `/openPositions`, `/openTrades`, `/transactions`. **Layer 4 / System 2 owns the API key and polls these**; System 3 receives the data over the queue / internal API, it does **not** hold the OANDA key. | Reconciliation of System 3's account state against broker truth (balance, equity, margin, open positions). | AMS-007 (reconciliation), AMS-004 |
| **`Fact_Macro_Events` table** | Existing NLP-populated macro/news events table in `ForexBrainDB`. | Feeds Gate Layer I time-based rules (reject/reduce within 2h of major events). | AMS-008, AMS-013 |
| **Holiday calendar** | A static/curated calendar of major market holidays (Christmas, New Year, Good Friday, July 4, etc.). | Weekend/holiday manager and Gate Layer I. | AMS-013 |

## 4. Existing assets to reconcile (no new purchase)

| Item | Current state | Why it matters |
|------|---------------|----------------|
| **Quarter-Kelly sizing** | Implemented in `src/layer7/oanda_executor.py` (`FRACTIONAL_KELLY=0.25`, `MAX_RISK_PERCENT=0.02`, `FIXED_WIN_RATE=0.45`, R:R calc). | The authoritative sizing logic **moves into the AMS risk engine (AMS-005)**; Layer 7 becomes a thin order placer using the size AMS provides. |
| **Correlation / exposure guards** | Implemented in `src/layer4_executor/live_pipeline.py` (`MAX_TOTAL_EXPOSURE_PCT=0.25`, `CORRELATION_THRESHOLD=0.85`, `CORRELATION_LOOKBACK_BARS=100`). | The portfolio correlation/exposure check **moves into Gate Layer H (AMS-008)** and is tightened to the AMS limits (6% per pair, 10% correlated, max 5 concurrent). |
| **`risk_config.json`** | Does not yet exist; thresholds are scattered as constants in Layer 4/7. | AMS-002 introduces `risk_config.json` as the single source of all risk thresholds (see proposed design §6.1). |
| **`Fact_Macro_Events`** | Populated by NLP but not yet enforced as a hard gate. | AMS-008/AMS-013 consume it for time-based rules. |

## 5. Decisions to record before downstream AMS work

1. **Datastore (FND-004)** — blocks AMS-001. Highest priority.
2. **Queue backend (FND-002)** — Redis vs Postgres NOTIFY; affects message contracts and staleness semantics for all three AMS queues.
3. **Computer 3 form factor** — Pi vs VPS; affects whether < 100 ms on H1 is achievable and where Redis is hosted.
4. **Where strategy×regime live stats live** — derived in AMS-009 and read by Gate Layer F; decide table/materialization so Gate reads are O(1).

## 6. Prerequisite ordering summary

- **Start after FND-004:** AMS-001.
- **Start after FND-002 + FND-003 + AMS-001:** AMS-002.
- **After AMS-002:** AMS-004; AMS-003 (also needs MODEL-008); AMS-011 (also needs FND-003).
- **After AMS-004:** AMS-005, AMS-006, AMS-007 (also needs EXEC-005).
- **After AMS-005 + AMS-006:** AMS-008. **After AMS-006:** AMS-014.
- **After AMS-007:** AMS-009 → AMS-010, AMS-012. **After AMS-008:** AMS-013.
