# issues/ — problems found in passing

**Things spotted while doing something else, that the owner will address later.**

This is not a task tracker. It is a lightweight inbox for observations that do not yet
have a definition of done. When an issue graduates to something with a plan, open a proper
task in `task/` or a fix doc in `docs/proposed-fixes/`.

## File layout

```
issues/
└── <Month>-Week-<N>/
    └── <YYYY-MM-DD>.md     one file per day, several issues per file
```

**Append to today's file if it already exists.** Do not open a second file for the same day.
If the folder for this week does not exist, create it.

Week numbering: N = 1–4 by position in the month. The month is the one containing that
week's Monday. A week that straddles months is filed under its Monday's month.

Example: `issues/August-Week-4/2026-08-28.md`

## What goes here

- A runtime anomaly you noticed but are not fixing now
- A code smell worth revisiting
- A doc that is out of date but not urgently wrong
- Anything that needs an owner decision before it can be acted on

## What does NOT go here

- A problem you are about to fix → that is a `task/`
- A recurring known defect with a remediation plan → that is `docs/proposed-fixes/`
- A bug you have already fixed → document in the task or commit that fixed it
