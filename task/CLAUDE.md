# task/ — work items

**Work items only.** A definition of done makes it a task; explanation makes it a doc
(`docs/`); an observation with no plan makes it an issue (`issues/`). Full procedure: the
`close-a-task` skill. `README.md` here holds the week status table.

## The register

`task/OPEN.md` is **the** open-items list. **Update it in place. Do not start a competing
list.** It became the start-here file after the champion removal precisely because parallel
lists had drifted apart.

## Week folders never move

Naming: `YYYY-Monthname-weekN`, N = 1–4 by position, month = the one containing that week's
**Monday**. 27 July – 2 August is `2026-July-week4`.

**A finished week stays where it is.** Week folders are cited by path from
`docs/proposed-fixes/` and from messages already sent to Computers 2 and 3 — and
`docs/comms/` treats those as frozen. Moving a finished week breaks every pointer and makes a
sent message inaccurate. Completion is tracked in the week table in `README.md`, **not** by
directory layout.

Known wrinkle: these names sort alphabetically, so `August` precedes `July` in a listing. Use
the table, not the sort order.

## Prompts

Reusable agent prompts go in `task/prompts/PROMPT-<slug>.md`. **Six prompts are deliberately
not there** — each is cited by path from another document or bound to a sibling `STATE.md`.
See the "Prompts that stay in place" table in `task/prompts/README.md` before moving one.

A prompt scoped to one week's work item stays beside that work item. Everything else lives in
`task/prompts/`.

## The definition of done — all six

1. It runs, and the output that proves it is in the record.
2. Tests are green, or the reds are named and shown to be pre-existing.
3. Output landed where `STRUCTURE.md` says it goes.
4. Docs the change made wrong were updated **in the same change set**.
5. An adversarial pass happened, and what it found is recorded — including "nothing".
6. `task/OPEN.md` reflects the new state.

Fewer than six means in flight. Saying so is not a failure; claiming six when you have four
is. See `GOVERNANCE.md` §2.2.
