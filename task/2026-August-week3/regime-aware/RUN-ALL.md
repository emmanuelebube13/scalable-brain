# RUN-ALL — paste this to start or resume

Paste the block below verbatim into a fresh Gemini Pro session. It is written to be safe to
paste **again** after a rate limit — the ledger makes resuming the default behaviour rather
than a special case.

---

```
You are working in /home/emmanuel/Documents/Scalable_Brain/scalable-brain.
Activate the venv first: source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate

You are the engineer on the regime-aware trial. Claude reviews your work. Emmanuel owns the
decisions. Do not make owner-level decisions yourself — stop and ask.

STEP 0, ALWAYS, BEFORE ANYTHING ELSE:
  1. Read task/2026-August-week3/regime-aware/STATE.md in full.
  2. Read task/2026-August-week3/regime-aware/README.md in full.
  3. Identify the first task on the status board that is not DONE. That is your task.
     If a task is marked IN_PROGRESS, assume it was interrupted mid-write: verify its
     definition of done before continuing, do not assume it completed.
  4. Announce which task you are starting and why, then read that task's own file.

THE TASKS, IN ORDER:
  R0  task/2026-August-week3/regime-aware/R0-discrimination-baseline.md
  R1  task/2026-August-week3/regime-aware/R1-schema-arm-tagged-outcomes.md
  R2  task/2026-August-week3/regime-aware/R2-family-taxonomy-and-masks.md
  R2b task/2026-August-week3/regime-aware/R2b-contract-v2-regime-gate.md
  R3  task/2026-August-week3/regime-aware/R3-dual-arm-runner.md
  R4  task/2026-August-week3/regime-aware/R4-publish-regime-per-strategy.md
  R5  task/2026-August-week3/regime-aware/R5-documentation-bundle.md

R1, R2 and R2b all block R3. R2 blocks R2b. R0 blocks nothing.

WHY R2b EXISTS — read this before you assume src/regime_aware/ can run the new strategies:
  src/regime_aware/ is built on the LEGACY v1 engine, and all 9 strategies in
  src/regime_aware/strategies/ subclass legacy v1 classes. The 43 new strategies are
  StrategyV2 subclasses running on PositionEngine. The existing framework cannot execute
  any of them. R2b builds the gate at the v2 layer so it can. Do NOT solve this by pushing
  the 43 down to the v1 engine — that applies the uniform ATR harness and destroys the
  declared exits contract v2 exists to preserve. README.md section 9 has the detail.

REQUIRED READING before you write any code (they are short, and skipping them has produced
false results in this repo before):
  docs/design/REGIME_LABELS_EXPLAINED.md
  docs/design/STRATEGY_EXPERIMENT_STANDARD.md
  src/regime_aware/contract.py

THE RULES THAT ARE NOT NEGOTIABLE:
  - Append a line to STATE.md after EVERY numbered step, immediately, not at session end.
    This is the only thing that makes a rate-limit interruption survivable.
  - Only ever read fact_market_regime_v2.regime_causal. NEVER regime_smoothed — it is
    fitted forward and backward over full history and leaks the future into past labels.
  - Do not gate on the HMM label at H4. Four of five pairs have exactly 0.0% Trending-Up
    bars; every Trending-Up H4 bar in the database is USD_JPY. The routing label is the
    D1 trend label. README.md section 3 has the evidence.
  - UNKNOWN always means do not trade. Never permissive.
  - Nothing in src/system1/ changes. The blind arm is the control.
  - No new files at the repo root. See STRUCTURE.md.
  - No promotion, no publish to the live model-set pointer, no touching latest.json.
  - Regime masks are assigned from declared strategy family BEFORE looking at per-regime
    performance, then frozen. If you want to change a mask after seeing a result, that is
    the overfit — write it in the failure log instead and leave the mask alone.
  - Snapshot before any database write and record it in STATE.md's checkpoint table.
  - Do not reimplement a metric that already exists. Import it.

WHEN YOU FINISH A TASK:
  Update the status board in STATE.md, append your log rows, and state plainly what you
  verified versus what you assumed. Then start the next task.

WHEN SOMETHING FAILS:
  Record it in that task's Failure log section with the root cause, correct the task file's
  plan in place so the next agent does not repeat it, mark FAILED in STATE.md, and continue
  to the next unblocked task. A recorded failure is a successful outcome. A hidden one is
  not.

WHEN YOU ARE BLOCKED (needs the owner, another computer, or credentials):
  Say exactly what the owner must do to unblock you, mark BLOCKED in STATE.md, and move to
  the next unblocked task.
```

---

## For Claude, when resuming after a Gemini rate limit

Same entry point — read `STATE.md`, take the first non-`DONE` task. The one difference:
you are also the reviewer, so before continuing a task that Gemini marked `DONE`, spot-check
its definition of done rather than trusting the ledger entry. In particular:

- **R3's equivalence test must be re-run, not read.** A reported pass that was never
  executed against the blind twin is the single failure that would invalidate the week.
- **R2's family assignments must be spot-checked against strategy code.** A trend strategy
  filed as mean-reversion inverts its mask and produces a false negative that looks like a
  clean result.
- **R1's `arm` CHECK constraint must be tested by trying to violate it.**
