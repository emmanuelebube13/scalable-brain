---
name: close-a-task
description: The procedure for finishing a work item — where deliverables go, updating STATE.md and task/OPEN.md, the six-point definition of done, and the adversarial pass. Use when completing a task, writing up a result, or deciding whether something is actually finished.
---

# Closing a work item

A task is closed when it is **done and recorded**, in that order. Recording it without the
first is how this repo accumulated results that looked finished and were not.

## Where things go

| Thing | Home |
|---|---|
| The open register | `task/OPEN.md` — **update in place. Do not start a competing list** |
| Raised, not started | `task/backlog/<slug>.md` |
| Active work this week | `task/<YYYY>-<Month>-week<N>/` |
| Deliverables | `task/<YYYY>-<Month>-week<N>/deliverables/<item>/` |
| Resume state | `STATE.md` beside the work item |
| A reusable prompt | `task/prompts/PROMPT-<slug>.md` |
| A problem found in passing | `issues/<Month>-Week-<N>/<YYYY-MM-DD>.md` — see the `log-an-issue` skill |

Week naming: `YYYY-Monthname-weekN`, N = 1–4 by position, month = the one containing that
week's **Monday**. 27 July – 2 August is `2026-July-week4`.

**Finished week folders stay put.** They are cited by path from `docs/proposed-fixes/` and
from messages already sent to other computers. Completion is tracked in the week table in
`task/README.md`, **not** by moving directories.

## The definition of done — all six

1. **It runs**, and the output that proves it is in the record.
2. **Tests are green**, or the reds are named and shown to be pre-existing.
3. **Output landed where `STRUCTURE.md` says it goes.**
4. **Docs the change made wrong were updated in the same change set.**
5. **An adversarial pass happened**, and what it found is recorded — including "nothing".
6. **`task/OPEN.md` reflects the new state.**

Fewer than six means in flight. Saying so is not a failure; claiming six when you have four
is.

## Tests

```bash
python -m pytest src -q --ignore=src/layer0/strategies/research/tests   # ~586 tests, ~20 s
black src/ && mypy src/
```

Known-red as of 2026-08-23, pre-existing:

- 2 collection errors in `src/layer0/strategies/research/tests/` — fixtures importing strategy
  modules that do not exist. They abort the whole run, hence the `--ignore`.
- 19 failures, all stale assertions rather than broken runtime: `test_gates.py` still asserts
  the old 60-month OOS gate; `test_wave1_guards.py` pins SHA256s of files that have since
  changed legitimately; plus `attribution`, `gatekeeper`, `signals`, `common/storage` cases.

**Distinguish your reds from these.** "Tests pass" without that distinction is not a result.

## The adversarial pass

Rule 5 of `GOVERNANCE.md`: someone who did not produce the work tries to break it. Pick by
what the work was:

| The work was | Invoke |
|---|---|
| A result, a number, a conclusion | `auditor`, then `devils-advocate` |
| A strategy or measurement | `measurement-reviewer`, `forex-strategist` |
| Features, labels, backtests | `leakage-hunter` |
| A publish or promotion | `release-guard` |
| SQL or a migration | `db-guardian` |
| A change set that added files | `structure-warden` |

Record what it found in the deliverable. "Nothing found" is a result worth writing down —
next time, it is the evidence that this was already checked.

## The write-up

A deliverable states: what was asked, what was done, the commands run with their output, what
changed on disk, what was **not** covered, and what the adversarial pass found. Every claim
carries its evidence inline — the command, the run id, the artifact path.

Do not write a summary that reads as more complete than the work. Rule 4 of `GOVERNANCE.md`:
**state what you did not check.**

## Then

- Update `task/OPEN.md` in place.
- Update the week table in `task/README.md` if the week's status changed.
- If a downstream system needs to know, use the `write-comms` skill.
- If you noticed problems you are not fixing, use the `log-an-issue` skill — do not let them
  disappear into the write-up's prose.
