---
name: write-comms
description: How to write, name, place and freeze a message to Computer 2 (execution) or Computer 3 (risk gate). Use when drafting any correspondence, notice, handoff, technical spec or question for another system in docs/comms/.
---

# Writing to Computers 2 and 3

These messages **cannot be retracted**. Other repos cite them by path. `docs/comms/` is
append-only in spirit: a correction is a new file, never an edit to a sent one.

## 1. Pick the folder

```
docs/comms/
├── to_system2/       execution engine and its dashboard
├── to_system3/       account manager / risk gate
├── handoffs/         formal handoffs between agents or sessions
├── notices/          status notices to all downstream systems
├── replies/          replies received from downstream
└── technical_docs/   specs that were transmitted (e.g. API contracts)
```

Do not move a file out of `technical_docs/` once another system has cited it by path.

## 2. Name it

| Kind | Name |
|---|---|
| To one system | `TO-SYSTEM2-<YYYY-MM-DD>-<slug>.md` |
| To both | `TO-SYSTEM2-3-<YYYY-MM-DD>-<slug>.md` |
| To the dashboard | `TO-DASHBOARD-<YYYY-MM-DD>-<slug>.md` |
| A question | `ASK-<YYYY-MM-DD>-<slug>.md` |

## 3. Know your reader

The receiving operator **cannot run your commands, read your logs, or query your database.**

| System | Cares about | Does not care about |
|---|---|---|
| **System 2 — The Hand** | Model set version, artifacts, checksums, what changed, what to download, breaking contract changes | Training internals |
| **System 3 — The Guardian** | Strategy stats, risk-relevant properties, anything affecting sizing or the account state machine | Feature engineering, gate internals |

**No downstream recomputation.** S3 never re-scores, S2 never re-sizes, S1 never knows if it
is live. A message asking a downstream system to recalculate something is a design violation.

## 4. The template

```markdown
# TO SYSTEM <N> — <subject>

**From:** System 1 (Computer 1) · **Date:** <YYYY-MM-DD> · **Status:** <FYI | ACTION REQUIRED>

## What you need to do
<Empty if FYI. Otherwise: the action, and by when.>

## What happened
<Plain statement, with the run id and artifact paths.>

## Evidence
| What | Value | Source |
|---|---|---|
| … | … | artifact path / run id |

## What this does not cover
<Scope you did not check. Open questions.>

## References
<Paths in this repo. Prior messages this supersedes, explicitly.>
```

## 5. The content rules

1. **Evidence, not conclusions.** Artifact path, run id, actual numbers. "Vetting passed" is
   useless to someone who cannot see vetting.
2. **Never state a threshold you did not read from the code.** A hardcoded `< 60mo` in a
   rejection string sent a downstream agent on a real investigation into a gate that was
   working correctly.
3. **Disclose designated cells.** `selection_basis: "designated"` means an owner override of
   a **failed** gate. If the message describes the live model set, that belongs in it.
4. **Name what is uncertain.** A message that reads as complete when it is not costs the
   other operator a day.
5. **Mention standing holds** the recipient should know about — the disabled retrain cron,
   the missing `scored-signals.heartbeat` topic, a WARN heartbeat.
6. **No credentials**, not even redacted. Reference the path, never the value.

## 6. Before it is written

- Search `docs/comms/` for anything this contradicts. You cannot retract — only supersede,
  and the supersession must be explicit and named.
- Is a `contracts/*.json` change involved? Those are **read at runtime by other machines**.
  That is a cross-system change and needs its own notice with a cutover date.
- Have `comms-liaison` review the draft. Its `FREEZE RISK` check is the one that matters:
  will this read as wrong in a month, given it is permanent?

## 7. After it is sent

The file is frozen. New information goes in a new file. If a reply comes back, it goes in
`replies/`.
