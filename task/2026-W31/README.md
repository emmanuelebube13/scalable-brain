# Week 2026-W31 (Mon 2026-07-27 → Sun 2026-08-02) — Fix Sprint

Source plan: `../2026-07-28.md`. This folder turns that plan into executable agent prompts.

## Files

| File | Task | Size | Depends on |
|------|------|------|-----------|
| `T1-reconnect-feedback-loop.md` | Fix broken trade-outcomes writer, backfill, fail-fast imports | Medium | — |
| `T2-secrets-and-env.md` | Rotate committed DB password (FIX-XC-003), `.env.example` | Small | — |
| `T3-promote-verified-work.md` | Sign off + promote leak-free champion/map, fix `beats_incumbent` ratchet | Medium | T1 (fresh outcomes make the OOS re-measure honest) |
| `T4-heartbeat-monitoring.md` | Daily freshness heartbeat for prices / outcomes / telemetry | Small | T1 (needs outcomes flowing to define "fresh") |
| `T5-derisk-money-layer.md` | VM sizing code into git; S3 unit-confusion fix package | Large | — (independent; parts blocked on VM/Computer-3 access) |
| `T6-research-strategy-engine.md` | Strategy contract + registry + research→staged→qualified pipeline (design + skeleton) | Large | T1 (builds on the repaired strategies package) |
| `RUN-ALL.md` | **The master prompt.** Paste it into a fresh LLM session to execute the whole week end-to-end | — | all |
| `STATE.md` | Progress ledger. Every agent reads it first and appends to it. Survives credit-limit interruptions | — | — |
| `deliverables/` | Created during execution. Per task: `DELIVERABLE.md` (detailed technical report), 1–2 PNG charts, `EXECUTIVE_SUMMARY.md` (1-page plain-language). Week rollup: `WEEK-EXECUTIVE-SUMMARY.md` + `week_scorecard.png`. A task is not DONE without these | — | — |

## How to use

- **One task at a time:** paste the contents of a single `T*.md` file as the prompt. The agent reads `STATE.md`, skips what's done, executes, validates, and updates `STATE.md`.
- **Everything:** paste `RUN-ALL.md`. It runs T1→T2→T3→T4→T5→T6 in dependency order, validates each, and reports.
- **After a credit-limit cutoff:** just paste the same prompt again (the task file or `RUN-ALL.md`). `STATE.md` records the last completed step; the agent resumes from there. Nothing needs to be re-explained.
- **After a failure:** the failing task file gets a `## Failure log` entry with the root cause and a corrected step written into it by the orchestrator. `RUN-ALL.md`'s final report tells you which prompt(s) to re-run and in what order.

## Ground rules baked into every task (do not remove from prompts)

1. This machine is **System 1 only**. Never run or edit `OtherSystems/system-2-execution-engine/` or `OtherSystems/system-3-account-management/` code as if it were live — they deploy on the other computers. Producing *hand-off packages* (specs, patches, test plans) for them is allowed and is exactly what T5 does.
2. The orchestrator (`src/system1/scheduler/orchestrator.py`) is the **only** champion promotion path. No new promotion paths, ever.
3. Log-only / dry-run is the default for anything promotion-capable. `--live` / `--force` only when the task explicitly says so.
4. No secrets in commits. Git commits: no Claude co-author trailer (repo convention).
5. Publish ordering is sacred: upload → SHA256 verify → pointer flip last.
