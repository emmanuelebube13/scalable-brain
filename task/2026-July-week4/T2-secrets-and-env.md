# T2 — Secrets Hygiene: Rotate the Committed DB Password (FIX-XC-003) + `.env.example`

> Paste this whole file as the prompt. Repo: `/home/emmanuel/Documents/Scalable_Brain/scalable-brain`.
> **First action: read `task/2026-July-week4/STATE.md` and follow its protocol.**

## Mission

The live `ForexBrainDB` `sa` password is committed in git-tracked files (`configuration/postgresql_connection_details.txt`, `index.html`) and in history. Rotate the credential, purge it from the tracked tree, and add a `.env.example` so the environment is reproducible without secrets. This is a P1 and it is small — finish it in one session.

## Read first

- `docs/proposed-fixes/cross-cutting/FIX-XC-003-db-password-committed-in-tracked-files.md` — full evidence and file list
- `src/common/db.py` — how the connection is built (env-driven; nothing should hardcode the DSN)

## Agent team

Single **general-purpose agent**. This task touches a live credential — no parallelism, every step verified before the next.

## Execution plan

0. **Capture the old credential into a shell variable — never into a file.** [REVISED 2026-07-29: the original steps embedded a literal fragment of the live password in this prompt, which would have committed the secret into git the moment the week folder was tracked. All greps now go through `$OLD_DB_PASS`.]
   ```bash
   OLD_DB_PASS="$(grep -m1 '^DB_PASS=' .env | cut -d= -f2-)"; [ -n "$OLD_DB_PASS" ] && echo "captured (${#OLD_DB_PASS} chars)"
   ```
   Keep this variable for the whole session; do not echo it, do not write it to any deliverable, do not paste it into a commit.
1. **Inventory — use `-F` (fixed string).** `git grep -lnF -e "$OLD_DB_PASS" HEAD` and `grep -rnIF --exclude-dir=.git --exclude-dir=.venv --exclude-dir=node_modules -e "$OLD_DB_PASS" .` [REVISED 2026-07-29: without `-F` the password's regex metacharacters silently change the search and the worst exposure is missed — see Failure log.] (also search for the DSN string `postgresql://sa:`). List every hit — tracked, untracked, and any logs/notebooks. Check `OtherSystems/` and `deployment-guide/` too (the other systems use the same DB creds pattern).
2. **Rotate the password in PostgreSQL.** Generate a strong password (no shell-special chars that broke things before — the old one's `$` caused quoting bugs): `ALTER ROLE sa WITH PASSWORD '<new>';` via psql. **Immediately** update `.env` (`DB_PASS=`) and verify: `python -c "from src.common.db import get_engine; get_engine().connect(); print('DB OK')"`.
3. **Update every other consumer of the old password found in step 1** — cron scripts, the ingest health-check path (see memory of OANDA ingest), any `.env` on this machine outside the repo. Re-run the connectivity check after each. If a consumer lives on another computer (System 2/3 VMs), record it in STATE.md as a BLOCKED item with the exact instruction for the user — do not guess remote credentials handling.
4. **Purge from the tracked tree.** Remove the credential from `configuration/postgresql_connection_details.txt` (replace file content with a pointer: "credentials live in `.env` — see `.env.example`") and from `index.html` (edit the troubleshooting note to reference `.env` instead of the literal). Commit. Note in the commit body that history still contains the old (now-rotated) secret — rotation, not history rewrite, is the mitigation; do NOT run a history rewrite (filter-repo/BFG) without explicit user sign-off since the repo has remotes/clones.
5. **`.env.example`.** Create it at repo root: every key from CLAUDE.md's ENVIRONMENT section with placeholder values and a one-line comment each (DB_*, OANDA_*, STORAGE_*, GOOGLE_APPLICATION_CREDENTIALS, QUEUE_*, LAYER3_APPROVAL_THRESHOLD). Confirm `.env` and `secrets/` are in `.gitignore`.
6. **Update the fix doc.** Set FIX-XC-003 status to `IMPLEMENTED <date> — rotated + purged from HEAD; history not rewritten (accepted risk, old credential dead)`.

## Validation

```bash
git grep -c -- "$OLD_DB_PASS" HEAD && echo "FAIL: secret still tracked" || echo "PASS: not in HEAD"
python -c "from src.common.db import get_engine; import sqlalchemy; e=get_engine(); e.connect(); print('DB OK with new password')"
# MUST FAIL (auth error) — old credential dead. psql needs an interactive password
# on this box, so assert it in Python instead:
python -c "import psycopg2,os,sys; \
  psycopg2.connect(host='localhost',port=5432,dbname='ForexBrainDB',user='sa',password=os.environ['OLD_DB_PASS'],connect_timeout=5) and sys.exit('FAIL: old password still works')" 2>&1 | grep -q "authentication failed" && echo "PASS: old credential dead"
test -f .env.example && echo "PASS: env template exists"
```

Also run one real pipeline touchpoint to prove nothing else broke: `python -m src.system1.scheduler.orchestrator` (expects clean `no_trigger_or_cooldown`).

## Acceptance criteria

- [x] Old password no longer authenticates (`FATAL: password authentication failed`); new one works via `src/common/db.py`
- [x] `git grep -- "$OLD_DB_PASS" HEAD` returns nothing (27 occurrences purged from 11 files)
- [x] All local consumers updated. No remote consumers — owner confirmed System 2/3 do not use this DB, so no BLOCKED item.
- [x] `.env.example` committed; `.gitignore` covers `.env` + `secrets/`
- [x] FIX-XC-003 status updated to IMPLEMENTED. Commit `8a0acd9`, no co-author trailer.

## Deliverables (required — task is not DONE without them)

Write to `task/2026-July-week4/deliverables/T2/`:

1. **`DELIVERABLE.md`** — detailed report: every location the secret was found (tracked / untracked / history / other machines), what was done at each, rotation timestamp, every consumer updated and its post-rotation connectivity check result, remaining exposure (history — accepted risk, credential dead), commit SHAs. **Never write the old or new password into any deliverable** — refer to them as OLD/NEW.
2. **Visual (1 PNG):** `exposure_before_after.png` — horizontal bar chart: each exposure location (tracked file ×2, git history, .env consumers, remote/VM consumers) with its status before (red = live secret exposed) and after (green = purged/rotated, amber = BLOCKED awaiting user action on another machine). One glance = what risk existed and what remains.
3. **`EXECUTIVE_SUMMARY.md`** — max 1 page: the live DB password was in the public-facing repo tree since at least June 26; it has been rotated and purged from HEAD; old credential verified dead; history still contains the dead credential (why that's acceptable / what a history rewrite would take); `.env.example` now makes setup reproducible without secrets.

## On failure

If rotation breaks any pipeline (cron, ingest, orchestrator): the fix is forward (update that consumer's env), **never** rolling back to the leaked password. Log root cause in `## Failure log`, correct the step, update STATE.md.

## Failure log

**2026-07-29 — step 1 inventory under-reported the exposure.**
*Failing check:* the first `grep -rIl` over the working tree returned 11 hits but **missed
`configuration/postgresql_connection_details.txt`**, the worst one (plaintext password + full
DSN), while `git grep` over HEAD did list it.
*Root cause:* the password contains regex metacharacters, and neither grep was given `-F`.
Basic-regex interpretation silently changed what was being searched for.
*Correction applied to step 1 above:* all inventory greps now use `-F` (fixed string).
*Also corrected (step 0, added):* the original step 1 embedded a literal fragment of the live
password in this prompt file. Committing the week folder would have re-introduced the secret
into git via the task designed to remove it. All greps now go through `$OLD_DB_PASS`, read
from `.env` at runtime.
