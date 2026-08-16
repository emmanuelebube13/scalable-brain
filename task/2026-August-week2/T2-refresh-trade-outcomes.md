# T2 — Refresh `fact_trade_outcomes` (destructive rebuild)

**Engineer:** Agy
**Reviewer:** Claude (will verify after you report)
**Repo:** `/home/emmanuel/Documents/Scalable_Brain/scalable-brain`
**Venv:** `source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate`
**Estimated time:** 45–60 min (most of it is the backtest running unattended).
**Risk:** medium — the writer `DELETE`s and commits *before* it rebuilds. The snapshot in step 1 is what makes this safe.

> Do this in its own sitting. Do not multitask through it, do not start anything else in this
> repo while the rebuild is running.

---

## Why this matters

`fact_trade_outcomes` is the evidence table. Attribution reads it, vetting reads attribution, the
gatekeeper trains on it. Its newest row is **2026-07-24** — 22 days old. Price data is current to
**2026-08-14 17:00**. So every score the system has produced for three weeks was computed on
evidence that stops three weeks short of the data we actually have.

This is currently the only alarm on the board that is telling the truth. Your job is to silence it
honestly: rebuild the table, prove the rebuild did not lose history, and write down exactly what
changed.

You are not fixing the writer, not improving the strategies, not re-running downstream stages.
See **Out of scope** at the bottom — it is unusually important on this task.

---

## Verified state as of 2026-08-15 05:20 UTC (re-verify before you act)

```
fact_trade_outcomes      134,407 rows | 2016-08-03 → 2026-07-24 | 84 MB
  H1                     115,668 rows | 2016-08-03 → 2026-07-24
  H4                      18,739 rows | 2016-08-15 → 2026-07-24
  is_oos true/false        93,405 / 41,002
  strategies present      10 (strategy_id 1–10)

fact_market_prices       H1 → 2026-08-14 17:00-03   H4 → 2026-08-14 14:00-03
                         all 5 active pairs current (EUR_USD GBP_USD USD_JPY AUD_USD USD_CAD)

existing backup          fact_trade_outcomes_bak_20260729  (134,520 rows, 2026-06-24 vintage)
```

Per-strategy row counts you should expect to see again in the same rough proportions:

| id | strategy | rows |
|---|---|---|
| 1 | Trend_EMA_ADX_H1 | 13,109 |
| 2 | Trend_EMA_ADX_H4 | 6,292 |
| 3 | Trend_EMA_ADX_MultiTF | 6,292 |
| 4 | Trend_Donchian_H1 | 24,117 |
| 5 | Trend_Donchian_H4 | 17,308 |
| 6 | Trend_Donchian_VCP | 11,146 |
| 7 | Range_Bollinger_H1 | 13,934 |
| 8 | Range_Bollinger_H4 | 13,934 |
| 9 | Range_Bollinger_Aggressive | 27,383 |
| 10 | Range_Stochastic_Divergence | 892 |

---

## What the writer actually does — read this before running it

`src/layer0/persist_trade_outcomes.py::run()`:

1. seeds `dim_strategy` / `dim_strategy_registry` for the 10 strategies from `get_all_strategies()`
2. `DELETE FROM fact_trade_outcomes WHERE strategy_id IN (1..10)` — **and commits**
3. preloads prices for `lookback_years`
4. runs 100 backtests (10 strategies × 5 pairs × H1/H4), accumulating every trade in memory
5. assigns `is_oos` / `fold_id` over the *whole* accumulated population
6. one bulk `execute_values` INSERT, then commits

Three consequences that drive every instruction below:

- **It is a rebuild, not a backfill.** There is no `ON CONFLICT` and no way to write only a date
  window. You cannot "add the missing three weeks".
- **A crash anywhere in steps 3–6 leaves the table empty**, because the DELETE already committed.
  There is no transaction around this. The snapshot is the entire safety net.
- **`--lookback-years` silently decides how much history exists.** The default is `5`. On
  2026-07-29 the first attempt ran at the default and produced **66,597 rows starting 2021-08** —
  it did not add recent weeks, it deleted half the history. Row count alone did not catch it; only
  the minimum timestamp did. **Pass `--lookback-years 10`.**

---

## Steps

### 0. Orient

```bash
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain
source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate
export PGPASSWORD=$(grep '^DB_PASS=' .env | cut -d= -f2-)
alias sbsql='psql -h localhost -p 5432 -U sa -d ForexBrainDB'
```

`PGPASSWORD` stays in the shell. **Never paste it, or any line of `.env`, into the report.**

Confirm the writer imports and the roster is the expected 10:

```bash
python -c "import src.layer0.persist_trade_outcomes; print('import OK')"
python -c "from src.layer0.qualify_strategies import get_all_strategies as g; print(len(g()))"
```

Expect `import OK` and `10`. **If the count is not 10, stop and report** — a changed roster changes
which `strategy_id`s get deleted, and the whole plan below assumes 1–10.

No concurrent writer will interfere: the hourly retrain cron is **not** installed (deliberate hold),
and the only active job is the Saturday 00:00 UTC OANDA ingest, which already fired today. Verify
with `crontab -l` before you start. If a retrain cron has appeared, stop and report.

### 1. Snapshot first — this is the safety net, not a formality

```bash
sbsql -c "CREATE TABLE fact_trade_outcomes_bak_20260815 AS SELECT * FROM fact_trade_outcomes;"
sbsql -c "SELECT count(*) FROM fact_trade_outcomes_bak_20260815;"
```

The count **must** be 134,407 (or whatever step 2 records as the live count — they must match
exactly). If it does not match, stop; do not run the rebuild.

Do **not** drop `fact_trade_outcomes_bak_20260729`. Two vintages on disk is fine; it is 84 MB.

### 2. Capture the baseline mechanically

```bash
sbsql -A -F'|' \
  -c "SELECT count(*), min(timestamp), max(timestamp) FROM fact_trade_outcomes;" \
  -c "SELECT granularity, count(*), min(timestamp), max(timestamp) FROM fact_trade_outcomes GROUP BY 1 ORDER BY 1;" \
  -c "SELECT strategy_id, count(*), max(timestamp) FROM fact_trade_outcomes GROUP BY 1 ORDER BY 1;" \
  -c "SELECT is_oos, count(*) FROM fact_trade_outcomes GROUP BY 1 ORDER BY 1;" \
  > /tmp/outcomes_before.txt
cat /tmp/outcomes_before.txt
```

Keep this file. The done-check is a diff against it, not a memory of what the numbers were.

### 3. Run the rebuild

Run it detached from your terminal so a dropped connection cannot kill it between the DELETE and
the INSERT:

```bash
nohup python -m src.layer0.persist_trade_outcomes \
  --granularities H1,H4 \
  --lookback-years 10 \
  > logs/persist_outcomes_20260815.log 2>&1 &
echo $!
```

Then watch, don't poke:

```bash
tail -f logs/persist_outcomes_20260815.log
```

`--lookback-years 10` is not optional and not a preference. Re-read the third bullet above if you
are tempted to drop it.

Expect ~100 lines of `  <strategy> <pair> <gran>: N trades backtested` followed by
`DONE: {'strategies': 10, 'backtests': 100, 'trades': ~134000}`. Budget 20–60 minutes.

**If it dies before `DONE:`** — the table is now empty or partial. Do not re-run blind and do not
let anything else read the table. Restore first, then report:

```bash
sbsql -c "SELECT count(*) FROM fact_trade_outcomes;"   # confirm the damage
sbsql -c "TRUNCATE fact_trade_outcomes;"
sbsql -c "INSERT INTO fact_trade_outcomes SELECT * FROM fact_trade_outcomes_bak_20260815;"
# the restore writes explicit outcome_ids, so the sequence is now behind the max id.
# without this, the NEXT rebuild's INSERT (which relies on nextval) dies on a PK collision.
sbsql -c "SELECT setval('fact_trade_outcomes_outcome_id_seq', (SELECT max(outcome_id) FROM fact_trade_outcomes));"
sbsql -c "SELECT count(*), min(timestamp), max(timestamp) FROM fact_trade_outcomes;"
```

That restores the 07-24 vintage exactly, including `outcome_id`. Then stop and report with the
tail of the log — do not attempt a second rebuild in the same sitting without a review.

### 4. Verify

Re-run the exact same four queries into `/tmp/outcomes_after.txt` and diff them:

```bash
sbsql -A -F'|' \
  -c "SELECT count(*), min(timestamp), max(timestamp) FROM fact_trade_outcomes;" \
  -c "SELECT granularity, count(*), min(timestamp), max(timestamp) FROM fact_trade_outcomes GROUP BY 1 ORDER BY 1;" \
  -c "SELECT strategy_id, count(*), max(timestamp) FROM fact_trade_outcomes GROUP BY 1 ORDER BY 1;" \
  -c "SELECT is_oos, count(*) FROM fact_trade_outcomes GROUP BY 1 ORDER BY 1;" \
  > /tmp/outcomes_after.txt
diff /tmp/outcomes_before.txt /tmp/outcomes_after.txt
```

Check each of these and say so explicitly in the report:

| # | Check | Pass condition | Meaning if it fails |
|---|---|---|---|
| 1 | **min timestamp** | `2016-08` or `2016-09` | ≥ 2021 means the lookback was 5 — history destroyed, re-run at 10 |
| 2 | **max timestamp** | ≥ 2026-08-05, and within a few days of 2026-08-14 | rebuild did not pick up recent prices |
| 3 | **total rows** | 130,000–140,000 | a large drop is a truncated window or a failed strategy |
| 4 | **rows vs snapshot** | did not shrink materially (−0.5% is fine, see below) | see #3 |
| 5 | **granularities** | exactly `H1` and `H4`, both populated | a granularity silently produced zero trades |
| 6 | **strategy ids** | all of 1–10 present, proportions ≈ the table above | a strategy stopped generating signals |
| 7 | **is_oos** | both `t` and `f` present, no NULLs | walk-forward labelling did not run |

Query for #7's NULL case specifically — it is the one a `GROUP BY` will show you but is easy to
skim past:

```bash
sbsql -c "SELECT count(*) FROM fact_trade_outcomes WHERE is_oos IS NULL;"   -- expect 0
```

**On "did the count shrink":** the window is a rolling 10 years, so the rebuild *gains* weeks at
the recent end and *drops* weeks at the 2016 end. The 2026-07-29 run went 134,520 → 134,407, a net
−113, and that was correct behaviour. A few hundred either way is the window rolling. A drop of
thousands is a defect. Report the number and the interpretation, not just the number.

### 5. Record the run

Write `task/2026-August-week2/deliverables/T2/DELIVERABLE.md` containing:

- the before/after table (rows, min, max, per granularity, per strategy, OOS split)
- the exact command line you ran, verbatim
- wall-clock runtime and the final `DONE:` line
- the seven checks above with pass/fail
- the snapshot table name and its row count
- anything you noticed and deliberately did not touch

Also append one line to `task/OPEN.md` under item 8 recording that the rebuild ran, the new max
timestamp, and that **attribution and vetting are now stale against it** (see below). Update item 8
in place — do not start a competing list.

---

## Two things you will see that are not bugs

**Strategy 10 (`Range_Stochastic_Divergence`) will be rebuilt with real-looking rows.** It reads the
future — `range_stochastic.py` uses `rolling(center=True)` for its divergence pivots — and it is
`INTEGRITY_DISQUALIFIED` in `src/system1/vetting/vet.py`. The disqualification is deliberately in
vetting, not in the strategy, so the rebuild reproduces its ~892 contaminated rows exactly as
before. That is expected. **Do not treat any metric derived from strategy 10 as evidence, and do
not "fix" the strategy in this task.**

**`max(timestamp)` will not reach 2026-08-14.** The column is trade *entry* time and only closed
trades are written, so the newest entry lags the last price bar by the holding period (median 4
bars H1 / 6 bars H4, max 50). Landing around 2026-08-12 ± 2 days is the correct outcome. "Within a
few days of now" means that — not equal to the last price bar.

---

## Out of scope — do not do these

- **Do not re-run attribution, vetting, the gatekeeper, or the orchestrator.** Fresh outcomes make
  `fact_strategy_regime_attribution` stale, and re-running that chain is the *next* task with its
  own review. `python -m src.system1.vetting.vet --live` writes the live map; the orchestrator can
  promote a champion. Neither has a mandate here. Note the staleness in your report and stop.
- **Do not edit `persist_trade_outcomes.py`.** Its unsafe DELETE-then-rebuild is a known,
  documented defect with an open follow-up (build into a temp table and swap). Fixing it under a
  data-refresh task means a code change and a data change land together with no way to tell which
  one moved the numbers.
- **Do not drop any `*_bak_*` table.**
- **Do not commit or push anything.** This task produces data and two markdown files; the review
  comes first.
- **No `Co-Authored-By:` trailer** anywhere, if you do end up writing a commit message for review.
- **No new files at repo root** — `STRUCTURE.md` is the map.

---

## Done when

- `fact_trade_outcomes_bak_20260815` exists with 134,407 rows.
- `max(timestamp)` in `fact_trade_outcomes` is 2026-08-05 or later.
- `min(timestamp)` is still in 2016 — **this is the check that catches the real failure mode**.
- Total rows did not shrink materially versus the snapshot (a few hundred is the rolling window).
- All 10 strategies, both granularities, no NULL `is_oos`.
- `deliverables/T2/DELIVERABLE.md` written; `task/OPEN.md` item 8 updated in place.

## Report back with

1. `diff /tmp/outcomes_before.txt /tmp/outcomes_after.txt`, pasted whole.
2. The exact command line, the runtime, and the final `DONE:` line from the log.
3. The seven checks, each with pass/fail and the actual value.
4. Your reading of the row-count delta: rolling window, or loss?
5. The snapshot table name and count.
6. Anything you noticed and deliberately did not touch.
