# RUN-REPORT — 2026-07-29

Session executed from `RUN-ALL.md`. **T1, T2 and T4 are DONE with full deliverables.**
T3, T5, T6, T7 are untouched and resumable. 17 commits, working tree clean, nothing pushed.

---

## 1. Status board

| Task | Status | Deliverables | Notes |
|---|---|---|---|
| **T1** reconnect-feedback-loop | **DONE** | ✅ DELIVERABLE.md · EXECUTIVE_SUMMARY.md · `outcomes_timeline.png` · `import_graph.png` | Outcomes current through 2026-07-24. Root cause was **not** what T1 described. |
| **T2** secrets-and-env | **DONE** | ✅ DELIVERABLE.md · EXECUTIVE_SUMMARY.md · `exposure_before_after.png` | Password rotated, old value verified dead, 27 occurrences purged from 11 files. |
| **T3** promote-verified-work | **NOT-STARTED** | — | Unblocked by T1. Ends in a decision only you can make. |
| **T4** heartbeat-monitoring | **DONE** | ✅ DELIVERABLE.md · EXECUTIVE_SUMMARY.md · `freshness_dashboard.png` · `outage_history.png` | 8 checks, daily cron installed, first run 8/8 PASS. |
| **T5** derisk-money-layer | **NOT-STARTED** | — | Independent; expected to end partially BLOCKED on VM access. |
| **T6** research-strategy-engine | **NOT-STARTED** | — | Largest task; depends on T1's package repair (now done). |
| **T7** archive-v1-cleanup | **NOT-STARTED** | — | Added to STATE.md mid-session. Runs strictly last. |

Tests: **242 passing** (`src/system1` 173 + new `src/layer0/tests` 42 + new `src/system1/monitoring` 27).

---

## 2. What each completed task actually changed

### T1 — the feedback loop is reconnected

`fact_trade_outcomes` had not been written since **23 June**. Every retrain for five weeks
re-derived its verdicts from a frozen table.

The task's stated root cause was wrong. The space-named directories it blamed contain only
`README.md` and are never imported. The real cause was three stacked breaks from the `layer0`
subpackage reorg: a deleted `strategies/__init__.py`, relative imports left pointing at
pre-reorg locations, and a 1,460-line verbatim copy of the old module appended to a shim.

It hid for five weeks because the shim's `except ImportError` **discarded the real error** and
re-raised an unrelated one, sending anyone who looked to the wrong place. Nine shims now
re-raise the original — and switching that on immediately exposed a second live break nobody
knew about (`qualification/demo.py`).

Outcomes rebuilt: **134,407 rows, current through 2026-07-24**, 1,059 trades recovered across
4 previously dead weeks. 42 regression tests added.

### T2 — the committed DB password is dead

The live `sa` password was in **11 tracked files, 27 times**, since 25 April — including,
notably, the FIX-XC-003 security report itself (7×) and the "secrets management and rotation"
roadmap task (2×). Rotated, old value verified rejected, all occurrences purged, `.env.example`
added. Both cron jobs source `.env` so nothing needed re-pointing.

### T4 — failures are no longer silent

Eight daily checks over prices, outcomes, regimes, champion-bundle integrity, telemetry,
retrain state, cron liveness, and the import chain. First run: **8/8 PASS**. Proven by
simulating the July ingest outage: CRITICAL, exit 2, alert flag raised and logged.

Two useful discoveries: the **VM telemetry publisher is alive** (that had been in doubt), and
the live champion bundle on GCS verified all 7 artifacts against their SHA256.

---

## 3. Failures encountered, and what was corrected

Every one of these was a defect **in the task prompts themselves**; each was fixed in place so
the next run does the right thing, and logged in the relevant `## Failure log`.

| # | Where | Problem | Correction |
|---|---|---|---|
| 1 | `T1` mission | Blamed space-named dirs that are never imported | Mission rewritten with the real three-part root cause |
| 2 | `T1` step 4 | Described an `ON CONFLICT` backfill; the writer actually does `DELETE`+commit then full rebuild — an interrupted run empties the table | Step now mandates a snapshot first and describes the real behaviour |
| 3 | `T1` step 4 | Omitted `--lookback-years`; the default of 5 **silently discarded half the history** (66,597 rows from 2021 vs the incumbent's 10-year 134,520) | Step now mandates `--lookback-years 10` and checking the **min** timestamp, not just the count |
| 4 | `T1` validation | Referenced `src/layer0/tests/`, which did not exist; and `psql`, which needs an interactive password here | Tests created; validation now queries via `src.common.db` |
| 5 | `T2` step 1 | Embedded a **literal fragment of the live password** in the prompt — committing the week folder would have re-leaked the secret via the task meant to remove it | Added step 0; all greps now use `$OLD_DB_PASS` read from `.env` at runtime |
| 6 | `T2` step 1 | Non-`-F` grep let the password's regex metacharacters silently **miss the worst exposure** (the plaintext connection memo) | All inventory greps now use `-F` |
| 7 | `T4` check table | "H1 > 26h behind now" would fire **6 days out of 7** — the ingest is weekly and the market shuts on weekends | Threshold rewritten against the last market close the last scheduled ingest should cover |
| 8 | `T4` outcomes check | Coverage alone cannot detect a dead writer (the backtest replays history), so it would have passed throughout the 5-week freeze | Check now also asserts `created_at` recency |

---

## 4. What to run next, in order

1. **Read `deliverables/T3`-relevant context first:** T1's finding is that the fresh-data map
   is **the same 4 cells, same single strategy** as the incumbent, with metric deltas in the
   second decimal. T3 should expect to *confirm* the incumbent, not overturn it.
2. **Paste `T3-promote-verified-work.md`.** It will build the evidence package and stop at
   `AWAITING-SIGNOFF`. Nothing gets promoted without you typing "promote".
3. **Paste `T5-derisk-money-layer.md`** whenever there is budget — independent of everything
   else, and expected to end partially BLOCKED on VM/Computer-3 access.
4. **Paste `T6-research-strategy-engine.md`** last of the build tasks; it needs the most
   budget and builds on T1's now-repaired package.
5. **`T7-archive-v1-cleanup.md` strictly last**, only once T1–T6 are each
   DONE/BLOCKED/AWAITING-SIGNOFF.

Or simply paste `RUN-ALL.md` again — `STATE.md` records everything above and the boot sequence
will resume at T3.

---

## 5. Decisions pending from you

| Decision | Recommendation |
|---|---|
| **Champion promotion** (T3) | Not yet actionable — T3 hasn't run. When it does, the evidence will likely say "the incumbent is still right", which is a legitimate outcome. |
| **Git history rewrite** for the dead password | **Don't.** The credential no longer authenticates, so a rewrite would break every clone on all three machines to remove a risk that no longer exists. Say the word if you disagree. |
| **Daily heartbeat cron** — installed at `0 6 * * *` | Keep it. Read-only; remove with `crontab -e` if unwanted. A backup of the previous crontab was taken. |
| **Move price ingest from weekly to daily** | Worth considering. While ingest is weekly, a dead price feed can only be *proven* dead after the next missed Saturday — capping detection at ~8 days rather than 24h. |
| **`GATEKEEPER_AUTOPROMOTE`** | Untouched this session; still off, deliberately. |
| **Backup table** `fact_trade_outcomes_bak_20260729` | Leave it until T3 signs off, then drop it. |

---

## 6. Week verdict

**Yes — the system is meaningfully closer to doing what it is meant to do, on the two
foundations that matter most.**

Before this session, System 1 was training on trade results that had stopped updating five
weeks earlier, and had no way to notice; its database password was readable by anyone with a
copy of the repo; and three weeks of engineering existed only in an uncommitted working tree,
one disk failure from gone.

All three are now fixed, and — more importantly — the *class* of failure behind the first one
is addressed rather than patched. Import failures are loud, 42 tests guard the packaging, and
a daily heartbeat watches eight data flows with thresholds that reflect how the system
actually runs rather than how the spec assumed it ran.

The honest counterweight: **none of this improved the model.** Re-running the analysis on
genuinely current data produced almost exactly the incumbent's answer, and the two real
structural weaknesses are untouched — the entire live model is still one strategy
(`Range_Stochastic_Divergence`), and the High-Volatility regime still has no qualifying
strategy at all. This week bought reliable *machinery for knowing the truth*. Whether the
truth is good enough to trade is what T3 and T6 exist to establish.
