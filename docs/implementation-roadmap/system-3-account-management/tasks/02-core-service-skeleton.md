# AMS-002 — Core Service Skeleton

- **Task ID**: AMS-002
- **System**: System 3 — Account Management
- **Priority**: P0-Critical
- **Estimated Effort**: 3d
- **Prerequisites**: FND-002, FND-003, AMS-001
- **External Dependencies**:
  - **Message queue (FND-002)** — Redis (or Postgres NOTIFY) client + connection. *Why:* the service must attach to `Scored_Signal_Queue`, `AMS_Outbound_Queue`, `AMS_Inbound_Queue` (consumers/producers added in later tasks).
  - **Secrets (FND-003)** — DB credentials, Telegram/SMTP tokens injected from the secrets store. *Why:* no secret may live in code/config.
  - **Computer 3 host** — always-on 1–2 vCPU / 1–2 GB VPS or Pi, NTP-synced, on the VPN. *Why:* deploy target; latency budget feasibility.
  - **Observability (FND-005)** — log/metric shipping + health-check scrape. *Why:* System-3-down must page; latency SLO must be measured.

## Objective
Stand up the System 3 always-on async service skeleton (config loader incl. `risk_config.json`, DB + queue connections, health endpoint, structured logging).

## Current State
**New.** No System 3 process exists. There is no `risk_config.json`; risk constants live inline in Layer 4/7. The repo convention is Python 3.12 with rotating file logs (`%(asctime)s | %(levelname)-8s | %(name)s | %(message)s`, 10 MB × 14 backups) and `.env`-based config; AMS will instead source secrets from FND-003.

## Target State
A lean, single-process async service (e.g. `src/ams/` package; `python -m ams` entrypoint) that on startup: loads `risk_config.json` + env/secret config, opens validated DB and queue connections, exposes a `/health` and `/ready` endpoint, emits structured logs, and runs an idle main loop with placeholder consumer/producer hooks (filled by AMS-003/007/008). It defaults to `mode=DEMO` and refuses to start if config is invalid or the DB is unreachable (fail-fast, default-safe).

## Technical Specification

### Process model
- Single asyncio event loop; lightweight tasks: queue consumers (added later), a periodic state/health heartbeat, and the HTTP health server (e.g. small ASGI). No GPU, no heavy frameworks — fit Computer 3.
- Graceful shutdown on SIGTERM: stop consuming, flush logs, close connections.

### Config loader
- `risk_config.json` (single source of risk truth; see proposed design §6.1). Key groups and selected keys:
  - `account`: `mode` (demo/micro_live/small_live/full_live), `demo_balance_usd`, `live_balance_usd`, `currency`, `max_leverage`, `broker`.
  - `position_sizing`: `method=quarter_kelly`, `kelly_fraction=0.25`, `max_risk_per_trade_percent=2.0`, `min_risk_per_trade_percent=0.1`, `atr_multiplier_for_stop=1.5`, `max_position_size_lots=1.0`.
  - `circuit_breakers`: `daily_loss_limit_percent=3.0`, `weekly_loss_limit_percent=6.0`, `max_drawdown_percent=20.0`, `max_consecutive_losses=5`, `soft_stop_loss_percent=2.0`, `soft_stop_pause_minutes=30`, `margin_warning_percent=150`, `margin_close_percent=120`, `volatility_spike_std=2.0`, `volatility_reduction_factor=0.5`.
  - `exposure_limits`: `max_concurrent_trades=5`, `max_trades_per_day=8`, `max_trades_per_pair_per_day=2`, `max_pair_exposure_percent=6.0`, `max_correlated_exposure_percent=10.0`, `max_total_heat_percent=15.0`.
  - `trade_parameters`: `friday_close_hour_utc=18`, `sunday_open_hour_utc=22`, `max_trade_duration_hours=72`, `min_trade_duration_hours=6`, `allow_over_weekend=false`, trailing/breakeven R.
  - `pairs`: `primary`, `secondary`, `correlation_groups`.
  - `notification`: per-event toggles, `channels=["telegram","email"]`.
- Schema-validate `risk_config.json` on load (e.g. pydantic). Any missing/invalid key → **refuse to start**.
- Env vars (from FND-003, not committed): `AMS_DB_URL` (or discrete `DB_*`), `AMS_QUEUE_URL`, `AMS_RISK_CONFIG_PATH`, `AMS_TELEGRAM_TOKEN`, `AMS_TELEGRAM_CHAT_ID`, `AMS_SMTP_*`, `AMS_HEALTH_PORT`, `AMS_LOG_LEVEL`, `AMS_ACCOUNT_ID`.

### Connections
- DB: connect to the FND-004 engine; verify the AMS-001 tables exist; load the single `AMS_Account_State` row into memory at startup. Connection pool sized small.
- Queue: connect per FND-002; declare/subscribe to the three queues but install no-op handlers (later tasks wire real ones). Honor FND-002 staleness windows.

### Health endpoint
- `GET /health`: process up, event loop responsive (liveness).
- `GET /ready`: DB reachable, queue connected, config valid, account-state row loaded (readiness). FND-005 + EXEC-008 consume readiness to detect a down Guardian.
- `GET /api/account/state` (read-only): current `AMS_Account_State` for Layer 5 (EXEC-009).

### Logging / metrics
- Structured JSON logs (request id / signal id correlation) + the repo's rotating file handler as local fallback; ship to FND-005. No secrets in logs.
- Emit a `decision_latency_ms` metric stub now so AMS-003/005/008 can record against it.

## Testing & Validation
- Start with valid config/DB/queue → reaches `ready`; `/api/account/state` returns the seed DEMO row.
- Start with a missing `risk_config.json` key → refuses to start with a clear error (fail-fast).
- Start with DB down → not `ready`; health reflects it; no decisions attempted.
- SIGTERM → graceful shutdown, no half-open connections.
- Footprint test on Computer 3: idle RSS and CPU within budget; event-loop heartbeat jitter measured (baseline for the < 100 ms latency budget).

## Rollback Plan
The service is **standalone and additive** — it consumes no queue messages destructively and publishes nothing yet (handlers are no-ops). Rollback = stop the process; the trading platform is unaffected because Layer 4 still reads from `AMS_Outbound_Queue` (empty) and, per EXEC-008, pauses safely if it sees no fresh approvals.

## Acceptance Criteria
- [ ] `python -m ams` starts on Computer 3, loads + validates `risk_config.json`, connects to DB and queue, and reports `ready`.
- [ ] Invalid/missing config or unreachable DB causes a fail-fast startup (no partial run).
- [ ] `/health`, `/ready`, and read-only `/api/account/state` work and are consumed by FND-005 / EXEC-009.
- [ ] Structured logs ship to FND-005 with zero secrets, and a `decision_latency_ms` metric exists.
- [ ] Idle footprint fits the chosen Computer-3 host.

## Notes & Risks
- Keep dependencies minimal (asyncio, a small ASGI server, a queue client, a DB driver, pydantic) — every dependency costs reliability/footprint on Computer 3.
- `risk_config.json` should be versioned in object storage (FND-001) and pulled, so all systems read the same risk parameters; document the source-of-truth path.
- Do not embed the OANDA key here — System 3 never calls the broker directly; it receives account data over the queue (System 2 owns the key).
