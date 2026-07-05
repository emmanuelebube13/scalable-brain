# FND-003 — Secrets Management & Rotation

- **Task ID**: FND-003
- **System**: Foundational & Cross-Cutting
- **Priority**: P0-Critical
- **Estimated Effort**: 2d
- **Prerequisites**: None
- **External Dependencies**:
  - A secrets-handling tool. Recommended for a solo operator: **SOPS + age** (encrypted secrets committed to git, decrypted at deploy with a key held only on each host) — zero recurring cost, no server. *Why:* current secrets sit in plaintext and must be encrypted at rest with a clear rotation story.
  - **Alternatives:** Docker/Compose secrets (file-based, simple) or a lightweight **HashiCorp Vault**/Infisical instance (richer, but a server to run). *Why:* documented escalation path if multi-host dynamic secrets are later needed.
  - One root key (age key / Vault unseal) stored offline as the recovery anchor.

## Objective
Establish centralized, encrypted secrets management with rotation and per-computer distribution so no credential ever lives in code or plaintext in the repo.

## Current State
Secrets live in a plaintext `.env` at the repo root (`DB_SERVER`, `DB_USER`, `DB_PASS=Emm5$manuel`, `OANDA_API_KEY`, `OANDA_ACCOUNT_ID_DEMO`, `LAYER3_APPROVAL_THRESHOLD`, etc.). `.env` is `.gitignore`d, but the DB password and OANDA key are visible in plaintext on disk and were quoted verbatim in `CLAUDE.md` — i.e. effectively exposed. There is no rotation, no separation between dev/live, and the same `.env` would have to be copied to three hosts.

## Target State
A single encrypted secrets source of truth that:
- Holds all credentials: OANDA practice + live API keys and account IDs, DB credentials, object-store key pairs (FND-001), Redis credentials (FND-002), Telegram bot token (AMS-011), SMTP credentials (AMS-011).
- Decrypts only on the host that needs a given secret, scoped per system (Computer 1 never holds live broker keys if it doesn't trade).
- Supports rotation without code changes, with a documented rotation runbook (FND-009).
- Leaves application code reading secrets only from environment/injected files at runtime.

## Technical Specification

### Inventory & classification
- Build a secrets inventory: name, owner system(s), sensitivity (e.g. **live OANDA key = critical**, demo key = high, Telegram token = medium), rotation cadence, last-rotated date.
- Split namespaces: `secrets/common`, `secrets/system1`, `secrets/system2`, `secrets/system3`, and `secrets/demo` vs `secrets/live` for broker credentials.

### SOPS + age model (recommended)
- One `age` keypair per host; `.sops.yaml` rules encrypt each secrets file to the public keys of only the hosts allowed to read it (e.g. live broker secrets encrypted only to Computer 2).
- Encrypted `*.enc.env`/`*.enc.yaml` files **may** be committed (ciphertext only); plaintext `.env` is removed from all hosts and added to a pre-commit guard.
- At deploy, a wrapper decrypts the relevant file into process environment (never to a world-readable file); FND-007 CI uses an ephemeral key with read-only scope for tests against dummy secrets.

### Rotation
- Cadence: live broker key every 90 days or immediately on suspected exposure; DB password every 180 days; object-store/Redis keys every 180 days; Telegram/SMTP on demand.
- Rotation procedure (runbook): provision new credential at provider → update encrypted secret → roll services → verify health → revoke old credential. Each rotation logged with date + operator.

### Hardening of the existing exposure
- Treat the `Emm5$manuel` DB password and any committed OANDA key as **compromised**: rotate them as the first action of this task, before migrating.
- Purge plaintext secret values from tracked docs (`CLAUDE.md` env block → replace literal values with placeholders).

## Testing & Validation
- A clone of the repo without the age key cannot reveal any secret value (verify ciphertext only).
- A host with only its scoped key can decrypt its secrets but **not** another system's (e.g. Computer 1 cannot decrypt live broker keys).
- Each service starts successfully reading only injected env/secret files; grep the codebase + CI logs for hardcoded credentials → zero hits.
- Rotation dry-run: rotate the DB password end-to-end; all dependent services reconnect with no code change.
- Pre-commit guard blocks a deliberately staged plaintext secret.

## Rollback Plan
Keep the existing `.env` on each host (outside git, 0600 perms) as a temporary fallback during cutover; services can read either source behind a loader flag. Once encrypted-secrets loading is verified on all hosts, delete plaintext `.env`. Reverting means re-pointing the loader at the local `.env` — but the rotated credentials are the new truth, so old `.env` values must be refreshed first.

## Acceptance Criteria
- [ ] All previously plaintext secrets are rotated and stored encrypted at rest; no plaintext secret remains in repo or docs.
- [ ] Per-host/per-system scoping verified — a host cannot decrypt secrets it shouldn't (live broker keys isolated to the trading host).
- [ ] Every service boots reading secrets only from injected env/files; codebase + CI scan shows zero hardcoded credentials.
- [ ] A documented, tested rotation runbook exists and a full rotation of one secret succeeds with no code change.
- [ ] A pre-commit / CI guard blocks committing plaintext secrets.

## Notes & Risks
- **Single-operator key-loss risk:** if the only age/unseal key is lost, all secrets are unrecoverable — the offline recovery anchor and a documented break-glass procedure (FND-009) are mandatory.
- SOPS+age keeps cost at zero and infra minimal, fitting the solo/part-time constraint; Vault is overkill until there are real multi-user or dynamic-secret needs.
- This task is an upstream dependency for nearly every other system (FND-001/002/005/008, AMS-011, all broker access) — schedule it early.
