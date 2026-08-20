# July 2026 Goals — Scalable Brain

*Drafted: 2026-07-08 · Owner: Emmanuel · Scope: all three systems + cloud plumbing*

---

## Where we are (verified 2026-07-08)

| System | Host | Verified status |
|--------|------|-----------------|
| System 1 — The Brain | Computer 1 (this machine) | **Running.** Last gated retrain 2026-07-01 → `promoted`, bundle `2026-07-01T12-56-32Z` published with `latest.json` pointer. Orchestrator now on hourly cron (installed 2026-07-08); Saturday OANDA ingest cron active. Legacy Layer-4 cron disabled (was failing every 30 min since FIX-S1-009 — 12,930 logged errors). |
| System 2 — The Hand | Computer 2 (other machine) | Engineering complete per checkpoint (152/152 tests). Ops steps outstanding: provision `config/.env.system2`, `python -m system2.common.db migrate`, practice drill, D-004 decision. Local copy on Computer 1 kept for reference only. |
| System 3 — The Guardian | Computer 2/3 (other machine) | Built per owner; status not yet visible from Computer 1 (this repo holds only docs + task specs 01–20). **Need progress ledger from that machine.** |
| Cloud (GCS + Pub/Sub) | GCP | GCS: System 1 has rw service account (`secrets/system1-rw.json`) and bucket configured. Pub/Sub: **not wired** — System 1 still has `QUEUE_PROVIDER=local`, so scored signals land in `results/state/queue` on this machine where no other computer can read them. |

## Overall July objective

> **One full end-to-end practice-mode run across all three computers by end of July:**
> System 1 publishes a bundle + scored signals → System 3 approves/sizes through the 10-layer
> gate → System 2 fills on OANDA practice → fills flow back to System 3 → journal closes the
> loop. Everything stays practice + SHADOW; the output of July is the **D-004 evidence
> package**, not live money.

Success criteria:
1. A scored signal generated on Computer 1 results in a (shadow-)fill recorded on the other computer(s) with no manual copying.
2. Both PAUSE (stale queue) and emergency STOP drills executed and logged.
3. D-004 review package assembled (dual-run parity report, drill logs, open risks). Go/no-go decision is deliberately **August**, not July.

---

## System-by-system goals

### Foundational / cloud plumbing (blocks everything else — do first)

- [ ] Create the three Pub/Sub topics + subscriptions + DLQs: `Scored_Signal_Queue` (S1→S3), `AMS_Outbound_Queue` (S3→S2), `AMS_Inbound_Queue` (S2→S3).
- [ ] Least-privilege service accounts per host (S1: GCS rw + publish-only; S2: GCS ro + consume/publish; S3: consume/publish). S1's rw key already exists.
- [ ] Secrets distribution per plan (SOPS+age); confirm no credential crosses hosts.
- [ ] Verify S2 can pull the *existing* `2026-07-01T12-56-32Z` bundle from GCS with SHA256 verification — first cross-system artifact test, no new code needed.

### System 1 — The Brain (this repo)

- [ ] **Land the working-tree changes**: FIX-S1-008 (gatekeeper leakage / pipeline unification gates), serializer + `publish_gatekeeper.py`, leakage & gate-teeth tests are modified/untracked. Commit them — they are currently the only copy.
- [ ] Switch `QUEUE_PROVIDER=local` → `pubsub` once topics exist; verify producer idempotency + DLQ against the real queue.
- [ ] Confirm next scheduled retrain (Sunday 00:00 UTC via new hourly cron) runs unattended and publishes; watch `logs/system1_retrain.log`.
- [ ] Clean up legacy monolith surface: `archieved/` moves already staged (layer4/5/6/7); decide whether Layer 5 legacy dashboard on this machine is retired (telemetry now belongs to System 2).
- [ ] Known-gap follow-up if time allows: retire/reconcile the T-SQL generator `src/layer0/layer2_config_adapter.py`; update CLAUDE.md to document `src/` (it currently only covers the legacy 8 layers).

### System 2 — The Hand (other machine)

- [ ] Provision `config/.env.system2` from the template (practice creds, `STORAGE_PROVIDER=gcs`, `QUEUE_PROVIDER=pubsub`); startup is fail-closed so a clean boot proves config.
- [ ] `python -m system2.common.db migrate`, then run continuously in practice + SHADOW through market hours; watch `/status` (queue lag, outbox depth, model set).
- [ ] Artifact sync: automatically pick up System 1's next Sunday bundle from GCS (poll interval 300 s, strict verify).
- [ ] **Practice integration drill** (RUNBOOK §6): approved order → OANDA practice fill → fill lands on `AMS_Inbound_Queue` → dual-run parity vs legacy formula → PAUSE and emergency-STOP exercises.
- [ ] Optionally install `deploy/system2.service` (systemd) so it survives reboots.
- [ ] **Stay in SHADOW all of July.** `EXEC_SHADOW=false` only after D-004 is logged APPROVED.

### System 3 — The Guardian (other machine)

*Goals below assume the build matches tasks 01–20; will refine once I can see its progress ledger.*

- [ ] Report/verify status of tasks 01–20, especially: account state machine (06), risk engine + Kelly sizing (07), circuit breakers (08), gate layers A–J (09–11).
- [ ] Consume real scored signals from `Scored_Signal_Queue` (produced by System 1 on Computer 1) — first S1→S3 integration.
- [ ] Publish approved, pre-sized orders to `AMS_Outbound_Queue`; consume fills from `AMS_Inbound_Queue`; post-trade processor + journal export (12, 19).
- [ ] Notifications live: Telegram + SMTP urgency routing (13).
- [ ] Scenario tests + shadow mode (20): default-safe REJECT paths proven (missing data, stale input, internal error).
- [ ] Local PostgreSQL confirmed zero-runtime-dependency on Computer 1.

---

## Weekly milestones

| Week | Target |
|------|--------|
| Jul 8–13 | Cloud plumbing done (topics, service accounts). System 1 changes committed. S2 `.env` provisioned + boots clean in SHADOW. S3 status ledger shared. |
| Jul 14–20 | Sunday Jul 19 retrain publishes unattended; S2 auto-syncs the bundle. S1 switched to Pub/Sub; S3 consuming scored signals in shadow. |
| Jul 21–27 | Full end-to-end practice drill (S1→S3→S2→fills→S3). PAUSE + STOP drills. Dual-run parity report started. |
| Jul 28–Aug 2 | Stability soak (unattended week). Assemble D-004 evidence package. August: human go/no-go for micro-live via graduated deployment (Paper→Micro→Small→Full). |

## What I need from the other computer

1. **System 3 progress ledger / checkpoint** (equivalent of `orchestration/PROGRESS_LEDGER.md`) — which of tasks 01–20 are complete, test counts, open gates.
2. **System 2 ops status there**: does `config/.env.system2` exist, has `db migrate` run, has it ever booted clean?
3. **GCP state**: which Pub/Sub topics/service accounts already exist (vs. still to create), and which GCP project ID the queues live in.
4. If System 3 has its own decisions log, the IDs of any decisions already taken (so we don't re-decide).

## Risks / watch items

- **Uncommitted System 1 work** is the single biggest current risk — one bad `git checkout` loses the leakage fix. Commit first.
- Scored signals currently dead-end in a local queue; until Pub/Sub is wired, S3 shadow-runs on nothing.
- Fri Aug 1 is inside the last milestone week — keep the soak week genuinely hands-off to make the D-004 evidence honest.
