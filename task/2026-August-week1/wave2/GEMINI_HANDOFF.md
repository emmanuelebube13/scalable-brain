# Wave-2 handoff — instructions for the continuing agent

You are finishing a job that is already 13/47 done. Everything you need is on this machine.
Follow this file literally. It is written to be mechanical: there are no decisions left for
you that are not marked **DECISION** below, and when you hit one you write it down instead of
resolving it.

**Repo root (all paths are relative to it):**
`/home/emmanuel/Documents/Scalable_Brain/scalable-brain`

**Every command in this file assumes you have first run:**

```bash
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain
source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate
```

---

## 0. What the job is

There are 51 forex trading strategies, each already written up as an exhaustive English
spec by a previous stage. Your job is **translation, not design**: turn each spec into one
Python class plus one test that proves the class matches the spec.

You are **not** being asked to invent, improve, tune, or evaluate any strategy. If a strategy
looks bad, that is not your problem and you must not fix it.

---

## 0-a. FIRST: three fixtures need rework before you write anything new

`kiss_h4`, `janus_swing_system` and `kpl_donchian_breakout` were delivered with fixtures that
are **too thin to be reviewed** and are now REJECTED by the audit. Their strategy modules are
fine — do not touch those. Rewrite only the fixture files.

What was wrong: 2 test functions, almost no comments, no arithmetic shown, and only the first
exit leg asserted. `kiss_h4`'s fixture is 58 lines with **zero** comment lines. A reviewer
reading `assert o1.stop.price == pytest.approx(1.194)` has no way to tell whether 1.194 is
what the spec requires or just what the program happened to print. That is the exact problem
the golden fixture exists to eliminate, so a fixture without the derivation fails its purpose
even when its numbers are correct.

Fix each one to meet the **hard minimums** in §3 Step 3 below, then re-run:

```bash
python task/2026-August-week1/wave2/audit_wave2.py --quick kiss_h4 janus_swing_system kpl_donchian_breakout
```

Use `test_inside_bar_pinbar_combo_fixture.py` — your own accepted work — as the model, or
`test_bb_midline_break_fixture.py` for the fuller pattern.

## 1. Your assignment: exactly these 27 strategies

Do these, in this order, one at a time:

```
inside_bar_pinbar_combo      kiss_h4                     janus_swing_system
kpl_donchian_breakout        liquidity_grab_fade         liquidity_sweep_ob
long_wick_pinbar_8ema        ma_crossover_swing          macd_divergence
nnfx_backtrader              nzdjpy_median_ma_retrace    outside_hma_klinger
pinbar_key_level_50pct       pinbar_nose_eyes            precision_swing
psar_gbpjpy_daily            retail_sentiment_fade       smash_days
smashing_forex_2             strong_weak_analysis        three_candle_swing_reversal
trending_retracement_daily   vshape_swing_breakout       weekly_day_reversal_ea
weekly_range_reversal        xard_ma_cross_daily_open    daily_fib_retracement_REPORT_ONLY
```

The last entry is not a strategy — see §7.

### DO NOT TOUCH these 11 — they are deliberately excluded

**Already finished (13).** Do not modify, "improve", reformat, or re-verify them:
`adx_trend_pullback_ea`, `amazing_crossover`, `bb_midline_break`, `currency_momentum_factor`,
`daily_fib_retracement`, `demark_fractal_breakout`, `double_bottom_measured_move`,
`engulfing_broken_level`, `h4_box_breakout`, `h4_forex_system`, `holy_grail_pullback`,
`inside_bar_continuation_ea`, `inside_bar_reversal`.

**Must not be built at all (4)** — they depend on data that does not exist in this repo.
Do not create files for them. Do not invent a substitute data source, a proxy, a stub, or a
hardcoded series. Creating any file for these is a failure:
`currency_value_ppp`, `usd_carry_basket`, `three_ducks`, `financial_regime_index`.

**Reserved for the other agent (7)** — every strategy that reads a second timeframe. Do not
attempt these; they contain a failure mode that testing does not catch:
`ema_cross_h4_filter_bot`, `h4_crossover_21_89_macd`, `mtf_swing_weekly_pivots`,
`reps_donchian_pyramiding`, `riding_trend_retracement`, `smart_money_swing`,
`sunday_breakout`, `weekly_gap_fade`.

---

## 2. Read these four files before you write any code

Read them once, now, in full. Do not skim.

| Read | Path |
|---|---|
| The frozen interface | `src/layer0/strategies/contract_v2.py` |
| A complete worked example, tested and passing | `src/layer0/strategies/research/reference_pullback_continuation.py` |
| The matching example test — **the format you must copy** | `src/layer0/strategies/research/tests/test_reference_pullback_continuation_fixture.py` |
| The full rules | `task/2026-August-week1/wave2/RUN_BRIEF.md` |

In `contract_v2.py`, pay particular attention to the `__post_init__` methods of `ExitLeg`,
`StopRule` and `OrderIntent`. They **reject** bad values when you construct them. Most
failures here are a rejected object, not broken logic. In particular:

- exit-leg `fraction` values must sum to **exactly 1.0**
- a long's stop must be **below** entry; a short's **above**
- a `buy_stop` must be **above** the decision bar's close; a `sell_stop` **below**
  (if it isn't, **skip that bar** — do not adjust the number to make it legal)
- `stop.move_to_breakeven_on` must name an exit leg label that actually exists

Also read, as needed for whatever indicators your spec names:
`src/layer0/data_access/indicators.py` and `src/layer0/strategies/causal_structure.py`.

---

## 3. The loop — repeat this for each of your 27 strategies

Let `<id>` be the strategy id, e.g. `kiss_h4`.

### Step 1 — read the spec, all of it

`task/2026-August-week1/fleet/upload/wave2/specs/SPEC-<id>.md`

**This spec is your only source of truth.** It is exhaustive on purpose:

- §1 the hypothesis (copy into `metadata.hypothesis`)
- §2 which timeframe and which currency pairs
- §3 the exact indicators and their exact parameters
- §4 / §5 the entry conditions for long / short, as literal inequalities
- §6 the stop formula · §7 every exit leg with its fraction and level formula
- §9 the causality audit — what is knowable when
- §10 the ambiguities, **already resolved for you**. Implement the resolution in the
  "conservative reading taken" column. Do not reopen these.

If the spec says an indicator is not available and gives you the formula, write it as a
private function in your own file (name it with a leading underscore).

### Step 2 — write the strategy module

Path: `src/layer0/strategies/research/<id>.py`

Copy the shape of `reference_pullback_continuation.py`. Imports must be relative, exactly
like the reference:

```python
from ..contract_v2 import ExitLeg, OrderIntent, StopRule, StrategyMetadataV2, StrategyV2
from ..causal_structure import last_n_confirmed_highs, last_n_confirmed_lows
from ...data_access.indicators import atr, ema, get_pip_value
```

Metadata rules, no exceptions:

- `strategy_id` = `<id>`, character for character
- `author="wave2-fleet"`, `version="0.1.0"`
- `hypothesis` = §1 of the spec (a long sentence; short strings are rejected)
- `pairs` = the available pairs named in §2. Never a pair §2 calls missing.
- `source_row` / `source_url` = from the spec's `**Source:**` line

**Write the whole file in ONE write operation.** A file left half-written breaks the entire
test suite for everyone. If you must revise it, use an edit that leaves it valid Python.

### Step 3 — write the golden fixture

Path: `src/layer0/strategies/research/tests/test_<id>_fixture.py`

Imports here are **absolute**, unlike the module:

```python
from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.<id> import YourClassName
```

The fixture must have all five of these:

1. **30–50 bars written out as a literal list in the test file.** Numbers you chose.
   Not random. Not loaded from a database. Not generated in a loop.
2. Bars arranged so the strategy **fires at least once long**, and **at least once short**
   if the spec says it trades short. If one series cannot do both, write two series.
3. **The expected order values, worked out by hand from the spec's formulas, with the
   arithmetic written in a comment** — entry type, entry level, stop level, and every exit
   leg's fraction and level.
4. Assertions that the strategy produces exactly those values.
5. A call to `assert_no_lookahead_v2(YourStrategy(), frames)`.

You may subclass your strategy inside the test to make periods smaller (40 bars cannot warm
a 200-period average). The reference fixture's `_FixtureScale` shows how. Shrink **periods
only** — never change a formula, a threshold, or a level.

### Hard minimums — the audit enforces all four

A fixture that meets fewer than these is rejected without its strategy being read:

| Minimum | Why |
|---|---|
| **at least 4 `def test_` functions** | one per thing being proved, not one lump |
| **at least 8 comment lines** showing the arithmetic and naming the spec rule (`§4.2`, `§6`…) each assertion enforces | this is what makes the fixture reviewable at all |
| **at least one assertion on exit-leg `fraction`** values | they must sum to exactly 1.0, and a single-leg strategy must assert `1.0` |
| **assert EVERY exit leg**, not just `exits[0]` | a spec with a TP leg and a time leg needs both pinned, with their fractions |

Concretely, the comment requirement means: for each order your fixture expects, write out the
sum — e.g. `# §6 stop = Close_t - 100 pip = 1.20400 - 0.01000 = 1.19400` — so a human can
check the number against the spec without running anything. Numbers with no visible derivation
are treated as unproven no matter how correct they are.

> ### The one thing that will get your work thrown out
>
> **Do not run the strategy, look at the numbers it prints, and paste those numbers into
> your assertions.** That produces a test which passes no matter what the code does, and
> proves nothing at all.
>
> You must compute the expected entry / stop / exit numbers yourself, from the formulas in
> spec §6 and §7, *before* running anything.
>
> **This is checked automatically and it cannot be bluffed.** The audit re-runs your test
> with the strategy deliberately broken so that it emits no orders. A real test fails when
> that happens. A pasted-output test still passes — and is rejected. See §5.
>
> If your hand arithmetic and the code disagree: **do not change the test to match the
> code.** One of them contradicts the spec. Work out which, fix that one, and write down
> what happened in your report.

### Step 4 — verify. All three must pass

```bash
black src/layer0/strategies/research/<id>.py \
      src/layer0/strategies/research/tests/test_<id>_fixture.py

mypy --ignore-missing-imports --follow-imports=silent \
     src/layer0/strategies/research/<id>.py

python -m pytest src/layer0/strategies/research/tests/test_<id>_fixture.py -q
```

Notes so you do not waste time:

- The `mypy` flags are required. Run mypy on the **strategy module only** — never on the
  test file, and never on both at once (you will get a bogus "Source file found twice"
  error).
- Run pytest on **your one test file**, not the whole suite.
- `mypy` must print `Success: no issues found in 1 source file`.

Fix and repeat until all three pass. **Never make a test weaker to make it pass.**

### Step 5 — write the report

Path: `task/2026-August-week1/wave2/REPORT-<id>.md`

Four short sections:

- **Implemented** — what you built; anywhere the spec was thinner than the code needed
- **Deviations** — anything done differently from the spec, and why. Ideally empty
- **Uncertainties** — **DECISION** points: judgement calls the spec did not cover. List
  them; do not resolve them silently. If a wrong choice would make the strategy meaningless,
  say so
- **Fixture rationale** — why those bars, and what the strategy does on them

### Step 6 — record progress, then go to the next strategy

Append one line to `task/2026-August-week1/wave2/GEMINI_PROGRESS.md`:

```
<id> — DONE — black ok, mypy ok, pytest N passed, fixture emits X long / Y short
```

or, if you could not finish it:

```
<id> — BLOCKED — <one sentence saying exactly what stopped you>
```

Then start the next strategy at Step 1. **One strategy at a time, start to finish.** Do not
begin several at once.

---

## 4. Absolute rules

1. **Only ever create or edit these three files per strategy:**
   `research/<id>.py`, `research/tests/test_<id>_fixture.py`,
   `task/2026-August-week1/wave2/REPORT-<id>.md`.
2. **Never edit a shared file** — `contract_v2.py`, `position_engine.py`,
   `causal_structure.py`, `indicators.py`, `v2_harness.py`, any `__init__.py`, or another
   strategy's files. Not even to fix something genuinely broken. Write it in your report
   instead.
3. **Never import `detect_swing_points`.** It looks into the future. Use
   `causal_structure.confirmed_swing_points`, `last_n_confirmed_highs`,
   `last_n_confirmed_lows`.
4. **Never write** `shift(-1)` (or any negative shift), `rolling(..., center=True)`,
   `.iloc[i+1:]`, or anything else that reads a bar later than the current one.
5. **Never read the database.** Your strategy receives data as an argument and returns
   orders. That is the whole interface. No file, network, or DB access.
6. **Never change a parameter** given in the spec, even if it looks wrong. Say so in the
   report instead.
7. **Never touch the 11 excluded strategies** in §1.
8. If you genuinely cannot proceed, write `BLOCKED` in the progress file with the reason and
   move on to the next strategy. Do not guess, and do not invent data.

---

## 5. How your work will be judged

One command decides it:

```bash
python task/2026-August-week1/wave2/audit_wave2.py
```

For each strategy it checks, in order, and stops at the first failure:

| # | Check | What fails it |
|---|---|---|
| 1 | FILES | module or fixture missing, or does not parse |
| 2 | BANNED | a future-reading pattern in your module |
| 3 | CONTEXT | unsafe second-timeframe read (does not apply to your 27) |
| 4 | META | `strategy_id` does not match the filename, or no pairs declared |
| 5 | FIXTURE | fewer than 30 hand-written price numbers, or it does not assert on the trade plan, or it never calls `assert_no_lookahead_v2` |
| 5b | **REVIEWABLE** | **fewer than 4 tests, fewer than 8 comment lines showing the arithmetic, or no assertion on exit-leg fractions — see §3 Step 3 "Hard minimums"** |
| 6 | TESTS | your fixture does not pass |
| 7 | **TEETH** | **your fixture still passes when the strategy is sabotaged to emit no orders — i.e. it asserts nothing** |
| 8 | REALDATA | the look-ahead probe fails against ten years of real market data |

Check 7 is the one that catches pasted output. All 13 finished strategies pass it. Yours
must too.

Run the audit on your own work as you go:

```bash
python task/2026-August-week1/wave2/audit_wave2.py --quick <id>
```

`--quick` skips the slow database check. Aim for `PASS <id>`.

---

## 6. Worked reference

`bb_midline_break` is a complete, accepted example. If you are unsure what "good" looks
like, read all three of its files and copy the pattern:

- `src/layer0/strategies/research/bb_midline_break.py`
- `src/layer0/strategies/research/tests/test_bb_midline_break_fixture.py`
- `task/2026-August-week1/wave2/REPORT-bb_midline_break.md`

---

## 7. One extra job: 9 missing reports

Nine finished strategies have code and tests but lost their report when the earlier run was
interrupted. **Do not change their code or tests** — they are accepted and verified. Just
read each one's spec, module and fixture, and write the missing report at
`task/2026-August-week1/wave2/REPORT-<id>.md`, using the four sections from Step 5 and describing what
the code actually does:

```
adx_trend_pullback_ea    amazing_crossover        currency_momentum_factor
daily_fib_retracement    demark_fractal_breakout  double_bottom_measured_move
engulfing_broken_level   holy_grail_pullback      inside_bar_reversal
```

Do this **after** all 27 strategies, not before. Working code matters more than paperwork.

Note for `adx_trend_pullback_ea`: two constants in its fixture were corrected by the
orchestrator (a rounding slip, annotated in the file). Mention that in its report.

---

## 8. When you are done

```bash
black --check src/layer0/strategies/research/
python -m pytest src/layer0/strategies -q
python task/2026-August-week1/wave2/audit_wave2.py
```

Then write a final summary in `task/2026-August-week1/wave2/GEMINI_PROGRESS.md`: how many strategies
you completed, which are BLOCKED and why, and every **DECISION** you recorded, gathered in
one list. That list is the most valuable thing you produce — it is what a human reviewer
must rule on.
