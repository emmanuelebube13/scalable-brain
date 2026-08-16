# BATCH-4 REVIEW

**Batch 4 (GEMINI_BRIEF §2, the multi-timeframe strategies — "highest risk"):**
`h4_crossover_21_89_macd`, `mtf_swing_weekly_pivots`, `riding_trend_retracement`,
`smart_money_swing`, `sunday_breakout`, `weekly_gap_fade`, `reps_donchian_pyramiding`.

Four (`h4_crossover_21_89_macd`, `mtf_swing_weekly_pivots`, `riding_trend_retracement`,
`smart_money_swing`) were built and measured in the 2026-08-15 session and recorded in the
ledger under batch 3; the session stopped mid-`reps_donchian_pyramiding` without writing
this review. `reps_donchian_pyramiding` was rebuilt and the remaining two were built and
measured 2026-08-16.

## Audit results

Full run (real-data probe included), `audit_wave2.py`, 2026-08-16 — all seven ACCEPT:

```
PASS h4_crossover_21_89_macd
PASS mtf_swing_weekly_pivots
PASS riding_trend_retracement
PASS smart_money_swing
PASS sunday_breakout
PASS weekly_gap_fade
PASS reps_donchian_pyramiding
```

## Ledger rows

```
| 3 | h4_crossover_21_89_macd | H4 | 5 | 0/5 | 200 | 1.00 | 0.01 | 12.36% | FAIL | |
| 3 | mtf_swing_weekly_pivots | D1 | 5 | 0/5 | 233 | 0.93 | -0.20 | 19.27% | FAIL | |
| 3 | riding_trend_retracement | H4 | 5 | 0/5 | 40 | 0.57 | -0.55 | 24.62% | FAIL | |
| 3 | smart_money_swing | H4 | 5 | 0/5 | 1246 | 0.92 | -0.44 | 33.74% | FAIL | |
| 4 | reps_donchian_pyramiding | D1 | 5 | 0/5 | 241 | 0.81 | -0.38 | 20.25% | FAIL | rebuilt 2026-08-16 |
| 4 | sunday_breakout | H4 | 1 | 0/1 | 344 | 0.90 | -0.28 | 40.10% | FAIL | only GBP_USD exists |
| 4 | weekly_gap_fade | H1 | 5 | 0/5 | 944 | 0.96 | -0.18 | 11.91% | FAIL | largest sample in the fleet |
```

## Systematic issues

**1. `reps_donchian_pyramiding` had never emitted a single order, and nothing caught it
until the whole suite was run.** The version on disk before 2026-08-16 constructed every
`OrderIntent` with `entry="market", entry_price=0.0` (the contract requires `None`) and
every `ExitLeg` with `kind="trailing", price=0.0` (a trailing leg must not carry a price).
Both raise `ValueError` at construction, so every emission path was dead. Its fixture never
reached one, and because the session ended before the batch review, the module sat in the
tree with a **failing test file** that broke `pytest src/layer0/strategies` repo-wide. The
lesson is the one already in `wave2/STATE.md` from run 1, in a new costume: a strategy is
not finished when its file parses and its fixture is written — it is finished when the
fixture is green and the audit says PASS. It was rebuilt from the spec rather than patched;
there was no prior verdict to preserve.

**2. Multi-timeframe context is usable only up to the decision bar's OPEN, and the spec
language says "close" every time.** Three of this batch's specs (`reps_donchian_pyramiding`
§6/§4.3, `sunday_breakout` §3, `weekly_gap_fade` §2) describe context values as knowable "at
the close of the decision bar". They are not usable there. `assert_no_lookahead_v2`
truncates a context frame to the bars that closed by the **open** of the last surviving
primary bar, so any strategy reading context data from inside the decision bar's own span
emits an order the truncated re-run cannot reproduce, and is rejected. Every MTF strategy in
this fleet therefore anchors context one primary bar earlier than its spec's wording. This
is not a defect in any one strategy — it is a systematic gap between how the specs were
written and what the probe enforces, and the next batch of specs should say "open".

**3. The absence of OCO is now measurable, not theoretical.** `sunday_breakout` emits a
buy stop and a sell stop each week and cannot cancel one when the other fills (§10 #8).
Result: **344 trades in ~7 OOS years on one pair ≈ 49/year**, against §11's estimate of
15–35 filled trades per year under the intended one-per-week rule. Roughly 40% of its trades
are the sibling fills the source forbids, concentrated in whipsaw weeks. If any breakout
strategy is ever promoted, contract v2 needs a cancel-on-fill / OCO group id; a
strategy-level workaround would have to shorten the pending expiry and would measure a
different strategy.

**4. Weekly-boundary detection by literal timestamp is wrong on this feed, and silently so.**
`weekly_gap_fade` §4 step 1 (and `sunday_breakout` §9) describe the week's opening bar as
"stamped Sunday 21:00 UTC". Measured on two years of EUR_USD H1: **68 of 108 week openings
are stamped 21:00 and 40 are stamped 22:00** (DST), with the predecessor at Friday 20:00 or
21:00 correspondingly. A literal stamp test would have vetoed every winter week — about 37%
of the sample — and produced a plausible-looking result from 63% of the data. Both
strategies detect the boundary structurally instead (session break + Sunday bar + Friday
predecessor). Any future strategy keying on session boundaries must do the same.

**5. Nothing in this batch came close.** Seven strategies, 3,208 pooled OOS trades, zero
qualifiers, and the best pooled profit factor is `h4_crossover_21_89_macd` at exactly 1.00.
The two largest samples (`weekly_gap_fade` 944 trades, `sunday_breakout` 344) are the two
most conclusive failures: they are not thin-sample noise, they are measured small negative
edges after the F10 cost model.

**6. Formatting and suite state.** `pytest src/layer0/strategies -q` → **411 passed** (the
`reps_donchian_pyramiding` rebuild cleared the 5 failures that were blocking the suite).
`black --check src/layer0/strategies/research/` still fails on three files belonging to
other strategies (`nnfx_backtrader.py`, `test_smashing_forex_2_fixture.py`,
`test_liquidity_grab_fade_fixture.py`) — reported, not touched (rule 1).
`python -m src.layer0.strategies.v2_harness --list` reports **48 discoverable strategies**.

## DECISIONs recorded in this batch

- **`reps_donchian_pyramiding`** — §3 and §4.2 disagree by one D1 bar on when a weekly
  breakout becomes usable. §3's mandated mechanics (shift one weekly interval,
  `allow_exact_matches=False`) were implemented; §4.2's reading would move every entry one
  session earlier and change every number.
- **`reps_donchian_pyramiding`** — `context_granularities = ("H4",)` rather than
  `("W1", "H4")`: the weekly frame is derived from D1 per §10 #3, and declaring a native W1
  dependency the strategy never reads would make the measurement depend on a feed it does
  not use.
- **`reps_donchian_pyramiding`** — the H4 add-on window is defined in bars (≤12), which is
  two sessions only when the broker prints six H4 bars per session.
- **`sunday_breakout`** — the residual second-fill risk of §10 #8 was accepted rather than
  suppressed by a shorter expiry; it is visible in the trade count.
- **`sunday_breakout`** — the `BE_2R` breakeven trigger banks 1% of the position at +2R,
  because a zero-size trigger leg is not expressible.
- **`weekly_gap_fade`** — the exit hour is fixed at 19:00 UTC year-round per §7, which is one
  hour before the summer session close and three before the winter one.
- **`weekly_gap_fade`** — the 5.0-pip gap threshold (5 × the 1.0-pip cost-model proxy) is
  looser than the author's 10–20 pip reality; it was not adjusted after seeing the result.
- **`weekly_gap_fade`** — the 5×ATR catastrophic stop makes this strategy's r-multiple scale
  incomparable with the rest of the fleet's; PF and win rate are comparable, Sharpe and
  recovery factor are not.

## Shared-file problems found and not touched

- No OCO / cancel-on-fill in contract v2 (issue 3) — a contract extension, not a strategy fix.
- `black` failures in three other strategies' files (issue 6).
