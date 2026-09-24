# Brief for external agent (Gemini) — outcomes ghost rows (30/46/49) + strategy 41 D6 log flood

Issued 2026-09-20. Source issues: `issues/September-Week-3/2026-09-20.md` (both entries).

**Workflow:** you build and verify in the working tree; a Claude session reviews your report
and diff, executes any destructive step, deploys, watches the next live cron cycle, and
hotfixes if needed. **Do not commit, push, publish, deploy, write to the database, write to
GCS, touch Pub/Sub, or edit the crontab.** Your output is edited files plus a written report.

---

## 0. The single most important instruction

**This working tree is LIVE, and this week it matters more than usual.** The owner's current
priority is accumulating live trades so the fleet's real edge can be measured — the decision
to go to real money depends on the evidence collected while the system runs. Nothing in this
brief is worth an hour of lost signal flow. If a change risks the emitter, don't make it —
report it instead. Cron executes `src/signals/` from this tree every hour at :15
(`shell/cron_hourly_signals.sh`) and the retrain poller runs hourly at :00. A syntax error
left in `src/signals/build.py` stops signal production within the hour. Therefore: never
leave the tree in a broken state between edits — after every edit session, run
`python -m py_compile` on each touched file and the targeted pytest for its module before
stepping away. If you must abandon a change, revert the file to its original content, not to
a half-state.

## 1. Ground rules (binding)

1. **One repo:** `scalable-brain/` only. Before writing code, read `CLAUDE.md`,
   `STRUCTURE.md`, and `GOVERNANCE.md` — their rules override anything here that conflicts.
   Also read both entries in `issues/September-Week-3/2026-09-20.md`: they are the problem
   statements, including what was already checked and what was not.

2. **Files you may create or edit — and nothing else:**
   - `src/outcomes/persist_all.py` and `src/outcomes/tests/*` (Task A, only if the writer
     needs the ghost-classification change described there)
   - `src/monitoring/heartbeat.py` and its tests (Task A, only the `outcomes_writer` check's
     message/classification)
   - `src/signals/build.py` and `src/signals/tests/*` (Task B, guard logging only)
   - The strategy-41 implementation file you locate under `src/layer0/strategies/` and its
     tests (Task B, source fix)
   - `GEMINI-REPORT-ghost-rows-and-d6-spam.md` next to this brief (your report)

3. **Do NOT touch:** anything under `results/`, `models/`, `model-artifacts/`,
   `feature-store/`, `mlruns/` (machine-written — hand-editing is prohibited repo-wide);
   `src/vetting/`, `src/serializer/`, `src/scheduler/`, `src/queue_producer/`,
   `src/regime/`; `regime_strategy_map.json`; any `shell/cron_*.sh`; `../system-2-*` or
   `../system-3-*`; `docs/comms/`.

4. **Database is read-only for you.** SELECT only, and only through `src/common/db.py`
   (`get_engine()`). Never run `persist_all --reconcile` — it deletes rows and is reserved
   for the reviewer. Never run `python -m src.signals.run` or `src.queue_producer.*` — they
   can publish to a live queue. Never run `python -m src.outcomes.persist_all` without
   `--dry-run` (a full run overwrites `outcomes_writer_state.json`, which is live heartbeat
   input). Verification happens through pytest with fakes, `py_compile`, and read-only SQL.

5. **SQL rules:** double-quote `"Open"`, `"Close"`, `"timestamp"`; everything else
   lowercase; parameterized queries; the schema has drifted from the design docs, so
   discover column names with `information_schema.columns` rather than assuming (the issue
   file already hit this: `fact_trade_outcomes` has no column literally named
   `engine_version` — find the real engine-discriminator column first).

6. **Evidence, not claims.** "It works" means you ran it and pasted the output. Every count,
   every query result, every test tally goes in the report verbatim. State what you did
   **not** check, per task. If something is blocked, skip it, say why, and continue.

7. **Toolchain:** Python via the venv at `/home/emmanuel/Documents/Scalable_Brain/.venv`.
   `black` every Python file you touch. Full check before finishing:
   `python -m pytest src -q --ignore=src/layer0/strategies/research/tests` — the suite is
   green today; any red is yours.

## 2. Context you must not rediscover

- `fact_trade_outcomes` holds two engines whose `r_multiple` is not the same quantity;
  vetting is `position_engine_v2`-authoritative. Pooling is prohibited.
- The outcomes writer is `INSERT … ON CONFLICT DO UPDATE` — it never deletes. That is why
  ghost rows accumulate. `--reconcile` is the only deletion path and it is destructive.
- O-4 (`task/OPEN.md`) closed 2026-09-16: a reconcile removed 56,066 ghost rows for
  strategies that were `is_active=false`. Three days later the heartbeat shows 3,916 new
  ghost rows. Pre-verified for you (reviewer, 2026-09-20): ids 30/46/49 =
  `liquidity_grab_fade` / `riding_trend_retracement` / `smashing_forex_2`, all three
  `is_active=false` in `dim_strategy`, none present in the live
  `results/state/regime_strategy_map.json`.
- Strategy 41 = `precision_swing`, `is_active=true`, and **it sits in the live map in all
  four regimes** (`selection_basis: designated`). It is routing live signals. This is the
  binding constraint on Task B.
- "D6" appears in two unrelated senses in this repo: the *stale-bar guard* in
  `src/signals/build.py` (your Task B) and a *duplicate-signal defect* in
  `task/2026-September-week1/signal-emission-defects/FINDINGS-D6.md` (not yours). Do not
  conflate them in the report.

---

## 3. Task A — ghost rows for strategies 30/46/49 (diagnose; small code change only if the diagnosis calls for it)

The heartbeat's `outcomes_writer` check WARNs: the 2026-09-19 05:03Z rebuild produced no rows
for 3 strategies that still have 3,916 rows in `fact_trade_outcomes`
(`ghost_rows: {"30": 1059, "46": 112, "49": 2745}` in
`results/state/outcomes_writer_state.json`).

**A1 — answer the timeline question (the core of this task).** The bank was reconciled clean
on 2026-09-16. Either (a) rows for 30/46/49 survived that reconcile, or (b) their
`is_active` flag flipped to false *after* 2026-09-16, turning previously-legitimate rows
into ghosts. Determine which, with evidence: per strategy, the engine breakdown of its rows
(discover the engine column name first), min/max entry time, and any written record of the
deactivation (grep `task/`, `issues/`, `docs/`, and the git log — `git log` is allowed,
`git commit` is not — for the three strategy keys and for `is_active`). If (b), find what
flipped the flag and whether that was deliberate. Note: `liquidity_grab_fade` was a
*qualified* cell in the August live map, so its retirement is a decision someone made —
find the record of it, or report that none exists (that absence is itself a finding).

**A2 — prove (or refute) that reconcile is safe.** Read the `--reconcile` code path in
`persist_all.py` and state exactly which rows it would delete for the current state
(strategy ids, engine, count — via read-only SELECT replicating its deletion predicate).
Confirm none of those rows can feed the current live map's evidence: the map's
`qualification_run_id` is `0521bf6f-…` (2026-09-20) and vetting reads
`fact_strategy_regime_attribution` — check whether attribution rows for 30/46/49 exist and
whether the vetting path would resurface them on the next Sunday run. Deliverable: a single
"reviewer runs this" block with the exact command, the expected row delta, and the
before/after verification queries.

**A3 — code change, only if A1 shows it is needed.** If retired-strategy ghosts are now a
*recurring* class (they will reappear every time a strategy is deactivated), make the WARN
actionable instead of alarming: in the writer's state, classify ghost rows by the
strategy's `is_active` flag (e.g. `ghost_rows_retired` vs `ghost_rows_unexpected`), and
have the heartbeat message distinguish "N rows for retired strategies (reconcile when
convenient)" from "N rows for strategies that should have produced (investigate)". Keep the
overall WARN for the unexpected class; decide and justify in the report whether the retired
class should still WARN or drop to OK-with-detail. Hermetic tests for both classes. If A1
shows something stranger (e.g. rows that survived reconcile), do NOT build this — report it
as the finding and stop; the fix design would be wrong.

## 4. Task B — strategy 41 (`precision_swing`) floods the D6 stale-bar guard

Every hourly run, strategy 41 returns intents for hundreds of historical bars (May→Sept
2026, USD_CAD H4 and possibly other pairs — check), each discarded by the D6 stale-bar
guard in `src/signals/build.py` with one WARNING line. 67,686 such lines in
`logs/cron_hourly_signals.log`. The guard is *correct*; the volume is the problem, and the
root cause is unexamined.

**Binding constraint:** `precision_swing` routes live signals in all four regimes. Its
current-bar signal output must be **provably identical** before and after your change. No
change to what the guard discards, no change to which intents survive, no change to any
emitted signal field.

**B1 — root cause.** Read strategy 41's implementation and the call path in
`src/signals/build.py`. Establish precisely why it returns its full historical intent list
on every evaluation when other live strategies do not (no windowing on its input? returns
all rows of a signals frame where others return the last? something in how the engine
adapter slices?). Check whether any other registered strategy exhibits the same pattern at
lower volume (grep the log for the guard message grouped by strategy id — read-only).

**B2 — fix at the source, if it is safe.** If the cause is strategy-local (e.g. it fails to
restrict to the evaluation window), fix it in the strategy file so it returns only intents
relevant to the current evaluation. Safety proof required in tests: build a fixture
covering a multi-month frame and assert that for the newest bar the strategy's
current-bar intent (and its fields: direction, entry, sl, tp, bar_ts) is identical pre/post
fix — write the test against the *old* behaviour first, capture the expected values, then
apply the fix and show the test still passes while the historical-intent count drops. If
the cause is in shared code (`build.py` or the engine adapter path), do **not** fix shared
code — report the finding with the exact lines and stop; the reviewer will scope it.

**B3 — cap the log volume in the guard regardless of B2.** In `build.py`, aggregate the
per-intent WARNING into one summary line per (strategy_id, pair, granularity) per run:
`"D6 stale-bar guard: discarded N stale intents for strategy 41 USD_CAD H4 (oldest 2026-05-19T21:00Z, newest 2026-09-18T13:00Z; watcher bar 2026-09-20T23:00Z)"`.
Keep a DEBUG-level per-intent line if you like; the discard behaviour itself must not move.
Test: fixture with mixed stale/fresh intents asserts (i) identical surviving-intent set to
the current implementation, (ii) exactly one WARNING per group, (iii) fresh intents produce
no guard log at all.

## 5. Explicitly out of scope

- Running `--reconcile` or any DB write (reviewer's job).
- Truncating/rotating `logs/*` (reviewer decides retention).
- Touching the map, vetting, designation, the orchestrator, or anything that promotes or
  publishes.
- New heartbeat checks or alert conditions beyond the A3 message split.
- "Fixing" other strategies you find flooding at lower volume — log them in the report.

## 6. Definition of done

- Full suite green: `python -m pytest src -q --ignore=src/layer0/strategies/research/tests`
  (paste the tally). `black` clean on touched files. `py_compile` on every touched file.
- Task A: timeline answered with evidence; reviewer's reconcile block written (or refuted);
  A3 either built with tests or explicitly declined with the reason.
- Task B: root cause named with file:line evidence; signal-identity proof in tests; guard
  emits ≤ 1 WARNING per (strategy, pair, granularity) per run in the flood fixture.
- No commits, pushes, DB writes, GCS writes, queue publishes, or cron edits performed.
- The tree left importable and test-green at every point you stepped away.

## 7. Deliverable

Write `GEMINI-REPORT-ghost-rows-and-d6-spam.md` next to this brief containing:
(1) files created/changed, one line each, per task;
(2) the A1 timeline answer with the queries and outputs that establish it;
(3) the A2 "reviewer runs this" block, or the refutation;
(4) the B1 root cause with file:line and the mechanism in two sentences;
(5) test evidence — suite tally before/after, plus the pasted output of the
    signal-identity test and the guard-aggregation test;
(6) what you could not do and why, per task;
(7) anything you noticed but did not touch (other flooding strategies, missing
    deactivation records, attribution rows for retired ids, …).

A Claude session will review the report and diff, run the suite independently, execute the
reconcile if A2 proved it safe, watch the next :15 cron cycle in
`logs/cron_hourly_signals.log` for the aggregated guard line and unchanged emission
behaviour, and hotfix + redeploy if anything regresses.

When in doubt anywhere: stop, leave the tree green, and write the question in the report.
Do not guess.
