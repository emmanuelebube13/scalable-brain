# T7 — Archive the v1 Leftovers · Executive Summary

**2026-07-29 · Nothing deleted · Nothing broke**

## What the old architecture left behind

The project used to be a single eight-layer program. It is now three independent systems, and
System 1 — this machine — kept only a fraction of that original code. But the fraction it
*stopped* using was still sitting in `src/` looking exactly as live as the rest: six retired
layer folders, a screenshot at the repo root, three stray log files, and a handful of folders
nothing had referenced since spring.

The risk isn't disk space. It's that **the next person to open this repository can't tell what
runs from what used to run** — and, in one case this week, that ambiguity had teeth.

## What moved

**227 files, 3.1 MB**, into `archieved/v1-cleanup-2026-W31/`, in three batches:

- **The six retired layer folders** — regimes, signals, executor, telemetry, auditor, broker.
  All had already been copied to the archive when they were retired; these were the
  live-looking originals still sitting in `src/`.
- **Root clutter** — a June screenshot, three stray log files, two orphaned config files.
- **Five orphaned folders** — including `src/research/`, now superseded by the proper sandbox
  built in T6.

Everything moved with `git mv`, keeping its original path inside the archive, so restoring any
of it is a one-line command.

## Proof nothing broke

The full test battery ran **after each of the three batches**, not just at the end:

| | after batch 1 | after batch 2 | after batch 3 |
|---|---|---|---|
| Tests | 265 pass | 265 pass | **282 pass** |
| Outcomes writer imports | ✅ | ✅ | ✅ |
| Retrain scheduler | clean | clean | clean |
| Daily heartbeat | exit 0 | exit 0 | exit 0 |

**No batch had to be rolled back.** The classification was right first time, because it was
built from what the code actually imports rather than from what looks old.

## One thing this fixed beyond tidiness

Two of the archived files — `layer4_executor/live_pipeline.py` and `layer7/oanda_executor.py` —
contain the **position-sizing bugs** T5 documented this week, including the one that breaches
your hard risk cap. There were two copies of each: a live-looking one in `src/` and an archived
one. T5's report warned that this invites someone to fix the wrong copy. Now there's one.

## Where the archive lives

```
archieved/v1-cleanup-2026-W31/       the folder, 227 files
archieved/v1-cleanup-2026-W31.zip    919 KB
archieved/v1-cleanup-2026-W31.sha256 a checksum for every file
```

Verified three ways: the zip tests clean, three random files were pulled back out and compared
byte-for-byte, and all 227 checksums match. **Both the folder and the zip are kept** — delete
the folder once you're satisfied, or leave it.

## Five things I did not move

These had no code referencing them, but something argued against archiving, so they stay where
they are until you say otherwise:

| | Why I stopped |
|---|---|
| `frontend/` | may be System 2's dashboard source rather than a v1 leftover |
| `design/` | 864 KB of assets, touched 5 July — recent |
| `MDs/` | edited this week during the password purge, so it's maintained |
| `proposedchanges/` | a root copy exists alongside `docs/proposedchanges/` — confirm it's a duplicate |
| `AGENTS.md` | may be read by tooling |

## Rollback, if you want any of it back

```bash
git revert 040dd31 6adb157 9920b5b
```

That restores every moved path. Or pull individual files out of the zip.

## The honest scale of this

`src/` went from 30 MB to 28 MB. The repository's real weight is logs (305 MB), the archive
(300 MB) and backups (167 MB) — all deliberately untouched, because they're data, not clutter.

**What changed is that `src/` now contains only what runs.**
