# T3 — Re-score and sync the live map

**Engineer:** Gemini
**Reviewer:** Claude (will verify after you report)
**Repo:** `/home/emmanuel/Documents/Scalable_Brain/scalable-brain`
**Venv:** `source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate`
**Estimated time:** 30 min (the two runs take about 5 of it; the rest is reading the output before you act on it)
**Risk:** low — vetting is preview-by-default and nothing promotes a champion without the orchestrator, which you are not running. The one irreversible-ish step is a single file overwrite, and step 2 takes a backup of it.

**Depends on:** T2 (`fact_trade_outcomes` rebuild) — **done**, finished 2026-08-15 02:28:13 UTC.

---

## Why this matters

`results/state/regime_strategy_map.json` is the live map: the file that says which strategy the
system will trade in which market regime. Right now it says `"regimes": {}` — nothing qualifies.
That verdict is almost certainly still correct after T2, and you are not expected to change it.

The problem is not the verdict, it is the **provenance**. The file carries
`qualification_run_id: 47fa3bd0-…`, and the attribution rows behind that id were written on
**2026-08-01**, from the 2026-07-24 vintage of `fact_trade_outcomes`, before the regime relabel
(FIX-S1-012/013) and before the `primary_granularity` de-duplication. The file's own
`rejection_summary` describes **80 cells**; the database now holds **40**.

So the file is a claim about data it never saw. That is worse than being empty — an empty map that
is honest is milestone M1; an empty map with a fabricated lineage is a file nobody can audit. Your
job is to make the claim true by re-running the chain that produces it and writing the result down.

You are not tuning gates, not promoting anything, and not touching strategies. See **Out of scope**.

---

## Verified state as of 2026-08-15 08:10 UTC (re-verify before you act)

```
fact_trade_outcomes            55,756 rows | 2016-08-21 → 2026-08-14 13:00-03   (T2 output, post-dedup)
fact_strategy_regime_attribution
  latest run 29709fc8-…        40 cells | created 2026-08-15 04:34:27-03  (already post-T2)
  prior  d8a47c5b-…            80 cells | created 2026-08-14 21:33:59-03  (pre-dedup)
  prior  56e0f4b6-…            80 cells | created 2026-08-14 21:32:26-03  (pre-dedup)
  prior  47fa3bd0-…            80 cells | created 2026-08-01 21:23:06-03  ← what the LIVE MAP cites
dim_strategy_registry          0 rows with is_qualified = true

results/state/regime_strategy_map.json     generated_at 2026-08-14T10:50:48Z   run 47fa3bd0
results/state/strategy_weights.json        written     2026-08-14 07:50 local  (same stale run)
results/reports/proposed_regime_strategy_map.json
                                           generated_at 2026-08-15T07:34:31Z   run 29709fc8
```

The stale live map versus the current preview, side by side. **The right-hand column is what you
should expect to end up publishing:**

| | live map (stale, 08-01 run) | preview (current, 29709fc8) |
|---|---|---|
| cells scored | 80 | **40** |
| qualifying | 0 | **0** |
| empty regimes | all 4 | **all 4** |
| pf_fail | 72 | **36** |
| sharpe_fail | 72 | **36** |
| maxdd_fail | 53 | **16** |
| winrate_fail | 47 | **23** |
| recovery_fail | 72 | **35** |
| oos_fail | 7 | **11** |
| integrity_fail | 8 | **4** |

**Do not read that as improvement.** The counts roughly halve because the cell population halved
(the `primary_granularity` fix stopped backtesting every strategy on both H1 and H4). Comparing a
36 against a 72 across that boundary is comparing two different denominators. The only number that
is comparable across the boundary, and the only one that matters here, is **qualifying = 0**.

---

## What the two commands actually do — read before running

### `python -m src.system1.attribution.attribute` (MODEL-004)

- Point-in-time joins every trade in `fact_trade_outcomes` to `fact_market_regime_v2.regime_causal`
  — the forward-only label in force at entry, not the smoothed reporting label (FIX-S1-005).
- Computes per `(strategy × regime × granularity)` metrics on **OOS trades only**, with Bayesian
  shrinkage for cells thinner than `N_MIN = 20`.
- Mints a **brand-new `qualification_run_id` (a fresh UUID) on every invocation** and inserts its
  rows alongside the previous runs. It deletes only its own run_id, so history accumulates. This is
  why re-running is safe, and also why you must not run it twice in parallel.
- Writes `results/state/strategy_regime_attribution.parquet` and
  `results/reports/attribution_report_<ts>.json`.
- Raises and refuses to write if metric sanity bounds are violated (drawdown > 100%, |Sharpe| > 10).

### `python -m src.system1.vetting.vet [--live]` (MODEL-005)

- Reads **the most recent attribution run only** — `ORDER BY created_at DESC LIMIT 1`. It does not
  take a run_id argument. Whatever attribution ran last is what gets scored.
- Applies `INTEGRITY_DISQUALIFIED` (strategy 10) **before** the performance gates, then the gates.
- **Without `--live`** → writes `results/reports/proposed_regime_strategy_map.json` and
  `proposed_strategy_weights.json`. Touches nothing live.
- **With `--live`** → overwrites `results/state/regime_strategy_map.json` **and**
  `results/state/strategy_weights.json`, **and** runs `_update_registry()`, which executes
  `UPDATE dim_strategy_registry SET is_qualified = false` across the board before re-flagging the
  qualifiers. With zero qualifiers that lands on the same state it is already in — but it is a real
  database write, so know that it happens.
- Both modes write a timestamped `results/reports/vetting_report_<ts>.json` with full per-cell
  rejection detail. That report, not the map, is where you read *why* things failed.
- Both artifacts are validated against `contracts/*-contract.json` before writing. An empty map is
  valid — the current live file proves it.

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

Now the one trap in this task:

```bash
env | grep -i VETTING || echo "VETTING_LOG_ONLY unset — good"
```

`vet.py` computes `live = args.live or os.environ.get("VETTING_LOG_ONLY", "true").lower() == "false"`.
If `VETTING_LOG_ONLY=false` is exported in your shell, **the preview run in step 3 writes the live
map**, and the whole point of previewing first is gone. If that variable is set to anything, unset
it (`unset VETTING_LOG_ONLY`) and say so in your report.

Confirm nothing else is going to write while you work:

```bash
crontab -l
```

The hourly retrain is on a deliberate hold and must not be installed. The Saturday 00:00 UTC OANDA
ingest already fired today. **If a retrain or vetting cron has appeared, stop and report** — it can
overwrite the map between your two runs.

### 1. Capture the pre-state mechanically

```bash
cp results/state/regime_strategy_map.json /tmp/map_before.json
cp results/state/strategy_weights.json    /tmp/weights_before.json

sbsql -A -F'|' \
  -c "SELECT count(*), min(timestamp), max(timestamp) FROM fact_trade_outcomes;" \
  -c "SELECT qualification_run_id, count(*), max(created_at) FROM fact_strategy_regime_attribution GROUP BY 1 ORDER BY 3 DESC LIMIT 5;" \
  -c "SELECT count(*) FROM dim_strategy_registry WHERE is_qualified;" \
  > /tmp/t3_before.txt
cat /tmp/t3_before.txt
```

Expect the outcomes line to read `55756 | 2016-08-… | 2026-08-14 13:00…`. **If it does not, stop
and report** — something has written to the evidence table since T2, and re-scoring on top of an
unexplained change is exactly the thing this task exists to prevent.

### 2. Back up the live map before anything can overwrite it

```bash
cp results/state/regime_strategy_map.json results/state/regime_strategy_map.json.bak-20260815-pre-t3
cp results/state/strategy_weights.json    results/state/strategy_weights.json.bak-20260815-pre-t3
ls -la results/state/regime_strategy_map.json*
```

There is already a `.bak-20260814` from the previous sync. Leave it. Two backups is fine; they are
about a kilobyte each.

### 3. Re-run attribution

```bash
python -m src.system1.attribution.attribute 2>&1 | tee logs/t3_attribution_20260815.log
```

Budget 1–5 minutes. The final line is a dict; the fields that matter:

```
n_trades 55756   n_oos_trades 38610   n_cells 40   n_unknown_regime 0   reconciliation_ok True
```

**This run should be a no-op refresh.** Attribution already ran against the post-T2 outcomes at
04:34 local (run `29709fc8`), so the inputs are unchanged and the arithmetic is deterministic. That
makes this a free determinism check, and it is check #2 below: if the new run's numbers differ from
`29709fc8` at all, something non-deterministic is in the pipeline and that is a finding worth more
than this task. Report it and stop rather than continuing to `--live`.

Capture the new run_id — you will need it twice more:

```bash
sbsql -A -F'|' -c "SELECT qualification_run_id, count(*), max(created_at) FROM fact_strategy_regime_attribution GROUP BY 1 ORDER BY 3 DESC LIMIT 3;"
```

### 4. Run vetting in **preview** mode and read the verdict

```bash
python -m src.system1.vetting.vet 2>&1 | tee logs/t3_vetting_preview_20260815.log
```

No `--live`. The printed summary must show `'mode': 'log_only'` and
`'map_path': '…/results/reports/proposed_regime_strategy_map.json'`. If it says `live`, you missed
the `VETTING_LOG_ONLY` trap in step 0 — stop, restore from the backups in step 2, and report.

Then read the proposal, do not skim it:

```bash
python - <<'PY'
import json
d = json.load(open("results/reports/proposed_regime_strategy_map.json"))
print("run_id       :", d["qualification_run_id"])
print("generated_at :", d["generated_at_utc"])
print("regimes      :", d["regimes"])
print("empty        :", d["empty_regimes"])
print("rejections   :", d["rejection_summary"])
PY
```

**The gate on proceeding to step 5 — all four must hold:**

| | Expected |
|---|---|
| `qualification_run_id` | the run_id from step 3, **not** `29709fc8` and **not** `47fa3bd0` |
| `regimes` | `{}` |
| `empty_regimes` | all four: Trending-Up, Trending-Down, Ranging, High-Vol |
| `rejection_summary` | `pf 36, sharpe 36, maxdd 16, winrate 23, recovery 35, oos 11, low_confidence 0, integrity 4` |

**If `regimes` is non-empty — i.e. something qualified — STOP and report.** Do not run `--live`.
A strategy appearing out of nowhere after a data rebuild is a finding to be reviewed, not a result
to be published; that is precisely how the contaminated champion got into the live map in the
first place (FIX-S1-014). The whole reason this task previews first is to make that outcome cheap.

If the rejection counts differ from the table by a small amount but `regimes` is still `{}`,
that is not automatically a stop — but you must say so explicitly, quote both sets of numbers, and
give your reading of why before you proceed.

### 5. Run vetting with `--live`

Only if step 4's four checks passed.

```bash
python -m src.system1.vetting.vet --live 2>&1 | tee logs/t3_vetting_live_20260815.log
```

The printed summary must show `'mode': 'live'`, `'n_qualifying': 0`, and a `map_path` under
`results/state/`.

Note for your report: this is a **third** attribution-independent scoring pass, but it re-reads the
same latest attribution run, so it must produce byte-identical content to step 4's proposal apart
from `generated_at_utc`. Verify that rather than assuming it:

```bash
python - <<'PY'
import json
a = json.load(open("results/reports/proposed_regime_strategy_map.json"))
b = json.load(open("results/state/regime_strategy_map.json"))
a.pop("generated_at_utc"); b.pop("generated_at_utc")
print("identical apart from timestamp:", a == b)
PY
```

### 6. Verify the sync

```bash
python - <<'PY'
import json, datetime
m = json.load(open("results/state/regime_strategy_map.json"))
gen = datetime.datetime.fromisoformat(m["generated_at_utc"])
t2  = datetime.datetime.fromisoformat("2026-08-15T02:28:13+00:00")
print("generated_at_utc :", m["generated_at_utc"])
print("after T2 rebuild :", gen > t2)
print("run_id           :", m["qualification_run_id"])
print("n_qualifying     :", sum(len(v) for v in m["regimes"].values()))
print("empty_regimes    :", m["empty_regimes"])
print("rejection_summary:", m["rejection_summary"])
PY

sbsql -c "SELECT count(*) FROM dim_strategy_registry WHERE is_qualified;"   -- expect 0
```

| # | Check | Pass condition | Meaning if it fails |
|---|---|---|---|
| 1 | map `generated_at_utc` | later than `2026-08-15T02:28:13Z` | the write did not happen; you read a cached file |
| 2 | attribution determinism | step 3's cells/trades/OOS identical to run `29709fc8` | non-determinism in the pipeline — a finding, stop |
| 3 | map `qualification_run_id` | equals step 3's new run_id | vetting scored an older run — check for a concurrent writer |
| 4 | `n_qualifying` | 0 | see step 4's stop rule; do not publish a surprise qualifier |
| 5 | `empty_regimes` | all four regimes listed | a regime vanished from the constant list |
| 6 | live vs proposed | identical apart from `generated_at_utc` | the two passes saw different attribution — concurrent writer |
| 7 | registry `is_qualified` | 0 | `_update_registry` did not run or did not commit |
| 8 | `strategy_weights.json` | rewritten, mtime today, `weights` empty | the map and the weights are now out of step with each other |

### 7. Record the numbers

Write `task/2026-August-week2/deliverables/T3/DELIVERABLE.md` containing:

- the before/after of the map: `generated_at_utc`, `qualification_run_id`, cell count, qualifier
  count, full `rejection_summary` for each
- the exact command lines, verbatim, in order
- the attribution report path and its `n_trades` / `n_oos_trades` / `n_cells` / `reconciliation_ok`
- the vetting report path for both the preview and the live run
- the eight checks above with pass/fail **and the actual value**
- the backup filenames from step 2
- anything you noticed and deliberately did not touch

Then update **`task/OPEN.md` item 1** ("Sync the live map") in place — mark it done, and record on
that line: the new `generated_at_utc`, the new run_id, `qualifier count: 0`, and `cells: 40`.
Update item 8's closing note so it no longer says attribution and vetting are stale.

**Update in place. Do not start a competing list**, and do not restructure `OPEN.md` — it is the
start-here document and its item numbers are referenced from elsewhere.

---

## Three things you will see that are not bugs

**`integrity_fail: 4`, down from 8.** Strategy 10 (`Range_Stochastic_Divergence`) is barred on
integrity grounds in all four regimes. It used to be barred 8 times because it was scored at both
H1 and H4; after the `primary_granularity` fix it is scored once per regime. Four is the correct
number now. The bar itself has not weakened.

**`n_low_confidence_cells: 3` with `low_confidence_fail: 0`.** Three cells are thin enough for
Bayesian shrinkage to flag them, but they failed a performance gate first, so they never reached
the low-confidence check. Zero here does not mean no thin cells exist.

**`oos_fail` went up, 7 → 11, while every other count went down.** The `oos_months` gate is 60 —
five years of out-of-sample trades in that specific regime cell. When each strategy stopped being
double-counted across granularities, its trades stopped being spread over two cells, but the cells
that remain still have to clear 60 months individually. Rising here alongside a halved population
is expected, not a regression.

---

## Out of scope — do not do these

- **Do not run the orchestrator, the gatekeeper, or any promotion path.** `vet --live` publishes a
  map; it does not promote a champion. Those are separate commands with separate reviews, and
  nothing in this task authorises them.
- **Do not touch `gates.py` or the thresholds.** If your reaction to `0 qualifying` is that a gate
  looks harsh, write that in the report as an observation. Zero qualifiers is the honest current
  state of the evidence (milestone M1) and moving a threshold to escape it is the one failure mode
  this whole pipeline exists to prevent.
- **Do not hand-edit `regime_strategy_map.json`.** It is generated. The next run silently discards
  any edit — this is exactly how the FIX-S1-014 contamination survived a "fix" once already.
- **Do not re-run `persist_trade_outcomes`.** T2 is done and signed off. If you believe the
  outcomes are wrong, stop and report; do not rebuild under a scoring task.
- **Do not drop any `*_bak_*` table or `.bak-*` file.**
- **Do not delete old rows from `fact_strategy_regime_attribution`.** The accumulated run history
  is the audit trail that made the stale-provenance problem visible in the first place.
- **Do not commit or push anything.** This task produces data, artifacts and two markdown files;
  the review comes first.
- **No `Co-Authored-By:` trailer** anywhere, if you do end up drafting a commit message for review.
- **No new files at repo root** — `STRUCTURE.md` is the map.

---

## Done when

- `results/state/regime_strategy_map.json` has `generated_at_utc` later than `2026-08-15T02:28:13Z`.
- Its `qualification_run_id` is the run minted by step 3, and that run has 40 cells.
- Its qualifier count is **0**, all four regimes listed in `empty_regimes`, and that number is
  written down in both `deliverables/T3/DELIVERABLE.md` and `task/OPEN.md` item 1.
- `strategy_weights.json` was rewritten in the same run.
- `dim_strategy_registry` still shows 0 qualified.
- Both `.bak-20260815-pre-t3` backups exist.

## Report back with

1. `/tmp/t3_before.txt`, pasted whole.
2. The three command lines, verbatim, and the printed summary dict from each of the three runs.
3. The before/after map comparison: `generated_at_utc`, run_id, cells, qualifiers, full
   `rejection_summary`.
4. The eight checks, each with pass/fail and the actual value.
5. Your answer to one question in your own words: **did the verdict change, and if not, what
   changed?** A one-line "0 qualifiers, same as before" is not sufficient — the point of the task
   is that the *provenance* changed even though the verdict did not.
6. Anything you noticed and deliberately did not touch.
