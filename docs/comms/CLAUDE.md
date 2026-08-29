# docs/comms/ — correspondence with Computers 2 and 3

**Everything here was transmitted to another machine's operator, and cannot be retracted.**
Other repos cite these files by path. Full procedure: the `write-comms` skill. Review with
the `comms-liaison` agent. `README.md` in this folder has the folder and naming tables.

## Append-only in spirit

1. **Never rewrite, move, or delete a sent message.** Its content is the permanent record of
   what was actually communicated.
2. A correction is a **new file** that explicitly names what it supersedes.
3. Do not move a file out of `technical_docs/` once another system has cited it by path.

This is not a stylistic preference. Six prompts elsewhere in the repo are pinned in place
specifically because a sent message cites them, and moving one silently makes an already-sent
message inaccurate.

## Content rules

- **Evidence, not conclusions.** The receiving operator cannot run your commands, read your
  logs, or query your database. Give the artifact path, the run id, and the actual numbers.
- **Never state a threshold you did not read from the code.** A hardcoded `< 60mo` in a
  rejection string sent a downstream agent on a real investigation into a working gate.
- **Disclose designated cells.** `selection_basis: "designated"` is an owner override of a
  **failed** gate. If the message describes the live model set, that belongs in it.
- **State what is uncertain.** A message reading as complete when it is not costs the other
  operator a day.
- **No credentials**, not even redacted. Reference the path, never the value.

## Respect the system boundaries

**No downstream recomputation.** System 3 never re-scores, System 2 never re-sizes, System 1
never knows if it is live. A message asking a downstream system to recalculate something is a
design violation, not a wording problem.

System 2 (The Hand) cares about the model set — version, artifacts, checksums, what changed.
System 3 (The Guardian) cares about strategy stats and anything affecting sizing or the
account state machine.

## Contract changes

`contracts/*.json` is **read at runtime by other machines**. Changing one is a cross-system
change and needs its own notice with an explicit cutover date — never a passing mention
inside another message.
