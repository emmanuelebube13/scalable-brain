# results/ — pipeline output

**Machine-written output only.** Nothing in this folder should be hand-authored.
If you are about to write a document here by hand, it belongs in `docs/` or `task/`.

## Subfolders

| Folder | What the pipeline writes here |
|---|---|
| `reports/` | Per-run JSON/MD reports: ingest manifests, DQ gap reports, attribution reports, vetting reports, qualification reports, STRATEGY_RANKING.md |
| `state/` | Live runtime state: `watcher_state.json`, `signal_emitter_state.json`, `cron_holds.json`, `retrain_state.json`, `regime_strategy_map.json`, `strategy_weights.json`, retrain logs, staging dirs |
| `research/` | Per-strategy backtesting results from `src/layer0/strategies/`. One subfolder per strategy key |
| `sql/` | SQL files deposited by pipeline runs |
| `logs/` | Redirect: `results/logs/` is a symlink or remnant — runtime logs go in the top-level `logs/` |

## Retention policy (established 2026-08-28)

The cron runs hourly and produces `ingest_manifest_*` and `dq_gap_report_*` every run.
Without a policy these accumulate indefinitely.

| Prefix | Keep | Delete |
|---|---|---|
| `ingest_manifest_*` | Most recent 7 files | Older runs (no operational value after 7 days) |
| `dq_gap_report_*` | Most recent 7 files | Older runs |
| `vetting_report_*` | All | Small count; useful for trend inspection |
| `attribution_report_*` | All | Referenced by docs and task records |
| `qualification_report_*` | All | Referenced by docs and task records |
| `STRATEGY_RANKING.md` | Always | Referenced by `task/2026-August-week3/promotion-path/STATE.md` |

**Before deleting any report**, grep `docs/`, `task/`, and `issues/` for the filename.
Several reports are cited as evidence in sent correspondence.

Apply this policy by running: keep last 7 of each timestamp-suffixed prefix, leave everything
else. The cleanup record at `task/2026-August-week3/deliverables/CLEANUP/CLEANUP-2026-08-28.md`
describes the first application of this policy.

## Never delete or move

| Path | Why |
|---|---|
| `state/watcher_state.json` | Bar deduplication cursor — deleting causes duplicate signal emission |
| `state/signal_emitter_state.json` | Emission telemetry, 46 signals to date |
| `state/cron_holds.json` | Suppresses heartbeat failures for declared holds |
| `state/retrain_state.json` | Retrain orchestrator state |
| `state/regime_strategy_map.json` | Live routing map — the vetting pipeline writes this |
| `state/strategy_weights.json` | Live strategy softmax weights |

## Do NOT put here

- Hand-authored documents (→ `docs/`)
- Work items (→ `task/`)
- Python scripts (→ `shell/` if one-off, `src/` if imported)
