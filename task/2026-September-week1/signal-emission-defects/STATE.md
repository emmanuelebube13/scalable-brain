# SIGNAL-EMISSION-DEFECTS — state

Resume file for `PROMPT.md` in this folder. **Read that first.**
Tick a box only after the step is verified **and** committed.

**Register:** O-23 (D6), O-24 (D7), O-25 (D8) in `task/OPEN.md`.

## Checklist

- [ ] S1 — Read `GOVERNANCE.md`, `CLAUDE.md` §AGENT RULES, `docs/proposed-fixes/system-1/`,
      `task/OPEN.md` (O-16/17/19/20/21/22). Confirm none of D6/D7/D8 is already covered.
      Create a branch.
- [ ] S2 — **Reproduce D6, no writes.** Replay the two USD_JPY rows; confirm causes (a), (b),
      (c) independently → `FINDINGS-D6.md`. Adversarial pass: `devils-advocate`.
- [ ] S3 — **BLOCKED ON OWNER.** Is re-affirmation of a still-current signal ever wanted?
- [ ] S4 — Implement D6: (c) first, then (a), then (b). Tests on **both** queue backends.
- [ ] S5 — **Investigate D7, no writes.** Reproduce strategy 30 at `2026-09-01T13:00:00Z`
      → `FINDINGS-D7.md`. Agents: `forex-strategist`, `leakage-hunter`.
- [ ] S6 — **BLOCKED ON OWNER.** Should System 1 refuse to emit a bad-R:R signal?
- [ ] S7 — Implement D7 per the decision.
- [ ] S8 — D8 index: settle O-19 retention + System 2's LIST answer, design, dry-run, implement.
      Agent: `release-guard`.
- [ ] S9 — Full suite + `black` + `mypy`. Distinguish your reds from the standing reds in
      `docs/critical/REPO_STATE.md`.
- [ ] S10 — `close-a-task` skill. Update `OPEN.md`, `REPO_STATE.md` if state changed, write
      `DELIVERABLE.md`. Agents: `auditor`, `structure-warden`.

## Blocking questions — answer before S4 and S7

| # | Question | Blocks | Answer |
|---|---|---|---|
| Q1 | Is re-affirming a still-current signal ever **wanted**? If yes, the fix is not suppression — a restatement must recompute stop and target and be marked as a restatement on the wire. | S4 | *unanswered* |
| Q2 | Should System 1 **refuse** to emit a bad-R:R signal, or compute and publish R:R and let System 3 decide? A refusal is a new enforcing live gate. | S7 | *unanswered* |
| Q3 | (External, System 2) Did **any** of the nine `signal_id`s reach their subscription? See `PROMPT-S2-3-D4-*` Q2. | priority of D6 | *unanswered* |
| Q4 | (External, System 2) Have they already built the prefix-LIST path against `telemetry/signals/`? | S8 design | *unanswered* |

**Q3 is the highest-leverage unknown.** If nothing is reaching System 2, suppressing duplicates
on a wire that delivers nothing is not the problem worth solving first.

## Log

- 2026-09-03 — Folder opened, brief written (Claude). **No code changed yet.** All evidence in
  `PROMPT.md` §4 was measured 2026-09-03 00:43–00:51Z from `results/signals/*.ndjson`,
  `results/state/*.json` and a live read of `telemetry/s1_health.json`. **Re-verify before
  acting** — the ledger grows hourly and the offsets in §D8 will have moved.
