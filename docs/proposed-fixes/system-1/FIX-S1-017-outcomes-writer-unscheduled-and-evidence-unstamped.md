# FIX-S1-017 — the outcomes writer was never scheduled, and published artefacts never stated their evidence age

**Status:** IMPLEMENTED (2026-08-29) · **Severity:** high · **Author:** Claude (Opus 5), at owner request

---

## Summary

`fact_trade_outcomes` stopped advancing on 2026-08-16 and nobody was told for thirteen days.
The heartbeat detected it correctly and on time. What failed is that the table has no
scheduled writer at all, and that every artefact derived from it publishes a fresh
timestamp without ever stating how old the evidence underneath it is.

The regime map published `2026-08-24T10:20:53Z` as `status: published` was vetted against
trades that stop `2026-08-14 17:00Z`. Nothing in that artefact records the gap.

## Evidence

```
$ psql -c 'select count(*), max("timestamp"), max(created_at) from fact_trade_outcomes'
 92994 | 2026-08-14 17:00Z | 2026-08-16 23:50Z

$ python -m src.monitoring.heartbeat --json
overall_status: CRITICAL, exit_code 2
outcomes: CRITICAL — "14.1 days behind the last market close (2026-08-28 20:00Z);
                      latest row 2026-08-14 17:00Z"  age 363.5h / threshold 168h
```

`docs/critical/REPO_STATE.md` recorded this as WARN at `2026-08-28T13:11:34Z`, with a
shortfall of 171.0 h. That number was correct when written; see defect 4 for why it then
jumped a full week in a single step.

## The four defects

### 1. No scheduled caller (the cause)

`src/outcomes/persist_all.py` holds its own `INSERT … ON CONFLICT` and is the writer of
`fact_trade_outcomes`. Grep across every `.py`, `.sh`, `.yaml` outside `task/` finds **zero
callers** — only its own logger name. The older `src/layer0/persist_trade_outcomes.py` is
called from tests and the heartbeat import-canary only.

The retrain was **not** what would re-derive it. `orchestrator._default_pipeline()` runs
`hmm_regime.run` → `attribute.run` → `vet.run`; all three only `SELECT` from the table. So
the hold on the retrain cron (expires 2026-09-15) neither caused this nor would lifting it
fix it — lifting it would re-run vetting against the *same* stale trades and publish a map
with a fresh `generated_at_utc` over unchanged evidence.

**Fix:** `shell/cron_persist_outcomes.sh`, `flock`-guarded, scheduled `0 2 * * 2-6`.
Placed after `cron_daily_ingest_and_signals.sh` (22:30 Mon-Fri, advances prices) and before
`cron_publish_strategy_stats.sh` (05:40, reads this table). Kept a separate job rather than
appended to the nightly ingest script, because that script also emits live signals and a
slow backtest must not be able to delay emission. A full 10-year rebuild of the registry
measures **4 min 03 s**.

### 2. The writer was unobservable, and dropped strategies silently

It collected everything in memory and committed once, with no state file, no progress
logging and no run record. `max(created_at)` was the only liveness signal available, and it
cannot distinguish "never scheduled" from "scheduled and crashing nightly" — both leave the
table untouched.

Worse, `run()` caught instantiation failure with `logger.error(...); continue`. **12 of 67
registered strategies currently fail to instantiate:**

| Strategies | Error |
|---|---|
| `Range_Bollinger_H1`, `_H4`, `_Aggressive` | `not found in get_all_strategies()` |
| 9 × `*_RA` (`Trend_EMA_ADX_*`, `Trend_Donchian_*`, `Range_Bollinger_*`) | `No module named 'src.regime_aware'` |

`src.regime_aware` was removed deliberately with the failed R3 experiment (it is already
recorded under "Known-broken" in `REPO_STATE.md` as the reason `publish_regime` is down).
So the 9 `*_RA` rows are stale registry entries to deactivate, not code to restore — the
registry kept advertising strategies whose implementation was intentionally deleted.

**Fix:** `results/state/outcomes_writer_state.json`, written atomically, in the same shape
as `signal_emitter_state.json`. New `outcomes_writer` heartbeat check reads it. Strategy
failures are reported there rather than as a non-zero exit — a run that fails every night on
a known-broken strategy turns the exit code into noise.

### 3. Orphaned rows — the upsert never deletes

`ON CONFLICT DO UPDATE` only adds or refreshes. A strategy whose code stops loading keeps
its old trades forever, with their original `created_at`, and they keep feeding attribution
and vetting.

A fresh rebuild produces **75,344** trades; the table holds **92,994**. The delta is
**17,583 rows across strategy_ids 7, 8, 9** — the three `Range_Bollinger` entries that no
longer load. This is the FIX-S1-013 shape reached by a different route: rows that outlive
the code that justified them, still able to qualify.

None of 7/8/9 is in the live map today. That is luck, not design.

**Fix:** the run reports `ghost_rows` in its state file and the heartbeat surfaces it. A
`--reconcile` flag deletes them **in the same transaction as the insert**, so the table is
either fully reconciled or untouched. It is **off by default and owner-gated** — deleting
17.5k rows of the primary evidence table is destructive even though the table is derived.

### 4. The freshness model assumed a cadence that no longer exists

`freshness.last_scheduled_ingest()` returned the most recent Saturday 00:00 UTC, documented
as *"the only thing that advances price data"*. True when written; the daily weekday ingest
was added afterwards and is not in `crontab.backup-20260802.txt`.

The consequence was not a false alarm but a **missed** one. Because the expected-coverage
bar only stepped on Saturdays, a daily ingest that died on a Monday left `prices` reporting
OK until the following weekend — and `regimes` and `outcomes` inherited the blind spot. It
is also why `outcomes` sat flat at 171 h all week and then crossed WARN→CRITICAL in a single
168 h jump at `2026-08-29T00:00Z`, with nothing in between.

**Fix:** `last_scheduled_ingest` now returns the later of the daily weekday slot (22:30) and
the weekly Saturday slot; `expected_price_coverage` clamps to the Friday close only when the
market was actually shut at that moment. Today's value is unchanged (`2026-08-28 20:00Z`),
so there is no regression; mid-week the bar now advances daily.

Tests asserting the Saturday-only model were updated to the current cadence per the standing
rule (fix the tests, do not revert deliberate behaviour), and a new test pins that the
expected bar moves on every weekday.

### 5. Artefacts did not state their own evidence age

`regime_strategy_map.json` carried `generated_at_utc` and no `data_through`.
`publish_strategy_stats.py` carried neither — and its cron runs **daily**, so for thirteen
days it republished derived risk stats to `risk/strategy_stats/latest.json` under a fresh
`produced_at` over frozen evidence. System 3 had no field that would have let it notice.

**Fix:** `data_through_utc`, `evidence_age_days` and `outcomes_written_at_utc` added to the
regime map, the weights document, and the strategy-stats document. Reported, never gated on
— System 1 publishes the measurement; the consumer decides what is too old. Absent rather
than defaulted when the DB is unreachable: a fabricated freshness claim is worse than a
missing one.

Contract change is **additive only**. The fields are in `properties` but **not** `required`
in `contracts/regime-map-contract.json` and `weights-contract.json`, per
`contracts/README.md` ("never add a field without a default") — System 2/3 must keep parsing
artefacts published before this change. In the stats document the fields sit outside the
checksum, which covers the `strategies` map only, so no existing consumer is invalidated.

## What this does not fix

- **The 12 broken strategies.** Reported now, not repaired. `src.regime_aware` does not
  exist in this repo; the three `Range_Bollinger` entries are active in `dim_strategy` but
  unreachable in code. Registry/code drift, owner decision.
- **The 17,583 orphaned rows.** Surfaced and removable, not removed.
- **The live map.** Still `status: published` against 2026-08-14 evidence. Owner elected to
  leave it live and re-vet after the first fresh writer run rather than withdraw it.
- **The retrain hold.** Untouched, and it was never the cause. Its 2026-09-15 expiry is now
  a deadline: the re-enabled retrain will republish a map, and that republish should land on
  fresh evidence.
