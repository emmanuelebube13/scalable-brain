# 2026-September-week2 — Mon 7 – Sun 13 Sep

**Agents start here.** Every work order active this week is indexed below, with its ordering and
what blocks it. Do not begin a work order without reading the one it depends on.

Theme: the structural regime becomes the system's single regime, at every timeframe strategies
trade on — and the system starts trading again.

---

## Status

| WO | folder | what | state | blocked by |
|---|---|---|---|---|
| 01 | — | Restore the structural writer; cost of a map rebuild | **Complete** | — |
| 02 | `regime-multi-timeframe/` | Structural at every granularity; flip selection | **Complete, conclusion corrected** | — |
| 03 | `regime-multi-timeframe/` | De-seasonalise intraday vol; measure honestly | **Complete — stopped at Stage D by a verdict since OVERTURNED** | — |
| 03B | `regime-multi-timeframe/` | Resume WO-03, take the map LIVE | **Complete — model set published 2026-09-09T04:09Z.** Reviewed: `audit/reports/work_order_03b_review.md` | — |
| 04 | `gatekeeper-degeneracy/` | Why the gatekeeper is a strategy lookup table | **ACTIVE — start here. Both phases now unblocked** | nothing |
| 05 | `holdout/` | A never-touched holdout period | **Queued** | WO-03, WO-04 Phase 1 |

## Ordering

```
NOW    WO-03  de-seasonalise → rebuild → map → TRADING
       ‖
       ‖  WO-04 Phase 1   diagnosis only, read-only, no shared files
       ↓
NEXT   WO-04 Phase 2   the gatekeeper fix, on settled labels
       ↓
LAST   WO-05  holdout — changes how the system decides; must not ride inside another change
```

WO-04 Phase 1 is parallel-safe **only** because WO-03 §4b(i) removes the shared dependency: the
gatekeeper stops recomputing labels and reads `fact_regime_structural` instead. Until that lands,
Phase 1 must stay read-only and must not train a model to disk.

---

## Read in this order

| # | file | why |
|---|---|---|
| 1 | `regime-multi-timeframe/ARCHITECTURE.md` | the design, the measurements, the three owner decisions (§9, all answered) |
| 2 | `audit/reports/work_order_02_review.md` | **corrects three findings in WO-02's summary.** Read before believing that summary. Reports live in `audit/reports/`, not here — `REPORTS.md` in this folder indexes them all |
| 3 | the work order you are assigned | |
| 4 | `audit/reports/work_order_01.md` | what was fixed 2026-09-07, and one live defect not to re-break |

Supporting: `docs/design/HOLDOUT_PROPOSAL.md` (rationale and numbers behind WO-05).

---

## Agents

Eight specialists live at `.agents/agents/{name}/agent.md` (workspace scope):

```
leakage-hunter   measurement-reviewer   forex-strategist   db-guardian
devils-advocate  release-guard          structure-warden   auditor
```

Seven are **read-only** — they read, they run commands, they cannot write. You build, they
review, you fix. `structure-warden` is the single exception and its write access is narrowly
scoped to moving files and repairing references; it never edits logic.

**Running the gates is mandatory.** Each work order names which one runs after which stage.

### Which agent, when, and why

| invoke | when | because |
|---|---|---|
| **`structure-warden`** | **BEFORE creating any file** (advisory) | Ask it where the file goes. A file placed right costs nothing; a file moved later risks every reference to it. |
| `leakage-hunter` | after touching labels, features, joins, folds | Look-ahead is this repo's most repeated defect. A coarse label joined to a fine bar is leakage if that bar has not closed. |
| `db-guardian` | after any schema change, write, or new join | A query missing `granularity` used to return one row and now returns three, arbitrarily. |
| `measurement-reviewer` | before writing any number into a report | Coverage is not quality; agreement is not accuracy; a cell passing on 5 trades is an artifact. |
| `forex-strategist` | after changing a rule, window, or regime definition | Code can be correct and still assert something no trader would defend. |
| `devils-advocate` | before anything goes live | Writes the post-mortem in advance, while it is still cheap to hear. |
| `release-guard` | before any publish or pointer flip | A bad publish lands on hardware you cannot reach. |
| **`structure-warden`** | **AFTER the work** (sweep) | Scans root and folders, relocates what is misplaced, updates references, **proves the suite still passes.** |
| **`auditor`** | **LAST** | Verifies every deliverable exists and every claim is supported — on a repo already in its final shape. |

### Ordering at the end of a work order — this matters

```
   … implementation + per-stage gates …
            ↓
   structure-warden  (sweep: place files, fix references, run the suite)
            ↓
   auditor           (verify deliverables and claims)
            ↓
   report to owner
```

**`structure-warden` runs second-to-last, never last.** If it ran after the audit, the auditor
would have verified a layout that then changed underneath it. If it ran first, it would be
sweeping files the work had not created yet.

**`auditor` is genuinely last.** It audits the repo in the shape it will be handed over in.

### File placement is continuous, not a cleanup step

Do not leave placement to the sweep. **Every file you create goes in its correct location at the
moment you create it** — `STRUCTURE.md` is the map, and `structure-warden` will tell you if you
are unsure. The end-of-work sweep is a safety net for what slipped through, not the plan.

The root is a fixed allowlist. Nothing new goes there. It reached 24 entries once because that was
not written down, and six `scratch*.py` files are sitting there in violation right now.

### How to run a gate — two ways, and either satisfies the requirement

**1. As a subagent, if your harness supports it.** These files use the workspace agent path, so
they should appear in your available-agents list. Invoke the named agent and give it the stage's
diff and the relevant work order section.

**2. If you cannot spawn subagents — read the file and apply it yourself.** Each agent file is a
complete, self-contained review checklist: what to grep for, what the repo's past defects were,
what verdicts to return. `Read .agents/agents/leakage-hunter/agent.md` and work through it
against your own change.

**The second route is not a lesser option** — the checks are what matter, not the mechanism. But
if you take it, **say so explicitly in your report**: "applied `leakage-hunter` manually, not as a
subagent." A gate silently skipped is worse than one openly done by hand, because only one of
those is visible to the owner.

The one thing you must not do either way is review your own work as though a gate had run.

A `CONFIRMED` leakage, `DEFINITIVELY BROKEN`, `NOT SUPPORTED` or `PUBLISH BLOCKED` verdict stops
the stage. Do not work around a finding.

Three further agents are Claude-Code-format under `.claude/agents/` (`structure-warden`,
`auditor`, `comms-liaison`). Same rule: invoke if you can, apply by hand if you cannot, say which.

---

## Decisions already made — do not re-litigate

| decision | answer | where |
|---|---|---|
| Volatility window | constant wall-clock: D1 252 · H4 1,512 · H1 6,048 | ARCH §9 |
| Volatility baseline | **per time-of-day slot** (252 obs per slot at every granularity) | WO-03 §2 |
| ADX(14), 50/200 EMAs | unchanged, and document the asymmetry in code | ARCH §9 |
| Engine for vetting | `position_engine_v2` | ARCH §9 |
| Structural regime | **kept and fixed**, not abandoned | WO-03 |
| Holdout cut | 2023-01-01, **in addition to** OOS, not replacing it | WO-05 |
| HMM retirement | deferred, separate work order | ARCH §7 |
| Low-Vol regime / renaming | deferred by owner | ARCH §7 |

If you believe one is wrong, **say so in your report and build it as specified anyway.** Scaling
the work down is the owner's call.

---

## Hard constraints, all work orders

- **Do not change any guard threshold** — the 54h D1 window, `MAP_MAX_AGE_DAYS`,
  `MAX_DEGENERATE_CELL_SHARE`, the vetting gates. If one looks wrong, report it and leave it.
- **Do not merge `SELECTION_SOURCE_LABEL` and `ROUTING_SOURCE_LABEL`.** Independent on purpose so
  the admissibility check can compare them.
- **Do not retire the HMM** or remove `hmm_model.joblib`.
- **Do not run `designate.py`, `--reconcile`, or `--withdraw`.** Do not set
  `REGIME_MAP_WRITES_FROZEN`, `GATEKEEPER_AUTOPROMOTE`, `MODEL_SET_AUTOPUBLISH`.
- **Do not hand-edit** anything under `results/`, `models/`, `model-artifacts/`.
- Dry-run is the default for anything that promotes or publishes.
- Nothing new at the repo root.

## Standing rules

- Claims carry their evidence inline. Verification means running it, not reading a docstring.
- **State what you did not check.**
- An empty map is a legitimate finding. Do not lower a gate or add a designation to avoid one.
- If a constraint conflicts with an outcome, stop and report — do not choose.
- Report failures faithfully, with the output.

---

## Before starting WO-04 — three carried-forward items

1. **Commit the working tree.** The live model set was published with `code_dirty: True`, so the
   code that produced it is not in version control and cannot be rolled back to from the commit.
2. **Strategy 58 (`xard_ma_cross_daily_open`) was hotfixed by the reviewer on 2026-09-09** — WO-02
   deleted `pip = get_pip_value(pairs[0])` and never replaced it, leaving a `NameError` on the
   emit path. Now resolves per pair via `_pip_size_from_price`. Do not re-apply the old line.
   Its backtested outcomes still reflect the old geometry and should be rebuilt when convenient.
3. **Watch for the first emitted signal.** `last_signal_emitted_at` is still 2026-09-04. The
   pipeline is healthy and polling; if nothing fires within two sessions, the question is whether
   the six live cells can fire at all — a map question, not a pipeline one.

## Current state

- **Not trading.** One blocker: the live map expired 2026-08-24 (14+ days, limit 7). The
  structural-freshness blocker cleared itself on 2026-09-07 once the scheduled labeller ran.
- Last emitted signal: 2026-09-04T21:15Z.
- The gatekeeper **cannot be retrained** — the degeneracy guard refuses, correctly. It does not
  block trading: the gate is in shadow mode, and a new System 1 bundle can pair with the existing
  gatekeeper pointer.
- 17,583 orphaned rows (strategies 7/8/9) still feed attribution. Owner-gated. Flag, do not fix.
