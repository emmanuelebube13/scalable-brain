# Work Order 01 — report

Run 2026-09-07, 12:40–13:05 UTC. Task A applied, Task B read-only.

---

# Part 1 — Task A

## What was actually wrong

**The diagnosis in the work order is wrong, and so is the one in `INCIDENT_RISK_OFF.md` if
it says the same thing.** `fact_regime_structural` was not behind. It held a label for every
D1 bar that exists in `fact_market_prices`, and it still does.

Per-asset, at the moment I started, row counts were *identical* in both tables:

| symbol | D1 price rows | structural rows | max D1 price bar | max structural bar |
|---|---|---|---|---|
| AUD_USD | 5914 | 5914 | 2026-09-03 21:00Z | 2026-09-03 21:00Z |
| EUR_USD | 5950 | 5950 | 2026-09-03 21:00Z | 2026-09-03 21:00Z |
| GBP_USD | 5943 | 5943 | 2026-09-03 21:00Z | 2026-09-03 21:00Z |
| USD_CAD | 5927 | 5927 | 2026-09-03 21:00Z | 2026-09-03 21:00Z |
| USD_JPY | 5959 | 5959 | 2026-09-03 21:00Z | 2026-09-03 21:00Z |

Running the writer confirmed it: **0 rows written**, `last_bar 2026-09-03 21:00:00+00:00`
for all five instruments. Outcome 1 of Task A was already true before I touched anything.

**The bar named in the work order, `2026-09-06T21:00Z`, does not exist in
`fact_market_prices` and cannot yet.** D1 bars here are stamped at their *open* and run
21:00Z→21:00Z. The bar stamped 2026-09-06T21:00Z is Monday's session; it closes tonight at
2026-09-07T21:00Z. The newest *complete* D1 bar is the one stamped 2026-09-03T21:00Z, which
covers Friday's session and closed at 2026-09-04T21:00Z.

### The hardcoded-date check you asked for

Negative. `load_full_history` (`build_structural.py:88-101`) has a **start** bound —
`ANCHOR_DATE = '2005-01-01'`, deliberate and documented, because a rolling `NOW() - N years`
frame would move the EMA seed every day — and **no end bound at all**. It is not in the
family of `hmm_regime.py:104`. Verified by reading the SQL and by running the writer against
live data and watching it reproduce the existing max exactly.

### So why is the check failing?

**The 54h contract cannot be satisfied on a Monday.** This is arithmetic, not staleness.

`risk_off._reference_time` already handles the weekend: while the market is shut it measures
against the Friday close rather than `now`, so Saturday and Sunday sit at a flat 24h. The
market reopens Sunday 21:00Z. At that instant the newest complete D1 bar is still Thursday's
stamp, and the age jumps straight to **72h** — already 18h over the limit — and climbs to
96h before Monday's bar closes and resets it to 24h.

Simulated with the real `market_is_open` / `last_market_close` and the real FX bar calendar,
3-hourly across a full week:

```
2026-09-04 18:00Z  Fri  open=True   newest complete bar 2026-09-02 21:00Z   45.0h  ok
2026-09-04 21:00Z  Fri  open=False  newest complete bar 2026-09-03 21:00Z   24.0h  ok
2026-09-05 12:00Z  Sat  open=False  newest complete bar 2026-09-03 21:00Z   24.0h  ok
2026-09-06 18:00Z  Sun  open=False  newest complete bar 2026-09-03 21:00Z   24.0h  ok
2026-09-06 21:00Z  Sun  open=True   newest complete bar 2026-09-03 21:00Z   72.0h  BREACH
2026-09-07 12:00Z  Mon  open=True   newest complete bar 2026-09-03 21:00Z   87.0h  BREACH
2026-09-07 18:00Z  Mon  open=True   newest complete bar 2026-09-03 21:00Z   93.0h  BREACH
2026-09-07 21:00Z  Mon  open=True   newest complete bar 2026-09-06 21:00Z   24.0h  ok
2026-09-08 18:00Z  Tue  open=True   newest complete bar 2026-09-06 21:00Z   45.0h  ok
2026-09-09 18:00Z  Wed  open=True   newest complete bar 2026-09-07 21:00Z   45.0h  ok
```

**Every week, Sunday 21:00Z → Monday 21:00Z, `fact_regime_structural` breaches its contract
no matter how well the writer is scheduled.** That is ~24h of guaranteed refusal per week,
covering the whole of Monday's trading. Mid-week the peak age is 45h against the 54h limit —
9h of headroom, which is fine.

I have **not** changed the threshold, per the constraint. Recording the analysis here as
instructed: the limit is not wrong in the mid-week case it was sized for, but `bar_hours`
gives a one-bar allowance where the weekend gap needs a three-bar one. Any fix belongs in
`_reference_time` (extend the "market shut" pin through the first trading day, since a D1
label genuinely cannot exist for a session that has not closed) rather than in the number.
That is a decision for you, not a mechanism I should pick.

### What *was* genuinely missing

Two of the four outcomes were real gaps, and both are now closed:

- **Outcome 2** — nothing ran the writer on a schedule. It was a manual CLI, referenced by
  no shell script and no crontab entry. It had been run by hand once.
- **Outcome 3** — nothing coupled the producer to it. The producer would happily run against
  a table nobody had refreshed.

Outcome 1 was already true. **Closing outcomes 2 and 3 does not clear today's refusal**, and
could not have — see the confirm-after section below.

## What I built, and the alternatives

The labelling step now runs **inside** the two scripts that run the producer
(`cron_hourly_signals.sh`, `cron_daily_ingest_and_signals.sh`), between the ingest and
`src.signals.run`, under the `set -euo pipefail` both scripts already carry. A non-zero exit
from the labeller aborts the script and the producer never starts.

**Alternatives I rejected.** A separate crontab line was the obvious candidate and is what
the discoverability outcome pulls toward, but two independently-scheduled jobs cannot express
"the producer must not run if labelling failed" — there is no ordering guarantee and no way
for one to know the other's exit status, so it fails outcome 3 outright. A systemd timer with
an `After=`/`Requires=` dependency does express it, but introduces a second scheduling system
for one job in a repo where everything else is cron, which fails outcome 4 in a different
way. Having `run.py` call the labeller itself gives the tightest possible coupling, but puts
a 30,000-row write inside the emission path and turns any labeller bug into a producer crash;
it is also directly contrary to `build_structural.py`'s own design note that consumers should
*read* the table rather than compute. The in-script step was the only option that satisfies
3 and 4 together without inventing new machinery.

For outcome 4 I did three things rather than rely on the script body: registered the job as
`structural_labels` in `job_runs.EXPECTED_INTERVAL_HOURS` so it appears in
`python -m src.monitoring.job_runs check` alongside every other scheduled job and its absence
is an alarm; had `build_structural` book itself into `fact_job_runs` regardless of caller; and
annotated the crontab so `crontab -l` says where the labeller runs and why it is not its own
line. Verified:

```
ok    hourly_signals        last success 2026-09-07T12:56:52Z (0.1h ago, expected within 3h)
ok    structural_labels     last success 2026-09-07T12:56:57Z (0.1h ago, expected within 3h)
```

Crontab schedule lines are byte-identical to `results/state/crontab.backup-20260907.txt`
(taken before the edit); only comments were added.

## Code changes to `build_structural.py`

**`--incremental`.** Full history is still computed every run — that is required, the label
for bar *t* depends on the series back to the anchor, and there is no such thing as
"labelling only the new bars". What changes is the *write*: it compares computed rows against
stored ones and upserts only those that are new or actually differ.

Reason: without it an hourly schedule rewrites ~29,693 rows every hour to record the five
bars a day that carry new information, and stamps a fresh `computed_at_utc` across twenty
years of history each time — destroying the only thing that column is for. It also makes
`rows_affected` in `fact_job_runs` meaningful: 0–5 on a normal day, and a large number means
a labeller change genuinely moved historical labels.

The comparison covers the label, `source_bar_time`, `labeller_version` **and every stored
indicator**. Comparing only the label would let a price revision that moved the indicators
but not the verdict go unwritten, leaving stored audit values describing a bar that no longer
exists — and the table exists precisely so a label can be disputed from those values.

**Partial-run failure.** In incremental mode, an active instrument that produced no labels now
raises instead of logging a warning and continuing. Under a schedule those are not the same
thing: the freshness contract reads `max(bar_time_utc)` across *all* instruments, so four
healthy pairs keep the check green while a fifth silently stops being labelled. Manual
backfills keep the old warn-and-continue behaviour, since a partially-populated DB is a normal
thing to backfill *into*.

A dry run is deliberately **not** booked into `fact_job_runs` — recording it would let a
hand-verification paper over the absence of the real scheduled run.

13 new tests in `src/regime/tests/test_incremental_write.py`. Full suite for the touched
areas: **255 passed** (`src/regime`, `src/monitoring`, `src/signals`), plus the 13 new.

Widening to `src/vetting` and `src/attribution` as well gives **368 passed, 1 failed**. The
failure is `test_designate_and_schema.py::test_cli_dry_run_writes_nothing`, and it is **not
mine** — verified by stashing all four of my source changes and re-running, where it fails
identically. It asserts `designate --dry-run` exits 0; it exits 1, and the captured output
ends in the `attribute.POOLED` warning text. That is the read-only pooling opt-in added by
engine_validation_2 §B2 — i.e. the test predates that change and was never updated. Recorded
here rather than fixed, because `designate.py` is explicitly out of scope for this work order.

## Timing

| step | measured |
|---|---|
| `build_structural --dry-run` | 1.8s |
| `build_structural --incremental`, no-op | 2.8s |
| full `cron_hourly_signals.sh` end-to-end | 15.8s |

The producer runs hourly at :15. A 2.8s step is not a scheduling concern, and the existing
`flock` single-flight guard already covers the case where a run overruns.

## First run after the machine has been off for three days

Nothing special happens, by construction. The run is a full recompute from a fixed anchor,
so it has no dependence on having run yesterday — there is no cursor to fall behind and no
gap to detect. It labels whatever is missing and writes exactly the divergent rows.

Verified rather than assumed: I corrupted one historical row (USD_CAD, 2026-04-16, label
overwritten with `CORRUPTED`) and re-ran. It found exactly that row out of 29,693, wrote
exactly 1, restored the correct `Trending-Down`, and recorded `rows_affected: 1`.

The real behaviour after three days off is set by the *ingest*, not the labeller: prices must
be pulled before there is anything to label, and that already happens in the same scripts,
before this step.

## If labelling fails at 03:00 on a Wednesday

Mechanically: the script aborts, the producer does not run, `_job_record.sh`'s EXIT trap
closes `hourly_signals` as `failed`, and `build_structural`'s own `record_job` closes
`structural_labels` as `failed`. No signals are emitted. Verified both halves — the
partial-run condition exits non-zero, and a failing step under `set -e` stops the script
before the producer line.

**Who finds out, and when: realistically, nobody, until someone looks.** This is worth saying
plainly rather than dressing up. `job_runs check` is not wired to anything — it is a command
someone runs. The daily heartbeat at 06:00 is the earliest human-visible artifact, three
hours later, and only if it is read. That is the same shape as the finding in R4.2's own
commit message: the heartbeat detected the 2026-08-24 staleness and reported CRITICAL every
morning for twelve days into a file with no consumer.

What is genuinely better than before is that the failure is now *loud in the data*: the job
shows STALE within 3h, the producer refuses instead of trading on a stale label, and
`s1_health.json` carries the refusal. What is not fixed — and is outside this work order — is
that no path exists from any of those to a human. I would not describe outcome 3 as
"someone finds out"; I would describe it as "nothing trades, and the evidence is there when
someone checks".

## Confirm-after

The work order asks me to confirm the table check passes and the map check still fails. **Only
the second happened, and the first could not.** Full script run at 12:56Z:

```
[2026-09-07T12:56:57Z] --- structural labels ---
INFO EUR_USD: 5950 bars, 0 to write        (all five instruments, 0 to write)
[2026-09-07T12:56:59Z] --- hourly signal producer ---
[ERROR] RISK-OFF — refusing to emit. Stale or missing decision-path inputs:
  - fact_regime_structural: newest row 2026-09-03T21:00:00+00:00 is 88.0h behind now, over the 54h limit
  - regime_strategy_map.json: map declares it was built 2026-08-24T10:20:53Z — 14.1 days ago, over the 7 day limit
```

The map check still fails — correct, and deliberate. The table check still fails because it is
Monday and the newest D1 bar that exists is Friday's. It will start passing tonight after
2026-09-07T21:00Z, when Monday's D1 bar closes, the 22:30 ingest pulls it and the labelling
step writes it — and it will fail again next Sunday at 21:00Z.

Per your instruction, flagging immediately: **the map check did not stop failing.** Nothing
went wrong there.

---

# Part 2 — Facts as measured

### 1. `fact_regime_structural` coverage, per granularity

```
granularity | rows  | assets | min bar_time_utc     | max bar_time_utc     | labels | distinct regime labels
D1          | 29693 | 5      | 2005-12-31 22:00:00Z | 2026-09-03 21:00:00Z | 5      | High-Vol, Ranging, Trending-Down, Trending-Up, UNKNOWN
```

**D1 is the only granularity present.** There are no H1, H4 or W1 rows.

### 2. `fact_trade_outcomes` OOS trade counts, per granularity

```
granularity | OOS   | total
D1          |  2658 |  3610
H1          | 43103 | 62103
H4          | 19490 | 27814
```

Split by engine:

```
engine              | gran | OOS   | total
backtest_engine_v1  | H1   | 30699 | 44312
backtest_engine_v1  | H4   |  8138 | 11721
position_engine_v2  | D1   |  2658 |  3610
position_engine_v2  | H1   | 12404 | 17791
position_engine_v2  | H4   | 11352 | 16093
```

Set against fact 1: the canonical label exists **only at D1**, while 62,593 of 65,251 OOS
trades (95.9%) are H1 or H4.

### 3. Can the writer produce non-D1 labels?

**No.** `GRANULARITY = "D1"` is a module constant with no CLI flag and no parameter. It is
used in three places: the price query filter (`build_structural.py:94`), the change-detection
query (`:226`), and the value written into the `granularity` column (`:278`). There is no
resampling anywhere in `build_structural.py` or `structural.py`.

So the writer neither computes non-D1 labels from their own bars nor resamples a daily label
down. H1/H4 trades receive the D1 label by a point-in-time backward join at the *consumer*,
governed by `attribute.REGIME_TAG_TOLERANCE_HOURS = {H1: 72, H4: 72, D1: 108, W1: 504}`.

### 4. `regime_distribution`, verbatim

From `results/reports/attribution_report_20260824T102053Z.json` — the most recent attribution
report, and the run (`7fde532c-bae1-4d43-a687-13166858af4d`) that produced the live map:

```json
{
  "UNKNOWN": 74971,
  "High-Vol": 5335,
  "Trending-Up": 4983,
  "Ranging": 4401,
  "Trending-Down": 3304
}
```

Report header, for context: `model_version: hmm-v1.0.0`, `n_trades: 92994`,
`n_oos_trades: 64856`, `n_unknown_regime: 74971`, `n_cells: 209`,
`n_low_confidence_cells: 31`, `n_min: 5`, `reconciliation_ok: true`.

### 5. Does `Ranging` appear, and at what share?

**Yes.**

```
UNKNOWN         74971   80.62%
High-Vol         5335    5.74%
Trending-Up      4983    5.36%
Ranging          4401    4.73%
Trending-Down    3304    3.55%
                -----
total           92994
```

`Ranging` is **4.73% of all trades**, or **24.42% of the 18,023 trades that carry a label at
all**. The number that dominates this table is UNKNOWN at 80.62%.

### Unexpected result, reported as instructed

The three retrains before this one recorded `Tagged regimes; 0 trades have UNKNOWN regime (no
prior label)` — on 2026-07-18, 2026-07-25 and 2026-08-01. The 2026-08-24 run recorded 74,971.
I am not offering an explanation for the step change; I am flagging that it exists and that
the live map was selected from the run on the far side of it.

---

# Part 3 — Task B

**`results/state/` is unchanged.** 692 files checksummed before and after; every pre-existing
file byte-identical. `regime_strategy_map.json` and `strategy_weights.json` verified
individually against a baseline taken *before* Task A as well. The one addition during the
window is `retrain_log_20260907T130002050174Z.json`, written by the 13:00 retrain cron while
I was working — not a Task B side effect.

Log-only mode writes to `results/reports/proposed_*` and `vetting_report_*` only. No live
status field was written anywhere.

### 1. What a map rebuild requires

The single governed path is `scheduler/orchestrator._default_pipeline` (`:296-326`):

| # | step | reads | writes | wall clock |
|---|---|---|---|---|
| 0 | `src.outcomes.persist_all` | `fact_market_prices`, strategy registry | `fact_trade_outcomes` | **3m 38s** (measured, cron log 2026-09-05 02:00:03→02:03:41) |
| 1 | `regime.hmm_regime.run()` | `fact_market_prices` (from hardcoded `'2021-08-20'`) | `fact_market_regime_v2`, `models/hmm_model.joblib` | **~23 min** (2026-08-01 retrain, 36 walk-forward folds at H1 alone) |
| 2 | `attribution.attribute.run(engine_version=…)` | `fact_trade_outcomes` + `fact_market_regime_v2.regime_causal` | `fact_strategy_regime_attribution`, `strategy_regime_attribution.parquet`, `attribution_report_*.json` | **~4s** (21:23:02→21:23:06) |
| 3 | `vetting.vet.run(live=True)` | latest `qualification_run_id` in `fact_strategy_regime_attribution` | `results/state/regime_strategy_map.json`, `strategy_weights.json`, registry | **0.8s** (measured today, log-only) |
| 4 | gatekeeper metrics | model artifacts | proposed bundle | ~5m 40s (21:23:07→21:28:49) |

Full pipeline on 2026-08-01: **~29 minutes**, dominated by the HMM.

Step 0 is not part of `_default_pipeline`; it runs on its own cron and feeds step 2.

### 2. Is any step broken, unscheduled, or manual?

**Yes — three of the five, and one is the same defect as Task A.**

- **Step 1, `hmm_regime`, has no scheduled writer at all.** Grep of `shell/` finds no
  reference. `fact_market_regime_v2` is advanced *only* from inside a retrain, and the retrain
  has not fired: every hourly poll since re-enabling records
  `{'trigger_reasons': [], 'ran': False, 'outcome': 'no_trigger_or_cooldown'}`. This is
  exactly the Task A shape — a table on the decision path with no job that refreshes it — and
  it matters more, because `attribute.SELECTION_SOURCE_LABEL = "regime_causal"` means **this
  is the label the map is selected under.** Its freshness contract is currently non-blocking
  (`risk_off.py`, "research only as of 2026-09"), so its decay does not stop trading, but
  selection still reads it.

- **Step 2 is blocked.** `attribute.AUTHORITATIVE_ENGINE_FOR_VETTING` is `None` and
  `orchestrator.py:309` raises before reaching it. Unchanged, per scope.

- **Step 3 is blocked.** `REGIME_MAP_WRITES_FROZEN` defaults to `"true"` and is not set in
  `.env`, so `assert_map_writes_allowed("vet --live")` refuses. Unchanged, per scope.

- Step 0 **is** scheduled (Tue–Sat 02:00 UTC), last ran 2026-09-05, next Tue 2026-09-08. It
  warns on every run: `17583 rows in fact_trade_outcomes belong to 3 strategies this run did
  not produce (7, 8, 9)`.

**Consequence for the question you actually asked.** `vet.py` does not re-run attribution — it
reads the latest `qualification_run_id` already in the table. That is still `7fde532c` from
2026-08-24, the run behind the live map. So a `vet.py` run today is **not** "a rebuild on
current data"; it is the current *code* against 14-day-old evidence. Getting a genuinely fresh
map requires steps 0–2, and 1 and 2 are blocked or unscheduled.

Confirmation that the evidence is identical — `rejection_summary`, live map vs today's
proposal, every figure the same:

```
                       live  proposed
integrity_fail            3         3
low_confidence_fail      30        30
maxdd_fail               38        38
oos_fail                 10        10
pf_fail                 158       158
recovery_fail           167       167
sharpe_fail             162       162
winrate_fail             91        91
```

This is useful in one specific way: it isolates code changes from data changes cleanly.
Everything in §4 below is attributable to code alone.

### 3. What the rebuilt map would contain

209 cells in, **6 qualifying out**. `Ranging` is empty (starvation).

```
strategy                    gran regime          trades      PF Sharpe   WinR   MaxDD   Recov  OOSmo  basis
-----------------------------------------------------------------------------------------------------------
xard_ma_cross_daily_open    H1   Trending-Up        224   1.112  0.534  0.370  0.1745   0.845  23.72  designated
liquidity_grab_fade         H4   Trending-Down       13   8.277  1.742  0.692  0.0005   7.879  23.62  qualified
macd_divergence             H4   High-Vol            20  13.581  2.915  0.750  0.0002  23.234  17.58  qualified
weekly_day_reversal_ea      D1   High-Vol             5   6.762  0.853  0.400  0.0101  17.580  23.36  qualified
xard_ma_cross_daily_open    H1   High-Vol           172   1.248  1.134  0.395  0.1445   1.912  17.67  designated
weekly_gap_fade             H1   High-Vol           100   1.298  0.802  0.520  0.0209   1.648  17.67  designated
```

Gates applied: `PF ≥ 1.50, Sharpe ≥ 0.80, MaxDD ≤ 0.25, WinRate ≥ 0.40, Recovery ≥ 3.00,
OOS ≥ 12 months`.

Note the shape of the three *qualified* cells: they pass on **13, 20 and 5 trades**, with
`max_drawdown` of 0.0005, 0.0002 and 0.0101. A drawdown of 0.02% is what drives
`recovery_factor` to 23.2 and clears a gate set at 3.0. The three designated cells are the
ones with real trade counts (100–224), and all three fail multiple gates by construction.

### 4. How that differs from the live map, entry by entry

Live map: **14 cells** (12 designated, 2 qualified). Proposal: **6** (3 designated, 3
qualified). Five cells shared, with **zero metric differences** on any of them.

```
+ ADDED    weekly_day_reversal_ea@D1@High-Vol
- REMOVED  double_bottom_measured_move@D1@High-Vol
- REMOVED  double_bottom_measured_move@D1@Trending-Down
- REMOVED  double_bottom_measured_move@D1@Trending-Up
- REMOVED  nnfx_backtrader@D1@High-Vol
- REMOVED  nnfx_backtrader@D1@Trending-Down
- REMOVED  nnfx_backtrader@D1@Trending-Up
- REMOVED  reference_pullback_continuation@H4@High-Vol
- REMOVED  reference_pullback_continuation@H4@Trending-Down
- REMOVED  reference_pullback_continuation@H4@Trending-Up
```

**Cause of the nine removals: the designations no longer exist in the code.** `vet.DESIGNATED`
currently holds exactly three keys — `weekly_gap_fade@H1@High-Vol`,
`xard_ma_cross_daily_open@H1@High-Vol`, `xard_ma_cross_daily_open@H1@Trending-Up`. The live
map carries twelve designated cells. Nine of them are designations that have since been
removed from `vet.py`, and on the gates alone those cells fail:

```
double_bottom_measured_move@D1  High-Vol       LOW_CONFIDENCE
double_bottom_measured_move@D1  Trending-Up    LOW_CONFIDENCE
nnfx_backtrader@D1              High-Vol       Sharpe=0.65 < 0.80, Recovery=1.60 < 3.00
nnfx_backtrader@D1              Trending-Down  LOW_CONFIDENCE
nnfx_backtrader@D1              Trending-Up    Recovery=1.51 < 3.00
reference_pullback_continuation@H4 High-Vol       LOW_CONFIDENCE
reference_pullback_continuation@H4 Trending-Down  LOW_CONFIDENCE
```

So the live map is carrying nine cells whose only basis for being there is a human
designation that is no longer in the codebase. A rebuild drops them. I am not judging whether
their removal from `DESIGNATED` was intended — only that the map and the code currently
disagree, and the map is the one that is live.

### 5. Does `weekly_day_reversal_ea@D1` still qualify?

**Yes — in High-Vol, and it is the single cell a rebuild would *add*.** It passes every gate:
PF 6.762 ≥ 1.50, Sharpe 0.853 ≥ 0.80, WinRate 0.400 ≥ 0.40 (exactly on the line), MaxDD
0.0101 ≤ 0.25, Recovery 17.580 ≥ 3.00, OOS 23.36mo ≥ 12. On **5 OOS trades**, which equals
`N_MIN`.

It fails in the other three regimes:

```
Ranging        PF=1.43 < 1.50, Sharpe=0.41 < 0.80, WinRate=15.0% < 40%, Recovery=0.57 < 3.00
Trending-Up    PF=0.97 < 1.50, Sharpe=-0.02 < 0.80, WinRate=16.7% < 40%, Recovery=-0.08 < 3.00
Trending-Down  LOW_CONFIDENCE
UNKNOWN        PF=1.46 < 1.50, Sharpe=0.44 < 0.80, WinRate=14.5% < 40%, Recovery=2.60 < 3.00
```

**This one needs your attention.** It appears as "added" because it was removed from the live
map by hand on 2026-09-05, and the recorded justification does not reproduce:

```json
{"removed_at_utc": "2026-09-05T17:37:01Z", "removed_by": "fix_register_s2",
 "variant": "weekly_day_reversal_ea@D1", "regime": "High-Vol", "selection_basis": "qualified",
 "reason": "S2: Cell no longer qualifies on current data. oos_months=0.0 (was 23.36),
            sharpe=0.0 (was 0.85). Stale fact_market_regime_v2 (last bar 2026-08-24)
            eliminated all labeled folds, collapsing OOS span. ..."}
```

The stored attribution row for that cell says `oos_months 23.36`, `sharpe 0.853` — the "was"
values, not the "now" values. The removal was based on a *re-derivation* against a stale
`fact_market_regime_v2`; the vetting path reads the stored attribution and gets the original
numbers. The two disagree because they are computing different things, and the hand-edit is
the one that is live.

### 6. Non-finite or NULL profit factor among qualifying cells?

**None.** All six are finite and non-null: `1.1116, 1.2475, 1.2980, 6.7624, 8.2772, 13.5813`.

The thing worth looking at is not a NULL but the upper end — 6.76, 8.28 and 13.58 on 5, 13
and 20 trades respectively.

### 7. `status` in this mode, and the live map's `status`

| | `status` | `generated_at_utc` | `source_label` | `expires_at_utc` |
|---|---|---|---|---|
| proposed (log-only) | `"proposed"` | 2026-09-07T12:58:46Z | `"regime_causal"` | 2026-09-14T12:58:46Z |
| **live** | `"published"` | 2026-08-24T10:20:53Z | *absent* | *absent* |

The live map predates R1.2, so it carries neither `source_label` nor `expires_at_utc` — which
is why `map_contract` ages it by `generated_at_utc` and why it is inadmissible on two grounds
rather than one. Note also that a rebuilt map would stamp `source_label: "regime_causal"`
while `ROUTING_SOURCE_LABEL` is `"regime_structural"` — so **a map rebuilt today would be
refused by the routing admissibility check even while fresh.** Rebuilding the map without
first flipping `SELECTION_SOURCE_LABEL` produces an artifact that cannot route.

---

# Part 4

## What I found that is not in any audit document

**1. The Monday breach window.** `fact_regime_structural` cannot satisfy its 54h contract from
Sunday 21:00Z to Monday 21:00Z, every week, regardless of scheduling. Measured above. Today's
refusal is the first instance since the contract was armed, so it has not had a chance to look
like a pattern yet.

**2. `job_runs check` currently reports three false alarms.** `daily_ingest_and_signals`,
`oanda_ingest_saturday` and `persist_outcomes` all show "no successful run has EVER been
recorded". None of them is broken — `_job_record.sh` landed 2026-09-05 19:07 and all three
last ran *before* that. They self-clear tonight (22:30), Tuesday (02:00) and Saturday (00:00)
respectively. Someone reading that output today would reasonably conclude three jobs are dead.
If `daily_ingest_and_signals` is still STALE on Tuesday morning, that one is real.

**3. Nine orphaned designations in the live map** (§4 above) — cells kept alive by a
`DESIGNATED` entry that no longer exists in `vet.py`.

**4. The `weekly_day_reversal_ea` removal does not reproduce** (§5 above).

**5. All six proposed cells ship `exits: {}`.** Every one. Consistent with the known
`vet.py` empty-exits defect, but worth noting that it is 6-for-6 and not occasional.

**6. Attribution's UNKNOWN share stepped from 0 to 80.62%** between the 2026-08-01 and
2026-08-24 runs (§Part 2, unexpected result). The live map was selected from the run after the
step change.

**7. One pre-existing red test**, `test_designate_and_schema.py::test_cli_dry_run_writes_nothing`
— stale against the `attribute.POOLED` warning introduced by engine_validation_2 §B2. Not
mine (verified by stash), not fixed (out of scope). Worth knowing because `CLAUDE.md` says to
treat the suite as green and any red as yours; this one is not.

## What in the work order was wrong or based on a false assumption

**1. "The backfill ran through 2026-09-03 and the missing bar is 2026-09-06T21:00Z."** The
first half is right, the second is not — that bar does not exist in `fact_market_prices` and
will not until 21:00Z tonight. There was no missing bar. You were right to tell me to check.

**2. "Confirm the next scheduled producer run reports the table check as passing."** Not
achievable today under the no-threshold-change constraint. The table was already as current as
the data allows before I started. I have reported the conflict rather than resolving it, per
the instruction.

**3. The implied hardcoded-end-date hypothesis.** Reasonable given `hmm_regime.py:104`, but
`build_structural.py` has a start anchor only and no end bound. Worth noting the *other* half
of that hypothesis landed elsewhere: `hmm_regime.py` itself is unscheduled, which is the
finding in Part 3 §2.

**4. "`vet.py` … produces a proposed map … what a rebuild on current data would actually
produce."** `vet.py` does not re-run attribution. It reads the latest stored
`qualification_run_id`, which is still the 2026-08-24 run. So log-only vetting cannot answer
"on current data" — it answers "current code, 14-day-old evidence". I ran it anyway because
that comparison turns out to be the more useful one (it isolates the nine orphaned
designations), but the question as posed cannot be answered without steps that are blocked by
O-27 and the map freeze.

**5. Not wrong, but worth stating:** Task A and Task B turn out to share a root cause. Task A
was a table on the decision path with no scheduled writer. Task B's step 1, `hmm_regime`, is
the same thing — and it feeds the label the map is selected under. Fixing one and not the
other leaves the map being rebuilt from a table nothing refreshes.
