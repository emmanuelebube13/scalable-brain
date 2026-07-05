# 00 — Foundational & Cross-Cutting Concerns

> Part of the **Scalable Brain — Migration & Implementation Architecture Plan**.
> Audience: Staff PM + Principal Architect. Author: Principal Software Architect.

## Purpose

Scalable Brain is being reorganized from a single-host, 8-layer monolith (Layers 0–7 on SQL Server 2022 `ForexBrainDB` + OANDA practice API, Python 3.12) into **three deployable systems across three computers**:

| System | Name | Layers | Host | Operating profile |
|--------|------|--------|------|-------------------|
| System 1 | Model Building / **The Brain** | Layers 0–3 + NLP | Computer 1 | Heavy, intermittent (training) |
| System 2 | Execution Engine / **The Hand** | Layers 4, 7, 5 | Computer 2 | Active during market hours |
| System 3 | Account Management / **The Guardian** (NEW) | Decision Gate, Risk Engine, circuit breakers, Layer 6 auditor | Computer 3 | Always-on (Raspberry Pi / small VPS) |

This folder owns the **plumbing that all three systems share**: object storage, the message queue, secrets, the canonical datastore decision, observability, backup/DR, CI/CD, inter-computer networking, documentation, and cost control. These are sequenced **before** the per-system work because System 1, 2, and 3 tasks declare hard dependencies on them (see the dependency map below).

## Goals

1. Establish a **single artifact exchange** (object storage) so Computer 1 can publish models/configs that Computers 2 and 3 consume — without shared filesystems.
2. Establish a **single asynchronous transport** (message queue) so signals, decisions, and acks flow between Layer 3, System 3, and Layer 4 across hosts with backpressure and staleness guarantees.
3. Remove all secrets from `.env`/git and give each computer **only the credentials it needs**, with a rotation procedure.
4. Resolve the **SQL Server vs PostgreSQL** ambiguity into one canonical datastore strategy (with TimescaleDB for time-series), unblocking AMS-001 and MODEL-001.
5. Make the distributed system **observable, recoverable, networked securely, and affordable** for a solo part-time operator on ~$4,000/month trading capital.

## Success Criteria

- [ ] All three computers read/write a shared object store using scoped, least-privilege keys.
- [ ] A signal published by System 1/Layer 3 reaches Layer 4 (via System 3) over the queue with measured end-to-end lag, and System 3's decision latency budget (< 100 ms on H1) is monitored.
- [ ] `git grep` finds **zero** live secrets in the repo; every credential is sourced from the secrets layer; rotation has been exercised at least once.
- [ ] The canonical datastore decision (FND-004) is ratified and documented; AMS and Model teams build against it.
- [ ] A backup taken yesterday can be restored into a clean environment within the stated RTO, and the restore was actually tested.
- [ ] CI gates (black/mypy/pytest) block a known-bad commit; green builds publish artifacts to object storage.
- [ ] The three computers communicate only over an encrypted private network (VPN + TLS); no service port is exposed to the public internet without TLS + auth.
- [ ] Recurring infra cost is documented and is a small, bounded fraction of monthly capital.

## Task Index

| ID | Task | Priority | Effort | Prerequisites |
|----|------|----------|--------|---------------|
| FND-001 | Provision object storage | P0-Critical | 2d | None |
| FND-002 | Provision message queue & IPC | P0-Critical | 2d | None |
| FND-003 | Secrets management & rotation | P0-Critical | 2d | None |
| FND-004 | Database strategy & consolidation | P0-Critical | 3d | None |
| FND-005 | Observability: logging, monitoring, alerting | P1-High | 3d | FND-003 |
| FND-006 | Backup & disaster recovery | P1-High | 2d | FND-001, FND-004 |
| FND-007 | CI/CD & automated test harness | P1-High | 3d | FND-003 |
| FND-008 | Inter-computer networking & security | P1-High | 2d | FND-003 |
| FND-009 | Developer onboarding, runbooks, docs | P2-Medium | 2d | None |
| FND-010 | Cost optimization audit | P2-Medium | 1d | FND-001, FND-002, FND-008 |

### Recommended execution order

1. **Parallel P0 wave** (no prerequisites): FND-001, FND-002, FND-003, FND-004 can all start immediately. FND-004 is the longest pole and gates downstream system work, so start it first.
2. **P1 wave** (after FND-003 lands secrets and FND-001/004 land storage/DB): FND-005, FND-007, FND-008 (all need FND-003), then FND-006 (needs FND-001 + FND-004).
3. **P2 wave**: FND-009 anytime; FND-010 once FND-001, FND-002, FND-008 are provisioned so real costs are known.

## Cross-system dependency map

Other agents author these system folders; this folder is referenced by their tasks:

- **System 1 (MODEL-001..010):** MODEL-007 (model serializer) and MODEL-001 depend on **FND-001**; MODEL-008 (queue producer) depends on **FND-002**; MODEL-001 also depends on the **FND-004** datastore decision.
- **System 2 (EXEC-001..009):** EXEC-001 (artifact downloader) depends on **FND-001**; EXEC-004/005 (queue consumer/producer) depend on **FND-002**.
- **System 3 (AMS-001..014):** AMS-001 (schema) depends on **FND-004**; AMS-002/008 (queue) depend on **FND-002**; AMS-011 (notifications) depends on **FND-003** (this folder owns provider/secret provisioning; System 3 owns sending logic).

## Division of ownership (notifications)

Notifications recur across the plan. **This folder owns the provisioning side**: choosing the email/SMTP and Telegram providers, registering the bot, storing the tokens in the secrets layer, documenting rate limits and templating conventions. **System 3 (AMS-011) owns the sending logic** (what to send, when, formatting, dedup). FND-003 and FND-005 reference AMS-011 accordingly.

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| DB decision (FND-004) churns after AMS/Model teams have built against it | Medium | High | Ratify FND-004 first; freeze the decision; require an ADR-style sign-off before AMS-001/MODEL-001 start. |
| Live secrets already committed or leaked from `.env` | Medium | Critical | Treat all current secrets as compromised: rotate OANDA key + DB password in FND-003; scan git history; the DB password is visible in `docker-compose.yml`/`CLAUDE.md` and must be rotated. |
| Always-on Computer 3 (Pi/VPS) is underpowered for < 100 ms decision latency | Medium | High | Keep System 3 logic lean (FND-005 SLO monitors latency); size the VPS in FND-010; design queue + decision path to avoid heavy per-decision I/O. |
| Cross-host queue/object-store outage stalls execution mid-market | Medium | High | Backpressure + staleness semantics (FND-002); local-cache fallback for last-known-good model (FND-001); circuit-breaker behavior owned by System 3. |
| Solo operator loses context / hit by a bus | High | High | Runbooks + onboarding docs (FND-009); everything-as-code; tested restore (FND-006). |
| Recurring infra cost erodes thin trading capital | Medium | Medium | FND-010 audit; prefer self-hosted/free-tier (MinIO on Computer 1, Redis local, Tailscale free tier) over managed paid services where reliability allows. |
| Network misconfiguration exposes a broker-authorized service publicly | Low | Critical | VPN-only east-west traffic + TLS + least-privilege (FND-008); no public ingress; audit logging on access. |
| Backups exist but were never restore-tested ("Schrödinger's backup") | Medium | High | FND-006 mandates a tested restore as an acceptance gate, not just a backup schedule. |
| Time/clock skew across 3 hosts corrupts H1 granularity and staleness checks | Medium | Medium | NTP on all hosts (FND-008); staleness windows defined in queue contract (FND-002). |
| AI-agent-generated infra config drifts from documented intent | Medium | Medium | All infra as reviewed config in git; CI lints config (FND-007); runbooks describe intended state (FND-009). |
