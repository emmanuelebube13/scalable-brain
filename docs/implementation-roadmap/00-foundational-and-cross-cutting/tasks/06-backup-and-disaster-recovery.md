# FND-006 — Backup & Disaster Recovery

- **Task ID**: FND-006
- **System**: Foundational & Cross-Cutting
- **Priority**: P1-High
- **Estimated Effort**: 2d
- **Prerequisites**: FND-001, FND-004
- **External Dependencies**:
  - **Object storage** (FND-001) as the off-host backup target (a dedicated `backups/` prefix or separate bucket, ideally with versioning + a different access key than the live artifact keys). *Why:* backups must survive loss of any single computer.
  - **PostgreSQL/TimescaleDB** (FND-004) backup tooling: `pg_dump`/`pg_basebackup` and, for TimescaleDB, continuous WAL archiving for point-in-time recovery. *Why:* the canonical operational store holds all trading state.
  - A scheduler (cron/systemd timer) on each host and credentials via FND-003.

## Objective
Define and automate backup schedules and a tested disaster-recovery runbook for databases, configs, model artifacts, and AMS state, with explicit RPO/RTO targets.

## Current State
There is no documented backup or DR process. State lives on single hosts: SQL Server in a Docker volume, model artifacts in local `models/`, configs/secrets in `.env`, run outputs in `results/`. Loss of a disk would lose trading history, the champion model, and account state. The only "recovery" today is re-running pipelines from raw data, which does not recover live-trade/account history.

## Target State
- Automated, scheduled, off-host backups of every stateful component, encrypted at rest.
- Documented RPO/RTO per component and a step-by-step DR runbook (FND-009) covering total loss of each computer.
- A periodically **tested restore** proving backups are usable, not just present.

## Technical Specification

### What to back up, cadence, RPO/RTO
| Component | Method | Frequency | RPO | RTO |
|-----------|--------|-----------|-----|-----|
| PostgreSQL/TimescaleDB (all Fact/Dim + AMS tables) | `pg_basebackup` + continuous WAL archive to object storage | base nightly, WAL continuous | ≤ 5 min | ≤ 4 h |
| AMS state (account_state, decision_log, circuit_breaker_log, equity_curve) | included in DB backup; plus nightly logical `pg_dump` of AMS schema | nightly | ≤ 24 h (point-in-time via WAL ≤ 5 min) | ≤ 1 h |
| Model artifacts | already versioned in object storage (FND-001); replicate bucket / enable cross-region or second-bucket copy | on publish | 0 (versioned) | ≤ 30 min |
| Configs (`risk_config.json`, runtime configs) | versioned in object storage + git (encrypted) | on change | 0 | ≤ 15 min |
| Secrets | encrypted store (FND-003) + offline copy of root key | on rotation | n/a | ≤ 30 min |
| Run outputs (`results/`) | nightly sync to object storage | nightly | ≤ 24 h | ≤ 1 h |

### DR runbook scenarios (documented step-by-step)
- **Computer 1 (training) lost:** rebuild host, restore configs from object storage, re-pull data; no live-trading impact (System 2/3 keep running off last published model).
- **Computer 2 (execution) lost:** rebuild host, redeploy Layer 4/7, re-download model (EXEC-001); System 3 safe-pauses meanwhile so no unmanaged trades.
- **Computer 3 (AMS) lost:** highest priority — rebuild host, restore DB/AMS state to latest WAL point, restart service; until restored, EXEC-008 keeps Layer 4 paused (no trading without risk approval). Reconcile open positions from OANDA (broker is the position source of truth).
- **DB corruption:** point-in-time recovery to just before corruption using WAL archive.

### Encryption & retention
- Backups encrypted at rest (object-store SSE) and in transit (TLS/VPN). Retain: daily for 30 days, weekly for 12 weeks, monthly for 12 months.
- Backup-access key is least-privilege (write+read backups only), separate from live artifact keys.

## Testing & Validation
- **Quarterly restore drill:** restore the DB to a scratch instance from the latest base+WAL and verify row counts + a known equity-curve value; record RTO actually achieved.
- Point-in-time recovery test: restore to a chosen timestamp and confirm a post-timestamp trade is absent.
- Model/config restore: delete a local artifact, restore from object storage, SHA256-verify.
- Backup-failure alerting: simulate a failed nightly backup and confirm FND-005 raises an alert (a silently failing backup is the real risk).
- AMS-loss simulation on demo: stop Computer 3, confirm Layer 4 pauses, restore AMS, reconcile open positions against OANDA with no double-counting.

## Rollback Plan
Backups are additive and read-only against production. If a backup job degrades performance or fills disk, disable the schedule (production state is untouched) and reconfigure. Restores are always performed to a **scratch** instance first and validated before promoting — never directly over a live DB.

## Acceptance Criteria
- [ ] Automated off-host, encrypted backups run on schedule for DB (with WAL/PITR), AMS state, artifacts, configs, and run outputs.
- [ ] RPO/RTO targets documented per component and a DR runbook covers total loss of each of the three computers.
- [ ] A full restore drill succeeds on a scratch instance with verified data integrity, and the achieved RTO is recorded.
- [ ] Point-in-time recovery is demonstrated.
- [ ] A failed backup raises an alert (no silent failures).

## Notes & Risks
- The broker (OANDA) is the authoritative source for open positions; AMS DR must **reconcile against the broker**, not assume the DB alone is complete — otherwise a restored AMS could mismanage live positions.
- Continuous WAL archiving needs disciplined retention to avoid filling backup storage; tie to FND-010 cost review.
- Restore is only as good as the last successful test — schedule the drill, don't rely on backup existence alone.
- Depends on FND-004 (final DB choice) and FND-001 (target) being settled, hence the prerequisites.
