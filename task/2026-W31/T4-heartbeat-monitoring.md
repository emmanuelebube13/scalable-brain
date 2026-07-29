# T4 — Freshness Heartbeat (kill the silent-failure pattern)

> Paste this whole file as the prompt. Repo: `/home/emmanuel/Documents/Scalable_Brain/scalable-brain`. Venv active.
> **First action: read `task/2026-W31/STATE.md`.** T1 should be DONE (so "outcomes fresh" is a meaningful assertion); if not, build the script anyway but mark the outcomes check `KNOWN-STALE until T1`.

## Mission

OANDA price ingest was dead 16 days (2026-07-04→07-20) and trade outcomes ~2 months before anyone noticed. Build one daily heartbeat that asserts freshness of every critical data flow and screams when something is stale. Cheapest insurance in the system.

## Read first

- Memory of prior outages: ingest bugs (import/NameError/tz/INSERT), `telemetry/latest.json` is dead — read `latest-vm.json` instead
- `shell/cron_system1_retrain.sh`, `shell/cron_oanda_ingest_saturday.sh` — existing cron patterns to imitate
- `src/common/db.py`, `src/common/storage/` — use these abstractions, no inline DSNs

## Agent team

- **Agent A (Plan):** design the check list + thresholds (30 min, output a table).
- **Agent B (general-purpose):** implement script + tests + cron. Sequential.

## Checks to implement (Agent A refines thresholds against actual cadences)

| # | Check | Source | Stale threshold (starting point) |
|---|-------|--------|-------------------------------|
| 1 | Price freshness | `fact_market_prices` max timestamp per granularity | **[REVISED 2026-07-29]** NOT '26h behind now' — that fires 6 days out of 7. The ingest is **weekly** (Saturday cron) and the market shuts Fri 21:00–Sun 21:00 UTC, so measure shortfall against `last_market_close(last_scheduled_ingest(now)) - 1h` (bars are stamped at open). 26h grace on that shortfall. |
| 2 | Trade outcomes freshness | `fact_trade_outcomes` max timestamp | > 8 days (weekly cadence + buffer) |
| 3 | Regime table freshness | `fact_market_regime_v2` max timestamp | > 8 days |
| 4 | Champion bundle pointer | backend `latest.json` readable, SHA256 of bundle matches manifest | unreadable OR checksum mismatch = CRITICAL |
| 5 | Telemetry | GCS `telemetry/latest-vm.json` (NOT `latest.json` — dead file) mtime | > 24h |
| 6 | Retrain state | newest `results/state/retrain_log_*.json` age + last status | > 8 days or status=failed |
| 7 | Cron liveness | `logs/cron_system1_retrain.log` mtime | > 2h (hourly cron) |
| 8 | Import canary | `import src.layer0.persist_trade_outcomes` + `import src.system1.scheduler.orchestrator` in a subprocess | ImportError = CRITICAL |

## Execution plan

1. **Design (Agent A).** Confirm each source's real cadence (query actual max timestamps, look at cron schedule) and finalize thresholds. Weekend-awareness matters for FX data — no false alarms every Monday morning.
2. **Implement (Agent B).** `src/system1/monitoring/heartbeat.py`, runnable as `python -m src.system1.monitoring.heartbeat`. Pure checks separated from I/O (repo convention). Output: (a) human-readable table to stdout, (b) `results/state/heartbeat_latest.json` (machine-readable, so future dashboards/System-2 can consume it), (c) exit code 0 = all fresh, 1 = warnings, 2 = critical. `--check <name>` runs one check.
3. **Alerting.** On non-zero: write a dated report to `logs/heartbeat_alerts.log` AND create a visible flag file `results/state/HEARTBEAT_ALERT` (content = failing checks). Keep it simple — no email/slack integration this week unless the user asks; the flag file + log is the contract.
4. **Tests.** For each check: a green case and a stale case (inject a fake timestamp via a seam/parameter, don't mutate real tables). Test the weekend-awareness logic explicitly.
5. **Cron.** Add `shell/cron_heartbeat_daily.sh` mirroring the existing cron scripts' style (venv activation, log redirection, lockfile) and install a daily crontab entry (e.g. `0 6 * * *`). Show the user the crontab diff before installing.
6. **Prove it screams.** Temporarily point one check at an impossible threshold, run, confirm exit 2 + alert file + log entry, then restore. Record the demonstration output in STATE.md.

## Validation

```bash
python -m src.system1.monitoring.heartbeat; echo "exit=$?"
pytest src/system1/monitoring -v
cat results/state/heartbeat_latest.json
crontab -l | grep heartbeat
```

Expected today: checks 1,3,4,6,7,8 PASS; 2 PASS if T1 done; 5 depends on the VM's publisher — if stale, that is a REAL finding, report it, don't tune the threshold to hide it.

## Acceptance criteria

- [x] All 8 checks implemented with FX-market-aware thresholds; 27 tests green (242 across the repo)
- [x] Machine-readable snapshot + `HEARTBEAT_ALERT` flag + alert log, demonstrated with a forced failure (exit 2, flag raised, logged, then auto-cleared)
- [x] `shell/cron_heartbeat_daily.sh` installed at `0 6 * * *`, styled after the existing cron scripts (venv, tee, flock)
- [x] First real run recorded in STATE.md: 8/8 PASS. No source genuinely stale. Telemetry VM publisher confirmed alive; champion bundle verified on GCS.

## Deliverables (required — task is not DONE without them)

Write to `task/2026-W31/deliverables/T4/`:

1. **`DELIVERABLE.md`** — detailed report: the 8 checks with final thresholds and the cadence evidence behind each, the alert contract (exit codes, flag file, log), cron entry installed, the forced-failure demonstration transcript, first real run's full output, test names, commit SHAs.
2. **Visuals (2 PNGs):**
   - `freshness_dashboard.png` — one horizontal bar per check: current data age vs its stale threshold (threshold as a vertical line), green if fresh / amber warning / red critical. This becomes the reusable template the heartbeat could render daily later.
   - `outage_history.png` — timeline Jan→today marking the two known silent outages (ingest 07-04→07-20, outcomes June→July) as red spans, with a marker where the heartbeat now sits: "detection time before: weeks; after: ≤24h."
3. **`EXECUTIVE_SUMMARY.md`** — max 1 page: the system failed silently twice this summer; there is now a daily watchdog over prices, outcomes, regimes, the champion bundle, telemetry, retrain state, cron liveness, and imports; how you'll know when something breaks (the flag file + log); any check currently reporting a REAL stale source (named finding, not hidden).

## On failure

Log to `## Failure log`, fix the step in place, update STATE.md. If a check can't be implemented because the source is inaccessible (e.g. GCS perms for telemetry), implement the check to report `BLOCKED: <reason>` rather than skipping it silently — visible degradation is the whole point of this task.

## Failure log

**2026-07-29 — the specified price threshold was unusable.**
*Failing check:* `prices` (and `regimes`) reported stale on completely healthy data.
*Root cause:* two compounding errors in the spec. (a) "H1 > 26h behind now" ignores that the
price ingest is **weekly**, not hourly — the newest bar is legitimately ~110h old midweek.
(b) Even after switching to a market-close comparison, bars are stamped at their **open**, so
the last H1 bar of the week is 20:00 against a 21:00 close, reporting healthy data as 1h short.
*Correction applied to the check table above and to `freshness.expected_price_coverage()`.*

**2026-07-29 — the `outcomes` check could not detect the failure it was written for.**
*Root cause:* the writer replays history from a backtest, so `max(timestamp)` looks plausible
even when nothing has been written for weeks. Coverage alone would have passed throughout the
five-week freeze. *Correction:* the check now also asserts `max(created_at)` recency, which is
the real liveness signal.

**2026-07-29 — the telemetry check was initially unimplementable.**
*Failing check:* `telemetry` returned `BLOCKED: object exists but the backend exposed no
modification time`. *Root cause:* `StorageBackend.head()` returned no mtime on either backend.
*Correction:* both backends now expose `updated`. Reporting BLOCKED rather than skipping is
the intended behaviour and is what made this visible.
