# GEMINI-REPORT — Alert bridge + catalog path fix

Issued: 2026-09-17  
Brief: `task/2026-September-week3/GEMINI-BRIEF-alerting-and-catalog.md`

---

## Files created

| File | Lines | Purpose |
|---|---|---|
| `src/monitoring/alert_bridge.py` | ~250 | Reads `HEARTBEAT_ALERT` and `signal_emitter_state.json`, evaluates three alert conditions, sends Telegram with 6h dedup and recovery messages. Atomic state write. `--dry-run` default, `--send` for real delivery. Exit 0 always. |
| `src/monitoring/tests/test_alert_bridge.py` | ~220 | 19 hermetic tests (tmp_path, monkeypatched env, fake `requests.post`). |
| `shell/cron_alert_bridge.sh` | ~38 | Cron wrapper: absolute venv, `flock`, `_job_record.sh alert_bridge`, `job_record_ok`. Proposed cron line in header comment: `*/30 * * * *`. |

## Files changed

| File | Change |
|---|---|
| `shell/build_strategy_catalog.py` | `OUT` path fixed from `docs/frontend/` → `docs/frontendEducation/`. Docstring comment updated to match. |

## Test results

```
$ python -m pytest src/monitoring -q
133 passed in 0.72s
```

Baseline was **114 passed**; the 19 new tests account for all growth. No existing tests broken.

### New test breakdown (19 tests)

| Class | Tests | Covers |
|---|---|---|
| `TestHeartbeatAlertFires` | 2 | HEARTBEAT_ALERT present → fires; absent → does not |
| `TestEmitterFaults` | 2 | consecutive_faults at threshold → fires; below → does not |
| `TestEmitterStaleness` | 3 | Stale weekday → fires; not stale → does not; **weekend does not fire** |
| `TestRecovery` | 1 | Previously-firing key absent → one "recovered" message sent |
| `TestDedupWindow` | 2 | Same key within 6h → suppressed; after 6h → re-notified |
| `TestSendTelegram` | 5 | Missing env vars → False; success → True; API 500 → False; ConnectionError → False; missing token only → False |
| `TestUnreadableState` | 2 | Corrupt JSON → empty dict (notify); missing file → empty dict (notify) |
| `TestDryRun` | 2 | Default invocation → zero `requests.post` calls; `--send` → at least one |

## What I could not do

Nothing was blocked. All four files in scope were delivered.

## Observations (not acted on — outside the file list)

1. **CLAUDE.md §391 documents the `OUT` bug** — the warning note in the documentation map can be removed now that the fix is landed. I did not edit `CLAUDE.md` as it was outside the permitted file list.

2. **`logs/alert_bridge.log`** does not exist yet and will be created on first cron run. The `tee -a` in the shell script handles this transparently.

3. **`results/state/alert_bridge_state.json`** will be created on first run via atomic write (tmp + `os.replace`). The parent directory already exists.

4. **The emitter state file's `last_signal_emitted_at` is currently non-null** (`2026-09-16T21:16:11Z`), so the staleness check will not fire on current data — this is correct behaviour given the emitter recently emitted.

5. **The heartbeat alert flag (`HEARTBEAT_ALERT`) is currently absent**, so the bridge will report "No alerts to send" on its first run — which is also correct.
