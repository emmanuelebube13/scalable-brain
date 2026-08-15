# Wave 2 — continuation handoff: the 30 unbuilt strategies

Paste this whole file as the prompt. It is self-contained.

**Repo root (all paths relative to it):** `/home/emmanuel/Documents/Scalable_Brain/scalable-brain`

**Every command below assumes you have first run:**

```bash
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain
source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate
```

---

## 0. Where the project stands

51 published forex strategies were each written up as an exhaustive English spec. Your job is
to turn the remaining ones into runnable, auditable Python. This is **translation, not
design** — the spec decides everything.

| | count |
|---|---|
| Specs written | 51 |
| Must **not** be built (external data absent) | 4 |
| Buildable target | 46 |
| Built and accepted so far | 16 |
| **Your assignment — never started** | **30** |

Of the 16 built, **zero** pass the qualification gates. That is expected — published retail
strategies rarely survive honest out-of-sample testing with costs. Your job is not to find
winners. It is to produce **honest measurements**, so that whatever edge exists is visible
and whatever doesn't is disproven rather than assumed.

## 1. Your assignment — exactly these 30

```
ema_cross_h4_filter_bot     h4_crossover_21_89_macd    liquidity_grab_fade
liquidity_sweep_ob          long_wick_pinbar_8ema      ma_crossover_swing
macd_divergence             mtf_swing_weekly_pivots    nnfx_backtrader
nzdjpy_median_ma_retrace    outside_hma_klinger        pinbar_key_level_50pct
pinbar_nose_eyes            precision_swing            psar_gbpjpy_daily
reps_donchian_pyramiding    retail_sentiment_fade      riding_trend_retracement
smart_money_swing           smash_days                 smashing_forex_2
strong_weak_analysis        sunday_breakout            three_candle_swing_reversal
trending_retracement_daily  vshape_swing_breakout      weekly_day_reversal_ea
weekly_gap_fade             weekly_range_reversal      xard_ma_cross_daily_open
```

### Do not touch — 4 strategies that must never be built

`currency_value_ppp`, `usd_carry_basket`, `three_ducks`, `financial_regime_index`. They
depend on data that does not exist here (interest rates, OECD PPP, nine macro series, M5
bars). **Do not invent a proxy, a stub, or a hardcoded series.** Creating any file for these
is a failure.

### Do not touch — the 16 already accepted

`adx_trend_pullback_ea`, `amazing_crossover`, `bb_midline_break`, `currency_momentum_factor`,
`daily_fib_retracement`, `demark_fractal_breakout`, `double_bottom_measured_move`,
`engulfing_broken_level`, `h4_box_breakout`, `h4_forex_system`, `holy_grail_pullback`,
`inside_bar_continuation_ea`, `inside_bar_pinbar_combo`, `inside_bar_reversal`,
`janus_swing_system`, `kiss_h4`. Do not modify, reformat or "improve" them.

## 2. How to build one — read this first

**`task/2026-August-week1/wave2/RUN_BRIEF.md` is the authoring specification.** Read it in full before
writing anything. It covers what to read, the import style, the metadata convention, the hard
rules (no look-ahead, no parameter tuning, no shared-file edits), the golden-fixture
requirements and the exact verification commands. Everything in it binds you.

Per strategy you deliver three files:

| File | Path |
|---|---|
| Strategy | `src/layer0/strategies/research/<id>.py` |
| Golden fixture | `src/layer0/strategies/research/tests/test_<id>_fixture.py` |
| Report | `task/2026-August-week1/wave2/REPORT-<id>.md` |

Work **one strategy at a time, start to finish**, and append a line to
`task/2026-August-week1/wave2/PROGRESS.md` after each. Write each file in a single write operation — a
half-written file breaks the whole test suite for everything else.

### The known traps, learned the hard way

These are not hypothetical. Each one cost real work on this project:

1. **`ExitLeg(kind="trailing")` with `fraction < 1.0` is rejected by the engine.** Whole-position
   trailing (`fraction=1.0`, or `StopRule.trail_atr_multiple`) is supported, including a fixed
   `pips` distance. If your spec wants to trail only *part* of a position, stop and report it —
   four strategies silently produced zero trades this way.
2. **Do not declare the trail twice.** If you set `StopRule.trail_atr_multiple`, do not also add
   a trailing exit leg for the same mechanism. The StopRule wins; the leg is noise.
3. **Never `ctx.loc[ctx.index <= t]` for a context frame.** Bars are stamped at their OPEN, so
   that admits a bar that has not closed. Use `contract_v2.closed_context_frame`. This produced
   108 phantom orders in review, and **a passing fixture will not catch it.**
4. **Never import `indicators.detect_swing_points`** — it uses `center=True` and reads the
   future. Use `causal_structure.confirmed_swing_points` and friends.
5. **Your fixture's expected values must be derived by hand from the spec's formulas.** Do not
   run the code and paste what it printed — that asserts the code equals itself. This is
   checked automatically and cannot be bluffed (see §3, check 7).
6. **A strategy that emits no orders is rejected**, not "neutral" — the look-ahead probe cannot
   prove anything about a strategy that never fires.

## 3. Acceptance stage 1 — the audit

```bash
python task/2026-August-week1/wave2/audit_wave2.py --quick <id>   # while iterating
python task/2026-August-week1/wave2/audit_wave2.py <id>           # full, incl. database
```

Nine checks, stopping at the first failure:

| # | Check | Fails when |
|---|---|---|
| 1 | FILES | module or fixture missing / does not parse |
| 2 | BANNED | a future-reading pattern in the module |
| 3 | CONTEXT | unsafe second-timeframe read |
| 4 | META | `strategy_id` mismatch, or no pairs declared |
| 5 | FIXTURE | < 30 hand-written price literals; no trade-plan assertions; no look-ahead call |
| 5b | REVIEWABLE | < 4 tests, < 8 comment lines showing the arithmetic, or no exit-fraction assertion |
| 6 | TESTS | the fixture does not pass |
| 7 | **TEETH** | the fixture still passes when the strategy is sabotaged to emit nothing |
| 8 | REALDATA | the look-ahead probe fails on 10 years of real prices |
| 9 | **TRADES** | the engine admits none of the orders — zero trades, so it can never qualify |

Aim for `PASS <id>`. Checks 7 and 9 are the ones that catch work which merely *looks* finished.

## 4. Acceptance stage 2 — qualification and risk audit

Once a strategy passes the audit, measure it:

```bash
python -m src.layer0.strategies.v2_harness <id>            # full fidelity (H1 fills)
python -m src.layer0.strategies.v2_harness <id> --no-h1    # faster, less faithful
python task/2026-August-week1/wave2/risk_audit.py <id>
```

`v2_harness` reports the gate metrics; `risk_audit.py` stress-tests whether the number means
anything. **Record both in the strategy's report.** A strategy is not "done" because it
passes the gates, and not "failed" because it doesn't — it is done when it has an honest
measurement plus an honest audit.

### What the risk audit checks, and why

A pooled Profit Factor is a scalar that hides how it was earned. The audit asks what the
scalar cannot:

1. **Outlier dependence** — recompute with the top 2% winners and bottom 1% losers removed. If
   PF falls below 1.10, the "edge" was a handful of trades: `OUTLIER_DEPENDENT`. Mean-R far
   above median-R means single-event harvesting, not a repeatable edge.
2. **Temporal consistency** — at least **65% of walk-forward folds** must be net positive. If
   one fold carries >40% of all fold profit, the edge is one regime, not a strategy:
   `REGIME_CONCENTRATION`.
3. **Drawdown and fat tails** — longest underwater stretch, share of the series spent
   underwater (>50% ⇒ `PERSISTENTLY_UNDERWATER`), and the three worst consecutive-loss runs.
   A strategy that is underwater 96% of the time is untradeable regardless of its final PF.
4. **Intrabar path fidelity** — native-bar vs H1-resolved. When one bar contains both the stop
   and the target, native resolution has to guess and the guess flatters the strategy. Sharpe
   dropping >0.4 or PF >0.3 under H1 ⇒ `INTRABAR_EXECUTION_BIAS`. **This requires a run
   WITHOUT `--no-h1`.**
5. **Verdict** — `ROBUST` · `MARGINAL` · `FRAGILE_OUTLIER_DRIVEN` · `REGIME_CONCENTRATED` ·
   `REJECT`, with three diagnostic bullets.

**Known limitation, stated so nobody over-reads the output:** per-trade entry timestamps are
not persisted — only fold windows. So calendar-cluster concentration is approximated at
**fold** level (6-month windows), and drawdown duration is counted in **trades**, not days.
Adding `entry_time` to the per-trade record in `v2_harness._fold_attribute` would make the
calendar-exact versions possible; that is a worthwhile small task if anyone wants it.

## 5. Absolute rules

1. Only ever create/edit your three files per strategy.
2. **Never edit a shared file** — `contract_v2.py`, `position_engine.py`, `causal_structure.py`,
   `indicators.py`, `v2_harness.py`, any `__init__.py`, or another strategy's files. Not even
   to fix something genuinely broken. Report it instead.
3. Never read the database from a strategy. It receives frames and returns orders.
4. Never change a parameter the spec gives, even if it looks wrong. Say so in the report.
5. Never weaken a fixture assertion to make a test pass. If code and hand arithmetic disagree,
   one of them contradicts the spec — find out which.
6. If genuinely blocked, write `BLOCKED — <reason>` in `PROGRESS.md` and move to the next
   strategy. Do not guess, and do not invent data.

## 6. Judgement calls

If the spec genuinely does not cover something, take the **most conservative** reading (the
one that trades less or loses more), implement it, and list it under **Uncertainties** in your
report. Do not resolve it silently. That list is the most valuable thing you produce — it is
what a human reviewer must rule on.

## 7. When you are done

```bash
black --check src/layer0/strategies/research/
python -m pytest src/layer0/strategies -q
python task/2026-August-week1/wave2/audit_wave2.py
python task/2026-August-week1/wave2/risk_audit.py
```

Then write a summary in `PROGRESS.md`: how many you completed, which are BLOCKED and why, and
every **Uncertainty** gathered into one list.

## 8. Worked references

- Strategy + fixture + report, all accepted: `bb_midline_break` (all three files).
- The Wave-1 example with four numbered notes on the easy-to-get-wrong parts:
  `src/layer0/strategies/research/reference_pullback_continuation.py`.
- Project history, every hand correction and why: `task/2026-August-week1/wave2/STATE.md`.
