# Work Order 02 — Structural regime at every traded granularity, and selection flipped onto it

**To the implementing agent:** this specifies outcomes, not implementations. Choose the
mechanism yourself. Read `ARCHITECTURE.md` in this folder first — it carries the measurements
this order rests on and three owner decisions you must not make yourself.

**Do not begin any work not described here.** If a stage surfaces something urgent, report it;
do not act on it.

---

## Before you start — three things must be true

1. **`ARCHITECTURE.md` DECIDE-1 and DECIDE-2 are answered** (window scaling). Without them you
   cannot write the labeller correctly. **Stop and ask** rather than choosing a default.
2. **`attribute.AUTHORITATIVE_ENGINE_FOR_VETTING` is set** by the owner. Stage C onward is
   blocked until it is. Stages A and B can proceed without it.
3. **You have read `audit/reports/work_order_01.md`.** It records what was already fixed on
   2026-09-07 (the structural writer is scheduled and coupled to the producer) and one live
   defect you must not re-break.

---

## STAGE A — Parameterise the labeller `[no owner decision needed to start]`

### Outcomes

1. `build_structural.py` produces labels for a granularity given as a parameter, not a constant.
2. It can label **D1, H4 and H1** in one invocation, and `fact_regime_structural` holds all three.
3. Existing D1 rows are **re-derived, not preserved**, if DECIDE-1 changes the window definition.
   A row whose `labeller_version` no longer matches the code is stale evidence, not history.
4. `structural.LABELLER_VERSION` is bumped to `structural-v2.0.0` and **every** artifact that
   names a regime model version derives it from that one constant — see ARCHITECTURE §5.3.
5. The incremental/scheduled mode added on 2026-09-07 still works, per granularity, and a
   partial run (one granularity or one instrument missing) still fails loudly rather than
   reporting success.

### Constraints

- **Do not merge `SELECTION_SOURCE_LABEL` and `ROUTING_SOURCE_LABEL`.** ARCHITECTURE §5.3 says
  why. Merging them silently deletes a safety property.
- **Do not change any guard threshold**, including the 54h D1 staleness window and
  `MAP_MAX_AGE_DAYS`. If your analysis says one is wrong, report it and leave it.
- **Do not touch the regime map** in this stage.
- The table is already keyed `(asset_id, granularity, bar_time_utc)`. If you find yourself
  writing a migration, stop — you have misread the schema.

### Verify before you act

The 2026-09-07 work confirmed `load_full_history` has a start anchor and **no end bound**.
Re-confirm that holds for whatever you write: a labeller that cannot advance past a fixed date
looks like it succeeded and changes nothing.

### Definition of done

`fact_regime_structural` reports non-zero rows for D1, H4 and H1, every row carries
`labeller_version = structural-v2.0.0`, and the full test suite is green.

---

## STAGE B — Make every consumer join on granularity

### Outcomes

1. No consumer of the structural label borrows a label from a different granularity.
   ARCHITECTURE §5.2 lists the four; **verify that list is complete rather than trusting it.**
2. `REGIME_TAG_TOLERANCE_HOURS` is re-derived for own-granularity joins. A 72h tolerance on an
   H1 label reintroduces exactly the staleness this work removes.
3. `risk_off.CONTRACTS` carries a per-granularity freshness contract with a correct `bar_hours`
   for each.
4. The live signal path resolves the regime at **the granularity the signal is for**, and
   `fact_regime_structural_live` records which granularity was used.

### Constraints

- `record_live_labels` is an observer. It must never be able to block a signal. Keep it that way.
- Do not "fix" the Monday D1 staleness window (`audit/reports/work_order_01.md` §Part 1). It is a
  separate owner decision.

### Definition of done

A test proves an H1 signal is scored against an H1 label and a D1 signal against a D1 label, and
that a missing label at the signal's own granularity is a **refusal**, never a silent fallback to
a coarser one.

---

## STAGE C — Flip selection onto structural `[BLOCKED until DECIDE-3]`

### Outcomes

1. `attribute.SELECTION_SOURCE_LABEL` is `"regime_structural"`.
2. Attribution is re-run and writes a new `qualification_run_id`.
3. Every artifact it produces claims structural provenance automatically — no hardcoded string
   anywhere in the chain.

### Report as measured, not as prose

- Trades labelled vs UNKNOWN, per granularity, before and after. (Baseline: 28.2% labelled under
  the HMM; the D1-only structural projection was 100%. Report what per-granularity labels give.)
- The `regime_distribution` from the new attribution report, verbatim.
- Cell count, and how many cells changed regime assignment versus the previous run.

---

## STAGE D — Rebuild the map `[BLOCKED until Stage C and the freeze is lifted]`

### Outcomes

1. A fresh `regime_strategy_map.json` whose `source_label` matches `ROUTING_SOURCE_LABEL` and
   which is therefore admissible for routing.
2. The producer emits, or refuses for a reason that is **not** the map.

### Constraints

- `vet.py --live` is refused while `REGIME_MAP_WRITES_FROZEN` is unset. **Do not set it
  yourself.** Run log-only first, report what the map would contain, and stop for owner sign-off.
- Do not run `designate.py`.
- If the rebuilt map is **empty, report that and stop.** An empty map is a legitimate finding
  (ARCHITECTURE §8). Do not lower a gate, add a designation, or otherwise manufacture a cell.

---

## STAGE E — Retrain the gatekeeper `[BLOCKED until Stage D]`

### Why this is mandatory, not optional

The gatekeeper's `regime_structural` feature changes meaning in this work order — the window
definition changes and H1/H4 signals stop borrowing a daily label. **A champion trained on the
old feature and scoring the new one is train/serve skew.** That is the FIX-S1-016 defect class.

### Outcomes

1. A gatekeeper retrained on the new labels, with its OOS uplift measured and bootstrap-tested.
2. Its bundle claims `structural-v2.0.0`, derived, not typed.

### Constraints

- **Promotion is dry-run only.** The orchestrator is the single governed promotion path; do not
  add a second. Do not set `GATEKEEPER_AUTOPROMOTE` or `MODEL_SET_AUTOPUBLISH`.
- If OOS uplift fails its gate, **report it and stop.** Do not promote a model that failed.

---

## STAGE F — Publish and notify `[owner-gated, do not self-authorise]`

1. Publish the model set following the contract in `CLAUDE.md` — versioned prefix, SHA256
   round-trip, archive previous, **pointer flip last**. Use the `publish-model-set` skill rather
   than reconstructing the order.
2. Draft (do **not** send) a System 2/3 notice covering: `regime_model_version` changes to
   `structural-v2.0.0`; the label now exists per granularity; `regime_source` semantics; and that
   the HMM artifact is unchanged for now. Use the `write-comms` skill. `docs/comms/` is
   append-only in spirit — a drafted message is not a sent one.

---

## Report

Write `audit/reports/work_order_02.md`. Do not summarise the architecture back — it is in this
folder. Report what you found and what you did.

Required, as query output rather than prose:

1. Rows, distinct assets, min/max `bar_time_utc` and distinct labels **per granularity** in
   `fact_regime_structural`.
2. Agreement between each granularity's own label and the D1 label it previously borrowed, so the
   ARCHITECTURE §2 measurement can be checked against your build.
3. Per-granularity labelled/UNKNOWN trade counts before and after the flip.
4. Every qualifying cell in the rebuilt map: strategy, granularity, regime, OOS trades, PF,
   Sharpe, OOS months, and `selection_basis`.
5. Cell-by-cell diff against the map live at the time you started.
6. Gatekeeper OOS uplift, with its bootstrap significance, old model vs new.
7. Wall-clock time per stage.

Then, briefly:

- What did you find that is not in `ARCHITECTURE.md` and the owner should know?
- What in this work order was wrong, unclear, or based on a false assumption about the codebase?
- **What did you NOT check?**

---

## Review gates — invoke these, do not skip them

Six specialist agents are installed for this work at
`.agents/agents/{name}/agent.md` (workspace scope):

`leakage-hunter` · `measurement-reviewer` · `forex-strategist` · `db-guardian` ·
`devils-advocate` · `release-guard`

**They are read-only by design, and that is deliberate.** A reviewer that can edit the code it
reviews is not a reviewer — it becomes a second author and the independent check is lost. They
have `run_command` because this repo's standard is that verification means *running* the code,
not reading its docstring. **You do the writing. They report. You fix what they raise.**

**Invoking them is mandatory, not advisory.** A stage is not done until its gate has run and its
findings are either fixed or explicitly answered in your report.

| after stage | invoke | what it is for |
|---|---|---|
| A | `leakage-hunter` | the labeller is `shift(1)`-ed and warm-up masked; a granularity loop is an easy place to lose causality |
| A | `db-guardian` | three granularities into a composite-key table — **it will check every query is granularity-qualified, which is the highest-risk defect in this work order** |
| B | `leakage-hunter` | a join reaching to a coarser granularity is look-ahead if that coarse bar has not closed yet |
| C | `measurement-reviewer` | the coverage and distribution claims — it will insist coverage is not reported as improvement |
| C | `forex-strategist` | whether an H1 "regime" computed this way is a market state or just intraday momentum |
| D | `devils-advocate` | **before any map goes live**, without exception |
| E | `measurement-reviewer` | uplift and its bootstrap significance |
| F | `release-guard` | publish ordering, pointer levels, the two `status` fields, contract changes |

If a gate returns `PUBLISH BLOCKED`, `DEFINITIVELY BROKEN`, `CONFIRMED` leakage, or
`NOT SUPPORTED`, **stop and report.** Do not proceed to the next stage and do not work around the
finding.

Three further agents exist under `.claude/agents/` (`structure-warden`, `auditor`,
`comms-liaison`). They are Claude Code-format and may not be invocable from your harness. If you
cannot call them, apply their standards yourself and **say in your report that you did so without
the agent** — do not silently skip the check.

---

## Standing rules for this repo

- **Dry-run is the default** for anything that promotes or publishes.
- **Claims carry their evidence inline.** Verification means running it, not reading a docstring.
- **State what you did not check.**
- Never hand-edit a machine-written artifact under `results/`, `models/`, `model-artifacts/`.
  If the output is wrong, the run is wrong.
- A hold is not a fix.
- Stop at the end of each stage's definition of done. Do not run ahead into the next.
