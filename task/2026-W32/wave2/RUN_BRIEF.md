# WAVE 2 — local run brief (read this first, then your spec)

You are **one agent in a 51-agent fleet**. Every other agent is working on a different
strategy at the same time, in the same repo. Stay strictly inside your own three files.

Repo root: `/home/emmanuel/Documents/Scalable_Brain/scalable-brain`
Venv: `source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate`
All paths below are relative to the repo root.

---

## Read, in this order

1. `task/2026-W32/fleet/upload/wave2/PROMPT.md` — the fleet brief. **Every hard rule in it
   binds you.** Where this local brief and PROMPT.md disagree, this brief wins (it only
   differs on file locations and on which verification commands you can run offline).
2. **Your spec**, in full: `task/2026-W32/fleet/upload/wave2/specs/SPEC-<id>.md`.
   This, not the CSV, is your source of truth. Every interpretive decision in it was
   already made and reviewed — implement it, do not re-litigate it. The spec is written to
   be exhaustive: §3 names the exact indicators and parameters, §4/§5 give the entry
   inequalities literally, §6/§7 the stop and every exit leg, §9 the causality audit, §10
   the ambiguities that are already resolved. Translate it.
3. `src/layer0/strategies/research/reference_pullback_continuation.py` — this is the file
   PROMPT.md calls `REFERENCE_STRATEGY.py`. Tested and passing. **Match its shape exactly.**
   Read all four numbered NOTES before writing a line; each marks a place where the obvious
   implementation is wrong.
4. `src/layer0/strategies/research/tests/test_reference_pullback_continuation_fixture.py` —
   this is `REFERENCE_FIXTURE.py`. Your fixture must follow this format.
5. `src/layer0/strategies/contract_v2.py` — the frozen interface. Read the `__post_init__`
   of `ExitLeg`, `StopRule` and `OrderIntent` closely: they *reject* malformed intents at
   construction, and most fleet failures are a rejected intent, not bad logic.
6. `src/layer0/strategies/causal_structure.py` and `src/layer0/data_access/indicators.py` —
   for whatever your spec §3 names. If §3 says an indicator is **not** in the inventory and
   gives you the formula, implement it as a private module-level helper in your own file.

## Deliver exactly two files — touch nothing else

| File | Path |
|---|---|
| Strategy | `src/layer0/strategies/research/<id>.py` |
| Golden fixture | `src/layer0/strategies/research/tests/test_<id>_fixture.py` |

**Do not try to write `REPORT-<id>.md`.** This harness refuses subagent writes to `.md`
report files ("Subagents should return findings as text, not write report files"), and every
agent in the first two runs lost that deliverable to the guard. Instead, **return the full
report content as markdown in your final message** and the orchestrator will persist it to
`task/2026-W32/wave2/REPORT-<id>.md` verbatim. Do not route around the guard with `bash`
heredocs or `python -c`. The report is still required — it is just delivered as text.

Do not create `__init__.py`, do not touch shared modules, do not "fix" anything you find in
`contract_v2.py`, `causal_structure.py`, `indicators.py` or another agent's strategy — even
if it is genuinely broken. **Report it instead**; the reviewer consolidates. A shared-file
edit from 51 agents at once is how this run gets destroyed.

## Write whole files, and leave them valid

A previous attempt at this fleet was interrupted, and one agent's fixture file was left cut
off mid-`def`. A single file with a `SyntaxError` **breaks pytest collection for the entire
suite** — it took down the other agents' ability to verify anything. So:

- Write each of your files in **one `Write` call** with its complete final content. Do not
  build a file up across several appends.
- If you must iterate, use `Edit` so the file stays syntactically valid between steps.
- If your target files already exist when you start, they are an **untrusted draft from the
  aborted run**. Verify every line against your spec or rewrite from scratch — never assume
  a pre-existing file is correct, and never assume it is yours. (Aborted-run drafts are
  parked in `task/2026-W32/wave2/aborted-run1-partials/`; they are unverified and must not
  be copied in wholesale.)

## Import style

- Strategy module: relative, exactly as the reference does —
  `from ..contract_v2 import ...`, `from ..causal_structure import ...`,
  `from ...data_access.indicators import ...`
- Fixture test: absolute, exactly as the reference fixture does —
  `from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2`
  `from src.layer0.strategies.research.<id> import <YourClass>`

## Metadata

`strategy_id` must equal your `<id>` exactly (the filename stem). Set `author="wave2-fleet"`,
`version="0.1.0"`, `hypothesis` = §1 of your spec (verbatim or near-verbatim; it must clear
the contract's minimum word count), `source_row` and `source_url` from your spec's
**Source:** line, and `pairs` = the *available* pairs from §2 (never a pair the spec lists
as missing/pending).

## Verify — all of these must pass before you report

```bash
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain
source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate

black src/layer0/strategies/research/<id>.py \
      src/layer0/strategies/research/tests/test_<id>_fixture.py

mypy --ignore-missing-imports --follow-imports=silent \
     src/layer0/strategies/research/<id>.py          # must be "Success: no issues found"

python -m pytest src/layer0/strategies/research/tests/test_<id>_fixture.py -q
```

Notes on the toolchain, so you do not chase ghosts:
- The `mypy` flags above are required. Without them mypy reports pre-existing errors in
  unrelated files, and passing your test file to mypy at the same time triggers a spurious
  "Source file found twice under different module names". **Only the strategy module is
  mypy-gated.** Do not mypy the test file.
- Run pytest on **your test file only**. Do not run the whole suite (other agents are
  writing to it concurrently, so unrelated red is expected and is not yours to fix).

### What you cannot run, and what replaces it

PROMPT.md's definition of done includes `assert_no_lookahead_v2` **against real data**.
That needs the database and the harness, which you must not touch (hard rule 6). Your proof
is `assert_no_lookahead_v2(<your strategy>, frames)` on your hand-built fixture frames — a
required test in your fixture file, exactly as the reference fixture's last test does. The
real-data probe is run centrally after the fleet lands (`verify_wave2.py`). Make your
fixture strong enough that it would catch the mistake: the probe only proves something if
your strategy actually **fires** on the fixture bars.

## The golden fixture — the part that gets you rejected

A strategy whose fixture does not pass is rejected without being read. Requirements:

1. **30–50 hand-constructed OHLC bars as a literal in the test file.** Not random, not
   loaded, not generated by a loop with a random seed. Bars you chose, for stated reasons.
2. Engineered so your strategy fires **at least once long**, and **at least once short** if
   it trades short at all. If your spec's conditions are so tight that one bar series cannot
   do both, build two literal series (`CLOSES_LONG`, `CLOSES_SHORT`) and two tests.
3. **Expected `OrderIntent` values computed by hand from the spec** — entry type, entry
   level, stop level, every exit leg with its fraction and level — with the arithmetic shown
   in a comment, as the reference fixture does. Derive them from the spec's formulas. Do
   **not** run the code and paste what it printed: that asserts the code equals itself and
   proves nothing.
4. An assertion that `generate_orders` produces exactly that.
5. A comment block mapping each assertion back to the numbered rule in your spec (§4.1,
   §6, §7 …) that requires it.

Subclassing your strategy in the fixture to shrink lookback periods and `warmup_bars` is
allowed and expected — 40 bars cannot warm a 50-period MA. The reference fixture's
`_FixtureScale` shows the pattern. Shrink *periods*; never change the *logic*, and never
change a level formula.

## Rules that are most often broken — reread these

- **Context frames:** if your spec declares any `context_granularities`, you MUST use
  `contract_v2.closed_context_frame(ctx, "<GRAN>", ts)` or the vectorised `merge_asof`
  form in NOTE 1 of the reference. `ctx.loc[ctx.index <= ts]` is look-ahead — bars are
  stamped at their OPEN, so it admits the bar that has not closed. That exact line produced
  108 phantom orders in the Wave-1 review, and the truncation probe **passes it clean**, so
  a green fixture will not save you here. If your spec §2 says context_granularities: none,
  read only your primary frame.
- **`indicators.detect_swing_points` is banned.** It uses `center=True` and reads the
  future. Use `causal_structure.confirmed_swing_points` /
  `last_n_confirmed_highs` / `last_n_confirmed_lows`, with the period your spec §3 states,
  and honour the confirmation lag in §9.
- **No `shift(-n)`, no `rolling(..., center=True)`, no `.iloc[i+1:]`, no whole-frame
  normalisation, no `resample` without a causal offset.**
- **Exit fractions sum to exactly 1.0.** The contract's tolerance is 1e-9.
- **A pending entry must be on the correct side of the decision-bar close** (NOTE 3). If it
  is not, skip that bar — do not clamp the level to make it legal.
- **`stop.move_to_breakeven_on` must name a label that exists** among your exit legs.
- **No parameter tuning** (hard rule 5). Use your spec's parameters. If they look wrong,
  say so in the report; do not improve them.
- **Purity:** `generate_orders` must not mutate the frames it is handed (the probe
  checksums them) and must do no I/O.

## Judgement calls

If you hit a decision your spec genuinely does not cover: take the **most conservative**
reading (the one that trades less, or loses more), implement it, and list it under
**Uncertainties** in your report. Do not resolve it silently — an unreviewed decision at
this stage is invisible to everyone downstream. If it is load-bearing enough that a wrong
choice makes the strategy meaningless, say so explicitly in the report.

Never weaken a fixture assertion to make a test pass. If the code and your hand arithmetic
disagree, one of them contradicts the spec — find out which.

## `task/2026-W32/wave2/REPORT-<id>.md` — four sections, short

- **Implemented** — what you built, and any place the spec was thinner than the code needed
- **Deviations** — anything done differently from the spec, and why. Ideally empty
- **Uncertainties** — judgement calls the spec did not cover. The reviewer decides
- **Fixture rationale** — why those bars, and what the strategy does on them

## Report back to the orchestrator

Your strategy id · pass/fail of each of the three verification commands · how many orders
your fixture produces and their directions · your Uncertainties list · anything you found
wrong in a shared file that you correctly did not edit.
