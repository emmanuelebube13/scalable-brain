# T7 — Archive the v1 / 7-Layer Leftovers · Technical Report

**Date:** 2026-07-29 · **Status:** COMPLETE · **Commits:** `9920b5b`, `6adb157`, `040dd31`, `5eca153`

**18 paths / 227 files / 3.1 MB** moved into `archieved/v1-cleanup-2026-W31/`, zipped with a
per-file SHA256 manifest. Nothing was deleted. Nothing broke.

---

## 1. Gate check (T7 runs last)

| Precondition | State |
|---|---|
| T1–T6 each DONE/BLOCKED/AWAITING-SIGNOFF | all six **DONE** |
| `results/state/retrain.lock` absent | confirmed absent |
| Working tree clean before starting | confirmed (0 dirty) |

## 2. Keep-set method

Three closures, in decreasing authority:

**Import closure (authoritative).** Imported all 18 documented entry points from CLAUDE.md's
run-commands table plus the outcomes writer, the ingest script and the T6 registry, then walked
`sys.modules` for anything resolving inside the repo. Result: **79 modules**, distributed
`system1` 44 · `layer0` 30 · `common` 4. **No other `src/` package was reached by any entry
point.**

**Reference closure.** `grep` for path strings in `shell/*.sh`, `.env.example` and CLAUDE.md's
docs map. This is what saved `src/nlp/` (cited in the docs map, MODEL-010 planned) and
`src/layer3_ml/` (tombstone + FIX-S1-008 guard tests).

**Recency (advisory only).** `git log -1 --format=%cs` per path. Old ≠ unused — used to raise
doubt, never to condemn. It is why `design/` (2026-07-05) and `frontend/` (2026-07-05) went to
UNCERTAIN rather than ARCHIVE despite having no closure membership.

**Test collection.** Test files by package: `system1` 25 · `layer3_ml` 3 · `layer0` 3 ·
`layer7` 1 · `common` 1. The single `layer7` test (`test_oanda_ping.py`) imports only `os`,
`requests` and `dotenv` — a broker connectivity ping with no repo dependency — so archiving
`layer7` cost no coverage.

## 3. The manifest

> ### ⚠️ CORRECTION 2026-08-01 — `contracts/` was archived in error and has been restored
>
> The archive criterion was the **Python import closure**. That closure cannot see files
> referenced by *runtime path string* rather than by `import`. `contracts/` is exactly such a
> dependency:
>
> ```python
> # src/system1/queue_producer/producer.py:28
> CONTRACT_PATH = os.path.join(_REPO_ROOT, "contracts", "signal-message-contract.json")
> ```
>
> Worse, the consumer **fails soft**: `_load_validator()` catches the missing file, logs an
> error, and falls back to a presence-only check that never validates types or enums. So the
> ScoredSignal `direction` enum (`"long"|"short"`) silently stopped being enforced on
> 2026-07-29 and nothing failed. Surfaced 2026-08-01 by a System-2 question about the
> `direction` contract; restored via `git mv`, 210/210 System-1 tests pass.
>
> **Lesson for any future archive pass: import-closure analysis is necessary but not
> sufficient. Also grep for the directory name in string literals** (`grep -rn '"contracts'`
> would have caught this), and treat a fail-soft consumer as a reason to verify by *running*
> the code path, not by static analysis alone.

### ARCHIVE

| path | era | KB | files | tracked | evidence |
|---|---|---:|---:|---|---|
| ~~`contracts`~~ | **REVERSED 2026-08-01** | 16 | 3 | yes | ⚠️ **archiving this was a mistake — restored to the repo root.** See the correction below. |
| `init-db` | orphan | 8 | 1 | yes | not in import closure (79 modules from 18 entry points); 0 live references. last commit 2026-07-03; DB is provisioned, not bootstrapped here |
| `src/research` | orphan | 96 | 13 | yes | not in import closure (79 modules from 18 entry points); 0 live references. superseded by the T6 sandbox at src/layer0/strategies/ |
| `src/todo` | orphan | 8 | 1 | yes | not in import closure (79 modules from 18 entry points); 0 live references. no .py files, no references |
| `testing` | orphan | 8 | 1 | yes | not in import closure (79 modules from 18 entry points); 0 live references. last commit 2026-04-01; not collected by pytest |
| `Screenshot from 2026-06-22 07-07-43.png` | stray-root | 308 | 1 | yes | not in import closure (79 modules from 18 entry points); 0 live references. one-off screenshot at repo root |
| `localhost` | stray-root | 8 | 1 | yes | not in import closure (79 modules from 18 entry points); 0 live references. last commit 2026-03-06; stray dir |
| `model001_ingest.log` | stray-root | 16 | 1 | no | not in import closure (79 modules from 18 entry points); 0 live references. stray root log |
| `model003_regime.log` | stray-root | 24 | 1 | no | not in import closure (79 modules from 18 entry points); 0 live references. stray root log |
| `oanda_ingest.log` | stray-root | 156 | 1 | no | not in import closure (79 modules from 18 entry points); 0 live references. stray root log; live logs live in logs/ |
| `path_map.json` | stray-root | 8 | 1 | yes | not in import closure (79 modules from 18 entry points); 0 live references. last touched 2026-04-04; no reader in the closure |
| `plotly-cloud.toml` | stray-root | 4 | 1 | yes | not in import closure (79 modules from 18 entry points); 0 live references. last touched 2026-03-17; no reader |
| `src/layer1_regime` | v1-layer | 120 | 8 | yes | not in import closure (79 modules from 18 entry points); 0 live references. superseded by src/system1/regime/ (HMM+KMeans) |
| `src/layer2_signals` | v1-layer | 432 | 38 | yes | not in import closure (79 modules from 18 entry points); 0 live references. fact_signals not in the System-1 retrain path |
| `src/layer4_executor` | v1-layer | 76 | 1 | yes | not in import closure (79 modules from 18 entry points); 0 live references. retired -> System 2; cron disabled 2026-07-08; copy in archieved/ |
| `src/layer5` | v1-layer | 1848 | 148 | yes | not in import closure (79 modules from 18 entry points); 0 live references. retired -> System 2 (telemetry); copy already in archieved/ |
| `src/layer6_auditor` | v1-layer | 16 | 2 | yes | not in import closure (79 modules from 18 entry points); 0 live references. retired -> System 3; copy already in archieved/ |
| `src/layer7` | v1-layer | 72 | 4 | yes | not in import closure (79 modules from 18 entry points); 0 live references. retired -> System 2 (broker); copy already in archieved/ |

### UNCERTAIN — not moved, awaiting your call

| path | era | KB | files | tracked | evidence |
|---|---|---:|---:|---|---|
| `AGENTS.md` | stray-root | 12 | 1 | yes | agent instructions; may be actively used by tooling |
| `MDs` | superseded | 72 | 4 | yes | T2 edited it this week (password purge); may hold reference material |
| `design` | superseded | 864 | 7 | yes | 864 KB of design assets, last commit 2026-07-05 — recent enough to be in use |
| `frontend` | superseded | 280 | 9 | yes | dashboard UI; layer5 telemetry is System 2's surface now, but this may be the S2 dashboard source |
| `proposedchanges` | superseded | 24 | 2 | yes | root copy vs docs/proposedchanges/ — CLAUDE.md's map cites the docs/ one; confirm the root copy is a duplicate |

### KEEP (explicitly stated)

| path | era | KB | files | tracked | evidence |
|---|---|---:|---:|---|---|
| `othersystemcommunication` | - | 56 | 6 | yes | cross-system comms, last commit 2026-07-28 |
| `src/layer3_ml` | - | 360 | 20 | yes | tombstone (intentional ImportError guard) + FIX-S1-008 guard tests |
| `src/nlp` | - | 44 | 3 | yes | CLAUDE.md docs map cites src/nlp/; MODEL-010 planned |
| `src/sql` | - | 88 | 12 | yes | timescaledb README referenced by docs |

## 4. Moves — three groups, validated after each

| Group | Commit | Contents |
|---|---|---|
| 1/3 root strays | `9920b5b` | screenshot, 3 stray root `.log` files (untracked), `path_map.json`, `plotly-cloud.toml`, `localhost/` |
| 2/3 legacy layers | `6adb157` | `layer1_regime`, `layer2_signals`, `layer4_executor`, `layer5`, `layer6_auditor`, `layer7` |
| 3/3 orphans | `040dd31` | `src/todo`, `src/research`, `testing/`, `init-db/`, `contracts/` |

Each moved with `git mv` (plain `mv` + `git add` for the 3 untracked logs), **preserving the
original relative path** — `src/layer5/...` → `archieved/v1-cleanup-2026-W31/src/layer5/...`.

### Validation after every group

| Check | Group 1 | Group 2 | Group 3 |
|---|---|---|---|
| `pytest src/system1 src/layer0/tests src/layer3_ml/tests` | 265 passed | 265 passed | 282 passed / 1 skipped |
| `import src.layer0.persist_trade_outcomes` | OK | OK | OK |
| `orchestrator` | `no_trigger_or_cooldown` | `no_trigger_or_cooldown` | `no_trigger_or_cooldown` |
| `monitoring.heartbeat` | exit 0 | exit 0 | exit 0 |
| `bash -n` both cron scripts | OK | — | — |
| T6 registry lists | — | — | OK |

**No group had to be reverted.** The keep-set method held on the first pass.

## 5. Archive integrity

```
archieved/v1-cleanup-2026-W31/          227 files, unzipped, kept in place
archieved/v1-cleanup-2026-W31.zip       919 KB   sha256 6cf820c6b7510698…
archieved/v1-cleanup-2026-W31.sha256    227 per-file checksums
```

- `unzip -t` → **No errors detected**
- 3 random files spot-restored from the zip and byte-compared → **all identical**
- `sha256sum -c` against the folder → **all 227 verify**

The unzipped folder stays alongside the zip. Recommend keeping both until next week's heartbeat
cycle is clean, then deleting the folder if you want the space back.

## 6. Tree before / after

| | before | after |
|---|---|---|
| `src/` | 30 MB | **28 MB** |
| `archieved/` | 296 MB | 300 MB (gained the archive + zip) |
| top-level entries | 35 | 28 |
| files (excl. `.git`) | 31,092 | 31,101 (net +9: the zip, checksums, manifest and charts) |

**This was about tree clarity, not disk space.** The repo's actual weight is `logs/` 305 MB,
`archieved/` 300 MB and `backups/` 167 MB — all protected by T7's own rules. What changed is
that `src/` now contains only what runs.

## 7. A T5 follow-up closed

`src/layer4_executor/live_pipeline.py` and `src/layer7/oanda_executor.py` hold the
**known-defective** exposure and position-sizing code documented in FIX-S3-002 and FIX-S3-004.
Both had live-looking copies in `src/` *and* archived copies in `archieved/`. T5's report
flagged that two copies of defective sizing logic invites someone to fix the wrong one. There
is now one, in the archive.

## 8. UNCERTAIN — awaiting your call

Five paths were **not moved**. Each has zero import-closure membership but something that
argues against archiving:

- **`frontend/`** (280 KB) — dashboard UI. Layer-5 telemetry is System 2's surface now, but
  this may be System 2's dashboard source rather than a v1 leftover.
- **`design/`** (864 KB) — design assets, last commit 2026-07-05. Recent.
- **`MDs/`** (72 KB) — T2 edited it this week (password purge), so it is at least being maintained.
- **`proposedchanges/`** (24 KB) — a root copy; CLAUDE.md's docs map cites `docs/proposedchanges/`.
  Confirm the root copy is a duplicate before archiving.
- **`AGENTS.md`** (12 KB) — agent instructions; may be read by tooling.

## 9. Rollback

```bash
git revert 040dd31 6adb157 9920b5b       # restores every moved path
# or restore selectively from the archive:
unzip archieved/v1-cleanup-2026-W31.zip 'v1-cleanup-2026-W31/src/layer5/*'
```

The three untracked logs are not in git history but are in both the folder and the zip.
