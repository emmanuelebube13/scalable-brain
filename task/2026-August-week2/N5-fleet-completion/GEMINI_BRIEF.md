# N5 — code and measure the remaining 29 strategies

**Instructions for the executing agent. Follow this file literally.**

Everything you need is on this machine. There are no decisions left for you that are not
marked **DECISION** below, and when you hit one you *write it down* instead of resolving it
silently.

**Repo root — every path in this file is relative to it:**
`/home/emmanuel/Documents/Scalable_Brain/scalable-brain`

**Every command assumes you have first run:**

```bash
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain
source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate
```

---

## 0. Where this stands, in numbers

There are **51 forex strategies**, each already written up as an exhaustive English spec by
an earlier stage. The specs are the source of truth; you are doing **translation and
measurement, not design**.

| | count | ids |
|---|--:|---|
| Specs total | 51 | `task/2026-August-week1/fleet/upload/wave2/specs/SPEC-*.md` |
| **Must not be built** — external data that does not exist here | 4 | `currency_value_ppp`, `usd_carry_basket`, `three_ducks`, `financial_regime_index` |
| Already built **and** accepted by the audit | 15 | see §2 |
| Already built, fixture **rejected** as too thin | 3 | `kiss_h4`, `janus_swing_system`, `kpl_donchian_breakout` |
| **Yours to build** | **29** | §2 |

Measurement so far: **18 strategies have been run through the harness. Every one of them
FAILED the gates. Zero qualifiers.** Best pooled result in the whole set is PF 1.46 on 34
trades — noise, not an edge.

That is the expected shape of this job. **If the first 18 are representative, the honest
expectation for the remaining 29 is roughly 0–2 genuine qualifiers.** You are not here to
produce a winner. You are here to produce a *truthful measurement of 29 more*, and a
truthful "all 29 failed" is a complete success. Read §7 before you are tempted otherwise.

---

## 1. What you produce, per strategy

Four things, in this order:

1. `src/layer0/strategies/research/<id>.py` — the contract-v2 strategy
2. `src/layer0/strategies/research/tests/test_<id>_fixture.py` — the golden fixture
3. a harness verdict in `results/research/<id>/` (written by the harness — you run it)
4. `task/2026-August-week1/wave2/REPORT-<id>.md` — the four-section report

plus one row per strategy appended to the ledger you create in §3:
`task/2026-August-week2/N5-fleet-completion/VERDICTS.md`.

> Reports stay in `task/2026-August-week1/wave2/` with the other 18, on purpose — a reviewer
> should find all 47 reports in one directory. Only the N5 ledger and batch reviews live in
> `task/2026-August-week2/N5-fleet-completion/`.

---

## 2. Your assignment — exactly these 29, in these batches

**Work one batch at a time, one strategy at a time inside a batch, start to finish.** Do
not start several at once. After each batch, stop and do the batch review in §5. The
batching exists so a systematic mistake surfaces after 8 strategies instead of 29.

### Batch 0 — three fixture reworks (do this first, it is small)

`kiss_h4` · `janus_swing_system` · `kpl_donchian_breakout`

These three have **correct, already-measured strategy modules** and fixtures that the audit
rejects as unreviewable (2 test functions, zero comment lines, only the first exit leg
asserted). **Rewrite the fixture files only. Do not touch the three modules.** Meet the hard
minimums in §4 Step 3. Then:

```bash
python task/2026-August-week1/wave2/audit_wave2.py --quick kiss_h4 janus_swing_system kpl_donchian_breakout
```

All three must read `PASS`. Do **not** re-run the harness on them — their modules are
unchanged, so their existing verdicts stand. If rewriting a fixture uncovers a genuine bug
in one of the three modules, **stop, write it in the batch review, and do not fix it** — a
module change invalidates a verdict that other documents already cite.

### Batch 1 — 8 single-timeframe (the calibration batch)

```
smash_days              macd_divergence         pinbar_nose_eyes        trending_retracement_daily
vshape_swing_breakout   ma_crossover_swing      weekly_day_reversal_ea  precision_swing
```

### Batch 2 — 8 single-timeframe

```
liquidity_grab_fade     liquidity_sweep_ob      long_wick_pinbar_8ema   pinbar_key_level_50pct
psar_gbpjpy_daily       smashing_forex_2        three_candle_swing_reversal  xard_ma_cross_daily_open
```

### Batch 3 — 6 awkward ones (read §6 before starting this batch)

```
nnfx_backtrader         outside_hma_klinger     strong_weak_analysis
weekly_range_reversal   retail_sentiment_fade   nzdjpy_median_ma_retrace
```

### Batch 4 — 7 multi-timeframe (highest risk — read §6.1 twice)

```
h4_crossover_21_89_macd  mtf_swing_weekly_pivots  riding_trend_retracement  smart_money_swing
sunday_breakout          weekly_gap_fade          reps_donchian_pyramiding
```

Every strategy in batch 4 declares `context_granularities`. That is the one failure mode a
passing fixture does **not** catch, and it has already produced 108 phantom orders once in
this project.

### Do not touch these

**The 4 that must not be built at all.** They depend on data that does not exist in this
repo. Do not create files for them. Do not invent a substitute source, a proxy, a stub, or
a hardcoded series. Creating any file for these is a failure, not a partial credit:
`currency_value_ppp` · `usd_carry_basket` · `three_ducks` · `financial_regime_index`.

**The 15 finished and accepted.** Do not modify, reformat, "improve", or re-measure:
`adx_trend_pullback_ea`, `amazing_crossover`, `bb_midline_break`, `currency_momentum_factor`,
`daily_fib_retracement`, `demark_fractal_breakout`, `double_bottom_measured_move`,
`ema_cross_h4_filter_bot`, `engulfing_broken_level`, `h4_box_breakout`, `h4_forex_system`,
`holy_grail_pullback`, `inside_bar_continuation_ea`, `inside_bar_pinbar_combo`,
`inside_bar_reversal`.

---

## 3. Before you write any code

### 3a. Read these five files in full. Do not skim.

| Read | Path |
|---|---|
| The frozen interface | `src/layer0/strategies/contract_v2.py` |
| A complete worked example | `src/layer0/strategies/research/reference_pullback_continuation.py` |
| Its fixture — **the format you must copy** | `src/layer0/strategies/research/tests/test_reference_pullback_continuation_fixture.py` |
| The full authoring rules | `task/2026-August-week1/wave2/RUN_BRIEF.md` |
| What data actually exists | `task/2026-August-week1/fleet/DATA_AVAILABILITY.md` |

In `contract_v2.py` pay particular attention to the `__post_init__` methods of `ExitLeg`,
`StopRule` and `OrderIntent`. They **reject** bad values at construction time, so most of
your failures will be a rejected object rather than broken logic:

- exit-leg `fraction` values must sum to **exactly 1.0** (tolerance 1e-9)
- a long's stop must be **below** entry; a short's **above**
- a `buy_stop` must be **above** the decision bar's close, a `sell_stop` **below** — if it
  is not, **skip that bar**; never nudge the level to make it legal
- `stop.move_to_breakeven_on` must name an exit-leg label that exists

Read as needed for your spec's indicators: `src/layer0/data_access/indicators.py` and
`src/layer0/strategies/causal_structure.py`.

### 3b. Data reality — five pairs, verified 2026-08-15

`EUR_USD` · `GBP_USD` · `USD_JPY` · `AUD_USD` · `USD_CAD`, each with H1/H4/D1 current to
2026-08-13/14 and W1 current to 2026-07-31. **The Wave-1 pair additions never landed.** Every
other pair a spec names (`GBP_JPY`, `EUR_JPY`, `NZD_USD`, `NZD_JPY`, `GBP_CAD`, `XAU_USD`, …)
does not exist. Allowed granularities: **H1, H4, D1, W1** only.

Declare in `metadata.pairs` only pairs from those five, chosen from the ones your spec's §2
`pairs_available` names. Record every pair the spec wanted and could not have under
**Coverage** in your report. Bars are stamped at their **OPEN** — a D1 bar timestamped
`2026-08-05T21:00Z` is not knowable until `2026-08-06T21:00Z`. That single fact is what
makes §6.1 dangerous.

### 3c. Create the ledger

Create `task/2026-August-week2/N5-fleet-completion/VERDICTS.md` with this header, then
append one row per strategy as you finish it (never rewrite an earlier row):

```markdown
# N5 — verdict ledger

One row per strategy, appended when its harness run completes. Never edited afterwards.
Gates (all must pass): PF >= 1.50 · Sharpe >= 0.80 · MaxDD <= 25% · WinRate >= 40% ·
Recovery >= 3.00 · OOS >= 60 months.

| batch | strategy_id | gran | pairs | cells pass/total | OOS trades | PF | Sharpe | MaxDD | verdict | note |
|--:|---|---|--:|---|--:|--:|--:|--:|---|---|
```

`verdict` is one of exactly four words:

- **QUALIFIED** — pooled `passed: true`. Stop and flag it loudly in the batch review.
- **FAIL** — it ran, it traded, it did not clear the gates. The expected outcome.
- **INSUFFICIENT** — it ran but produced 0 orders, 0 cells, or so few trades that the
  result means nothing. **This is a measurement failure, not a verdict** — say which in the
  note (`0 orders emitted`, `only 4 OOS trades`, `no data for the only declared pair`).
- **UNMEASURABLE** — cannot be run at all on existing data (see `nzdjpy_median_ma_retrace`
  in §6.2). Build it, audit it, record it, move on.

---

## 4. The per-strategy loop

Let `<id>` be the strategy id, e.g. `smash_days`.

### Step 1 — read the whole spec

`task/2026-August-week1/fleet/upload/wave2/specs/SPEC-<id>.md`

It is exhaustive on purpose:

- §1 hypothesis → copy into `metadata.hypothesis`
- §2 timeframe, context frames, pairs
- §3 exact indicators and exact parameters
- §4/§5 entry conditions for long/short, as literal inequalities
- §6 stop formula · §7 every exit leg with its fraction and level formula
- §9 the causality audit — what is knowable when
- §10 the ambiguities, **already resolved**. Implement the "conservative reading taken"
  column. Do not reopen these.

If the spec says an indicator is unavailable and gives you the formula, write it as a
private function in your own file, named with a leading underscore.

### Step 2 — write the strategy module

Path: `src/layer0/strategies/research/<id>.py`. Copy the shape of
`reference_pullback_continuation.py`. Imports are **relative**, exactly like the reference:

```python
from ..contract_v2 import ExitLeg, OrderIntent, StopRule, StrategyMetadataV2, StrategyV2
from ..causal_structure import last_n_confirmed_highs, last_n_confirmed_lows
from ...data_access.indicators import atr, ema, get_pip_value
```

Metadata rules, no exceptions:

- `strategy_id` = `<id>`, character for character (it must equal the filename)
- `author="n5-fleet"`, `version="0.1.0"`
- `hypothesis` = §1 of the spec — a long sentence; short strings are rejected
- `pairs` = per §3b
- `source_row` / `source_url` = from the spec's `**Source:**` line

**Write the whole file in ONE write operation.** The harness discovers strategies by
importing *every* module in `research/`, so a file left half-written breaks discovery and
the test suite for everything, not just for you. If you must revise, use an edit that leaves
the file valid Python at every point.

### Step 3 — write the golden fixture

Path: `src/layer0/strategies/research/tests/test_<id>_fixture.py`. Imports here are
**absolute**, unlike the module:

```python
from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.<id> import YourClassName
```

All five of these are required:

1. **30–50 bars written out as a literal list in the test file.** Numbers you chose, for
   stated reasons. Not random, not loaded from the database, not generated in a loop.
2. Bars arranged so the strategy fires **at least once long**, and **at least once short**
   if the spec trades short. If one series cannot do both, write two.
3. **Expected order values worked out by hand from the spec's formulas, with the arithmetic
   shown in a comment** — entry type, entry level, stop level, and every exit leg's fraction
   and level.
4. Assertions that the strategy produces exactly those values.
5. A call to `assert_no_lookahead_v2(YourStrategy(), frames)`.

You may subclass your strategy inside the test to shrink lookback periods and `warmup_bars`
— 40 bars cannot warm a 200-period average; the reference fixture's `_FixtureScale` shows
the pattern. Shrink **periods only**. Never a formula, a threshold, or a level.

**Hard minimums — the audit enforces all four:**

| Minimum | Why |
|---|---|
| at least **4** `def test_` functions | one per thing proved, not one lump |
| at least **8** comment lines showing the arithmetic and naming the spec rule (`§4.2`, `§6`) each assertion enforces | this is what makes the fixture reviewable at all |
| at least one assertion on exit-leg **`fraction`** values | they must sum to exactly 1.0; a single-leg strategy asserts `1.0` |
| assert **every** exit leg, not just `exits[0]` | a spec with a TP leg and a time leg needs both pinned |

Concretely: for each expected order, write out the sum —
`# §6 stop = Close_t - 100 pip = 1.20400 - 0.01000 = 1.19400` — so a human can check the
number against the spec without running anything. A number with no visible derivation is
treated as unproven no matter how correct it is.

> ### The one thing that gets your work thrown out
>
> **Do not run the strategy, read the numbers it prints, and paste them into your
> assertions.** That produces a test that passes no matter what the code does.
>
> Compute the expected entry / stop / exit values yourself, from spec §6 and §7, *before*
> running anything.
>
> **This is checked automatically and cannot be bluffed.** The audit re-runs your fixture
> with the strategy sabotaged to emit no orders. A real fixture fails; a pasted-output
> fixture still passes, and is rejected (audit check 7, TEETH).
>
> If your hand arithmetic and the code disagree, **do not change the test to match the
> code.** One of them contradicts the spec. Work out which, fix that one, and write what
> happened in the report.

### Step 4 — verify locally. All three must pass

```bash
black src/layer0/strategies/research/<id>.py \
      src/layer0/strategies/research/tests/test_<id>_fixture.py

mypy --ignore-missing-imports --follow-imports=silent \
     src/layer0/strategies/research/<id>.py

python -m pytest src/layer0/strategies/research/tests/test_<id>_fixture.py -q
```

- The `mypy` flags are required. Run mypy on the **module only** — never the test file, and
  never both at once (you will get a bogus "Source file found twice").
- `mypy` must print `Success: no issues found in 1 source file`.
- Run pytest on **your one test file**.
- **Never weaken a test to make it pass.**

### Step 5 — audit

```bash
python task/2026-August-week1/wave2/audit_wave2.py --quick <id>
```

Aim for `PASS <id>`. `--quick` skips the real-data probe; the batch review runs the full
version. Note that this script **overwrites `AUDIT.json`** on every run, so the file only
ever reflects the last invocation.

### Step 6 — measure

```bash
python -m src.layer0.strategies.v2_harness <id>
```

It takes about 10 seconds. It prints the pooled verdict and writes the full report to
`results/research/<id>/v2_evaluation_<timestamp>.json`. What it does: loads up to 10 years
for each declared pair, re-proves `assert_no_lookahead_v2` **against real data**, resolves
fills on H1 bars, attributes trades to anchored walk-forward OOS folds (36-month minimum
train, 6-month step, 6-month OOS), and evaluates the same gates the live system uses.

Read the JSON for the row you are about to write: `pooled.passed`, `pooled.n_oos_trades`,
`pooled.cell.{profit_factor,sharpe,max_drawdown}`, `dispersion.n_passed`/`n_cells`, and
`skipped` (which pairs had no data).

**Run the harness exactly once per finished strategy.** If you run it again after changing
code, say so in the report and keep both verdicts.

### Step 7 — record

Append the ledger row (§3c), then write `task/2026-August-week1/wave2/REPORT-<id>.md` with
five short sections:

- **Implemented** — what you built; anywhere the spec was thinner than the code needed
- **Deviations** — anything done differently from the spec, and why. Ideally empty
- **Uncertainties** — **DECISION** points the spec did not cover. List them; do not resolve
  them silently. If a wrong choice would make the strategy meaningless, say so
- **Coverage** — pairs declared, pairs the spec wanted that do not exist, pairs the harness
  skipped
- **Verdict** — the harness numbers and one sentence on what limited them (too few trades?
  drawdown? win rate?). **No speculation about how to make it pass.**

Then start the next strategy at Step 1.

---

## 5. The batch review — stop here, every 8

At the end of each batch, before starting the next one:

```bash
# 1. full audit (real-data probe included) on the batch's ids
python task/2026-August-week1/wave2/audit_wave2.py <id1> <id2> ... <id8>

# 2. nothing else broke
black --check src/layer0/strategies/research/
python -m pytest src/layer0/strategies -q

# 3. every v2 strategy is still discoverable
python -m src.layer0.strategies.v2_harness --list
```

Then write `task/2026-August-week2/N5-fleet-completion/BATCH-<n>-REVIEW.md`:

- the audit line for each of the 8 (`PASS` / the first failing check)
- the ledger rows for the 8, copied in
- **anything that looks systematic** — the same mistake in more than one strategy, the same
  spec section misread twice, an INSUFFICIENT count above 2 in one batch. This is the entire
  point of batching. Say it plainly.
- every **DECISION** you recorded in the batch, gathered in one list
- anything you found wrong in a shared file and correctly did not edit

If a systematic mistake appears, **fix it across every strategy in the batch before starting
the next batch**, and record what you changed. Carrying a systematic error into batch 3 is
the failure this structure exists to prevent.

---

## 6. Traps, named in advance

### 6.1 Context frames (all of batch 4)

If your spec declares any `context_granularities`, you **must** read them through
`contract_v2.closed_context_frame(ctx, "<GRAN>", ts)` or the vectorised `merge_asof` form in
NOTE 1 of the reference strategy. `ctx.loc[ctx.index <= ts]` is **look-ahead** — bars are
stamped at their open, so that form admits a bar that has not closed yet. It produced 108
phantom orders in an earlier review, and **the fixture probe passes it clean**. A green
fixture will not save you here; audit check 3 (CONTEXT) is what catches it.

`reps_donchian_pyramiding` declares W1 *derived from D1 by resampling*. A resample without a
causal offset is the same bug in a different costume — the weekly bar containing `t` is not
knowable at `t`.

### 6.2 Strategies that cannot fully be measured

- **`nzdjpy_median_ma_retrace`** — its spec's `pairs_available` is literally **NONE**;
  NZD_JPY is not in the database. Build it, audit it, and record it as **UNMEASURABLE**.
  Do not substitute a different pair to get a number.
- **`retail_sentiment_fade`** — the retail positioning feed does not exist. Its spec was
  written to be implementable without it; implement exactly what §3–§7 say and record what
  the missing feed costs. **Do not proxy sentiment with price.**
- **`strong_weak_analysis`** — cross-sectional currency strength, but the harness hands your
  strategy **one pair at a time**. Follow the precedent set by `currency_momentum_factor`:
  implement the single-pair-reachable path, keep the cross-sectional helper pure and
  unreachable from it, and document the degradation in the report. **Never load another
  pair from inside a strategy.**

### 6.3 The zero-order strategy

A strategy that emits no orders on ten years of real data is not a strategy that failed —
it is a strategy that was never measured. Two of the finished 18 are in that state. If your
harness run reports 0 cells or 0 OOS trades, first check the obvious causes (warmup longer
than the data, an entry condition that can never be true, pairs all skipped), record it as
**INSUFFICIENT** with the cause, and flag it in the batch review. **Do not loosen the entry
conditions to produce trades.**

### 6.4 Banned outright

- `indicators.detect_swing_points` — it uses `center=True` and reads the future. Use
  `causal_structure.confirmed_swing_points` / `last_n_confirmed_highs` /
  `last_n_confirmed_lows`, with the period your spec §3 states and the confirmation lag §9
  states.
- `shift(-n)`, `rolling(..., center=True)`, `.iloc[i+1:]`, whole-frame normalisation,
  `resample` without a causal offset.
- `generate_orders` must not mutate the frames it is handed (the probe checksums them) and
  must do no I/O of any kind.

---

## 7. The rule that matters most

**You may not change a strategy after seeing its result.**

Every parameter comes from the spec. If a strategy fails the gates — and almost all of them
will — that is **the finding**, and the finding is what this whole exercise is for. Do not
tune a period, shift a threshold, swap a granularity, add a filter, or drop the worst pair
to improve a number you have already seen. Doing so silently converts a measurement into a
curve fit, and it is not detectable from the code afterwards, which is exactly why it is
forbidden.

If you believe a spec parameter is wrong, write it under **Uncertainties** and leave the
code as specified.

If something must change after a harness run — a genuine bug, not a disappointing number —
then: state it in the report, re-run the harness, and keep **both** ledger rows with the
reason. Never overwrite the first one.

---

## 8. Absolute rules

1. **Only ever create or edit these three files per strategy:** `research/<id>.py`,
   `research/tests/test_<id>_fixture.py`, `wave2/REPORT-<id>.md` — plus the two N5 files in
   `task/2026-August-week2/N5-fleet-completion/` (`VERDICTS.md`, `BATCH-<n>-REVIEW.md`).
   Batch 0 edits three fixtures and no modules.
2. **Never edit a shared file** — `contract_v2.py`, `position_engine.py`,
   `causal_structure.py`, `indicators.py`, `v2_harness.py`, `gates.py`, any `__init__.py`,
   the audit script, or another strategy's files. Not even to fix something genuinely
   broken. Write it in the batch review instead.
3. **Never widen the gates.** `src/system1/vetting/gates.py` defines what "good" means for
   the live system. It is not yours to touch, and the harness deliberately imports it rather
   than restating it.
4. **Database access is read-only and only through the harness.** You may run
   `v2_harness`, `audit_wave2.py` and `verify_wave2.py`, which read prices through
   `research_data.load_ohlcv_readonly`. You may not write to any table, run DDL, or open a
   connection from inside a strategy. A strategy receives frames as an argument and returns
   orders; that is the whole interface.
5. **Never invent data.** No proxies, no stubs, no hardcoded series, no substituted pair.
6. **Never touch the 19 excluded strategies** in §2.
7. If you genuinely cannot proceed, record `BLOCKED — <one sentence>` in the ledger and move
   to the next strategy. Do not guess.

---

## 9. Definition of done

```bash
black --check src/layer0/strategies/research/
python -m pytest src/layer0/strategies -q
python task/2026-August-week1/wave2/audit_wave2.py         # full run, all 51 ids
python -m src.layer0.strategies.v2_harness --list
```

Done means:

- **47 of 51** strategies exist and are `PASS` in the audit (51 − the 4 that must not be
  built). The audit prints `BLOCKED-OK` for those 4; that is correct, not a failure.
- **46 of 47** have a harness verdict in `results/research/<id>/` and a ledger row
  (`nzdjpy_median_ma_retrace` is UNMEASURABLE and has a row but no verdict).
- Every one of the 29 has a `REPORT-<id>.md`.
- Four `BATCH-<n>-REVIEW.md` files exist.

Then write `task/2026-August-week2/N5-fleet-completion/SUMMARY.md`:

1. The full ledger, sorted by pooled Sharpe descending.
2. Counts: QUALIFIED / FAIL / INSUFFICIENT / UNMEASURABLE / BLOCKED.
3. **Every QUALIFIED strategy, in detail** — its cells, its dispersion, its trade count, and
   whether the pooled pass rests on one pair or several. A pooled pass with one passing cell
   out of five is a concentration artifact, and the harness already flags it under
   `dispersion.warning`. Say so if it applies.
4. The full **DECISION** list from all four batches, gathered in one place. *This is the most
   valuable thing you produce* — it is what a human reviewer must rule on.
5. Anything systematic you found, including in the 18 that were already finished.

Report the result as it came out. "0 qualifiers out of 47" is a complete and successful
outcome, and is the outcome the existing evidence predicts.
