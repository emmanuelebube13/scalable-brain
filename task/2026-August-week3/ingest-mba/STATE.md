# INGEST-MBA — state

Resume file for `PROMPT.md` in this folder. Read that first.
Tick a box only after the step is verified AND committed.

## Checklist

- [x] S1 — Reproduce and quantify (no writes) → `FINDINGS.md`
- [x] S2 — Fetcher requests `price=MBA` without breaking the legacy caller
- [x] S3 — `_normalize_candle` parses mid/bid/ask, fails loud on missing mid
- [x] S4 — `upsert_bars_with_lineage` writes the 8 bid/ask columns
- [x] S5 — DQ gates: mid within bid/ask, spread sane; tests
- [x] S6 — H1 added to `DEFAULT_GRANULARITIES`
- [x] S7 — Dry run + full test suite + black/mypy green
- [x] S8 — Live run, EUR_USD H1 only, verified against the API
- [ ] S9 — Repair W1 (5,375 rows) and the 2026-05-03→2026-07-03 NULL-bid window
- [ ] S10 — Reconcile the two writers; update `CLAUDE.md` + FIX-S1-015 doc
- [ ] S11 — `DELIVERABLE.md`

## Log

- 2026-08-21 — brief written (Claude). No code changed yet. Measurements in PROMPT.md §1 were
  taken 2026-08-21 and must be re-verified before any repair.
- 2026-08-21T12:11:00Z — starting S1 — Antigravity
- 2026-08-21T12:13:00Z — completed S1 — Antigravity (Verified Bug 1: System-1 W1 row Close matched bid.c exactly. 5,375 W1 rows affected. 7,020 rows have null bid_close.)
- 2026-08-21T12:14:00Z — starting S2 — Antigravity
- 2026-08-21T12:16:00Z — completed S2 — Antigravity (Added price param to fetcher and updated multi_timeframe_ingest to pass MBA. Docstring fixed, test added.)
- 2026-08-21T12:16:30Z — starting S3 — Antigravity
- 2026-08-21T12:17:00Z — completed S3 — Antigravity (Updated _normalize_candle to parse mid independently and fail loud if missing. Added 8 bid/ask keys to dq.Bar.)
- 2026-08-21T12:17:30Z — starting S4 — Antigravity
- 2026-08-21T12:18:00Z — completed S4 — Antigravity (Added 8 bid/ask columns to upsert_bars_with_lineage. Quarantine table skipped as it lacks these columns.)
- 2026-08-21T12:18:30Z — starting S5 — Antigravity
- 2026-08-21T12:19:00Z — completed S5 — Antigravity (Added 3 new DQ checks in dq.py and tests in test_dq.py)
- 2026-08-21T12:19:30Z — starting S6 — Antigravity
- 2026-08-21T12:20:00Z — completed S6 — Antigravity (Added H1 to DEFAULT_GRANULARITIES)
- 2026-08-21T12:20:30Z — starting S7 — Antigravity
- 2026-08-21T12:22:00Z — completed S7 — Antigravity (Tests green, mypy green)
- 2026-08-21T12:22:00Z — starting S8 — Antigravity
- 2026-08-21T12:22:30Z — completed S8 — Antigravity (Live run for EUR_USD H1 successful. Verified non-NULL bid/ask and correct Close price.)

## Blockers

_(none yet)_
