# System 3 — Account Management System (AMS), "The Guardian"

> Part of the **Scalable Brain — Migration & Implementation Architecture Plan**.
> Audience: Staff PM + Principal Architect. Author: Principal Software Architect.

## Overview

System 3 is a **new, always-on middleware** that sits as a **Decision Gate between Layer 3 (the ML gatekeeper) and Layer 4 (the executor)**. It does **not** replace any existing layer. Every signal that Layer 3 scores and approves must pass through System 3 before it can become a live order: System 3 reads scored signals off `Scored_Signal_Queue`, runs a sequential **10-layer Decision Gate (Layers A–J)**, and only then publishes an approved, correctly-sized order to `AMS_Outbound_Queue` for Layer 4 to execute. It also consumes fill confirmations on `AMS_Inbound_Queue`, maintains live account state, runs multi-layer circuit breakers, tracks performance, audits strategy decay, and notifies the operator.

System 3 runs on **Computer 3** — a lightweight, always-on host (Raspberry Pi 4, an old laptop, or a small VPS; **no GPU**). It must be the **simplest, most reliable** component in the platform. It does **math, not ML**. Its latency budget is **< 100 ms per decision on H1**, and its footprint must fit a 1–2 vCPU / 1–2 GB host.

**Safety coupling:** if System 3 is down or its outbound queue is stale (> 5 min), Layer 4 **pauses** rather than trading without risk approval (owned by EXEC-008). System 3 itself is **default-safe**: any uncertainty, missing data, or error inside the gate results in **REJECT**, never an approve.

> Note on the datastore: the AMS design assumes PostgreSQL, but the active primary DB is SQL Server 2022 (`ForexBrainDB`). The canonical-datastore decision is foundational task **FND-004**, on which **AMS-001** (schema) hard-depends. All AMS DDL/types in this folder are written to be portable and are finalized against whatever FND-004 ratifies.

## The 5 Inviolable Principles

1. **Preservation over profit.** Capital survival outranks every return target. When a rule and a profit opportunity conflict, the rule wins. The gate rejects on uncertainty.
2. **Dynamic position sizing.** No fixed lot sizes. Every position is sized from Quarter-Kelly and then scaled down by drawdown, consecutive-loss, regime-compatibility, and account-stage multipliers, with a 0.1% floor.
3. **Regime-aware risk.** A strategy's permission and size depend on its *measured live win rate in the current market regime*, not on its backtest alone.
4. **Circuit breakers.** Layered, automatic hard stops (soft stop, daily, weekly, max-drawdown, consecutive-loss, margin, correlation, volatility) that cannot be argued with — they fire on math and halt trading.
5. **Full transparency.** Every decision (approve / reduce / delay / reject + reasons), every state transition, every breaker event, and every human override is logged with full context and is auditable forever.

## Goals

1. Insert a reliable risk **Decision Gate** between Layer 3 and Layer 4 without changing the proven upstream/downstream layer logic.
2. Move scattered risk logic (correlation/exposure from `src/layer4_executor/live_pipeline.py`, Quarter-Kelly sizing from `src/layer7/oanda_executor.py`) into **one authoritative, testable component** so risk is decided in exactly one place.
3. Maintain a single source of truth for **account state** (mode × sub-state, balances, drawdown, counters) updated from real fills.
4. Enforce **graduated deployment** (Paper → Micro → Small → Full) so live capital is exposed only after demonstrated edge.
5. Give the solo operator **timely, multi-channel notifications** and **audited manual overrides** (pause, flat-all, breaker reset).
6. Detect **strategy decay** (live vs backtest divergence) and quarantine failing strategies before they bleed capital.

## Success Criteria

- [ ] Every Layer-3-approved signal is gated by System 3; no order reaches Layer 4 without an `AMS_Decision_Log` row recording the outcome and reasons.
- [ ] Median decision latency is **< 100 ms on H1** on the chosen Computer-3 host, measured under load.
- [ ] All eight circuit breakers fire correctly in simulated scenarios (incl. a March-2020-style gap/volatility shock) and are logged to `AMS_Circuit_Breaker_Log`.
- [ ] Position sizes match the Quarter-Kelly + multipliers + 0.1% floor specification to the cent across a fixture suite.
- [ ] On System 3 outage, Layer 4 pauses (verified jointly with EXEC-008); on restart, account state is reconstructed correctly from the DB and fills.
- [ ] Notifications deliver across Telegram + email with urgency routing, and a Telegram outage falls back to email.
- [ ] The gate **fails closed** (rejects) on missing strategy/regime data, DB errors, or stale inputs.

## Inviolable defaults at a glance

| Threshold | Value | Source |
|-----------|-------|--------|
| Max risk per trade | 2.0% | `risk_config.json` |
| Min risk per trade (floor) | 0.1% | `risk_config.json` |
| Kelly fraction | 0.25 (Quarter-Kelly) | `risk_config.json` |
| Daily loss → soft stop | ≥ 2% (−50% size, pause 30m) | circuit breakers |
| Daily loss → hard stop | ≥ 3% (stop 24h) | circuit breakers |
| Weekly loss → stop | ≥ 6% (0.5% next week) | circuit breakers |
| Max drawdown → circuit break | ≥ 20% (close all, RECOVERY) | circuit breakers |
| Consecutive losses → stop | 5 (24h cooling, manual review) | circuit breakers |
| Max concurrent trades | 5 | exposure limits |
| Max exposure per pair | 6% of equity | exposure limits |
| Max correlated exposure | 10% of equity | exposure limits |
| Stage risk multipliers | demo 0.5 / micro 0.5 / small 0.75 / full 1.0 | state machine |

## Task Index

| ID | Task | Priority | Effort | Prerequisites |
|----|------|----------|--------|---------------|
| AMS-001 | AMS database schema | P0-Critical | 2d | FND-004 |
| AMS-002 | Core service skeleton | P0-Critical | 3d | FND-002, FND-003, AMS-001 |
| AMS-003 | Decision Gate Layers A–C | P0-Critical | 3d | AMS-002, MODEL-008 |
| AMS-004 | Account state machine | P0-Critical | 3d | AMS-002 |
| AMS-005 | Risk engine — Kelly sizing (Gate D–G) | P0-Critical | 4d | AMS-004 |
| AMS-006 | Circuit-breaker system | P0-Critical | 3d | AMS-004 |
| AMS-007 | Post-trade processor | P0-Critical | 3d | AMS-004, EXEC-005 |
| AMS-008 | Decision Gate H–J + outbound queue | P0-Critical | 3d | AMS-005, AMS-006 |
| AMS-009 | Performance tracker | P1-High | 3d | AMS-007 |
| AMS-010 | Strategy-decay auditor (Layer 6) | P1-High | 3d | AMS-009 |
| AMS-011 | Notification service | P1-High | 3d | AMS-002, FND-003 |
| AMS-012 | Graduated deployment manager | P2-Medium | 3d | AMS-009 |
| AMS-013 | Weekend/holiday manager | P2-Medium | 2d | AMS-008 |
| AMS-014 | Human-override controls | P1-High | 2d | AMS-006 |

### Recommended execution order

1. **Foundation:** AMS-001 (schema, needs FND-004) → AMS-002 (service skeleton, needs FND-002/003).
2. **Core state & math:** AMS-004 (state machine) → AMS-005 (risk engine) and AMS-006 (breakers) in parallel.
3. **Gate ends & I/O:** AMS-003 (Gate A–C, needs MODEL-008 producing scored signals) and AMS-007 (post-trade, needs EXEC-005 fills) → AMS-008 (Gate H–J + outbound queue, needs AMS-005 + AMS-006). After AMS-008 the gate is end-to-end.
4. **Operate & protect:** AMS-011 (notifications), AMS-014 (overrides) early for safety; then AMS-009 (performance) → AMS-010 (decay auditor) and AMS-012 (deployment manager); AMS-013 (weekend/holiday) feeds Gate Layer I.

Each task is incremental and leaves a **stable, default-safe** system: until a gate layer exists, its check rejects (or the gate is feature-flagged off in DEMO).

## Cross-system dependencies (referenced by these tasks)

- **FND-002** — message queue: contracts for `Scored_Signal_Queue`, `AMS_Outbound_Queue`, `AMS_Inbound_Queue`.
- **FND-003** — secrets: Telegram bot token + chat ID, SMTP credentials, DB credentials.
- **FND-004** — canonical datastore decision (blocks AMS-001).
- **FND-005** — observability/SLOs: ships the < 100 ms latency SLO and System 3 health alerts.
- **FND-006** — backup/DR for the AMS tables.
- **MODEL-008** — Layer 3 producer of `Scored_Signal_Queue` (consumed by AMS-003).
- **EXEC-004** — Layer 4 consumer of `AMS_Outbound_Queue`.
- **EXEC-005** — Layer 4 producer of fill confirmations onto `AMS_Inbound_Queue` (consumed by AMS-007).
- **EXEC-008** — Layer 4 safety-pause when System 3 / its queue is down.
- **EXEC-009** — Layer 5 telemetry reads AMS state for dashboards.

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| DB ambiguity (SQL Server vs Postgres) churns the AMS schema after build | Medium | High | Block AMS-001 on FND-004; keep DDL portable (no DB-specific types in the contract); pin to FND-004's decision before AMS-002 connects. |
| Computer 3 (Pi/VPS) too slow to meet < 100 ms on H1 | Medium | High | Keep gate logic pure-math and in-memory; cache strategy/regime stats; avoid per-decision heavy I/O; FND-005 SLO monitors p95 latency; size host in FND-010. |
| System 3 outage trades unguarded or stalls execution | Medium | Critical | Layer 4 pauses on stale outbound queue (EXEC-008); AMS reconstructs state from DB+fills on restart; idempotent decision/fill processing. |
| Gate has a logic bug that approves what it should reject | Medium | Critical | Default-safe (reject on uncertainty); exhaustive fixture + scenario tests (March 2020); shadow/DEMO dry-run with full logging before any live mode. |
| Account-state drift vs broker truth (missed/duplicate fills) | Medium | High | Idempotent fill processing keyed on broker order ID; periodic reconciliation against OANDA account summary; alert on divergence. |
| Drawdown/peak-equity miscomputation under-protects capital | Low | Critical | Single authoritative drawdown calc with unit tests; peak-equity is monotonic and persisted; breaker re-evaluation on every fill. |
| Notification provider rate-limits or outage hides a critical alert | Medium | High | Urgency-based routing; per-channel rate-limit handling + backoff; CRITICAL events go to all channels; Telegram→email fallback; queued retry. |
| Secrets (Telegram/SMTP/DB) leak | Low | Critical | All secrets via FND-003; none in code/config files; least-privilege per host; encryption in transit. |
| Over-conservative gate rejects everything (no trades, no learning) | Medium | Medium | DEMO mode is a full dry-run with logging (never blocks learning); calibrate thresholds against historical signals; alert if rejection rate is abnormal. |
| Time/clock skew corrupts UTC-day budgets and time-based rules | Medium | Medium | NTP on Computer 3 (FND-008); all day/week boundaries computed in UTC; staleness windows from FND-002 queue contract. |
| Solo operator unavailable when a breaker needs manual reset | High | Medium | Notifications with clear next-steps; conservative auto-RECOVERY defaults; overrides (AMS-014) usable from mobile via Telegram. |
