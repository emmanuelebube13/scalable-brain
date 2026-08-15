# T7 — Archive the v1 / 7-Layer Leftovers and All Unused Files (added mid-week 2026-07-29)

> Paste this whole file as the prompt. Repo: `/home/emmanuel/Documents/Scalable_Brain/scalable-brain`. Venv active.
> **First action: read `task/2026-July-week4/STATE.md` and follow its protocol.**
> **Gate: this task runs LAST.** Do not start unless T1–T6 are each DONE, BLOCKED, or AWAITING-SIGNOFF in STATE.md. If any task is IN_PROGRESS or PENDING-and-runnable, stop and report — moving files under a working agent corrupts its run. Also confirm no retrain is in flight (`results/state/retrain.lock` absent) before moving anything.

## Mission

The repo root still carries the v1 / 8-layer-monolith era: legacy layer trees, root-level stray files (screenshots, one-off logs, dead HTML), superseded folders, and files nothing imports or references anymore. Identify every file that is not part of the current System-1 runtime or its support surface — **including unused files nested inside otherwise-useful folders** — move them (never delete) into one archive folder, zip it with a checksum manifest, and leave the tree containing only what matters. Everything must be reversible: `git mv` + one zip.

## Non-negotiable protections (never archive these)

- `.git/`, `.env`, `.env.example`, `.gitignore`, `secrets/`, `CLAUDE.md`, `README.md`, `requirements.txt`
- `src/system1/` (the runtime), `src/common/` (db/storage/queue), `shell/` (active crons), `task/`, `docs/`
- `src/layer0/` **active** parts: whatever T1's repaired import graph shows the outcomes writer, indicators, backtest engine, and their subpackages (`core_engine/`, `qualification/`, `data_access/`, `promotion/`, `strategies/`) actually use — plus `src/layer0/tests/`
- `src/layer3_ml/train_ml_gatekeeper.py` **tombstone** (intentional ImportError guard — archiving it defeats its purpose) and `src/layer3_ml/tests/` (FIX-S1-008 guard tests run in CI/pytest)
- Live data/state: `model-artifacts/`, `results/`, `logs/`, `feature-store/`, `mlruns/`, `backups/`
- The existing `archieved/` folder (already archived; typo name is deliberate) — it is the *destination's* sibling, not a source of "unused" files to re-classify
- Anything T2 turned into a pointer file (e.g. `configuration/postgresql_connection_details.txt`) and anything created by this week's tasks (`deliverables/`, `live-vm-capture/`, `T5-fix-package/`)

## Agent team

- **Agent A (Explore, read-only) — evidence builder.** Produces the classification manifest. Nothing moves until this is complete and written to the deliverable.
- **Agent B (general-purpose) — mover.** Executes the manifest with `git mv`, in small commits per group.
- **Agent C (general-purpose) — verifier.** Runs the full validation battery after each commit group and does the zip.
A → B → C strictly sequential.

## Execution plan

1. **Build the keep-set (Agent A).** Compute the closure of "in use" from four roots, and record the method in the deliverable:
   - *Import closure:* every module transitively imported from the entry points in CLAUDE.md's run-commands table (all `python -m src.system1.*`, `src.layer0.persist_trade_outcomes`) plus both cron scripts plus `pytest` collection (`pytest --collect-only -q src/` — anything a test imports stays).
   - *Reference closure:* `grep -rn` for path strings in configs, cron scripts, `.env.example`, docs map — a file referenced by a live config stays.
   - *Recency signal (advisory only):* `git log -1 --format=%ci -- <path>` and file mtimes — old ≠ unused, but recent+referenced = definitely keep.
2. **Classify everything else (Agent A).** Walk the repo root and produce `deliverables/T7/manifest.md` with one row per candidate: path, size, era (v1-layer / stray-root / superseded / orphan), evidence of non-use (not in any closure), and verdict `ARCHIVE` / `KEEP` / **`UNCERTAIN`**. Known candidates to evaluate (verify, don't assume): `index.html`, `Screenshot from 2026-06-22*.png`, root-level `*.log` (`oanda_ingest.log`, `model001_ingest.log`, `model003_regime.log`), `localhost/`, `MDs/`, `testing/`, `frontend/`, `init-db/`, `othersystemcommunication/`, `path_map.json`, `plotly-cloud.toml`, `design/`, `contracts/`, `proposedchanges/` (referenced in CLAUDE.md docs map — check), and within `src/`: `layer1_regime/`, `layer2_signals/`, the non-test remainder of `layer3_ml/`, `layer5/`, `layer6_auditor/`, `layer7/` remnants, `nlp/` (MODEL-010 planned — likely KEEP), unused modules *inside* kept packages (e.g. dead files in `layer0/` that the closure doesn't reach). **UNCERTAIN items are NOT moved** — they go in a review table for the user.
3. **User checkpoint.** Present the manifest summary (counts + total MB per verdict, the full ARCHIVE list, the UNCERTAIN list) and wait for the user's go-ahead before moving anything. This is a large irreversible-feeling change; the user decides, not the agent.
4. **Move (Agent B).** Create `archieved/v1-cleanup-2026-W31/` and `git mv` each ARCHIVE item into it **preserving its original relative path** (`src/layer2_signals/...` → `archieved/v1-cleanup-2026-W31/src/layer2_signals/...`). Small commits per group (root-strays / legacy-layers / orphans), each commit message listing the moved paths. Untracked ARCHIVE items are moved with plain `mv` and noted as untracked in the manifest. Update CLAUDE.md's legacy table + docs map in the same change set (repo rule).
5. **Verify after each group (Agent C).** Full battery below — if anything breaks, `git revert` that group's commit, mark the offending file KEEP in the manifest with the evidence, and continue. A revert here is a *finding*, not a failure.
6. **Zip (Agent C).** From repo root: build `archieved/v1-cleanup-2026-W31.zip` of the archive folder, plus `archieved/v1-cleanup-2026-W31.sha256` (per-file checksums generated before zipping). Verify: `unzip -t` clean, spot-restore 3 random files and byte-compare against the folder. Exclude nothing — the archive folder should contain only what was deliberately moved. The **unzipped folder stays** alongside the zip (user's call later to delete it once satisfied; recommend keeping both until next week's heartbeat cycle is clean).
7. **Record.** Final tree summary (`du -sh` top-level before/after, file counts), manifest finalized, STATE.md updated.

## Validation (the full battery, after every move group and at the end)

```bash
pytest src/system1 src/layer0/tests src/layer3_ml/tests -v      # everything green
python -c "import src.layer0.persist_trade_outcomes; print('writer import OK')"
python -m src.system1.scheduler.orchestrator                     # clean no_trigger_or_cooldown
python -m src.system1.monitoring.heartbeat; echo "exit=$?"       # if T4 shipped it — must not regress
unzip -t archieved/v1-cleanup-2026-W31.zip | tail -1             # "No errors detected"
git status --porcelain | head                                    # clean tree, all moves committed
```

Both crons must still resolve their targets: `bash -n shell/cron_system1_retrain.sh shell/cron_oanda_ingest_saturday.sh` and check any path they reference still exists.

## Deliverables (required — task is not DONE without them)

Write to `task/2026-July-week4/deliverables/T7/`:

1. **`DELIVERABLE.md`** — the full manifest (every ARCHIVE/KEEP/UNCERTAIN verdict with evidence), the keep-set method, move commit SHAs, zip checksum + size, the UNCERTAIN review table for the user, and the revert log if any group had to come back.
2. **Visuals (2 PNGs, matplotlib `Agg`, real measured data):**
   - `repo_before_after.png` — horizontal bars of top-level directory sizes before vs after the sweep; the archived total called out. One glance = how much dead weight left the tree.
   - `classification_breakdown.png` — file counts and MB by verdict (ARCHIVE by era category / KEEP / UNCERTAIN), so the user sees what kind of debt this was.
3. **`EXECUTIVE_SUMMARY.md`** — max 1 page: what the v1 era left behind, what was moved (N files, M MB) and where the zip + checksums live, proof nothing live broke (test/orchestrator results), the UNCERTAIN list awaiting your call, and the one-command rollback story (`git revert` range + zip restore).

## On failure

A validation break after a move group ⇒ revert that group, reclassify, continue — log it in `## Failure log` with the file that turned out to be load-bearing and how the keep-set missed it (then fix the keep-set method description so the manifest is honest). Update STATE.md after every group.

## Failure log

**No group required a revert.** The keep-set method (import closure from 18 documented entry
points → 79 modules; reference closure over crons/`.env.example`/CLAUDE.md docs map; recency
advisory only) held on the first pass. All three move groups passed the full validation battery.

**2026-07-29 — one task assumption did not hold: `index.html` does not exist.**
Step 2 lists it as a known candidate (and T2 named it as a password-exposure site). It is absent
from the repo — already removed at some earlier point. No action needed; recorded so the next
reader does not go looking.

**2026-07-29 — `src/layer4_executor` initially showed 1 "live reference".**
The reference-closure grep matched `src/system1/queue_producer/__init__.py:6`, which is a
*docstring* reading "NO import of src/layer4_executor anywhere in this package" — a negative
reference. Verified by reading the line before classifying. Worth noting because a naive grep
count would have kept a dead tree alive on the strength of a comment saying it was dead.
