# shell/ — scripts invoked by cron or by hand

One-off analysis scripts and cron entry points. Nothing here is imported by `src/`.
If a script is imported by Python code, it belongs in `src/common/` instead.

## Cron scripts (do not rename without updating crontab)

The crontab references these by absolute path. Renaming a script silently breaks the schedule.
Run `crontab -l | grep -vE '^\s*#'` to verify paths before touching any of these.

| Script | Schedule | What it does |
|---|---|---|
| `cron_hourly_signals.sh` | `15 * * * *` | ingest → signals → health → model-card mirror. The hourly cadence exists because H4 bars close 6×/day |
| `cron_daily_ingest_and_signals.sh` | `30 22 * * 1-5` | Full daily ingest + signals on weekday close |
| `cron_heartbeat_daily.sh` | `0 6 * * *` | Daily freshness heartbeat |
| `cron_oanda_ingest_saturday.sh` | `0 0 * * 6` | Saturday OANDA ingest |

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
