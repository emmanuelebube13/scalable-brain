# Remediation Pass 2 — Report

**Spec:** Scalable-Brain — Remediation Pass 2 (supersedes `REMEDIATION_R1.md` in full).
**Started:** 2026-09-05
**Operator:** admin@profine.ca
**Status:** IN PROGRESS

---

## §0 — Live-trading decision (RECORDED)

**Decision: (a) HALT NOW.**

Recorded 2026-09-05 by the operator, in response to an explicit prompt naming both options
and their consequences. This is the document's default and its recommendation. It was taken
as a positive decision, not by falling through to the default.

### State at the moment of the decision (measured, not asserted)

| Fact | Value | Source |
|---|---|---|
| Emitter enabled | `true` | `.env:47` `DISABLE_LEGACY_SIGNALS=false` |
| Hourly signal cron | installed, `15 * * * *` | `crontab -l` |
| Daily signal cron | installed, `30 22 * * 1-5` | `crontab -l` |
| Last run | `2026-09-05T11:15:18Z`, outcome `no_signals_generated` | `results/state/signal_emitter_state.json` |
| Last signal actually emitted | `2026-09-04T21:15:44Z` | same |
| Signals published, cumulative | 63 | same |
| Live map generated | `2026-08-24T10:20:53Z` | `results/state/regime_strategy_map.json` |
| Live map label provenance | `regime_model_version: "hmm-v1.0.0"` | same |
| Live map qualification run | `7fde532c-bae1-4d43-a687-13166858af4d` | same |

The map header's `regime_model_version: hmm-v1.0.0` is direct confirmation of the spec's
central finding: the artifact that routes live signals records an **HMM** provenance, while
`src/signals/run.py:48` routes on the **structural** label. The map does not merely happen
to have been built on a different label — it says so, in a field nobody was reading.

### Halt executed

The halt uses `DISABLE_LEGACY_SIGNALS=true`, which is the documented structural cutover
lever (`task/2026-August-week3/inference-migration/CUTOVER.md` §4): it bypasses the
`producer.publish_signals` block entirely in `src/signals/run.py:526`, so emission becomes
unreachable by construction rather than by a conditional that could be mis-evaluated.

**Deliberately NOT done: removing the signal crons.** `shell/cron_hourly_signals.sh` runs
price ingest, health telemetry, ledger publication and the model-card mirror in the same
script as the producer. Removing the cron would have stopped price ingest too, making
`fact_market_prices` stale — which is the exact failure mode R4 exists to prevent, and would
have been self-inflicted. The producer still runs on schedule, still emits its heartbeat,
and now records `suppressed_by_flag`; downstream liveness is preserved while the wire is
silent.

`.env` backed up to `.env.backup-preR2-20260905` (git-ignored, as `.env` is).

**Verification** — run through the same import path cron uses, so `load_dotenv()` fires
exactly as it does under the scheduler:

```
$ .venv/bin/python -c "import os; from src.common.db import get_engine; \
    print(repr(os.environ.get('DISABLE_LEGACY_SIGNALS')))"
DISABLE_LEGACY_SIGNALS = 'true'
emit_enabled would be  = False
```

`emit_enabled = False` is the value read at `run.py:302` and `run.py:526`. Confirmation from
a real scheduled run is pending the next hourly tick and is recorded in the R1 section below.

---

## Pre-flight

### P.1 — Backup — **DONE (with a recorded deviation)**

| | |
|---|---|
| Path | `/home/emmanuel/Documents/Scalable_Brain/backups/ForexBrainDB_preR2_20260905.dump` |
| Format | `pg_dump -Fc -Z6` |
| Size | 656,799,948 bytes (657 MB) |
| Taken | 2026-09-05 11:56:51Z → 11:58:11Z (80 s) |
| SHA256 | `0415006c1c0b3d5a8d2add2d02b53230fdb7c6bd3d2f82dec16e752142654417` |

**Deviation: the restore-to-scratch could not be completed as specified.** The `sa` role is
not a superuser (`rolsuper = f`), and `timescaledb_pre_restore()` sets
`timescaledb.restoring`, which is a superuser-only GUC:

```
ERROR:  permission denied to set parameter "timescaledb.restoring"
CONTEXT: SQL statement "ALTER DATABASE ... SET timescaledb.restoring ='on'"
```

Without it, chunk data fails with `permission denied for schema _timescaledb_internal`
(1,086 such errors). Passwordless sudo is unavailable and `postgres` peer auth fails, so no
superuser route existed. Rather than declare the backup unverified, it was verified by a
different method that is arguably stronger than a row-count comparison, because it is
per-chunk rather than per-table:

**What was verified**

1. **Archive integrity.** `pg_restore --list` exit 0, 7,119 TOC entries, all six target
   tables present, 6,891 `_timescaledb_internal` entries.
2. **Non-hypertable tables — actually restored into a scratch DB and counted:**

   | table | source | restored | |
   |---|---|---|---|
   | `dim_asset` | 5 | 5 | ✅ |
   | `dim_strategy` | 67 | 67 | ✅ |
   | `fact_trade_outcomes` | 93,527 | 93,527 | ✅ |
   | `fact_strategy_regime_attribution` | 3,665 | 3,665 | ✅ |

3. **`fact_market_regime_v2`** (uncompressed hypertable) — all **62 chunks compared
   chunk-by-chunk**, dump vs source: **0 mismatches**, totals 200,941 = 200,941. ✅
4. **`fact_market_prices`** (mostly compressed) — all **507 compressed chunks compared
   batch-for-batch**: **0 mismatches**. Row arithmetic closes exactly:

   ```
      56,935  uncompressed rows in dump (265 chunks of hypertable 1)
   4,698,433  rows represented by 10,784 compressed batches (sum of _ts_meta_count)
   ---------
   4,755,368  = source count of fact_market_prices          ✅ exact
   ```

**Finding (P.1-F1): a truncated dump passes `pg_restore --list`.** An aborted `pg_dump` from
an interrupted earlier run had left
`ForexBrainDB_preR1_20260905.dump` (282 MB) in the backups directory. `pg_restore --list`
exits **0** on it and prints a complete-looking TOC, because the TOC is written near the
start of the archive. Only reading to the end reveals it:

```
$ pg_restore --data-only -f /dev/null ForexBrainDB_preR1_20260905.dump
pg_restore: error: could not read from input file: end of file        # exit 1
```

Quarantined by rename to `...dump.TRUNCATED-DO-NOT-RESTORE` (not deleted — it is evidence),
and `backups/README.md` written documenting both this trap and the superuser requirement.
**If any backup verification in this project has ever consisted of `pg_restore --list`, it
verified nothing.**

**Finding (P.1-F2): disaster recovery on this host is currently impossible without
credentials nobody has recorded.** Restoring this database requires postgres superuser. That
should be established and documented *before* it is needed, not during an incident.

**Finding (P.1-F3): a catalog inconsistency in the compressed hypertable.** Querying the
internal parent `_timescaledb_internal._compressed_hypertable_7` raises
`ERROR: chunk compress_hyper_7_249_chunk has no dimension slices`. Per-chunk access is
unaffected and all data verified intact, so this is not data loss. Not investigated further
— out of scope for this pass. Recorded so it is not rediscovered as new.

### P.2 — Branch — **DONE (with a recorded deviation)**

| | |
|---|---|
| Branch | `remediation/R2` |
| Base SHA | `0d41b51601cce666d3303982a19f4e8b65307b20` |

**Deviation: branched off the current working branch, NOT off `main`.** The spec says
"branch `remediation/R2` off current main". Doing so would have been actively harmful:

- `main` is at `f5a0c8f` dated **2026-08-23** — 13 days stale.
- The working branch `fix/signal-emission-defects-d6-d7-d8` is **21 commits / 223 files**
  ahead of it.
- **`main` does not contain `src/signals/publish_ledger.py`, which the installed hourly cron
  executes every hour** (`shell/cron_hourly_signals.sh`). Branching off `main` would produce
  a tree whose own scheduler references a module that does not exist.
- `main` also lacks `src/signals/ledger.py`, and its `src/signals/run.py` differs from the
  deployed one — and R2.2 requires editing exactly that file.

Every other file this pass touches (`attribute.py`, `gates.py`, `backtest_engine.py`,
`discrimination.py`, `analytics/extract.py`, `designate.py`, `structural.py`) is **identical**
on `main` and `HEAD`, so nothing is gained by the riskier base.

**Finding (P.2-F1): what is deployed is an unmerged feature branch.** The code running in
production is not on `main` and has not been for at least 13 days. "Branch off main" was
written on the assumption that `main` reflects production; it does not. This is a release-
hygiene defect independent of everything else in this pass, and it is why the deviation was
necessary rather than merely convenient.

### P.3 — Live map snapshot — **DONE**

`audit/reports/baseline/regime_strategy_map_pre_R2.json`
SHA256 `4d09d42a42b40c7d8a4eb0c7e4a85642a632f48f9cf4a2c1afb453286a7af9d7`

Header confirms the §0 diagnosis directly:

```json
"generated_at_utc":     "2026-08-24T10:20:53.232599+00:00",
"regime_model_version": "hmm-v1.0.0",
"qualification_run_id": "7fde532c-bae1-4d43-a687-13166858af4d",
"status":               "published"
```

15 entries / 8 distinct strategies: **3 qualified, 5 designated** — matching the spec's
"five of eight". `Ranging` is empty.

| regime | entries |
|---|---|
| Trending-Up | 4 (all designated) |
| Trending-Down | 4 (1 qualified: `liquidity_grab_fade`) |
| High-Vol | 7 (2 qualified: `macd_divergence`, `weekly_day_reversal_ea`) |
| Ranging | 0 |

**R3.3's claim verified independently.** Hashing each entry's full body excluding the regime
key, three strategies are **byte-identical across all three non-empty regimes**:
`nnfx_backtrader`, `reference_pullback_continuation`, `double_bottom_measured_move`.
(`xard_ma_cross_daily_open` appears in two regimes with *differing* bodies, so it is not part
of this defect.)

Noted in passing on `nnfx_backtrader`'s own designation record:
`"pairs_passed_fraction": "0/5"` — **zero of five pairs passed individually**, and the
written reason says so and forces it in anyway on pooled strength. The override is at least
honest about what it is overriding.

### P.4 — Attribution baseline — **DONE**

`audit/reports/baseline/attribution_pre_R2.parquet`
SHA256 `d25cbe78348dea7e87bc98dfa4f5d81301d440d96cb218bfef9b1c97324fa327`
209 rows × 21 columns, run `7fde532c-bae1-4d43-a687-13166858af4d`.

**158 non-UNKNOWN cells** — matching the denominator the spec names for R3.2(d). Regime
split: UNKNOWN 51, High-Vol 50, Trending-Down 41, Ranging 41, Trending-Up 26.
Granularity: H4 93, D1 80, H1 36. 51 distinct strategies.

Recomputing the current gate against this baseline reproduces the spec's findings
independently, from the data rather than from the report:

| spec claim | measured here | |
|---|---|---|
| gate selects *for* small samples | median n of PF≥1.5 cells **9.0**; of PF<1.5 cells **24.5** | ✅ exact |
| MaxDD ≤ 0.25 passes 145/158 (92%) | **145 / 158** | ✅ exact |
| survivors' MaxDD ~0.0002 and 0.0005 | 0.000193, 0.000524, 0.010135 | ✅ |
| survivors' Recovery 8–23 | 7.88, 23.23, 17.58 | ✅ |
| the three qualified cells | strategy 30 @H4 n=13, 34 @H4 n=20, 55 @D1 n=5 | ✅ exact |

**93 of 158 cells (59%) have fewer than 30 OOS trades** — the floor R3.2(a) introduces.

One number does **not** reconcile and is flagged for R3.5: the stored `avg_r` for
non-UNKNOWN cells has mean **+1.34** and median **+1.10**, which cannot be squared with the
spec's "mean OOS R −0.070". The stored `avg_r` is non-negative for every cell (min 0.0),
which is not the shape of a real per-trade R distribution. Whatever the verification report
computed as "mean OOS R", it is **not** this column. Resolving which is correct is part of
R3.1/R3.5 and is called out here so the discrepancy is not silently inherited.

---

## R1 — Live map control — **DONE**

### R1.1 — Freeze — DONE

New module `src/vetting/map_contract.py`. Env switch `REGIME_MAP_WRITES_FROZEN`,
**default frozen**. Enforced at both live write paths:

- `vet.py` `run(live=True)` — checked *after* the map is built and validated, before
  anything is written, so a frozen run still computes and reports everything. The freeze
  costs publication, not visibility.
- `designate.py` — checked in the non-dry-run branch only, so `--dry-run` still shows
  exactly what a designation would do while frozen.

Default-frozen is deliberate: fail-closed applies to writes too, and §7 expects the map to
end this pass empty, so a writer that refuses by default matches the intended end state.
Override is explicit: `REGIME_MAP_WRITES_FROZEN=false <command>`. Anything that is not
literally `false/0/no` stays frozen, so a typo in the override fails safe.

### R1.2 — Provenance and expiry — DONE

`provenance_header()` adds `built_at_utc`, `built_from_run_id`, `source_label`,
`labeller_version`, `code_git_sha`, `expires_at_utc`, `max_age_days`.

**Deviation: fields were ADDED, not renamed.** The spec's shape uses `built_at_utc` /
`built_from_run_id` / `entries`; the existing artifact uses `generated_at_utc` /
`qualification_run_id` / `regimes` and is read by `contracts/regime-map-contract.json` at
runtime, by the serializer, the model card, analytics, and Systems 2 and 3. Renaming is a
cross-system contract change and is listed out of scope. The contract schema does not set
`additionalProperties`, so additive fields validate cleanly. Verified.

**`source_label` is derived, not declared.** It comes from
`attribution.attribute.SELECTION_SOURCE_LABEL` — the same constant that now selects
attribution's query via a whitelist dict. The map therefore cannot claim one label while
selection used another; changing the selection label changes the map header automatically.
This is the direct fix for the failure mode that caused the incident: a *docstring* claimed
structural labels while the code read `regime_causal`, and a docstring cannot be checked at
runtime.

### R1.3 — Fail closed — DONE

`routing_refusals()` is a pure function (no I/O, so it cannot itself fail open on a network
error) returning **all** reasons rather than the first, so one log line says everything
wrong with the artifact instead of revealing defects one deploy at a time.

Refuses on: missing/unparseable map · missing `regimes` · any missing provenance field ·
`source_label` unrecognised · `source_label` ≠ routing label · age > `MAP_MAX_AGE_DAYS`
(7, config) · past `expires_at_utc` · timezone-naive timestamps.

Wired into `signals/build.py::load_model_set()` — the real gate on the live path, since
that function reads the map from the **GCS model set**, not the local file.

**"No map" and "bad map" are now different outcomes.** `load_model_set()` returns `None`
for both, so `build.last_refusal()` carries the reason and `run.py` records
`map_inadmissible` instead of `no_model_set`. `map_inadmissible` counts as a fault for
`consecutive_faults` / `last_healthy_run_at`. Without this a refusal would have reported
itself as healthy — the FIX-S1-016 shape rebuilt one layer up.

**Verification — the real artifact is refused:**

```
$ routing_refusals(<the actual published map that was trading>)
REFUSE: map is missing required provenance field(s): built_at_utc, built_from_run_id,
        source_label, labeller_version, code_git_sha, expires_at_utc
```

and a map that is well-formed but selected under the wrong label:

```
REFUSE: map was SELECTED under 'regime_causal' but signals are ROUTED under
        'regime_structural' — the map's cells do not describe the conditions that
        would fire them
```

**Tests:** 25 new in `src/vetting/tests/test_map_contract.py`, 4 new end-to-end in
`src/signals/tests/test_model_set_source.py`. Includes a regression pin that runs the
genuine 2026-08-24 published map through the real check — if that test ever passes, the
guard has been defeated.

### R1.4 — Revalidate the three qualified cells — **DONE, but the finding does NOT replicate**

Recomputed against current data (93,527 trades, latest entry 2026-09-04T19:00Z) using the
real pipeline functions, in-process, without persisting.

| cell | n | PF | Sharpe | WR | MaxDD | Recovery | OOS | mean R | verdict |
|---|---|---|---|---|---|---|---|---|---|
| `liquidity_grab_fade@H4` (30, Trending-Down) | 13 | 22.14 | 2.07 | 0.846 | 0.000413 | 22.26 | **23.98 mo** | +0.0705 | **PASS** |
| `macd_divergence@H4` (34, High-Vol) | 20 | 13.58 | 2.89 | 0.750 | 0.000193 | 23.23 | **17.94 mo** | +0.0224 | **PASS** |
| `weekly_day_reversal_ea@D1` (55, High-Vol) | 5 | 6.76 | 0.84 | 0.400 | 0.010135 | 17.58 | **23.98 mo** | +3.4963 | **PASS** |

Strategy-id ↔ name mapping verified against `dim_strategy` (30/34/55 are exactly those
three), so this is not a case of validating the wrong cells.

**R1.4-F1 — could not confirm the spec's claim.** The spec states the verification report
found `weekly_day_reversal_ea@D1` fails on **OOS = 11.89 mo < 12 mo**. Recomputed here it
is **23.98 mo**, passing comfortably. `oos_months` is the union span of the OOS windows the
cell actually traded in (`WF.oos_month_span` over the folds whose `fold_id` appears among
the cell's OOS trades). I cannot reproduce 11.89 under that definition and do not know what
definition produces it.

**Therefore the cell was NOT removed from the map.** Three reasons, in order of weight:

1. The stated justification does not replicate, and removing a cell on an unconfirmed
   measurement is the same class of error as admitting one on an unconfirmed measurement.
2. It is moot. Emission is halted (§0) and R1.3 now refuses the **entire** map, every cell,
   not just this one. The live risk this action was meant to reduce is already zero.
3. Doing it would require hand-editing a frozen, machine-written artifact — forbidden by
   rules-of-engagement §1.6 and by `CLAUDE.md`'s prohibition on editing machine-written
   files. The correct removal path is a vetting re-run, which is R3.5.

**This is flagged rather than actioned. If the 11.89 figure is correct, the definition that
produces it needs stating, because it disagrees with the pipeline's own.**

**R1.4-F2 — the real coverage problem is far larger than the spec describes.** The spec
cites attribution covering "12,414 of 31,149 H1 rows (~40%)". That is the fraction of
*regime bars* carrying a causal label. The fraction of **trades** that receive one is much
worse:

| granularity | trades with a regime label |
|---|---|
| D1 | 21.1% |
| H4 | 19.9% |
| H1 | 19.5% |
| **overall** | **18,418 of 93,527 — 19.7%** |

**80.3% of all trades are attributed to the UNKNOWN cell**, because trades span 2016-2026
while `regime_causal` exists only from ~2021 and only inside completed folds. Every
regime-conditioned metric in the current map was computed on under a fifth of the evidence.
They are bucketed as UNKNOWN, not dropped (answering R2.5's question directly), which is why
51 of 209 cells are UNKNOWN — but UNKNOWN is not routable, so those trades inform nothing
that ships.

**R1.4-F3 — Sharpe is being clamped on a lot of cells.** The run logged 8 cells whose raw
annualised |Sharpe| exceeded the 10.0 sanity bound and were clamped, including
`|sharpe| = 4736.98` (strategy 44, Trending-Down, D1, n=6) and `1514.27` (strategy 44,
Trending-Up, D1, n=16). `metrics.validate_metrics` documents that breaching this bound
"indicates a measurement bug, not a real strategy" — yet the pipeline clamps and continues
rather than failing the cell. A clamped 10.0 then sails through the Sharpe ≥ 0.8 gate. This
is a gate being satisfied by a number the code itself classifies as a bug.

**R1.4-F4 — staleness tolerance added (not in the spec).** `tag_regime_at_entry` used
`merge_asof(direction="backward")` with **no `tolerance`**, so the last known regime label
was carried forward indefinitely. With `regime_causal`'s newest non-null D1 row at
2026-08-19 and trades running to 2026-09-04, a fortnight of trades were tagged with a
fortnight-old regime and presented as "the regime at entry"; a stale label and a live one
are the same string. Added per-granularity tolerances (H1/H4 72 h, D1 108 h, W1 504 h),
sized to span a weekend, mirroring `watcher.py`'s `LATENCY_THRESHOLDS`.

Measured impact is small — UNKNOWN 80.3% → 80.5% — because the dominant cause of missing
labels is the HMM's limited history, not edge staleness. Recorded because it is a real
correctness fix and because its smallness is itself the evidence that it will not confound
R2.5's before/after coverage comparison.

---

## Not in the spec

*(accumulated throughout; consolidated at the end of this report)*

- **P.1-F1** — a truncated `pg_dump` passes `pg_restore --list` with exit 0.
- **P.1-F2** — DR on this host needs superuser credentials that are not recorded anywhere.
- **P.1-F3** — `_compressed_hypertable_7` parent raises "no dimension slices"; data intact.
- **P.2-F1** — production runs an unmerged branch; `main` is 13 days and 21 commits stale,
  and lacks a module the installed crontab executes hourly.
- **P.4-F1 — RESOLVED, and it is a real defect.** The column named `avg_r` is **not**
  average R. `metrics.avg_r()` computes `mean(wins) / |mean(losses)|` — a *payoff ratio*,
  which is why it is never negative. The actual mean R is in `expectancy`.

  The spec's "mean OOS R = −0.070" is reproduced exactly from `fact_trade_outcomes`:
  **−0.0701 over 64,889 OOS legs**. Only 13 of 51 strategies have a positive OOS mean R.

  The gap this creates is not academic. For `macd_divergence@H4`, the best-looking cell in
  the live map:

  | column | value | what a reader assumes |
  |---|---|---|
  | `avg_r` | **4.5271** | "makes 4.5R per trade" |
  | `expectancy` | **0.0224** | the truth: 0.02R per trade, n=20 |

  A column called `avg_r` sitting next to `expectancy` in a table consumed by vetting and
  read by humans is a trap, and R3.5's requirement to report "every cell's mean R" would
  have reported the wrong column by default. **R3.5 will report `expectancy`.**
- **R1.4-F1** — the spec's `weekly_day_reversal_ea@D1` OOS = 11.89 mo does not replicate;
  measured 23.98 mo. Cell not removed; see R1.4 for the reasoning.
- **R1.4-F2** — only **19.7% of trades** receive any regime label at all (not the ~40% of
  *bars* the spec cites). The live map's cells were selected on under a fifth of the
  evidence.
- **R1.4-F3** — 8 cells produce annualised |Sharpe| above the code's own "this is a
  measurement bug" bound (up to 4736.98) and are silently **clamped to 10.0**, which then
  passes the Sharpe ≥ 0.8 gate.
- **R1.4-F4** — `merge_asof` had no `tolerance`, carrying stale regime labels forward
  indefinitely. Fixed; impact measured at 0.2pp.
- **R1-F5 — the local map and the published map are different artifacts, and nothing
  notices.** `results/state/regime_strategy_map.json` is from qualification run
  `7fde532c` (2026-08-24T10:20Z); the map actually published and routing is from run
  `77f83887` (2026-08-23T18:12Z). The routing entries happen to be identical — only
  `designated_at_utc` differs (10:51:36 local vs 10:02:57 published), i.e. the map was
  re-designated 27 seconds *after* publication and never republished. Harmless this time,
  purely by luck. Any tooling that reasons about "the live map" by reading the local file
  is reading a different artifact from the one System 2 downloads.
- **TEST-F1 — the test suite's verdict depends on operator state.** Three tests in
  `src/signals/tests/test_ledger.py` read `DISABLE_LEGACY_SIGNALS` from the ambient
  environment via `load_dotenv()` rather than isolating it. Halting trading in `.env` — the
  documented, correct response to an incident — turns them red:

  ```
  DISABLE_LEGACY_SIGNALS=true   -> 3 failed, 31 passed   (wire == "suppressed")
  DISABLE_LEGACY_SIGNALS=false  -> 34 passed
  ```

  Not caused by this pass's code changes (confirmed by stashing them). It means "are the
  tests green?" cannot be answered without knowing whether the operator has halted the
  producer, and an incident response makes the suite look broken. They should
  `monkeypatch.setenv` the flag like `test_ledger.py:430` already does elsewhere.

