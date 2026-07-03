# FND-005 — Observability: Structured Logging, Monitoring & Alerting

- **Task ID**: FND-005
- **System**: Foundational & Cross-Cutting
- **Priority**: P1-High
- **Estimated Effort**: 3d
- **Prerequisites**: FND-003
- **External Dependencies**:
  - A log aggregation + metrics + dashboard stack. Recommended lightweight set: **Grafana + Loki + Promtail** (logs) and **Prometheus** or **Netdata** (host/service metrics), plus **Uptime Kuma** for uptime/heartbeat checks. *Why:* three hosts can no longer be observed by tailing local files; a single pane is needed for health, queue lag, and latency SLOs.
  - An alert sink — reuses the AMS-011 Telegram/email channels for operational (non-trading) alerts. *Why:* the operator must learn about infra failures (broker down, queue stalled, Computer 3 offline) the same way they learn about trades.
  - Credentials/endpoints via FND-003; cross-host scraping over the FND-008 VPN.

## Objective
Stand up structured JSON logging, metrics, dashboards, and alerting across all three computers with defined SLOs for system health (not just trading outcomes).

## Current State
Logging is rotating local files only — the project standard is `%(asctime)s | %(levelname)-8s | %(name)s | %(message)s`, 10MB/file, 14 backups, under `logs/` (and `oanda_ingest.log`). Logs are human-readable but unstructured, per-host, and invisible across machines. There is no metrics collection, no dashboard, and no alerting on system health; failures are discovered by manually reading logs.

## Target State
- All services emit **structured JSON logs** (timestamp, level, service, host, `correlation_id`, message, context) shipped to a central store, retaining the rotating-file handler locally as a fallback.
- Host + service metrics (CPU/mem/disk, queue depth/lag, DB connections, decision latency) collected centrally.
- Dashboards per system + one global health board.
- Alerting on SLO breaches routed to the operator.

## Technical Specification

### Structured logging
- Adopt a JSON formatter wrapping the existing format fields plus `host`, `system` (1/2/3), `layer`, `correlation_id` (the FND-002 trace id), and `event` type. Keep the rotating file handler as local durable backup; Promtail tails and ships to Loki.
- Standard event taxonomy: `signal.scored`, `decision.{approved,reduced,rejected}`, `order.{submitted,filled,rejected}`, `circuit_breaker.triggered`, `model.published`, `queue.stalled`, `service.{start,stop,error}`.

### Metrics & SLOs
| SLO | Target | Source |
|-----|--------|--------|
| System 3 decision latency (signal→verdict), H1 | p99 < 100 ms | timing metric in AMS-003/008 |
| `AMS_Outbound_Queue` consumer lag | < 5 min (else EXEC-008 safe-pause) | queue depth/age metric (FND-002) |
| Computer 3 (AMS) uptime | ≥ 99% during market hours | Uptime Kuma heartbeat |
| Broker/queue/DB reachability | up during market hours | health probes |
| Model freshness (Computer 2 vs latest.json) | ≤ 1 publish cycle behind | EXEC-001 metric |
| Trade-pipeline error rate | < 1% of cycles error | log-derived metric |

### Alerting policy
- **Critical** (page immediately, all channels): circuit breaker tripped, Computer 3 offline, queue stalled > 5 min, broker auth failure, DB unreachable.
- **Warning** (Telegram): decision-latency SLO breach, model staleness, disk > 80%, elevated error rate.
- Dedup + rate-limit alerts (reuse AMS-011 limits) to avoid alert storms; every alert links to the relevant runbook (FND-009).

### Dashboards
- Per-system board (System 1 training runs/MLflow links; System 2 execution/fills/slippage; System 3 account state/equity/decision log).
- Global health board: host vitals, queue depths, SLO status, last model publish, last heartbeat per host.

### Footprint
- The stack runs on Computer 1 or a small VPS — **not** on the lightweight Computer 3 (only a metrics exporter + log shipper run there) to respect AMS resource limits.

## Testing & Validation
- Emit a log line on each host; confirm it lands centrally with correct `host`/`system`/`correlation_id` within seconds.
- Trace a single `correlation_id` across `signal.scored → decision → order.filled` in the central store.
- Trip each critical condition in a controlled test (kill the queue, stop Computer 3) and confirm the correct alert fires within its threshold and links a runbook.
- Latency metric sanity: inject a known delay into a decision and confirm the p99 panel reflects it.
- Alert rate-limit test: fire repeated identical conditions; confirm dedup/throttle holds.

## Rollback Plan
Observability is non-intrusive: services keep their local rotating file logs regardless. If the central stack misbehaves, disable Promtail/exporters (services unaffected) and fall back to local log inspection. The stack can be rebuilt without touching application code.

## Acceptance Criteria
- [ ] All services emit structured JSON logs shipped centrally, with local rotating-file fallback retained.
- [ ] A single `correlation_id` is traceable end-to-end across the three queues in the central store.
- [ ] Dashboards exist per system plus a global health board with live SLO status.
- [ ] Critical conditions (queue stall, Computer 3 offline, circuit breaker, DB/broker down) fire alerts within threshold and link runbooks.
- [ ] The stack runs off the lightweight Computer 3 (only exporters/shippers there).

## Notes & Risks
- Distinguish **trading** alerts (owned by System 3 / AMS-011 — entries, exits, breakers) from **operational** alerts (owned here — infra health). They share channels but different ownership; document the split to avoid duplication.
- Over-alerting causes the operator to ignore alerts — invest in dedup/severity tiers from day one.
- Keep the stack lightweight to fit the cost constraint (FND-010); a full Prometheus+Grafana+Loki set is fine self-hosted, but avoid paid SaaS tiers unless justified.
