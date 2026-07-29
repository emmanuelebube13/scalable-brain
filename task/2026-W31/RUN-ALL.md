# RUN-ALL — Week 2026-W31 End-to-End Orchestrator

> **This is the master prompt. Paste this entire file into a fresh Claude Code session at
> `/home/emmanuel/Documents/Scalable_Brain/scalable-brain` and it will execute the whole week.**
> It is safe to paste repeatedly: state lives in `task/2026-W31/STATE.md` and every run resumes
> from where the last one stopped.

## Your role

You are the week's engineering lead. You will execute tasks T1–T6 in `task/2026-W31/` in
dependency order, deploying specialized subagent teams per task exactly as each task file
specifies, validating every task with its own validation section, and maintaining the state
ledger so any interruption (credit limit, crash, user stop) is resumable by re-pasting this
same prompt.

## Boot sequence (always, every run)

1. Read `task/2026-W31/STATE.md` in full. Note every DONE step and every BLOCKED item.
2. Read `task/2026-W31/README.md` ground rules. They override convenience at all times.
3. `git -C /home/emmanuel/Documents/Scalable_Brain/scalable-brain status` — if the tree has
   unexpected changes not explained by STATE.md, STOP and report before touching anything.
4. Announce (one short paragraph): what is already done, what you will run this session, and
   in what order.

## Execution order and gating

```
T1 (feedback loop)  ──►  T3 (promote)   ──►  T6 (research engine)  ─┐
T2 (secrets)        ──►  T4 (heartbeat)                             ├──►  T7 (archive v1 cleanup — strictly LAST)
T5 (money layer)    — independent, run any time; partially BLOCKED ─┘
```

Rules:
- Run **T1 first** unless already DONE. T2 may run in the same session after T1 (small).
- T3 only when T1 is DONE. T3 step 5 (promotion) **requires explicit user confirmation** —
  if the user is not present, complete through step 4 (evidence package), mark T3
  `AWAITING-SIGNOFF` in STATE.md, and continue with other tasks.
- T4 after T1 (or run with the outcomes check marked KNOWN-STALE if T1 is blocked).
- T5 whenever there is budget; BLOCKED items in it do not block anything else.
- T6 after the above — it needs the most budget and depends on T1's package repair.
- **T7 strictly last** (added 2026-07-29): the archive-and-zip sweep of v1/unused files.
  Start it only when T1–T6 are each DONE / BLOCKED / AWAITING-SIGNOFF, the tree is clean,
  and `results/state/retrain.lock` is absent. It contains a mandatory user checkpoint
  (manifest review) before any file moves — respect it even when running autonomously:
  produce the manifest, mark T7 `AWAITING-SIGNOFF`, and stop there if the user is absent.
- Within a task, follow that task file's agent-team section: spawn the agents it names
  (Explore for read-only recon, Plan for design, general-purpose for implementation),
  sequential where it says sequential.

## Per-task loop (repeat for each task)

1. Open the task file. Skip steps STATE.md marks DONE.
2. Execute remaining steps via the specified agents.
3. Run the task's **Validation** section verbatim. Then its **Live run check** if present.
4. Produce the task's **Deliverables** section in full — `DELIVERABLE.md`, the named PNG
   visuals (matplotlib, `Agg` backend, saved to `task/2026-W31/deliverables/<task>/`), and
   `EXECUTIVE_SUMMARY.md`. **A task without its deliverables is not DONE**, even if all
   validation passed. Charts use real measured data from the task's own runs — never
   illustrative/fabricated numbers; if a number isn't measurable, say so on the chart.
5. **PASS:** tick the acceptance boxes in the task file, set the task DONE in STATE.md
   (status board + log lines), commit the work in small logical commits (no co-author
   trailer), move to the next task.
6. **FAIL:** do not silently retry more than once. Diagnose the root cause, then:
   a. Append to the task file's `## Failure log`: timestamp, failing check, root cause,
      evidence (the actual error output).
   b. **Edit the task file's execution plan in place** — correct the wrong instruction or
      insert the missing step, marked `[REVISED <date>: <why>]`, so the next run of that
      prompt does the right thing.
   c. Update STATE.md (status FAILED, note).
   d. If the failure blocks dependents, mark them BLOCKED in STATE.md with the reason.
   e. Continue with independent tasks.
7. **BLOCKED (needs user / VM / other computer):** record the exact unblocking action in
   STATE.md, continue with other tasks.

## Budget & interruption protocol (credit limits)

- Update STATE.md **after every step**, not at session end. Treat every tool call as
  potentially your last.
- Before starting any Large task (T5, T6), append a `CHECKPOINT` line to STATE.md naming
  the next step, so a cut-off mid-task resumes cleanly.
- Record non-obvious discoveries in STATE.md → Knowledge notes the moment you learn them
  (file paths found, thresholds chosen, access methods, decisions taken) — the next session
  must not have to re-derive them.
- If you notice you are re-doing work a previous session already did, stop, re-read
  STATE.md and the git log, and reconcile before continuing.

## Week executive rollup (when all runnable tasks are DONE/BLOCKED/AWAITING-SIGNOFF)

Write `task/2026-W31/deliverables/WEEK-EXECUTIVE-SUMMARY.md` — max 2 pages, for the system
owner, synthesized from the per-task `EXECUTIVE_SUMMARY.md` files (T1–T7):

- One paragraph per task: what was done and what is now true (link its DELIVERABLE.md and
  embed/reference its charts by relative path).
- Plus **one week-level visual**: `deliverables/week_scorecard.png` — a single chart scoring
  the week's five first-principles (feedback loop live / truth promoted / secrets rotated /
  failures loud / money layer unit-correct) as done, partial, or pending.
- Close with: the remaining risks, the pending user decisions, and the recommended focus
  for next week (2026-W32).

## Final report (end of every session, even interrupted ones)

Write `task/2026-W31/RUN-REPORT-<date>.md` and print its contents:

1. **Status board** — each task: DONE / PARTIAL (last step) / FAILED (why) / BLOCKED (what
   unblocks) / AWAITING-SIGNOFF / NOT-STARTED — and whether its deliverables
   (DELIVERABLE.md + charts + EXECUTIVE_SUMMARY.md) exist.
2. **Failures** — for each: root cause, what was corrected in which prompt file.
3. **What to run next, in order** — the exact list the user needs, e.g.:
   - "1. Do the VM capture command in STATE.md, then paste `T5-derisk-money-layer.md`"
   - "2. Review `T3-signoff-evidence.md`, reply 'promote', then paste `T3-promote-verified-work.md`"
   - "3. Paste `RUN-ALL.md` again to continue T6 from step 4."
4. **User decisions pending** — promotion sign-off, AUTOPROMOTE, history rewrite, crontab
   installs — each with a one-line recommendation.
5. **Week verdict** — one paragraph: is the system closer to "doing what it's meant to do"
   (feedback loop live, truth promoted, money layer unit-correct, failures loud)?

## Hard boundaries (repeated because they matter)

- Promotion of the live champion happens ONLY via the System-1 orchestrator and ONLY after
  the user says "promote". Never weaken a gate to make a promotion pass.
- Never run/edit `OtherSystems/system-2-*` or `system-3-*` as live systems from this
  machine; T5 produces hand-off packages only.
- Never commit secrets; never roll back to the leaked DB password; no git history rewrite
  without explicit user sign-off.
- A validation that fails on honest data is a finding to report, not an obstacle to route
  around.

Begin with the boot sequence now.
