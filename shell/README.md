# shell/ — scripts invoked by cron or by hand

One-off analysis scripts and cron entry points. Nothing here is imported by `src/`.
If a script is imported by Python code, it belongs in `src/common/` instead.

## Cron scripts (do not rename without updating crontab)

The crontab references these by absolute path. Renaming a script silently breaks the schedule.
Run `crontab -l | grep -vE '^\s*#'` to verify paths before touching any of these.

> ⚠️ **These times are LOCAL, not UTC — and the crontab has no `CRON_TZ` line.** The
> machine's timezone is America/Halifax. Every script header, and every other doc
> (`docs/critical/REPO_STATE.md`, `src/monitoring/job_runs.py` comments) that labels
> these schedules "UTC" is aspirational, not actual. Today (ADT, UTC−3) each job fires
> **3 hours later than its documented UTC time**; after the 2026-11-01 DST transition to
> AST (UTC−4) that widens to **4 hours later**. The relative *order* of the jobs
> (ingest → outcomes → stats → heartbeat) is preserved either way — only the absolute
> times drift. The orchestrator's own Sunday-00:00-UTC retrain *trigger* is unaffected
> because it is evaluated in UTC by the hourly poll, independent of when cron fires it.
> Found during the 2026-09-16 cron/automation audit
> (`issues/September-Week-3/2026-09-16.md`); the crontab itself is owner-installed and
> hand-managed, so this doc was corrected rather than the schedule.

All 7 installed jobs, times as written in the crontab (local, America/Halifax — see above):

| Script | Schedule (local) | What it does |
|---|---|---|
| `cron_hourly_signals.sh` | `15 * * * *` | ingest → signals → health → model-card mirror. The hourly cadence exists because H4 bars close 6×/day |
| `cron_system1_retrain.sh` | `0 * * * *` | Retrain orchestrator hourly trigger poll (MODEL-009). No-ops unless the Sunday-00:00-UTC window, a low-Sharpe trigger, or a circuit breaker fires; single-flight + cooldown guarded |
| `cron_daily_ingest_and_signals.sh` | `30 22 * * 1-5` | Full daily ingest + signals on weekday close |
| `cron_persist_outcomes.sh` | `0 2 * * 2-6` | Rebuild `fact_trade_outcomes` (FIX-S1-017). Tue–Sat, after the weekday 22:30 ingest and before the 05:40 strategy-stats publish that reads it |
| `cron_publish_strategy_stats.sh` | `40 5 * * *` | Publish `risk/strategy_stats/latest.json` for System 3 |
| `cron_heartbeat_daily.sh` | `0 6 * * *` | Daily freshness heartbeat |
| `cron_oanda_ingest_saturday.sh` | `0 0 * * 6` | Saturday OANDA ingest |

Installed lines are recorded in `results/state/crontab.backup-20260907.txt` (and earlier
backups from 09-03/08-28); that file is the source of truth for what is actually installed —
prefer it over this table if they ever disagree.

All cron scripts hardcode the venv at `/home/emmanuel/Documents/Scalable_Brain/.venv`.
Do not move the venv or reference it relatively.

## Analysis scripts (moved from root 2026-08-28)

| Script | What it does |
|---|---|
| `generate_ranking_report.py` | Generate a strategy ranking report |
| `generate_reference_vector.py` | Generate a reference feature vector |
| `generate_report.py` | Generate an ad-hoc results report |

## Other scripts

| Script | What it does |
|---|---|
| `build_strategy_catalog.py` | Regenerates `docs/frontend/strategy-catalog.html` — run this, do not edit the HTML |
| `provision_pubsub.sh` | Creates the Pub/Sub topics (the `scored-signals.heartbeat` topic was never created — see CLAUDE.md troubleshooting) |

## Do NOT put here

- Anything imported by `src/` — that is a library, it goes in `src/common/`
- Runtime pipeline modules — those are `python -m src.<module>` entry points in `src/`
