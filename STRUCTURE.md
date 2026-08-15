# STRUCTURE — where everything lives, and where new things go

The map of this repository. **One line per folder: what it is for, and what belongs in it.**

If you are about to create a file and are not sure where it goes, the answer is in the
"Put here" column. If nothing fits, that is a signal the file is something new — say so
rather than dropping it at the root.

Last updated: 2026-08-14 (structure/cleanup pass, `task/2026-August-week2/deliverables/CLEANUP/`)

---

## The one rule

> **Nothing new at the repo root.** The root is for repo-level config only
> (`README`, `CLAUDE.md`, `STRUCTURE.md`, `requirements.txt`, `conftest.py`,
> `docker-compose.yml`, `LICENSE`, `.env.example`, `.gitignore`).
>
> Everything else belongs in one of the eight folders below. The root grew to 24 entries
> because this rule did not exist in writing.

---

## Outside the repo

```
/home/emmanuel/Documents/Scalable_Brain/
├── scalable-brain/   this repo — all work happens here
├── .venv/            Python 3.12 environment. Cron scripts and CLAUDE.md
│                     hardcode this path. Do not move or rename it.
└── .claude/          Claude Code harness config
```

Nothing else should ever live at that level. Loose files there are outside version
control, so a mistake is permanent rather than a `git revert`.

---

## The eight folders

| Folder | What it is | Put here | Do NOT put here |
|---|---|---|---|
| **`src/`** | **The runtime.** Python that actually executes. | Pipeline modules, shared libraries, their unit tests (co-located in `tests/`) | Docs, notes, one-off scripts, generated output |
| **`shell/`** | Scripts invoked by cron or by hand | `cron_*.sh`, setup/migration scripts, one-off analysis scripts | Anything imported by `src/` — that is a library, it goes in `src/common/` |
| **`contracts/`** | JSON schemas for cross-machine messages. **Read at runtime.** | Message/data contracts shared with Systems 2 and 3 | Documentation *about* the contracts — that is `docs/` |
| **`docs/`** | **All prose.** Ten subfolders, listed below. | Anything explanatory | Work items with a definition of done — those are `task/` |
| **`task/`** | **Work items.** Something to do, with a done condition. | See the `task/` section below | Reference material or explanation — that is `docs/` |
| **`results/`** | Pipeline output — reports, state, queue | Machine-written files | Anything hand-authored |
| **`logs/`** | Runtime logs. Git-ignored in full. | Nothing by hand | — |
| **`archieved/`** | **Frozen history.** Zips + SHA256 manifests. | A `.zip` and its `.sha256`, nothing else | Unpacked trees. If it is unpacked it is not archived, it is just moved |

Plus four generated I/O paths that code writes to and `.env` points at — leave them alone:
`models/`, `model-artifacts/`, `feature-store/`, `mlruns/`.

And two you should not touch: `secrets/` and `configuration/` (both hold credentials,
both git-ignored).

> **The `archieved` spelling is deliberate.** It is referenced by `.gitignore` and by
> prior task records. Leave the typo.

---

## `src/` — the runtime

| Path | Role |
|---|---|
| `src/system1/` | **The live pipeline**, MODEL-001…010. This is the code that matters. Do not reorganise casually |
| `src/common/` | Shared abstractions: `db.py`, `storage/`, `queue/`. All DB access goes through `db.py` |
| `src/layer0/` | Legacy name, **still load-bearing**: indicators, backtest engine, the strategies sandbox |
| `src/layer3_ml/` | A deliberate tombstone plus its guard tests. Do not "fix" it by restoring the retired module |
| `src/nlp/`, `src/sql/` | Auxiliary FinBERT work; raw SQL |

Legacy layers 1, 2, 4, 5, 6, 7 were retired and archived — see `CLAUDE.md`.

---

## `docs/` — all prose

| Folder | What goes in it |
|---|---|
| `design/` | System design, ERDs, data dictionary, contract specs, System-3 design |
| `database/` | Schema, SQL translation rules, PostgreSQL guides, migration records |
| `implementation-roadmap/` | MODEL-001…010 task specs, per-system roadmaps |
| `proposed-fixes/` | `FIX-S1-*`, `FIX-S2-*`, `FIX-S3-*`, `FIX-XC-*`. **Check here before reporting a bug** — it may be known, fixed, or in flight |
| `comms/` | Correspondence with Computers 2 and 3. Append-only in spirit: **do not rewrite a message that was already sent** |
| `goals/` | Targets and milestones: value ladder, metrics-and-targets framework, period goals |
| `research/` | Papers, ML research notes, exploratory analysis |
| `reference/` | How-to guides, chart system docs, documentation indexes |
| `notes/` | Scratch and third-party notes. The one folder allowed to be untidy |
| `critical/` | Readiness checklists and known-issue registers |
| `presentations/` | Slide decks and their generators |
| `frontend/` | Static HTML doc viewers (ERD browser, data dictionary). **Not an application** — no build, no server |
| `worklog/` | Dated session records: what happened on a given day |
| `system1Education/` | **A nested git repo** with its own GitHub remote. Git-ignored here. Do not move it, do not zip it |

**Choosing between `docs/` and `task/`:** if it has a definition of done, it is a task.
If it explains something, it is a doc. A document that does both should be split.

---

## `task/` — work items

```
task/
├── OPEN.md          <- START HERE. The current open-items register.
│                       Update in place. Do not start a competing list.
├── backlog/           Raised, scoped, not started
├── 2026-July-week4/   Week folders — YYYY-Monthname-weekN (N = 1–4)
├── 2026-August-week1/
├── 2026-August-week2/
└── 2026-07-28.md      Older loose session logs (superseded convention)
```

| Status | Where |
|---|---|
| Current priorities | `task/OPEN.md` |
| Raised but not started | `task/backlog/<slug>.md` |
| Active work, this week | `task/<YYYY>-<Month>-week<N>/` — the month is the one holding that week's **Monday** |
| Finished work | **stays in its week folder** |

Week folders are **not** moved or nested when finished. Other documents cite them as
evidence (`task/2026-July-week4/deliverables/T3/` appears throughout `docs/proposed-fixes/`, and
in correspondence already sent to Computers 2 and 3). Moving a finished week silently
breaks every one of those pointers and makes sent messages inaccurate. Completion status
is tracked in the week table in **`task/README.md`**, not in the directory layout.

---

## Adding something new

1. **A new Python module?** → `src/`, next to what it relates to, with its test beside it.
2. **A new document?** → pick a `docs/` subfolder from the table. If two fit, pick the one
   a stranger would search first.
3. **A new work item?** → `task/OPEN.md` if it is next, `task/backlog/` if it is not.
4. **A one-off script?** → `shell/`.
5. **None of the above fit?** → do not default to the root. That is how the root reached
   24 entries. Propose a new folder and add a row to this file in the same change.

**Whenever you add or rename a folder, update this file in the same change set.** A map
that is not maintained becomes a second thing to be confused by.
