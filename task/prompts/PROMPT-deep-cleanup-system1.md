# Deep Cleanup Prompt — System 1 (`scalable-brain`)

> Paste everything below the line into the cleanup agent.

---

## Task

Perform a full housekeeping pass on the System 1 repository at
`/home/emmanuel/Documents/Scalable_Brain/scalable-brain` (branch `cleanup`).

Four workstreams:

1. **Root cleanup** — the repo root has drifted past its allowlist. Return it to the allowlist.
2. **Misplaced files elsewhere** — files sitting in the wrong folder anywhere in the tree.
3. **Routine deletion** — remove short-term/testing artifacts with no future value.
4. **README refresh** — every folder that needs orientation has an accurate README.

**This is a live production system.** Read the two constraint sections before touching anything.

---

## Read these first, in this order

1. `STRUCTURE.md` — the authoritative folder map. It contains "the one rule" (nothing new at the
   root) and a per-folder "Put here / Do NOT put here" table. **This file is your specification.**
2. `CLAUDE.md` — repo conventions, the AGENT RULES section in particular.
3. `task/OPEN.md` — the open-items register, so you don't delete something with active work on it.

Where `STRUCTURE.md` and reality disagree, reality wins and **you update `STRUCTURE.md`** — see
"Known map drift" below.

---

## HARD CONSTRAINTS — violating any of these is a failed task

### The system is live right now

- An hourly cron fires at **:15 past every hour** (`shell/cron_hourly_signals.sh`) and does
  ingest → signals → health → model-card mirror. It reads `src/`, writes `results/state/` and
  `logs/`. Additional crons: `30 22 * * 1-5`, `0 6 * * *` (heartbeat), `0 0 * * 6` (Saturday ingest).
- **Do not move, rename, or delete anything under `shell/`** without checking `crontab -l` first.
  The crontab references absolute paths; renaming a script silently breaks the schedule.
  (Note: `crontab -l | head` hides the entries behind a long comment block — use
  `crontab -l | grep -vE '^\s*#'`.)
- Cron scripts hardcode the venv at `/home/emmanuel/Documents/Scalable_Brain/.venv`
  (outside the repo). Do not move or reference it relatively.
- Prefer to do bulk file operations **shortly after :20**, not at :14, so you never race a run.

### Never delete or move these

| Path | Why |
|---|---|
| `conftest.py` (root) | Load-bearing — it is what makes `import src...` resolve. Deleting it breaks the entire test suite. It IS on the root allowlist. |
| `.env` (root) | Runtime config, git-ignored. Not in the STRUCTURE.md allowlist but required. Leave it. |
| `results/state/*.json` | **Live runtime state**, not scratch: `watcher_state.json` (bar dedup cursor), `signal_emitter_state.json` (emission telemetry, 46 signals to date), `cron_holds.json`, `retrain_state.json`, `regime_strategy_map.json`. Deleting these causes duplicate or lost signal emission. |
| `secrets/`, `configuration/` | Credentials. Do not read out, do not move, **never commit**. |
| `models/`, `model-artifacts/`, `feature-store/`, `mlruns/` | Generated I/O paths that `.env` points at. Leave alone. |
| `archieved/` | Frozen history, git-ignored wholesale. **The typo is deliberate** — `.gitignore` and prior task records reference it. Do not "fix" the spelling. |
| `src/layer0/` | Legacy name, still load-bearing (indicators, backtest engine, strategy sandbox). |
| `src/layer3_ml/` | A deliberate tombstone plus guard tests. Do not restore it, do not delete the guards. |
| `task/<YYYY>-<Month>-week<N>/` | Finished week folders **stay put**. `docs/proposed-fixes/` and messages already sent to Computers 2 and 3 cite these paths as evidence. Moving one silently breaks every citation. |
| `docs/comms/` | Append-only in spirit. **Do not rewrite or delete a message that was already sent.** |
| `docs/frontendEducation/fullArchitecture/`, `docs/frontendEducation/system1Education/` | **Nested git repos** with their own GitHub remotes, git-ignored here. Do not move, zip, or reorganize. |
| `../system-2-execution-engine/`, `../system-3-account-management/` | Deployed on other machines. Local copies are reference only. Do not touch. |
| The six prompts listed under "Prompts that stay in place" in `task/prompts/README.md` | Prompt consolidation was already done on 2026-08-28. Those six are cited by path from other documents — one from a message already sent — or bound to a sibling `STATE.md`. **Do not move them into `task/prompts/`.** New prompts go in `task/prompts/`; that folder is already correct. |

### Credentials at the root — handle with care

`.env.bak-20260817` and `.env.bak-20260822T172002Z` sit at the repo root and almost certainly
contain live OANDA / DB / GCS credentials in plaintext.

- Do **not** `git add` them, and do not paste their contents into any output or commit message.
- Verify they are git-ignored (`git check-ignore -v <file>`).
- Treat them as **owner-approval-required deletions**. Recommend moving them outside the repo
  (or into `secrets/`) rather than deleting outright, and flag whether the credentials in them
  differ from the current `.env` — if they do, they may be the only copy of a rotated secret.

---

## Workstream 1 — Root cleanup

`STRUCTURE.md` defines the root allowlist as exactly:
`README.md`, `CLAUDE.md`, `STRUCTURE.md`, `requirements.txt`, `conftest.py`,
`docker-compose.yml`, `LICENSE`, `.env.example`, `.gitignore` (plus `.env` and tooling dotdirs
in practice).

Current violations to resolve — for each, determine the correct destination from
`STRUCTURE.md`, or recommend deletion with a reason:

**Loose Python scripts** (candidates for `shell/`, `src/`, or deletion — decide per file by
checking whether anything imports or references them):
- `generate_ranking_report.py`
- `generate_reference_vector.py`
- `generate_report.py`
- `run_R0.py`
- `test_eval.py`
- `test_p1.py`

**Logs at the root** (`logs/` already holds same-named files — verify they are duplicates,
then delete the root copies):
- `model001_ingest.log`
- `model003_regime.log`

**Docs at the root:**
- `SYSTEM_ARCHITECTURE_EXPLANATION.md` → pick a `docs/` subfolder

**Credential backups** — see the care note above:
- `.env.bak-20260817`, `.env.bak-20260822T172002Z`

**Root directories not in the STRUCTURE.md map** — classify and resolve:
- `goal/` — holds one file, `2026-08-AUGUST-WEEKEND-GET-TRADING-STARTED.md`. Note `docs/goals/`
  already exists and is the mapped location. Almost certainly a merge target.
- `scratch/` — holds one file, `extract_docs.py`. Not in the map.

For each root script, before proposing deletion run something like
`grep -rn "<basename>" --include='*.py' --include='*.sh' --include='*.md' .` to prove nothing
references it. **Evidence of non-reference is required for every deletion proposal.**

---

## Workstream 2 — Misplaced files elsewhere

Walk the tree and find files violating the `STRUCTURE.md` "Do NOT put here" column. Look
specifically for:

- Docs/prose sitting inside `src/` (belongs in `docs/`)
- One-off scripts inside `src/` (belongs in `shell/`)
- Hand-authored files inside `results/` (`results/` is machine-written output only)
- Work items with a definition of done filed under `docs/` (belongs in `task/`)
- Anything unpacked inside `archieved/` (it should be `.zip` + `.sha256` only)

**In-flight reorganization you must resolve deliberately, not blindly:** the working tree
already has an uncommitted move of `docs/comms/*.md` → `docs/comms/to_system2/` (git shows these
as deletes plus untracked additions). Some files appear in the new location that were not in the
old. Reconcile this into a single coherent, intentional state — and preserve every sent message.
Confirm the direction with the owner if ambiguous.

---

## Workstream 3 — Routine deletion of short-term artifacts

The biggest accumulation is `results/reports/` — **385 files**, dominated by hourly cron output:

| Prefix | Count |
|---|---|
| `ingest_manifest_*` | 144 |
| `dq_gap_report_*` | 144 |
| `vetting_report_*` | 33 |
| `attribution_report_*` | 29 |
| `qualification_report_*` | 24 |

Do **not** blanket-delete these. Instead:

1. Propose an explicit **retention policy** (e.g. "keep the most recent N of each prefix, plus
   any file referenced by a doc").
2. Before deleting any report, grep `docs/`, `task/`, and `issues/` for its filename — several
   reports are cited as evidence in proposed-fixes and in correspondence already sent.
3. Apply the policy only after owner approval, and record the policy in
   `results/README.md` so the next pass is mechanical rather than another judgment call.

Also sweep for: `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `*.pyc`, `*.tmp`, `.DS_Store`,
editor backups, and `*.orig`/`*.rej` merge leftovers. Confirm each is git-ignored; if not, add
to `.gitignore` in the same change.

---

## Workstream 4 — README refresh

Currently only **19** READMEs exist across the repo, and many mapped folders have none —
including `contracts/`, `results/`, `docs/design/`, `docs/comms/`, `docs/goals/`,
`docs/research/`, `docs/worklog/`, and every `docs/proposed-fixes/system-*/`.

Rules:

- A README should orient a newcomer: **what this folder is for, what belongs in it, and what
  does not.** Match the tone and format of `STRUCTURE.md` and the existing READMEs — read
  `task/README.md` and `src/common/storage/README.md` first as the house style.
- **Use judgment about depth.** `results/research/` has ~47 per-strategy subfolders; those need
  *one* explanatory README at the `results/research/` level describing the naming convention,
  **not 47 stub files**. Blanket stub READMEs are clutter, not documentation.
- Do not add a README to the nested git repos, to `archieved/`, or to `secrets/` /
  `configuration/`.
- Every README must be accurate as of today. Do not describe aspirational structure.

---

## Known map drift — fix as part of this pass

- `STRUCTURE.md` lists **`src/regime_aware/`** as a live experiment folder. **It no longer
  exists** (removed with the failed R3 experiment, FIX-S1-016). Remove the row.
- `CLAUDE.md` states "Signals emitted to date: **0**" and describes a **6-cell** regime→strategy
  map. Both are stale as of 2026-08-28: `results/state/signal_emitter_state.json` shows
  **46 signals published**, last emitted `2026-08-26T21:15:36Z`, and the live map has **13 cells**.
  The "0 signals" line in particular will send a reader hunting an already-fixed bug.
- `CLAUDE.md` lists the crontab as four entries "verified 2026-08-23" — re-verify against
  `crontab -l` and correct if drifted.
- Confirm the "Last updated" line at the top of `STRUCTURE.md` and the header block in
  `CLAUDE.md` are updated in the same change set, per the rule at the bottom of `STRUCTURE.md`.

---

## Method

1. **Inventory first, change nothing.** Produce a complete classification of every candidate:
   `path | verdict (move/delete/keep) | destination | evidence`.
2. **Present the plan and get owner approval before any deletion.** Moves inside the repo are
   reversible via git; deletions of git-ignored files are not. Treat every git-ignored file as
   unrecoverable and require explicit sign-off.
3. Execute in **small, reviewable commits**, grouped by workstream — not one giant commit.
   Use `git mv` so history follows the file.
4. Do not commit `.env`, `secrets/`, `configuration/`, credential backups, or model binaries.

## Verification — all must pass before you report done

```bash
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain
source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate

# 1. Test suite still collects and runs (see the known-red note below)
python -m pytest src -q --ignore=src/layer0/strategies/research/tests

# 2. Critical modules still import
python -c "import src.signals.run, src.signals.build, src.ingestion.multi_timeframe_ingest, src.monitoring.heartbeat; print('imports OK')"

# 3. The live path still works end to end, without emitting
python -m src.signals.run --dry-run
python -m src.monitoring.heartbeat --json

# 4. Cron scripts still resolve their paths
bash -n shell/cron_hourly_signals.sh && crontab -l | grep -vE '^\s*#'

# 5. Nothing sensitive staged
git status --short && git diff --cached --name-only
```

**Known-red baseline (pre-existing — do not attribute to your changes, and do not "fix" by
reverting behavior):** 2 collection errors in `src/layer0/strategies/research/tests/`, plus
~19 failures that are stale assertions against the old 60-month OOS gate (deliberately lowered
to 12 on 2026-08-21) and pinned SHA256s in `test_wave1_guards.py`. **Capture the exact
pass/fail counts BEFORE you start** and confirm the numbers are unchanged at the end. Any *new*
failure is yours.

Also confirm after the next `:15` cron run that `logs/cron_hourly_signals.log` shows a clean
run and `results/state/signal_emitter_state.json` still advances `last_run_at`.

## Deliverable

- A written cleanup record at `task/<current-week>/deliverables/CLEANUP/CLEANUP-<YYYY-MM-DD>.md`
  following the precedent of `task/2026-August-week2/deliverables/CLEANUP/CLEANUP-2026-08-16.md`:
  what moved, what was deleted and why, what was deliberately left alone.
- `STRUCTURE.md` and `CLAUDE.md` updated in the same change set.
- A short summary of anything you found but did **not** act on, filed to
  `issues/<Month>-Week-<N>/<today>.md` (append to today's file if it exists).

## Report back

State plainly: what you moved, what you deleted, what you left and why, the before/after test
counts, and anything you deliberately skipped. If a workstream was blocked, finish the others in
full and say explicitly what was left out.
