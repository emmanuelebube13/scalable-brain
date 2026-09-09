# START HERE — Work Order 02

**You are the implementing agent for this work order.** Everything you need is in this folder.
Nothing here is optional and nothing here is a suggestion.

Repo: `/home/emmanuel/Documents/Scalable_Brain/scalable-brain`
Venv: `/home/emmanuel/Documents/Scalable_Brain/.venv` (outside the repo — do not move it)

---

## 1. Read these three files, in this order, before writing any code

| # | file | what it gives you |
|---|---|---|
| 1 | `ARCHITECTURE.md` (this folder) | the design, the measurements it rests on, and the three owner decisions — **all now answered, §9** |
| 2 | `WORK-ORDER.md` (this folder) | stages A–F, each with outcomes, constraints and a definition of done |
| 3 | `/audit/reports/work_order_01.md` | what was fixed on 2026-09-07, and one live defect you must not re-break |

Then skim `CLAUDE.md` at the repo root for the standing rules, and `GOVERNANCE.md` for the output
standard you will be held to.

**Do not start from this README alone.** It tells you how to begin; the other files tell you what
to build and why.

---

## 2. The decisions are made — do not re-litigate them

| decision | answer |
|---|---|
| Volatility z-score window | **Scales to constant wall-clock.** ~1 year everywhere: D1 **252**, H4 **1,512**, H1 **6,048** bars |
| ADX(14) and 50/200 EMAs | **Do not scale.** Unchanged at every granularity — and document *why* in code, or the next reader will "fix" it |
| `AUTHORITATIVE_ENGINE_FOR_VETTING` | **`position_engine_v2`** — set it in Stage C, not before |
| `LABELLER_VERSION` | becomes **`structural-v2.0.0`** |
| Granularities to label | **D1, H4, H1** — exactly the ones strategies trade. Not M30/M15/W1 |

If you believe one of these is wrong, **say so in your report and build it as specified anyway.**
Scaling the work down is the owner's call, not yours.

---

## 3. How to work

**Stage by stage. Stop at each definition of done.** Do not run ahead. A stage is complete when
its outcomes are true, its review gate has run, and its findings are fixed or explicitly answered.

**Stages A and B are unblocked and can start now.**
Stage C is blocked until A and B are done. D on C. E on D. F is owner-gated.

### Invoke the agents — this is mandatory

Six read-only specialists are installed at `.agents/agents/{name}/agent.md`:

```
leakage-hunter   measurement-reviewer   forex-strategist
db-guardian      devils-advocate        release-guard
```

They can read and run commands. **They cannot write — deliberately.** You do the building; they
review; you fix what they raise. A reviewer that edits the code it reviews is not a reviewer.

| after stage | invoke |
|---|---|
| A | `leakage-hunter`, `db-guardian` |
| B | `leakage-hunter` |
| C | `measurement-reviewer`, `forex-strategist` |
| D | `devils-advocate` — **before any map goes live, no exceptions** |
| E | `measurement-reviewer` |
| F | `release-guard` |

**If a gate returns `CONFIRMED` leakage, `DEFINITIVELY BROKEN`, `NOT SUPPORTED`, or
`PUBLISH BLOCKED` — stop and report.** Do not proceed and do not work around the finding.

`db-guardian` after Stage A is the one to take most seriously. The highest-risk defect in this
work order is a query that filters on `(asset_id, bar_time_utc)` without `granularity` — it used
to return one row and will now return three, picking arbitrarily.

---

## 4. Hard constraints

- **Do not merge `SELECTION_SOURCE_LABEL` and `ROUTING_SOURCE_LABEL`.** They look duplicated. They
  are independent on purpose so the admissibility check can compare them. Merging deletes a safety
  property and re-authorises the 2026-08-24 defect.
- **Do not change any guard threshold** — including the 54h D1 staleness window and
  `MAP_MAX_AGE_DAYS`. If your analysis says one is wrong, report it and leave it alone.
- **Do not retire the HMM, remove `hmm_model.joblib`, or touch the promotion gates.** Separate
  work order. It still gates promotion and still ships.
- **Do not run `designate.py`.** Do not set `REGIME_MAP_WRITES_FROZEN`, `GATEKEEPER_AUTOPROMOTE`
  or `MODEL_SET_AUTOPUBLISH`. Do not call `--withdraw`.
- **Do not hand-edit anything under `results/`, `models/`, `model-artifacts/`.** If the output is
  wrong, the run is wrong — editing the file hides the defect and the next run reverts it.
- **Dry-run is the default** for anything that promotes or publishes.
- Nothing new at the repo root. `STRUCTURE.md` is the map and the root is closed.

---

## 5. Standing rules you will be judged against

- **Claims carry their evidence inline.** Verification means running it, not reading a docstring.
- **State what you did not check.** A clean report on three of five call sites is not clean.
- **An empty map is a legitimate finding.** Do not lower a gate or add a designation to avoid one.
- **Report failures faithfully.** If tests fail, say so with the output. If a stage is skipped,
  say that.

---

## 6. Deliverables

### 6.1 The report — `audit/reports/work_order_02.md`

Follow the "Report" section of `WORK-ORDER.md` exactly. It specifies seven items that must be
**query output, not prose**. Do not summarise the architecture back — it is already written.

### 6.2 A summary for review — `task/2026-September-week2/regime-multi-timeframe/SUMMARY.md`

Short. One page. Written for someone who has not been following:

1. **What changed** — files touched, one line each
2. **What is now true that was not before** — with the numbers
3. **What broke, and what you did about it**
4. **What each agent found**, and whether it is fixed or answered
5. **What you could not do, and why**
6. **What you did not check**
7. **The single thing you would want checked before this goes live**

### 6.3 A drafted, unsent System 2/3 notice (Stage F only)

Use the `write-comms` skill. `docs/comms/` is append-only in spirit — **a drafted message is not a
sent one.** Do not send it.

---

## 7. If you get stuck

- **A decision you were not given** — stop and ask. Do not default.
- **A constraint conflicts with an outcome** — stop and report the conflict. Do not choose.
- **Something urgent surfaces that is out of scope** — report it, do not act on it. Log it in
  `issues/September-Week-2/<date>.md`.

Do everything that does not depend on the answer first, then ask.

---

## 8. Current state, so you are not surprised

- The system is **not trading.** One blocker: the live map expired 2026-08-24 (14+ days, limit 7).
- The structural label refreshes automatically before every signal attempt, and the producer
  refuses if labelling fails. That landed 2026-09-07 and is working — do not undo it.
- The last emitted signal was 2026-09-04T21:15Z.
- One test is red and it is **not yours**:
  `test_designate_and_schema.py::test_cli_dry_run_writes_nothing`, stale against the
  `attribute.POOLED` warning. Leave it; note it if you touch that area.
- 17,583 orphaned rows in `fact_trade_outcomes` (strategies 7, 8, 9) still feed attribution.
  Removal is destructive and owner-gated. **Do not run `--reconcile`.** Flag that the rebuild
  inherits them.

**Getting the system trading again is the point of this work order.** But not at the cost of
shipping a map you cannot defend. If the honest answer at the end is "zero qualifying cells,"
that is the result — report it and stop.
