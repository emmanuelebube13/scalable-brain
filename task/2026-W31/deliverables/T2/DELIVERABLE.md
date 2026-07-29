# T2 — Secrets Hygiene (FIX-XC-003) · Technical Report

**Date:** 2026-07-29 · **Repo:** `scalable-brain` · **Status:** COMPLETE

> **No password value — old or new — appears in this document.** They are referred to
> throughout as OLD and NEW. The NEW value exists only in the git-ignored `.env` on this
> machine.

The live `ForexBrainDB` `sa` password was committed in plaintext across 11 tracked files.
It has been **rotated**, the old value **verified dead**, and all 27 tracked occurrences
purged from HEAD. `.env.example` now makes the environment reproducible without secrets.

---

## 1. Inventory (measured, not estimated)

The task file's original step 1 grepped for a **literal fragment of the live password**.
That was corrected before anything was committed — had the week's task folder been committed
as written, the secret would have been re-introduced into git by the very task meant to
remove it. Step 0 now reads the credential into `$OLD_DB_PASS` at runtime.

A second correction: the first inventory pass used `grep` without `-F`. The password
contains regex metacharacters, so plain-regex matching **missed
`configuration/postgresql_connection_details.txt`** — the single worst exposure, a plaintext
memo containing both the password and a full DSN. All counts below come from fixed-string
(`-F`) matching.

| Location | Occurrences | Tracked? | Disposition |
|---|---:|---|---|
| `configuration/postgresql_connection_details.txt` | 2 | yes | file rewritten as a pointer to `.env` |
| `docs/postgresql/POSTGRESQL_COMPLETE_GUIDE.md` | 5 | yes | → `${DB_PASS}` |
| `docs/postgresql/POSTGRESQL_NATIVE_SETUP.md` | 3 | yes | → `${DB_PASS}` |
| `docs/postgresql/POSTGRESQL_NATIVE_QUICK_START.md` | 2 | yes | → `${DB_PASS}` |
| `docs/postgresql/POSTGRESQL_MIGRATION_SUMMARY.md` | 1 | yes | → `${DB_PASS}` |
| `docs/proposed-fixes/cross-cutting/FIX-XC-003-…md` | 7 | yes | → `${DB_PASS}` (the fix report itself leaked it) |
| `docs/RESEARCH_NOTES_POSTGRESQL.md` | 1 | yes | → `${DB_PASS}` |
| `docs/implementation-roadmap/…/00-dependencies-and-prerequisites.md` | 1 | yes | → `${DB_PASS}` |
| `docs/implementation-roadmap/…/tasks/03-secrets-management-and-rotation.md` | 2 | yes | → `${DB_PASS}` (the secrets-management task leaked it) |
| `MDs/SCALABLE_BRAIN_LIVE_TRADING_READINESS_REVIEW.md` | 1 | yes | → `${DB_PASS}` |
| `src/sql/timescaledb/README.md` | 2 | yes | → `${DB_PASS}` |
| **Tracked subtotal** | **27 across 11 files** | | **all purged** |
| `.env` | 1 | no (git-ignored) | updated to NEW |
| `.claude/settings.local.json` | 1 | no | stale `export PGPASSWORD='…'` permission entry **deleted** |
| git history | 8 commits | — | **remains** — see §5 |
| System 2 / System 3 (other computers) | 0 | — | owner confirmed they do not connect to this database |

`index.html` was named in the task file as an exposure site; fixed-string matching found
**no occurrence** there. It is not a consumer.

---

## 2. Rotation

1. Generated a 28-character random password from an alphabet that **excludes shell-special
   characters** (`$ \` " ' \ ! & ; | < >` and space). The OLD password contained `$`, which
   had previously caused quoting bugs in cron scripts and psql URLs — `.env.example`
   documents this constraint.
2. `ALTER ROLE sa WITH PASSWORD '<NEW>'` executed through `src/common/db.py`.
3. `.env` `DB_PASS=` updated in the same step, before any other action.

### Verification

| Check | Result |
|---|---|
| NEW password via `src/common/db.py` | **DB OK** — read 134,407 rows from `fact_trade_outcomes` |
| OLD password via direct `psycopg2.connect` | **REJECTED** — `FATAL: password authentication failed for user "sa"` |

The old credential is dead. This was verified by attempting a real connection, not inferred.

---

## 3. Consumers updated

| Consumer | Action | Post-rotation check |
|---|---|---|
| `.env` (repo root) | `DB_PASS` → NEW | `get_engine().connect()` OK |
| `shell/cron_system1_retrain.sh` (hourly cron) | **no edit needed** — sources `.env` | orchestrator run clean |
| `shell/cron_oanda_ingest_saturday.sh` (weekly cron) | **no edit needed** — sources `.env` | reads 4,685,603 price rows OK |
| `.claude/settings.local.json` | stale PGPASSWORD permission entry removed | JSON re-parsed and rewritten |
| System 2 / System 3 | none — confirmed not consumers of this DB | n/a |

Both crontab entries invoke scripts that source `.env`, so the rotation propagates with no
further edits. There is **no BLOCKED remote item** for this task.

Full-pipeline touchpoint after rotation:

```
python -m src.system1.scheduler.orchestrator
{'ran': False, 'promoted': False, 'outcome': 'no_trigger_or_cooldown'}
```

---

## 4. `.env.example`

Created at the repo root with every key from CLAUDE.md's ENVIRONMENT section, placeholder
values, and a one-line comment each: `DB_*`, `OANDA_*`, `STORAGE_*`,
`GOOGLE_APPLICATION_CREDENTIALS`, `QUEUE_*`, `LAYER3_APPROVAL_THRESHOLD`. It records two
non-obvious operational facts: avoid shell-special characters in `DB_PASS`, and the GCS copy
of `latest.json` — not the local one — is authoritative.

`.gitignore` confirmed to cover `.env` and `secrets/`.

---

## 5. Remaining exposure — git history (accepted risk)

`git log -S<OLD>` matches **8 commits**. The old value is still recoverable from history by
anyone with a clone.

**This is accepted, not overlooked.** The mitigation is rotation: the credential in history
no longer authenticates against anything, so its disclosure value is zero. A history rewrite
(`git filter-repo` / BFG) would rewrite every commit hash, break every existing clone and
remote ref, and invalidate the SHAs referenced throughout this week's deliverables. It has
**not** been performed and requires explicit owner sign-off.

If a rewrite is ever chosen, note that it must also cover the `origin` remote and any clone
on the other two computers, and that the credential would still be in any fork or backup
taken before the rewrite — which is precisely why rotation, not rewriting, is the real fix.

---

## 6. Validation

```
git grep -F <OLD> HEAD          → PASS: not in HEAD
.env.example exists             → PASS
.gitignore covers .env, secrets/ → PASS
NEW password authenticates      → PASS
OLD password rejected           → PASS
orchestrator post-rotation      → no_trigger_or_cooldown
```

---

## 7. Commits

| SHA | Subject |
|---|---|
| `8a0acd9` | FIX-XC-003: rotate the committed sa password and purge it from the tracked tree |

The T2 prompt fix (removing the password fragment from the task file) landed earlier in
`90aecac` as part of the week-folder baseline commit.

No co-author trailer. Nothing pushed.

---

## 8. Follow-ups

1. **Two of the leaking files were the security documents themselves** — the FIX-XC-003
   report (7 occurrences) and the "secrets management and rotation" roadmap task (2). Any
   future secret-handling doc should reference `${DB_PASS}`, never a value.
2. **Nothing prevents recurrence.** A pre-commit secret scan would have caught all 27
   occurrences. Recommended for W32 — the publish path already has a secret scanner
   (MODEL-007) that could be reused.
3. `.claude/settings.local.json` held a credential in a tool-permission string. Worth a
   periodic check; it is untracked, so no scanner covers it.
