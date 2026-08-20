# RUN-ALL — paste this to start or resume

Paste the block below verbatim into a fresh Gemini Pro session. Safe to paste **again**
after a rate limit — the ledger makes resuming the default behaviour.

---

```
You are working in /home/emmanuel/Documents/Scalable_Brain/scalable-brain.
Activate the venv first: source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate

You are the engineer building the promotion path. Claude reviews. Emmanuel owns the
decisions. Do not make owner-level decisions yourself — stop and ask.

STEP 0, ALWAYS, BEFORE ANYTHING ELSE:
  1. Read task/2026-August-week3/promotion-path/STATE.md in full.
  2. Read task/2026-August-week3/promotion-path/README.md in full.
  3. Take the first task on the status board that is not DONE. If one is IN_PROGRESS,
     assume it was interrupted mid-write: verify its definition of done before continuing.
  4. Announce which task you are starting and why, then read that task's file.

THE TASKS:
  P0  P0-unified-strategy-registry.md        every strategy, one view, stable integer ids
  P1  P1-v2-outcome-persistence.md           all strategies' trades into fact_trade_outcomes
  P2  P2-attribution-and-vetting-all.md      attribution + vetting over the whole universe
  P3  P3-selection-basis-and-map-schema.md   qualified vs designated; direction + exits
  P4  P4-gatekeeper-cold-start.md            a strategy with no history (independent)
  P5  P5-live-signal-producer.md             THE MISSING LINK — nothing trades without it
  P6  P6-transport-and-withdrawal-drill.md   Pub/Sub + a rehearsed undo

  P0 -> P1 -> P2 -> P3 -> P5.  P4 is independent.  P6 needs P5 to be meaningful.

WHAT YOU ARE BUILDING, IN ONE SENTENCE:
  One governed door through which ANY strategy — the 10 legacy, the 43 v2 research, the 9
  regime-aware ports — can reach a published model set, plus the producer that turns that
  model set into signals System 2 can actually execute.

THE RULES THAT ARE NOT NEGOTIABLE:
  - Append to STATE.md after EVERY numbered step, immediately. Not at session end.
  - NEVER record an owner sign-off that did not happen. This was done once already. Every
    other control in this system assumes the ledger is true.
  - DO NOT modify src/system1/vetting/gates.py. No new thresholds, no soft mode, no
    configurability. The owner will publish a strategy that fails the gates; that is what
    selection_basis="designated" is for. Weakening a gate silently re-labels all history.
  - "qualified" is earned by passing the gates and by nothing else. "designated" requires a
    human name, a human reason, and the list of gate failures read from gates.py.
  - Range_Stochastic_Divergence (id 10) stays in INTEGRITY_DISQUALIFIED and can never be
    designated. A look-ahead defect is not a performance shortfall.
  - Legacy strategy ids 1..10 never change. 55,756 rows reference them.
  - is_oos / fold_id come from src/system1/validation/walk_forward.py — that module, never
    a reimplementation.
  - Only ever read fact_market_regime_v2.regime_causal. NEVER regime_smoothed.
  - Publish ordering: upload -> SHA256 verify -> ONLY THEN flip the pointer.
  - status and qualification_run_id stay mandatory on every published artefact.
  - Dry-run is the default on every promotion-capable command.
  - Snapshot before any database write; record it in STATE.md's checkpoint table.
  - Do not reimplement a metric that already exists. Import it.
  - Do not create billable GCP resources. Prepare the commands and mark BLOCKED.
  - No new files at the repo root. See STRUCTURE.md.

REQUIRED READING before you write code (short, and skipping them has produced false
results in this repo before):
  docs/design/systems/CONTRACT_V2_AND_POSITION_ENGINE.md  section 11
  docs/design/REGIME_STATE_AND_HOW_TO_RUN.md
  docs/design/STRATEGY_EXPERIMENT_STANDARD.md
  task/2026-August-week3/regime-aware/STATE.md            (the trial, and its null result)

WHEN YOU FINISH A TASK:
  Update the status board, append your log rows, and state plainly what you VERIFIED
  versus what you ASSUMED. Then start the next task.

WHEN SOMETHING FAILS:
  Record it in that task's Failure log with the root cause, correct the task file's plan in
  place so the next agent does not repeat it, mark FAILED in STATE.md, continue to the next
  unblocked task. A recorded failure is a successful outcome. A hidden one is not.

WHEN YOU ARE BLOCKED (needs the owner, another computer, credentials, or GCP):
  Say exactly what the owner must do, mark BLOCKED in STATE.md, move to the next task.
```

---

## For Claude, resuming after a rate limit

Same entry point. The difference: you are also the reviewer, so before continuing past a
task Gemini marked `DONE`, spot-check its definition of done rather than trusting the
ledger. Specifically:

- **P0** — query the database and confirm ids 1..10 still map to the same names. Try to
  insert a duplicate `strategy_key` and confirm it is rejected.
- **P1** — diff the legacy 10's rows against the pre-run backup table. They must be
  identical; this task adds strategies, it does not re-measure old ones.
- **P2** — `git diff src/system1/vetting/gates.py` must be empty.
- **P3** — try to create a `designated` entry with no `gate_failures`. It must fail schema
  validation, not merely be discouraged. Try to designate strategy 10; it must refuse.
- **P5** — construct a forming (unclosed) bar and confirm no signal is produced. Kill the
  runner mid-pass and restart it; confirm neither duplication nor a skipped bar.

The pattern across the last two weeks is that the code is usually close to right and the
*test* is weaker than the claim. Re-run the load-bearing test yourself rather than reading
that it passed.
