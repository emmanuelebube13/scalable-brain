# docs/ — all prose

Everything explanatory lives here. **If it has a definition of done it is a task, not a
doc** — put it in `task/`. See `STRUCTURE.md` for the full repository map.

| Folder | What goes in it | Start with |
|---|---|---|
| `design/` | System design, ERDs, data dictionary, contract specs, System-3 design | `RESEARCH_STRATEGY_ENGINE.md`, `SCALABLE_BRAIN_REVIEW_AND_SYSTEM3_DESIGN.md` |
| `database/` | Schema, SQL rules, PostgreSQL guides, migration records | `SQL_TRANSLATION_RULES.md` |
| `implementation-roadmap/` | MODEL-001…010 specs, per-system roadmaps | `system-1-model-building/` |
| `proposed-fixes/` | `FIX-S1-*`, `FIX-S2-*`, `FIX-S3-*`, `FIX-XC-*` | `README.md` |
| `comms/` | Correspondence with Computers 2 and 3 | `README-START-HERE.md` |
| `goals/` | Targets and milestones | `VALUE_MILESTONES.md`, `SYSTEM1_METRICS_AND_TARGETS.md` |
| `research/` | Papers, ML research, exploratory analysis | `RESEARCH_NOTES_QUICKSTART.md` |
| `reference/` | How-to guides, chart docs, documentation indexes | `DOCUMENTATION_INDEX_2026_04_05.md` |
| `notes/` | Scratch and third-party notes — the one folder allowed to be untidy | — |
| `critical/` | Readiness checklists, known-issue registers | `buyer_readiness_checklist.md` |
| `presentations/` | Slide decks and their generators | — |
| `frontend/` | Static HTML doc viewers. **Not an application** — no build, no server | `index.html` |
| `worklog/` | Dated session records: what happened on a given day | most recent date |
| `system1Education/` | **A nested git repo** with its own GitHub remote, git-ignored here. Do not move or zip it | `01-big-picture.html` |

## Two rules

1. **Before reporting a bug, check `proposed-fixes/`.** It may be known, fixed, or in flight.
2. **Do not rewrite anything in `comms/` that was already sent.** Those are records of
   what another machine was told. Correct them with a new message, not an edit.

## Choosing a folder

If two fit, pick the one a stranger would search first. If none fit, do not leave the file
loose in `docs/` — propose a folder and add a row to this table in the same change.
