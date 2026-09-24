# Structure Warden Sweep Report (2026-09-24)

## Moved

- `SUMMARY-04B.md` → `audit/reports/SUMMARY-04B.md`
  - **Rule**: "Output of a work item (a report) | `audit/reports/`"
  - **References Updated**: 1 (`task/2026-September-week2/gatekeeper-degeneracy/WORK-ORDER-04B.md`)
- `gk_train_log.txt` → `logs/gk_train_log.txt`
  - **Rule**: "Runtime logs. Git-ignored in full. Nothing by hand."
  - **References Updated**: 1 (`audit/reports/gatekeeper_feature_basis.md`)
- `my_eval_output.txt` → `logs/my_eval_output.txt`
  - **Rule**: "Runtime logs. Git-ignored in full. Nothing by hand."
  - **References Updated**: 1 (`audit/reports/gatekeeper_feature_basis.md`)
- `model001_ingest.log` → `logs/model001_ingest.log`
  - **Rule**: "Runtime logs. Git-ignored in full. Nothing by hand."
  - **References Updated**: 10 (including `src/ingestion/multi_timeframe_ingest.py`, `audit/reports/gatekeeper_feature_basis.md`, and references in `task/` records)
- `model003_regime.log` → `logs/model003_regime.log`
  - **Rule**: "Runtime logs. Git-ignored in full. Nothing by hand."
  - **References Updated**: 9 (including `src/regime/hmm_regime.py`, `audit/reports/gatekeeper_feature_basis.md`, and references in `task/` records)
- `backlog_run.log` → `logs/backlog_run.log`
  - **Rule**: "Runtime logs. Git-ignored in full. Nothing by hand."
  - **References Updated**: 1 (`audit/reports/gatekeeper_feature_basis.md`)
- `run_traceback.log` → `logs/run_traceback.log`
  - **Rule**: "Runtime logs. Git-ignored in full. Nothing by hand."
  - **References Updated**: 1 (`audit/reports/gatekeeper_feature_basis.md`)

## Not moved, and why

- `get_cols.py`, `get_cols2.py`, `get_regime_fix.py`, `list_pg_tables.py`, `test_ghost.py`, `test_regime.py`, `test_regime2.py`, `test_regime3.py`, `test_regime4.py`
  - **Reason**: These are unversioned, untracked scratch scripts at the root with 0 references across the repository. I deliberately left them in place rather than arbitrarily relocating them.
  - **Action**: Propose deletion. Deletion is the owner's call.
- `ForexBrainDB.sqlite`
  - **Reason**: Unversioned, untracked local SQLite database at the root. 0 references found in the repository codebase. Left in place to avoid breaking any local unversioned DB usage.
  - **Action**: Propose deletion or `git ignore` update if it's meant to be kept locally.

## Test Results

**Before sweep:**
```
914 passed, 3 skipped in 30.06s
```

**After sweep:**
```
914 passed, 3 skipped in 30.02s
```

## What I did NOT check

- Untracked files inside ignored directories (e.g., `logs/`, `.venv/`, `.mypy_cache/`) were not scanned for misplaced items.
- Reference verification was primarily done via `git grep` and `grep` across tracked/versioned files.
- The `system1Education/` and `frontendEducation/fullArchitecture/` repos were not audited because they are nested git repositories.
