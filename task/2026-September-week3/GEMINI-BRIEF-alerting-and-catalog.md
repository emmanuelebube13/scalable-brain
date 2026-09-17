# Brief for external agent (Gemini) — Computer-1 alerting bridge + catalog script fix

Issued 2026-09-17. Review-before-merge: a Claude session reviews and lands this work; do
not push, publish, or merge yourself.

## Ground rules (binding)

1. Work in the repo at `scalable-brain/`. Read `CLAUDE.md` and `STRUCTURE.md` first; their
   rules bind you.
2. **Files you may create/edit:** `src/monitoring/alert_bridge.py` (new),
   `src/monitoring/tests/test_alert_bridge.py` (new), `shell/cron_alert_bridge.sh` (new),
   `shell/build_strategy_catalog.py` (existing, one bug), and nothing else. Do NOT touch
   `src/gatekeeper/`, `src/signals/`, `src/scheduler/`, `src/vetting/`, `src/serializer/`,
   or any file under `results/`, `models/`, `docs/comms/`.
3. No DB writes, no GCS writes, no Pub/Sub, no crontab edits (propose the cron line in a
   comment; a human installs it). No git commits. No network calls in tests.
4. Python 3.12, venv at `../.venv` (`source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate`).
   Run `python -m pytest src/monitoring -q` (must stay green) and `black` on your files.

## Task 1 — `src/monitoring/alert_bridge.py`

Problem: nothing pages a human when System 1 breaks. The heartbeat writes
`results/state/HEARTBEAT_ALERT` (a flag file with text) and `logs/heartbeat_alerts.log`;
the emitter writes `results/state/signal_emitter_state.json` (fields:
`consecutive_faults`, `last_run_outcome`, `last_run_fault_detail`, `last_signal_emitted_at`).
Nothing consumes these for notification. The estate's only alert channel is a Telegram
bot on the VM (`TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` env vars — same convention here).

Build a small, dependency-light module (stdlib + `requests` only — `requests` is already
in the venv):

- `collect_alerts() -> list[dict]`: pure read of the two state files above. Emits an
  alert dict for: HEARTBEAT_ALERT present; `consecutive_faults >= 3`;
  `last_signal_emitted_at` older than 26 open-market hours (use
  `src.monitoring.freshness.open_hours_between` — weekends must not fire it). Each dict:
  `{key, severity ("warn"|"critical"), message}` with `key` stable across runs
  (e.g. "heartbeat_alert", "emitter_faults", "emitter_stale").
- `send_telegram(text) -> bool`: POST to the Bot API; missing env vars → log one warning,
  return False; never raise.
- Dedup state at `results/state/alert_bridge_state.json`: an alert `key` notifies at most
  once per 6 wall-clock hours (repeat notification if still firing after that); a key
  that STOPS firing sends one "recovered: <key>" message. Atomic write (tmp + os.replace).
  Unreadable state degrades to "notify" (never to silence), logged.
- `main()` with `--dry-run` (print, send nothing — default) and `--send`. Exit 0 always
  (an alerting failure must never look like a job failure to cron).
- Module docstring: name the problem (detector-with-no-consumer, cite the 2026-08-24
  regime stall: heartbeat CRITICAL 10 days, nothing read it) and the design rule that the
  bridge is an OBSERVER — it must never write anything another module reads.

`shell/cron_alert_bridge.sh`: follow the exact pattern of `shell/cron_heartbeat_daily.sh`
(absolute venv path, `flock`, `source shell/_job_record.sh alert_bridge`, `job_record_ok`).
Proposed cron line in the header comment: every 30 min. Note in the comment that this
machine's crontab runs in America/Halifax local time (no CRON_TZ support).

Tests (all hermetic, tmp_path, monkeypatched env + a fake `requests.post`): each alert
condition fires and recovers; weekend does not fire staleness; 6h dedup window; unreadable
state → notify; missing env vars → False without raising; `--dry-run` sends nothing.

## Task 2 — `shell/build_strategy_catalog.py` output path

Known wrinkle (documented in CLAUDE.md's documentation map): the script's `OUT` still
writes to `docs/frontend/`, which no longer exists — a re-run lands in a new folder
instead of updating the committed page at `docs/frontendEducation/strategy-catalog.html`.
Fix `OUT` to the `frontendEducation` path. Do NOT run the script against the DB; just fix
the path and any stale comment beside it.

## Deliverable

A short report at `task/2026-September-week3/GEMINI-REPORT.md`: files created/changed,
test count and output, anything you could not do and why, and anything you noticed but
did not touch (observations welcome; action outside the file list above is not).
