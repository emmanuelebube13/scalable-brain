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
| `task/2026-August-week1/fleet/upload/wave0/PROMPT.md` | Fleet wave brief, paired with that wave's `STATE.md` |
| `task/2026-August-week1/fleet/upload/wave1/PROMPT.md` | As above |
| `task/2026-August-week1/fleet/upload/wave2/PROMPT.md` | Cited by full path from `task/2026-August-week1/wave2/RUN_BRIEF.md` |

The rule going forward: **a prompt scoped to one week's work item stays beside that work item;
everything else lives here.** When in doubt, put it here and link to it.
