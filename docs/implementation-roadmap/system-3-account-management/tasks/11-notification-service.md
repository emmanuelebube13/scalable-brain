# AMS-011 — Notification Service

- **Task ID**: AMS-011
- **System**: System 3 — Account Management
- **Priority**: P1-High
- **Estimated Effort**: 3d
- **Prerequisites**: AMS-002, FND-003
- **External Dependencies**:
  - **Telegram Bot API** — bot token + operator chat id provisioned in FND-003. *Why:* real-time, mobile-friendly alerts and (with AMS-014) the override entry point.
  - **SMTP / transactional email** — credentials + verified sender in FND-003. *Why:* digests, weekly reports, and fallback when Telegram is down.
  - **Secrets (FND-003)** — owns provisioning of both providers/tokens. *Why:* no secret in code/config. (FND-003 owns provisioning; **this task owns sending logic**.)

## Objective
Build the multi-channel notification service (Telegram bot + SMTP email) with per-event templates, urgency routing, rate-limit handling and delivery-failure fallback.

## Current State
**New.** No notifications exist. Operational visibility is only file logs. FND-003 provisions the providers; FND-005 references AMS-011 for alert delivery.

## Target State
An internal notification module (called by AMS-003/006/007/009/010/012/013/014) that renders per-event templates, routes by **urgency** to the right channel(s), handles provider rate limits with backoff + queueing, and falls back (Telegram → email) on delivery failure, with a delivery audit log. Channel toggles and per-event enables come from `risk_config.json.notification`.

## Technical Specification

### Event catalogue, urgency & routing
| Event | Urgency | Channels | Source |
|-------|---------|----------|--------|
| Trade entry | Normal | Telegram + Email | AMS-008/007 |
| Trade exit (win/loss) | Normal | Telegram | AMS-007 |
| Soft stop triggered | High | Telegram + Email | AMS-006 |
| Circuit breaker | CRITICAL | **All channels** | AMS-006 |
| Daily summary | Normal | Email | AMS-009 (21:00 UTC) |
| Weekly report | Normal | Email | AMS-009 (Sun 20:00 UTC) |
| Model updated | Normal | Telegram | System 1 hook |
| Margin warning | High | Telegram + Email | AMS-006 |
| Strategy flagged/quarantined | High/CRITICAL | Telegram + Email | AMS-010 |
| Stage escalation/de-escalation | High | Telegram + Email | AMS-012 |
| Override executed | High | Telegram + Email | AMS-014 |

Urgency → channel policy: `Normal` honors `risk_config.json` toggles; `High` always at least Telegram + email; `CRITICAL` always all channels and bypasses dedup/rate-limit suppression.

### Templates
- One template per event (subject + body), with variables (pair, size, P&L, drawdown %, reason, action, running daily P&L, consecutive losses). Keep them short for Telegram; richer for email (daily/weekly include figures/charts from AMS-009). Templates versioned in config/repo, never hardcoded inline.

### Rate-limit & failure handling
- Telegram (~30 msgs/sec, per-chat limits): a small outbound queue with token-bucket throttling + exponential backoff on 429; coalesce duplicate Normal events within a short window (never coalesce CRITICAL).
- SMTP: connection reuse, retry with backoff on transient failures.
- **Fallback**: if Telegram delivery fails after retries, send the same content via email (and vice-versa for High/CRITICAL). Persist undelivered CRITICAL alerts and retry until acked or escalate.
- **Delivery audit**: log each notification (event, channels attempted, outcome, latency) — no secrets/PII beyond what's needed.

### Interface (pseudo-code)
```
notify(event_type, payload, urgency)            # called by other AMS modules
    template = render(event_type, payload)
    channels = route(urgency, config.notification)
    for ch in channels: enqueue(ch, template)    # throttled, retried
    on_failure(ch): fallback(other_channel)
    audit(event_type, channels, outcomes)
```

### Security
- Tokens/credentials only from FND-003 env injection; redact secrets from logs; TLS for SMTP and HTTPS for Telegram.

## Testing & Validation
- Unit: each event renders the correct template with substituted variables; routing matches the urgency table.
- Rate-limit: a burst of Normal events is throttled/coalesced without dropping; CRITICAL is never suppressed.
- Fallback: simulated Telegram 5xx/429 routes High/CRITICAL to email; the failure and fallback are audited.
- CRITICAL delivery: a circuit-breaker event reaches all channels even under throttling.
- Config toggles: disabling a Normal event in `risk_config.json` suppresses it but never suppresses High/CRITICAL.
- No-secret-leak: logs contain no token/credential.

## Rollback Plan
The service is leaf functionality — callers tolerate a notification failure (they log and continue; trading logic never depends on a notification succeeding). Rollback = disable a channel via config or stop the module; the gate and breakers keep working. CRITICAL events still hit the structured log/FND-005 even if both channels fail.

## Acceptance Criteria
- [ ] Sends all catalogued events via Telegram and/or SMTP per the urgency routing table.
- [ ] Per-event templates render correctly from payloads; templates are config-driven, not hardcoded.
- [ ] Rate limits are handled with backoff/coalescing; CRITICAL is never suppressed.
- [ ] Telegram↔email fallback works on delivery failure and is audited.
- [ ] No secrets appear in logs; all credentials come from FND-003.

## Notes & Risks
- Notification failure must **never** block or alter a risk decision — fire-and-forget with audit; the gate's correctness cannot depend on Telegram being up.
- Alert fatigue is real: coalesce Normal events and keep CRITICAL rare and meaningful, or the operator will mute the bot and miss a real circuit breaker.
- Telegram is also the AMS-014 override channel — keep its command-handling separate from outbound notification to avoid coupling.
