# `task/prompts/` — agent prompts

**The single home for reusable agent prompts.** If you write a prompt for an agent to execute,
it goes here, named `PROMPT-<slug>.md`.

Created 2026-08-28. Before this folder existed, prompts were scattered across `task/backlog/`,
`docs/proposed-fixes/`, and individual week folders, with no way to find them.

| Put here | Do NOT put here |
|---|---|
| A prompt written to be handed to an agent, reusable or one-off | The *output* of running a prompt — that is a `task/<week>/deliverables/` record |
| Prompts not tied to a single week's work item | A prompt that is the definition of a specific week's work and lives beside its `STATE.md` — see "Prompts that stay in place" |

Name new files `PROMPT-<slug>.md`. Keep the slug specific enough to read at a glance in a
directory listing.

---

## In this folder

| Prompt | What it is |
|---|---|
| [`PROMPT-deep-cleanup-system1.md`](PROMPT-deep-cleanup-system1.md) | Full housekeeping pass on the repo: root allowlist, misplaced files, routine deletion, README refresh. Written 2026-08-28, not yet run |
| [`PROMPT-implementation-agents-system1.md`](PROMPT-implementation-agents-system1.md) | Implementation-agent briefs for the System 1 proposed fixes. Was `docs/proposed-fixes/system-1/IMPLEMENTATION_AGENT_PROMPTS.md` |
| [`PROMPT-gemini-signal-hardening.md`](PROMPT-gemini-signal-hardening.md) | Signal-path hardening brief. Was `task/backlog/` |
| [`PROMPT-gemini-telemetry-strategy-section.md`](PROMPT-gemini-telemetry-strategy-section.md) | Telemetry dashboard strategy section. Was `task/backlog/` |
| [`PROMPT-S2-D0-where-to-work.md`](PROMPT-S2-D0-where-to-work.md) | **D0 — read before D1–D4.** Two dashboard apps exist in the System 2 repo and one renders nothing; the live one is `telemetry-dashboard/src/App.tsx`. Verified by Systems 2/3 on 2026-09-03 |
| [`PROMPT-S2-D1-gate1-outcome-mix-tile.md`](PROMPT-S2-D1-gate1-outcome-mix-tile.md) | **D1** — the Gate-1 tile renders `last_run_*` under an all-time caption. Written 2026-09-03 for the System 2 repo |
| [`PROMPT-S2-D2-mock-strategy-attribution.md`](PROMPT-S2-D2-mock-strategy-attribution.md) | **D2, P0** — `Momentum_Breakout` mock names attached to real P&L in the live blotter. Third notice on this name |
| [`PROMPT-S2-D3-avg-confidence-tile.md`](PROMPT-S2-D3-avg-confidence-tile.md) | **D3** — `AVG CONFIDENCE 0.650` is not a System 1 number; real mean is 0.469 |
| [`PROMPT-S2-3-D4-candidate-stream-reconciliation.md`](PROMPT-S2-3-D4-candidate-stream-reconciliation.md) | **D4** — 4,102 Gate-2 drops against 58 signals ever published. A question, not a fix. **Its Q2 gates the other four** |
| [`PROMPT-S2-D5-duplicate-trade-intent-dedupe.md`](PROMPT-S2-D5-duplicate-trade-intent-dedupe.md) | **D5, P0** — `(signal_id, score_run_id)` will not stop a duplicate trade intent. Corrects guidance already sent |

The six `PROMPT-S2-*` files above are the hand-off set for the 2026-09-03 dashboard
reconciliation. They are written to be sent to Computers 2/3 and run there; the covering
message is `docs/comms/to_system2/TO-SYSTEM2-3-2026-09-03-dashboard-reconciliation-and-mock-data.md`,
and System 1's own three defects from the same audit are briefed in
`task/2026-September-week1/signal-emission-defects/PROMPT.md` (register: O-23, O-24, O-25).
That prompt **stays beside its work item** — it is bound to a sibling `STATE.md` and belongs in
the "Prompts that stay in place" category below.

## Prompts that stay in place

These are **deliberately not moved.** Each is either cited by path from another document — in one
case a message already sent to another computer, which `docs/comms/` treats as append-only — or is
bound to a sibling `STATE.md` / `RUN_BRIEF.md` that reads "the PROMPT.md in this folder". Moving
any of them silently breaks a live reference.

| Prompt | Why it stays |
|---|---|
| `docs/proposed-fixes/SYSTEM_AUDIT_AGENT_PROMPT.md` | Linked from `docs/proposed-fixes/README.md`; belongs with the fix register it drives |
| `task/2026-August-week3/inference-migration/PROMPT-SYSTEM1.md` | Cited by `docs/comms/technical_docs/TONIGHT-2026-08-22-restore-trading.md` (already sent) and by its sibling `STATE.md` |
| `task/2026-August-week3/ingest-mba/PROMPT.md` | Cited by its sibling `STATE.md` |
| `task/2026-September-week1/signal-emission-defects/PROMPT.md` | Cited by its sibling `STATE.md`; scoped to that week's work item (D6/D7/D8) |
| `task/2026-August-week1/fleet/upload/wave0/PROMPT.md` | Fleet wave brief, paired with that wave's `STATE.md` |
| `task/2026-August-week1/fleet/upload/wave1/PROMPT.md` | As above |
| `task/2026-August-week1/fleet/upload/wave2/PROMPT.md` | Cited by full path from `task/2026-August-week1/wave2/RUN_BRIEF.md` |

The rule going forward: **a prompt scoped to one week's work item stays beside that work item;
everything else lives here.** When in doubt, put it here and link to it.
