# Dependencies & Prerequisites — Foundational & Cross-Cutting

> Everything in this list must be provisioned (or a decision recorded) **before** the corresponding foundational task can finish, and before any per-system task that depends on it can start. Each entry states **what** and **why**.

## 1. Accounts & third-party services to provision

| Item | What | Why | Used by |
|------|------|-----|---------|
| **Object storage** | Either self-hosted **MinIO** (on Computer 1, which is already a capable training box) or a **Cloudflare R2** bucket (free egress, S3 API). | Single artifact exchange for models/configs/performance across the 3 hosts; no shared filesystem exists once split. | FND-001; MODEL-001/007, EXEC-001 |
| **Message broker** | **Redis** (self-hosted on an always-on host, recommended Computer 3) with AOF persistence; Postgres `LISTEN/NOTIFY` documented as fallback. | Cross-host transport for `Scored_Signal_Queue`, `AMS_Outbound_Queue`, `AMS_Inbound_Queue`. | FND-002; MODEL-008, EXEC-004/005, AMS-002/008 |
| **Secrets store** | A pragmatic solo-operator choice — **SOPS + age** (encrypted files in git) is the recommended primary; Docker secrets / lightweight Vault are alternatives. | Remove plaintext secrets from `.env`/git; enable rotation; distribute per-computer least-privilege creds. | FND-003; AMS-011 |
| **Always-on host (Computer 3)** | A small VPS (e.g. 1–2 vCPU / 1–2 GB) or a Raspberry Pi 4/5 with reliable power + network. | Hosts System 3 (Guardian), Redis, and uptime monitoring; must run 24/7 independent of training. | FND-002, FND-005, FND-008, FND-010 |
| **VPN / overlay network** | **Tailscale** (free tier, WireGuard-based, easiest for solo) or self-hosted WireGuard. | Private, encrypted east-west connectivity between the 3 computers without public ingress. | FND-008; all cross-host traffic |
| **Telegram bot** | A bot registered via @BotFather; bot token + the operator's chat ID captured. | Real-time operational/risk alerts. Provider + token provisioning is owned here; sending logic is **AMS-011**. | FND-003, FND-005, AMS-011 |
| **Email/SMTP sender** | A transactional email provider with a free/cheap tier (e.g. an SMTP relay or API-based sender) + verified sender domain/address. | Email channel for digests and alert fallback when Telegram is unavailable. | FND-003, FND-005, AMS-011 |
| **Monitoring/alerting stack** | Lightweight: **Grafana + Loki + Promtail** (logs/metrics) or **Netdata + Uptime Kuma** (low-footprint). | System health visibility + SLO alerting across 3 hosts. | FND-005 |
| **CI runner** | **GitHub Actions** (repo already reserves `.github/workflows/` in `.gitignore`) or a self-hosted runner. | Lint/type/test gates and artifact publishing. | FND-007 |
| **Git remote** | A private remote (GitHub) for the repo. | Source of truth for code + SOPS-encrypted secrets + CI. | FND-003, FND-007 |

## 2. Existing assets to inventory / reconcile (no new purchase)

| Item | Current state | Why it matters |
|------|---------------|----------------|
| **SQL Server 2022 `ForexBrainDB`** | Active primary DB, all `Fact_*`/`Dim_*` tables, run via `docker-compose.yml`. | FND-004 must decide whether it stays, is consolidated to Postgres/TimescaleDB, or runs dual-DB. |
| **PostgreSQL (research notes)** | Secondary, used only by `src/research_notes_api.py`. | Candidate consolidation target; AMS design assumes Postgres. |
| **`.env`** | Plaintext secrets (`DB_PASS=Emm5$manuel`, `OANDA_API_KEY`, account IDs). Excluded by `.gitignore` but **the DB password is also in `docker-compose.yml` and `CLAUDE.md`**. | FND-003 must rotate and migrate these; treat as compromised. |
| **OANDA practice API** | `OANDA_API_KEY`, `OANDA_ACCOUNT_ID_DEMO`, `practice` env, `https://api-fxpractice.oanda.com`. | Key must move into secrets and be rotated; only System 2/Layer 7 needs it. |
| **`models/` artifacts** | `champion_model.pkl`, `champion_preprocessor.pkl`, `champion_manifest.json` (+ legacy fallbacks). | Defines the object-storage `models/` contract (FND-001). |
| **`logs/`** | Rotating file logs (10 MB × 14 backups). | Baseline that FND-005 replaces/augments with structured logging + shipping. |
| **`shell/cron_*.sh`** | Cron-driven Layer 4 / ingest jobs. | Scheduling must be re-homed per system; runbooks (FND-009) document the new layout. |

## 3. Decisions that must be recorded before downstream work

1. **Canonical datastore** (FND-004) — blocks AMS-001 and MODEL-001. Highest-priority decision.
2. **Object-storage backend** (MinIO vs R2) — affects FND-006 backup paths and FND-010 cost.
3. **Queue backend** (Redis vs Postgres NOTIFY) — affects FND-002 contract, FND-008 ports, FND-010 cost.
4. **Secrets tool** (SOPS+age vs Docker secrets vs Vault) — affects FND-007 CI secret injection and FND-008/009 distribution.
5. **Computer 3 form factor** (Pi vs VPS) — affects latency budget feasibility (FND-005) and cost (FND-010).

## 4. Prerequisite ordering summary

- **No prerequisites (start now):** FND-001, FND-002, FND-003, FND-004.
- **Need secrets first (FND-003):** FND-005, FND-007, FND-008.
- **Need storage + DB (FND-001 + FND-004):** FND-006.
- **Need real provisioned infra to cost:** FND-010 (after FND-001, FND-002, FND-008).
- **Independent:** FND-009 (can run in parallel throughout).
