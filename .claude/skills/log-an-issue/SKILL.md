---
name: log-an-issue
description: How to record a problem noticed in passing — the issues/ folder layout, one file per day, and the distinction between an issue, a task, and a proposed fix. Use whenever something is spotted that will not be fixed right now.
---

# Logging a problem found in passing

`issues/` is a **lightweight inbox for observations that do not yet have a definition of
done.** It is not a task tracker.

## Which of the three is it?

| It is | If | Home |
|---|---|---|
| An **issue** | You noticed it, you are not fixing it now, it has no plan | `issues/<Month>-Week-<N>/<YYYY-MM-DD>.md` |
| A **task** | You are about to fix it, and there is a definition of done | `task/OPEN.md` or `task/backlog/<slug>.md` |
| A **proposed fix** | It is a recurring known defect with a remediation plan | `docs/proposed-fixes/system-1/FIX-S1-<NNN>.md` |

Getting this wrong is why the three registers have drifted before. When in doubt it is an
issue — that is the cheapest one to promote later.

## File layout

```
issues/
└── <Month>-Week-<N>/
    └── <YYYY-MM-DD>.md      one file per day, several issues per file
```

Week numbering: N = 1–4 by position in the month; the month is the one containing that week's
**Monday**. Example: `issues/August-Week-4/2026-08-28.md`.

**Append to today's file if it already exists. Do not open a second file for the same day.**
If the week folder does not exist, create it.

## The entry

```markdown
## <short title>

**Found while:** <what you were actually doing>
**Where:** <file:line, table, artifact path, or command>
**What:** <the observation, stated plainly>
**Evidence:** <the output, query result, or path that shows it>
**Why it matters:** <or "unclear — needs an owner decision">
**Not done:** <what you did not check about it>
```

Keep the evidence inline. An issue that says "attribution looks off" and nothing else is a
note to nobody — in a month, no one can tell whether it was real.

## Before you log it

**Check whether it is already known.** This repo has a long memory and duplicated
investigations are expensive:

- `docs/proposed-fixes/system-1/` — `FIX-S1-001…016`. Check here before "discovering" a bug;
  it may be known, fixed, or in flight.
- `issues/` — recent days.
- `CLAUDE.md` → **Standing findings** and **Troubleshooting**. Several things that look like
  defects are working as designed:
  - Producer logs "No signals generated" — usually correct; watcher staleness rejects bars
    outside market hours. D1 is 108 h **on purpose** so Monday's Friday-close bar survives.
  - Orchestrator exits `no_trigger_or_cooldown` — normal.
  - Publish aborts on checksum mismatch — working as designed; retry.
  - Pub/Sub 404 on `scored-signals.heartbeat` — known, the topic was never created.
  - D1 HMM falls back to K-Means — by design.
  - 2 collection errors + 19 test failures — pre-existing, stale assertions.

## When it is not an issue

**If the heartbeat is red and you know why, that is a hold, not an issue.** Declare it in
`results/state/cron_holds.json` with a reason, evidence, and an **expiry** — do not silence
the check. A hold suppresses the heartbeat failure while preserving the underlying
measurement.

A hold that has been silently renewed three times is an open issue wearing a disguise. If you
see one, log *that*.
