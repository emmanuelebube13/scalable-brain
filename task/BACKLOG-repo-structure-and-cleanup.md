# BACKLOG — repository structure, archival and deletion pass

**Status:** planned, **not started**. Deliberately deferred until the current M1 work lands.
**Raised:** 2026-08-13 · **Precedent:** T7 (`task/2026-W31/T7-archive-v1-cleanup.md`)

---

## Two facts that shape everything below

**1. The root is not version-controlled.**

```
/home/emmanuel/Documents/Scalable_Brain/          <- NOT a git repo
├── scalable-brain/                               <- the only versioned tree
├── OtherSystems/          2.7M
├── system1Education/      1.0M
├── sandbox-handoff/        80K
├── oanda_ingest.log        68K
├── plans/                  48K
└── Scalable_Brain_Strategy_Qualification_and_Training.docx   56K
```

Inside `scalable-brain/` a bad delete is `git revert`. **Outside it, a bad delete is permanent.**
That asymmetry drives the whole procedure: archive first, verify the archive, then delete.

**2. There is no space pressure.**

Everything outside `scalable-brain/` is **~4 MB**. Deleting it reclaims nothing worth having.

> **Therefore the goal of this task is clarity, not reclamation.** Where the two conflict,
> clarity loses to safety: when the cost of keeping something is 4 MB and the cost of wrongly
> deleting it is losing the only local copy of another machine's documentation, keep it.

`OtherSystems/system-2-execution-engine/` and `OtherSystems/system-3-account-management/` are
**reference copies for two machines this repo cannot reach.** They are the highest-risk deletion
candidates and should be assumed precious until each is confirmed reproducible from its own host.

---

## Procedure — in this order, no shortcuts

### Phase 1 — Inventory (read-only, produces a document)

Produce `task/<week>/deliverables/CLEANUP/INVENTORY.md` listing **every** path at root and every
top-level path in `scalable-brain/`, each with: size, last-modified, whether git-tracked, what
last referenced it (`grep -rl` across the repo), and a proposed classification.

Nothing is touched in this phase. **The inventory is the deliverable**, and it is reviewed before
anything moves.

### Phase 2 — Classify

Exactly four buckets. Every path gets exactly one:

| Bucket | Meaning | Action |
|---|---|---|
| **KEEP** | actively referenced by code, cron, or docs | leave in place, possibly relocate in Phase 4 |
| **ARCHIVE** | historical value, no live reference | zip + manifest, then remove from the working tree |
| **DELETE** | reproducible, generated, or superseded | delete **after** the archive exists |
| **UNCERTAIN** | cannot be classified confidently | **leave in place and list it** — the user decides |

The UNCERTAIN bucket is mandatory and must not be empty out of tidiness. T7 left five paths
unresolved on purpose (`frontend/`, `design/`, `MDs/`, `proposedchanges/`, `AGENTS.md`) and that
was correct behaviour — those are still open and belong in this pass.

### Phase 3 — Archive, then verify, then delete

Follow the T7 pattern exactly, because it worked:

1. `zip` the ARCHIVE + DELETE sets into `archieved/<name>-<date>.zip`
2. Write a SHA256 manifest of every file in the archive
3. `unzip -t` the archive — must report no errors
4. **Spot-restore at least 3 files and diff them byte-for-byte against the originals**
5. Only then delete from the working tree
6. Record the zip name, its sha256, and the file count in the deliverable

Step 4 is the one that is tempting to skip and must not be. An archive nobody has restored from
is a belief, not a backup.

### Phase 4 — Structure

Only after Phases 1–3. Propose a target layout **as a document first**, with the moves listed
and justified, and get it approved before executing. Then move in **small groups, running the
full test suite after each group** — T7's method, which caught problems early.

Constraints on any restructure:

- `src/system1/` is the runtime. Do not reorganise it casually.
- `src/layer0/` is partially reused (indicators, backtest engine, the strategies sandbox) and is
  load-bearing despite living under a "legacy" name.
- Check `crontab -l` and `shell/*.sh` for hardcoded paths **before** moving anything.
- The `archieved` spelling is deliberate. Leave it.

---

## Specific items already known to need a decision

| Path | Note |
|---|---|
| `OtherSystems/system-2-execution-engine/`, `system-3-account-management/` | reference copies; confirm each host has the authoritative version **before** touching |
| `OtherSystems/deployment-guide/` | canonical S2+S3 setup docs — likely KEEP |
| `OtherSystems/comms/`, `othersystemcommunication/` | inter-machine correspondence; two locations, possibly duplicated |
| `sandbox-handoff/` | external-agent brief; superseded by `task/2026-W32/fleet/`? |
| `system1Education/` | pushed to GitHub already — if so, DELETE is safe |
| `plans/`, `*.docx` at root | early planning; likely ARCHIVE |
| `oanda_ingest.log` | log at root; the live one is `logs/` — likely DELETE |
| `scalable-brain/frontend/`, `design/`, `MDs/`, `proposedchanges/`, `AGENTS.md` | T7's five UNCERTAIN paths, still unresolved |
| `results/reports/*.json`, `results/state/retrain_log_*.json` | machine-generated; retention policy needed, not ad-hoc deletion |
| `fact_market_regime_v2_bak_20260811`, `fact_trade_outcomes_bak_*` | **DB tables, not files.** Do not drop until the corresponding fix is confirmed live |

---

## Definition of done

- `INVENTORY.md` covering every path, each in exactly one bucket
- Archive created, `unzip -t` clean, **≥ 3 spot-restores byte-identical**, manifest recorded
- Deletions performed only after the above
- Full test suite green after every move group
- `CLAUDE.md` documentation map updated in the same change set
- UNCERTAIN items listed and left in place for the user

## Explicitly out of scope

- Dropping any database table
- Touching `secrets/`, `.env`, or anything git-ignored that holds credentials
- Reorganising `src/system1/` internals
- Deleting anything under `OtherSystems/` before its host confirms an authoritative copy
