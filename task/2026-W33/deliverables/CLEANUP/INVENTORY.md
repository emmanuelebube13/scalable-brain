# CLEANUP — Phase 1 Inventory

**Task:** `task/BACKLOG-repo-structure-and-cleanup.md`
**Date:** 2026-08-14 · **Phase:** 1 of 4 (read-only — nothing has been moved or deleted)
**Precedent:** T7 (`task/2026-W31/T7-archive-v1-cleanup.md`)

---

## 0. Headline

The backlog was written on 2026-08-13 and said *"there is no space pressure — everything
outside `scalable-brain/` is ~4 MB, so the goal is clarity, not reclamation."*

**That was true of the root and is still true of the root. It is not true inside the repo.**

| | Size |
|---|---|
| `.venv/` (root, keep — cron and CLAUDE.md depend on it) | 6.4 G |
| `scalable-brain/` | 1.1 G |
| everything else at root | 200 K |

Of the 1.1 G inside the repo, **~715 M is regenerable cache, dead-layer logs, and a
`node_modules` tree inside an archive.** None of it is referenced by anything. Reclaiming it
is not the point, but it is the reason the tree feels unnavigable: the four largest things in
the repo are all garbage, and they sit next to the four things that matter.

The clarity problem and the weight problem have the same fix, so this pass does both.

---

## 1. Root — `/home/emmanuel/Documents/Scalable_Brain/` (NOT version-controlled)

A bad delete here is permanent. Note the root is already much cleaner than the backlog
described: `OtherSystems/` and `system1Education/` have since moved into the repo.

| Path | Size | Modified | Tracked | Last referenced by | Bucket |
|---|---|---|---|---|---|
| `scalable-brain/` | 1.1 G | live | — (is the repo) | everything | **KEEP** |
| `.venv/` | 6.4 G | — | no | `CLAUDE.md`, all `shell/cron_*.sh` | **KEEP** |
| `.claude/` | 4 K | 2026-07-05 | no | Claude Code harness | **KEEP** |
| `plans/` | 48 K | 2026-07-10 | no | nothing | **ARCHIVE** — 3 design docs for the strategy-research engine; superseded by `docs/design/RESEARCH_STRATEGY_ENGINE.md` (T6, shipped) |
| `sandbox-handoff/` | 80 K | 2026-08-09 | no | nothing in repo | **ARCHIVE** — blind-protocol brief for external agents; superseded by `task/2026-W32/fleet/` |
| `oanda_ingest.log` | 68 K | **2026-06-23** | no | nothing | **DELETE** — stale by 7 weeks; the live one is `scalable-brain/logs/oanda_ingest.log` |
| `.pytest_cache/` | 28 K | 2026-08-11 | no | pytest (regenerates) | **DELETE** |

**Root after this pass: `scalable-brain/`, `.venv/`, `.claude/`, and a new `README.md`
that says where everything is.** That is the layout you asked for.

---

## 2. Repo — `scalable-brain/`

### 2a. DELETE — generated, regenerable, referenced by nothing

| Path | Size | Why it is safe |
|---|---|---|
| `.mypy_cache/` | **122 M** | mypy rebuilds it. **Not in `.gitignore`** — that is a bug this pass fixes |
| `archieved/layer5/frontend/node_modules/` | **292 M** | npm install output, inside an archive of a retired layer. `package.json` + `package-lock.json` stay |
| `logs/cron_layer4.log`, `layer4_cron.log`, `layer4_execution.log*`, `layer4_cron_*.log` (2661 files) | **~300 M** | Layer 4 was retired 2026-07-08 (FIX-S1-009) and its cron disabled; last entry 2026-07-04. Git-ignored, so no history exists either way |
| `__pycache__/`, `shell/__pycache__/` | 8 K | regenerated |
| ~~`results/qualification_report_*`~~ | — | **CORRECTED 2026-08-14 — not deleted.** These read as 0 B under `du` because they are **symlinks** into `results/reports/` and `results/state/`, not empty files. They are backward-compatibility shims; 36 of them clutter the `results/` root but removing them could break an unknown caller. **Left in place — moved to UNCERTAIN (§2e)** |
| `design/` (whole folder) | 864 K | **All 7 files are byte-identical duplicates** of `docs/design/` — verified with `cmp`. Confirmed: `DatabaseERD.drawio`, `datadictionary.pdf`, `datadictionary.xlsx`, `dfd.drawio.png`, `DFD_level1.drawio`, `erd.png`, `logo.png` |

**Subtotal: ~715 M, zero live references.**

### 2b. ARCHIVE — historical value, no live reference

| Path | Size | Note |
|---|---|---|
| `backups/ForexBrainDB_pre_timescaledb_*.dump` | 167 M | Pre-TimescaleDB DB dump, 2026-06-22. Git-ignored. **Do not delete** — but it does not belong in a code tree. Move to `~/backups/` outside the repo |
| `archieved/v1-cleanup-2026-W31/` | 3.2 M | Already has its own `.zip` + `.sha256` **sitting beside it, unpacked.** Keep the zip, drop the unpacked copy |
| `MDs/` | 72 K | 4 orphan docs (`INSTALL_ADVANCED_CHARTS`, `LAYER5_ISSUES_AND_FIXES`, `POSTGRESQL_MIGRATION_GUIDE`, `LIVE_TRADING_READINESS_REVIEW`). Two are about retired layers; two duplicate `docs/postgresql/` topics. **T7 UNCERTAIN — resolve now** |
| `proposedchanges/` | 24 K | 2 phase-migration prompts, FND-004 era, complete. **T7 UNCERTAIN — resolve now** |

### 2c. KEEP but RELOCATE — right content, wrong place

This is the actual "hard to track where things are" problem. Fourteen top-level folders where
four would do.

| Path | Size | Where it should go | Why |
|---|---|---|---|
| `frontend/` | 280 K | `docs/frontend/` | 9 static HTML docs (ERD viewer, data dictionary, architecture). Not an app — no build, no server. Referenced only from other docs. **T7 UNCERTAIN — resolve now** |
| `othersystemcommunication/` | 204 K | `docs/comms/` | Inter-machine correspondence. A second copy exists at `archieved/OtherSystems/comms/` — this is the live one |
| `docs/postgresql/` | 52 K | `docs/database/` | Same subject, split across two folders |
| `docs/chartdesign/` | 40 K | `docs/reference/` | 2 chart guides; `reference/` already holds `CHART_SYSTEM_PROMPT.md` |
| `docs/proposedchanges/` | 76 K | `docs/architecture/` | System-3 design docs — architecture, not proposals |
| `configuration/` | 8 K | delete folder, keep file | One git-ignored file: `postgresql_connection_details.txt`. Credentials belong with `secrets/` |
| `model001_ingest.log`, `model003_regime.log`, `oanda_ingest.log` (repo root) | 124 K | `logs/` | Loose logs in the repo root |
| `STATUS-2026-08-14.md` (repo root, untracked) | 12 K | `docs/worklog/` | Where `2026-08-14.md` already lives |
| `scripts/` (1 file) | 16 K | `shell/` | A single one-off `fix_s1_012_sensitivity.py` alone in a folder |
| `task/2026-07-28.md`, `task/2026-08-14.md` | 8 K | `task/` (rename) | See §3 |

### 2d. KEEP IN PLACE — load-bearing, do not touch

| Path | Why |
|---|---|
| `src/` | The runtime. Backlog constraint: `src/system1/` is not reorganised casually; `src/layer0/` is load-bearing despite the legacy name |
| `shell/` | **`crontab -l` references `shell/cron_oanda_ingest_saturday.sh` by absolute path.** Moving this folder breaks the only live cron. Excluded from this pass |
| `contracts/` | Read at runtime by `src/system1/vetting/vet.py` |
| `results/`, `models/`, `model-artifacts/`, `feature-store/`, `mlruns/` | Pipeline I/O paths hardcoded in `src/` and `.env` |
| `docs/system1Education/` | **Nested git repo** with its own GitHub remote. Git-ignored. Do not move, do not zip |
| `archieved/OtherSystems/system-2-*`, `system-3-*` | Reference copies for two unreachable machines. Backlog: out of scope until each host confirms an authoritative copy |
| `secrets/`, `.env` | Explicitly out of scope |
| `conftest.py`, `requirements.txt`, `docker-compose.yml`, `LICENSE`, `.env.example`, `README.md`, `CLAUDE.md` | Standard repo root |

### 2e. UNCERTAIN — left in place, your call

The backlog requires this bucket to be non-empty. Three items:

| Path | The question |
|---|---|
| `AGENTS.md` (9 K, 2026-07-05) | Predates the current `CLAUDE.md` and overlaps it. Two agent-instruction files that can disagree is worse than one that is wrong. Merge into `CLAUDE.md`, or keep as the tool-neutral copy? **T7 left this open; still open** |
| `mlruns/` (188 K) | MLflow tracking DB, **not git-ignored** but never committed. 4 experiment dirs, last written 2026-06-24. Live MLflow runs or dead? |
| `archieved/OtherSystems/system1-documentation/` (92 K) | A copy of *this* system's docs, sent to the other machines. May have drifted from `docs/` |
| `results/qualification_report_*` (36 symlinks) | Backward-compat symlinks into `results/reports/` + `results/state/`, created 2026-04-04. They make `results/` look like it holds 46 loose files when it holds 10. Safe to remove only once you confirm no caller resolves them |

---

## 3. The structural problem, stated plainly

Cleanup is not the whole ask. The ask was *"it is hard for me to maintain structure as folders
keep growing."* Deleting 715 M does not fix that. Three things cause it:

**1. There is no rule for where a document goes.** `docs/` has 15 subfolders, and prose also
lives in `MDs/`, `proposedchanges/`, `othersystemcommunication/`, `design/`, `frontend/`, and
loose at the repo root. A new doc has six plausible homes, so it lands wherever, and the next
one lands somewhere else.

**2. `task/` mixes three different things.** Loose dated files (`2026-07-28.md`,
`2026-08-14.md`), week folders (`2026-W31/`, `2026-W32/`), and a backlog file — with no
signal about which are finished. `2026-W31/` is complete; `2026-W32/` is mid-flight;
`2026-08-14.md` is the current open-items register. You cannot tell that by looking.

**3. Nothing in the tree describes the tree.** `CLAUDE.md` has a documentation map, but it is
an agent-facing file listing individual documents — not a statement of what each *folder* is
for and what belongs in it. When a folder has no stated purpose, it accumulates.

The fix for all three is one file: **`STRUCTURE.md`** at the repo root — one line per folder
saying what it is for and what goes in it, so the question "where does this go?" has an
answer that is written down rather than remembered.

---

## 4. Proposed target layout — Phase 4, for approval

```
/home/emmanuel/Documents/Scalable_Brain/
├── README.md          <- NEW. "Everything is in scalable-brain/. Start at STRUCTURE.md."
├── scalable-brain/    the repo
├── .venv/             the Python 3.12 environment (cron depends on this path)
└── .claude/           harness config
```

```
scalable-brain/
├── STRUCTURE.md       <- NEW. What each folder is for, what goes in it. The map.
├── README.md          three-system topology narrative
├── CLAUDE.md          agent instructions
├── conftest.py  requirements.txt  docker-compose.yml  LICENSE  .env.example
│
├── src/               RUNTIME CODE — untouched this pass
│   ├── system1/         the live pipeline (MODEL-001…010)
│   ├── layer0/          reused primitives (indicators, backtest engine)
│   ├── layer3_ml/       tombstone + FIX-S1-008 guard tests
│   ├── common/          db, storage, queue abstractions
│   └── nlp/  sql/
│
├── shell/             cron + setup scripts — NOT MOVED (crontab absolute paths)
├── contracts/         JSON message contracts — read at runtime
│
├── docs/              ALL PROSE. One home, seven folders, each with a stated purpose.
│   ├── README.md        <- NEW. index of the seven
│   ├── architecture/    topology, ERDs, data dictionary, System-3 design   (<- design/, docs/design/, docs/proposedchanges/)
│   ├── database/        schema, SQL rules, migration record               (<- docs/postgresql/)
│   ├── roadmap/         MODEL-001…010 task specs                         (<- docs/implementation-roadmap/)
│   ├── fixes/           FIX-S1-*, FIX-XC-*                               (<- docs/proposed-fixes/)
│   ├── comms/           inter-machine correspondence                     (<- othersystemcommunication/)
│   ├── research/        papers, notes, goals, milestones                 (<- docs/research/, docs/notes/, docs/goals/)
│   ├── reference/       guides and how-tos                               (<- docs/chartdesign/, MDs/)
│   ├── frontend/        static HTML doc viewers                          (<- frontend/)
│   ├── worklog/         dated session records                            (<- STATUS-2026-08-14.md)
│   └── system1Education/  nested git repo — do not touch
│
├── task/              WORK ITEMS ONLY
│   ├── README.md        <- NEW. how a week works; where a new task goes
│   ├── OPEN.md          the current register (was 2026-08-14.md)
│   ├── backlog/         raised, not started
│   └── archive/         closed weeks (2026-W31/, and 2026-07-28.md)
│       └── 2026-W32/, 2026-W33/  stay at top level while in flight
│
├── results/  models/  model-artifacts/  feature-store/  mlruns/   pipeline I/O (mostly ignored)
├── logs/              git-ignored, retention policy added
└── archieved/         frozen history: zips + manifests only, nothing unpacked
```

**Net: 24 top-level entries → 16.** Prose has one home. Every folder has a written purpose.

---

## 5. Execution order (Phase 3 + 4) — grouped by risk

Each group is a separate commit, full test suite (`pytest src/system1 src/layer0`) after each.

| Group | Content | Risk | Reversible by |
|---|---|---|---|
| **G0** | Archive everything in §2a/§2b: zip + SHA256 manifest, `unzip -t`, **≥3 spot-restores diffed byte-for-byte**, only then delete | none | the archive |
| **G1** | Delete generated: `.mypy_cache/`, `node_modules/`, layer-4 logs, `__pycache__`, zero-byte reports. Add `.mypy_cache/` to `.gitignore` | none | regeneration |
| **G2** | Delete `design/` (verified byte-identical dup); move loose root logs into `logs/`; move root `plans/` + `sandbox-handoff/` into the archive; delete stale root `oanda_ingest.log` | low | `git revert` |
| **G3** | `docs/` consolidation (all moves in §2c). `git mv` only, then `grep -rl` every old path and fix cross-references | low — prose only | `git revert` |
| **G4** | `task/` reshape: `OPEN.md`, `backlog/`, `archive/` | low | `git revert` |
| **G5** | Write `STRUCTURE.md`, root `README.md`, `docs/README.md`, `task/README.md`; update the `CLAUDE.md` documentation map in the same change set | none | `git revert` |

`shell/`, `src/`, `contracts/`, `secrets/`, and everything under `archieved/OtherSystems/`
are **not touched**. No database table is dropped.

---

## 6. Definition of done (from the backlog)

- [x] `INVENTORY.md` covering every path, each in exactly one bucket
- [ ] Archive created, `unzip -t` clean, ≥3 spot-restores byte-identical, manifest recorded
- [ ] Deletions performed only after the above
- [ ] Full test suite green after every move group
- [ ] `CLAUDE.md` documentation map updated in the same change set
- [x] UNCERTAIN items listed and left in place for the user (§2e — 3 items)
