# N5 — fleet completion summary

**Written 2026-08-16.** Covers the 29 strategies assigned in `GEMINI_BRIEF.md` (batches 0–4)
and, where it matters, the 18 that were finished before N5 started.

Work split across two sessions: batches 0–2 and part of 3–4 were built on 2026-08-15; that
session stopped mid-`reps_donchian_pyramiding` without writing its batch reviews. The
remainder — `reps_donchian_pyramiding` (rebuilt), `strong_weak_analysis`,
`weekly_range_reversal`, `retail_sentiment_fade`, `sunday_breakout`, `weekly_gap_fade` —
plus both missing batch reviews and this summary were completed on 2026-08-16.

---

## 1. The ledger, sorted by pooled Sharpe

| strategy_id | gran | pairs | cells | OOS trades | PF | Sharpe | MaxDD | verdict |
|---|---|--:|---|--:|--:|--:|--:|---|
| nnfx_backtrader | D1 | 5 | 0/5 | 113 | 1.63 | 0.94 | 12.37% | **QUALIFIED** (logged as PASS) |
| strong_weak_analysis | D1 | 5 | 0/5 | 295 | 1.24 | 0.36 | 7.94% | FAIL |
| ma_crossover_swing | D1 | 3 | 0/3 | 69 | 1.21 | 0.27 | 6.30% | FAIL |
| precision_swing | H4 | 5 | 0/5 | 543 | 1.04 | 0.19 | 27.39% | FAIL |
| macd_divergence | H4 | 5 | 0/5 | 441 | 1.10 | 0.16 | 5.82% | FAIL |
| weekly_day_reversal_ea | D1 | 5 | 0/5 | 150 | 1.08 | 0.15 | 8.57% | FAIL |
| liquidity_sweep_ob | H4 | 5 | 0/5 | 14 | 1.05 | 0.03 | 6.93% | FAIL |
| xard_ma_cross_daily_open | H1 | 5 | 0/5 | 2115 | 1.00 | 0.02 | 72.18% | FAIL |
| h4_crossover_21_89_macd | H4 | 5 | 0/5 | 200 | 1.00 | 0.01 | 12.36% | FAIL |
| psar_gbpjpy_daily | D1 | 1 | 0/0 | 0 | 0.00 | 0.00 | 0.00% | INSUFFICIENT |
| nzdjpy_median_ma_retrace | D1 | 1 | 0/0 | 0 | 0.00 | 0.00 | 0.00% | INSUFFICIENT |
| retail_sentiment_fade | D1 | 3 | — | 0 | — | — | — | UNMEASURABLE |
| trending_retracement_daily | D1 | 5 | 0/5 | 4 | 0.98 | −0.01 | 1.00% | FAIL |
| pinbar_nose_eyes | H4 | 5 | 0/5 | 14 | 0.92 | −0.05 | 3.07% | FAIL |
| long_wick_pinbar_8ema | D1 | 3 | 0/3 | 98 | 0.93 | −0.13 | 15.95% | FAIL |
| weekly_gap_fade | H1 | 5 | 0/5 | 944 | 0.96 | −0.18 | 11.91% | FAIL |
| mtf_swing_weekly_pivots | D1 | 5 | 0/5 | 233 | 0.93 | −0.20 | 19.27% | FAIL |
| pinbar_key_level_50pct | D1 | 5 | 0/5 | 53 | 0.76 | −0.23 | 25.34% | FAIL |
| three_candle_swing_reversal | D1 | 3 | 0/3 | 12 | 0.68 | −0.25 | 2.01% | FAIL |
| sunday_breakout | H4 | 1 | 0/1 | 344 | 0.90 | −0.28 | 40.10% | FAIL |
| reps_donchian_pyramiding | D1 | 5 | 0/5 | 241 | 0.81 | −0.38 | 20.25% | FAIL |
| kiss_h4 | H4 | 5 | 0/3 | 286 | 0.86 | −0.42 | 23.86% | FAIL † |
| kpl_donchian_breakout | D1 | 13 | 0/5 | 359 | 0.86 | −0.43 | 24.10% | FAIL † |
| smart_money_swing | H4 | 5 | 0/5 | 1246 | 0.92 | −0.44 | 33.74% | FAIL |
| janus_swing_system | D1 | 11 | 0/5 | 6 | 0.33 | −0.52 | 8.37% | INSUFFICIENT † |
| riding_trend_retracement | H4 | 5 | 0/5 | 40 | 0.57 | −0.55 | 24.62% | FAIL |
| vshape_swing_breakout | H4 | 5 | 0/5 | 2369 | 0.91 | −0.58 | 42.66% | FAIL |
| weekly_range_reversal | H1 | 5 | 0/5 | 45 | 0.41 | −0.88 | 24.88% | FAIL |
| liquidity_grab_fade | H1 | 5 | 0/5 | 737 | 0.66 | −0.96 | 19.69% | FAIL |
| outside_hma_klinger | H4 | 5 | 0/5 | 1291 | 0.85 | −1.07 | 56.06% | FAIL |
| smash_days | D1 | 5 | 0/5 | 2 | 0.00 | −3.60 | 0.37% | INSUFFICIENT |
| smashing_forex_2 | D1 | 5 | 0/5 | 1911 | 0.50 | −4.19 | 100.00% | FAIL |

† These three batch-0 rows are **not comparable with the rest of the table** — see §5, item 2.

## 2. Counts

| verdict | count |
|---|--:|
| QUALIFIED | **1** (`nnfx_backtrader`, logged in the ledger as "PASS" — see §3) |
| FAIL | 26 |
| INSUFFICIENT | 4 (`psar_gbpjpy_daily`, `nzdjpy_median_ma_retrace`, `janus_swing_system`, `smash_days`) |
| UNMEASURABLE | 1 (`retail_sentiment_fade`) |
| BLOCKED | 0 |
| **ledger rows** | **32** |

Fleet-wide, across all 51 specs:

- **4** must not be built (`currency_value_ppp`, `usd_carry_basket`, `three_ducks`,
  `financial_regime_index`) and correctly have no files — the audit reports `BLOCKED-OK`.
- **47** exist as module + golden fixture.
- **46** have a harness verdict artefact in `results/research/<id>/`;
  `retail_sentiment_fade` is the one that cannot produce one.
- **1** pooled pass and **1** passing cell (a different strategy — see §3) in 47 strategies.

Full audit, all 51 ids, `python task/2026-August-week1/wave2/audit_wave2.py`
(2026-08-16, real-data probe included):

```
{"ACCEPT": 42, "ACCEPT-UNPROVEN": 3, "BLOCKED-OK": 4, "REJECT": 2}
ACCEPT-UNPROVEN (no data for any declared pair): h4_box_breakout,
                nzdjpy_median_ma_retrace, psar_gbpjpy_daily
REJECT: daily_fib_retracement, retail_sentiment_fade
```

Both rejections are informative rather than sloppy, and both are covered in §5:
`daily_fib_retracement` (one of the "finished and accepted 15") emits 254 orders on EUR_USD
of which the engine admits **zero**, because its exit legs are fractional trailing legs;
`retail_sentiment_fade` is rejected for emitting nothing, which is the correct behaviour for
a strategy whose only non-price input does not exist.

## 3. The two results worth a human's attention

### 3a. The only passing CELL in the fleet — `demark_fractal_breakout` on USD_JPY (DEBUNKED 2026-08-16)

Not a qualifier (its pooled verdict fails at PF 1.02), and not part of N5 — it is one of the
finished 15 — but it was initially flagged as the single strongest measured result in the set. `results/research/demark_fractal_breakout/v2_evaluation_20260816T065324Z.json` showed:

| USD_JPY H4 cell | value | gate |
|---|--:|---|
| OOS trades | **610** | — |
| profit factor | 1.5101 | ≥ 1.50 ✓ |
| Sharpe | 1.1139 | ≥ 0.80 ✓ |
| max drawdown | 6.97% | ≤ 25% ✓ |
| win rate | 43.8% | ≥ 40% ✓ |
| recovery factor | 9.74 | ≥ 3.00 ✓ |
| OOS months | 84 | ≥ 60 ✓ |

**INVESTIGATION RESULT:** The edge was entirely a measurement artifact. The strategy's pip calculation contained a hardcoded bug that explicitly converted pip sizes using `EUR_USD` (`0.0001`), even when running on `USD_JPY`. Because USD_JPY requires a pip size of `0.01`, the buffers applied (4-pip entry, 3-pip stop) were exactly 100x too small (effectively 0 pips). 

Once the pip scaling was corrected and dynamically inferred by price magnitude, the harness was re-run (2026-08-16T21:13:16Z). **The edge completely vanished.** The strategy now fails all 5 cells with a pooled PF of 0.97 and negative Sharpe. The single passing cell in the entire fleet was a code defect, not a genuine pocket of edge.

### 3b. The one QUALIFIED strategy, in detail

**`nnfx_backtrader`** — `results/research/nnfx_backtrader/v2_evaluation_20260815T222805Z.json`
(re-confirmed byte-identical by the 2026-08-16T06:55:21Z sweep).

| pooled metric | value | gate |
|---|--:|---|
| profit factor | 1.6342 | ≥ 1.50 ✓ |
| Sharpe | 0.9361 | ≥ 0.80 ✓ |
| max drawdown | 12.37% | ≤ 25% ✓ |
| win rate | 45.13% | ≥ 40% ✓ |
| recovery factor | 3.7564 | ≥ 3.00 ✓ |
| OOS months | 83.9 | ≥ 60 ✓ |
| OOS trades | 113 | — |

`pooled.passed: true`, `failures: []`. **Three reasons not to treat this as a find yet:**

1. **The pooled pass rests on one pair.** `dispersion.n_passed = 0 of 5`. The best cell is
   **EUR_USD at PF 3.31 on 16 trades**; the worst is USD_CAD at PF 0.80 with a negative
   Sharpe. A pooled pass with zero passing cells is the concentration artefact the brief
   asks to be named explicitly, and `dispersion.warning` is `null`, so the harness's own
   flag did not fire.
2. **Two harness runs 73 seconds apart, only one ledger row.** `…222652Z.json` reports
   0 trades and `LOW_CONFIDENCE`; `…222805Z.json` reports the passing result. Nothing
   records what changed between them. Brief §7 requires both rows plus the reason.
3. **The module fails `black --check`,** so it did not pass the §4 Step 4 gate every other
   module passed. That is not evidence of a defect, but it means one verification step was
   skipped on the single most consequential file in the set.

Recommended before it is cited anywhere: reconcile the two runs, review the per-cell
r-multiples, and re-run with EUR_USD excluded to see what survives.

## 4. Every DECISION, all four batches

These are the points a human reviewer must rule on. Nothing here was resolved silently.

**Batch 0** — fixture reworks only; no decisions.

**Batch 1**
- `smash_days` — inside days excluded, since a smash day is defined by closing below the
  prior day's low.
- `macd_divergence` — TP/SL anchored to the decision close, not the (unknowable) fill.
- `pinbar_nose_eyes` — the source's `rolling(21, center=True)` swing logic replaced with
  `causal_structure.confirmed_swing_points`.
- `trending_retracement_daily` — the spec's adverse −25.0 pip breakeven offset is rejected
  by the engine; clamped to exact breakeven (0.0).
- `vshape_swing_breakout` — the wider of the two documented stops taken (V-swing extreme
  plus 1 pip).
- `ma_crossover_swing` — a 50/50 split between TP and time exit, because contract v2 cannot
  express "A or B closes the whole position".
- `weekly_day_reversal_ea` — take profit disabled entirely so 100% of the position rides
  the 23-hour time stop.
- `precision_swing` — PSAR acceleration capped at 0.02 (never accelerates), the literal
  reading of the spec's "(0.02|0.02)".

**Batch 2**
- `long_wick_pinbar_8ema` — trend slope evaluated as `EMA8[t] > EMA8[t-2]`.
- `liquidity_sweep_ob` — strict order-block sweep (wick penetrates, body closes inside),
  which cut the sample to 14 trades in ten years.
- `pinbar_key_level_50pct` — 50%-wick limit orders expire after 1 bar.
- `psar_gbpjpy_daily` — `["GBP_JPY"]` declared to satisfy contract validation despite the
  pair being absent, which is why its verdict is INSUFFICIENT.
- **`smashing_forex_2` — the spec was OVERRIDDEN**: its 50/50 fixed-target-plus-trailing
  runner is rejected by the position engine (`TRAILING_LEG_UNSUPPORTED` for fractional
  trailing legs), so the trailing runner was removed and the whole position exits at TP1.
  This is the only case in the fleet where a spec was changed to fit the engine; it turns a
  trend-runner into a fixed-target mean-reversion strategy, and its −4.19 Sharpe should be
  read with that in mind.
- `three_candle_swing_reversal` — stop at the exact 3-candle extreme, zero buffer.
- `xard_ma_cross_daily_open` — the daily open computed causally from trailing H1 bars.

**Batch 3**
- `strong_weak_analysis` — §3.5 fixes the tie-break as alphabetical but not which end of a
  tie is "worst"; one descending ranking is built and `worst` is its last entry.
- `strong_weak_analysis` — the strength-rank gate is **not applied at all**; what was
  measured is the trend-plus-pullback skeleton, which trades far more often than §4.1 would.
- `weekly_range_reversal` — §11's frequency estimate (10–35 trades/pair/year) is wrong by an
  order of magnitude; the measurement is ~1/pair/year. Nothing was widened to chase it.
- `weekly_range_reversal` — the 24-bar CCI arming window is the spec's invention (§10 #9)
  and is the most consequential undocumented parameter in that strategy.
- `retail_sentiment_fade` — implemented in full against the §3/§9 schema with the sentiment
  series injected; no price proxy and no degraded SMA-only mode.
- `retail_sentiment_fade` — the 24h publication lag is an assumption, not the vendor's
  documented cadence.

**Batch 4**
- `reps_donchian_pyramiding` — §3 and §4.2 disagree by one D1 bar on when a weekly breakout
  becomes usable; §3's mandated merge mechanics were implemented.
- `reps_donchian_pyramiding` — `context_granularities = ("H4",)`: the weekly frame is
  derived from D1 per §10 #3, so declaring a native W1 dependency would make the measurement
  depend on a feed the strategy never reads.
- `reps_donchian_pyramiding` — the H4 add-on window is counted in bars (≤12), which equals
  two sessions only when six H4 bars print per session.
- `sunday_breakout` — §10 #8's residual second-fill risk accepted rather than suppressed by
  a shorter expiry.
- `sunday_breakout` — the breakeven trigger banks 1% of the position at +2R, because a
  zero-size trigger leg is not expressible.
- `weekly_gap_fade` — the exit hour is fixed at 19:00 UTC year-round per §7, one hour before
  the summer session close and three before the winter one.
- `weekly_gap_fade` — the 5.0-pip gap threshold is looser than the author's 10–20 pip
  reality; not adjusted after seeing the result.
- `weekly_gap_fade` — the 5×ATR catastrophic stop makes this id's r-multiple scale
  incomparable with the rest of the fleet's.

## 4b. Definition of done — verified 2026-08-16

| check | result |
|---|---|
| `black --check src/layer0/strategies/research/` | **3 files would be reformatted**, none of them N5's: `nnfx_backtrader.py`, `test_smashing_forex_2_fixture.py`, `test_liquidity_grab_fade_fixture.py`. Not touched — rule 1. |
| `pytest src/layer0/strategies -q` | **411 passed** |
| `audit_wave2.py` (full, 51 ids) | ACCEPT 42 · ACCEPT-UNPROVEN 3 · BLOCKED-OK 4 · REJECT 2 |
| `v2_harness --list` | 48 discoverable strategies |
| harness verdict + ledger row | 46 of 47; `retail_sentiment_fade` cannot produce one |
| `REPORT-<id>.md` for each of the 29 | complete (38 reports in `wave2/`) |
| four `BATCH-<n>-REVIEW.md` | complete (0, 1, 2 from 2026-08-15; 3 and 4 written 2026-08-16) |

One pre-existing gap, unrelated to N5 and unchanged by it: **10 of the 15 strategies
finished before N5 have no `REPORT-<id>.md`** — `adx_trend_pullback_ea`,
`amazing_crossover`, `currency_momentum_factor`, `daily_fib_retracement`,
`demark_fractal_breakout`, `double_bottom_measured_move`, `ema_cross_h4_filter_bot`,
`engulfing_broken_level`, `holy_grail_pullback`, `inside_bar_reversal`. `wave2/STATE.md`
records why (agents could not write `.md` files and the orchestrator lost the returned
text). Two of those ten are the strategies §3a and §5 item 11 are about, so the gap is not
harmless.

## 5. Systematic findings, including in the 18 already finished

**1. `reps_donchian_pyramiding` sat in the tree for a day emitting nothing, and broke the
test suite while doing it.** Every `OrderIntent` it built was invalid at construction
(`entry="market"` with `entry_price=0.0`; `ExitLeg(kind="trailing", price=0.0)`), so every
emission path raised. Its fixture never reached one and failed with a `LookAheadError`,
which took `pytest src/layer0/strategies` from green to 5 failures repo-wide. Rebuilt from
the spec on 2026-08-16; the suite is now **411 passed**.

**2. Three ledger rows are native-resolution numbers in an H1-resolved table.** The batch-0
rows for `kiss_h4`, `janus_swing_system` and `kpl_donchian_breakout` were carried over from
runs made on 2026-08-13/14 that contain **only** the `native` resolution. Every other row
comes from a run containing both `native` and `h1`, and the pooled verdict prefers the
H1-resolved series (CONTRACT §5). The gap is not cosmetic: `kpl_donchian_breakout` is
**359 trades / PF 0.86 / Sharpe −0.43** in the ledger and **752 trades / PF 0.95 /
Sharpe −0.20** in its current artefact. The three rows are marked † in §1 and should be
re-stated from the 2026-08-16 artefacts before anyone compares them with the rest.

**3. A bulk harness sweep ran at 2026-08-16T06:52–06:56Z over every strategy** and is now
the newest artefact for 44 ids. For all but the three above it reproduces the ledger
exactly, which is a useful independent confirmation — but nothing in the task folder records
who ran it or why, and the brief's "run the harness exactly once per finished strategy" rule
means a re-run should have been minuted.

**4. Four of the 46 measured strategies produced no OOS trades at all, and four more
produced fewer than five.** Zero: `daily_fib_retracement` (5 cells, 0 trades),
`h4_box_breakout` (0 cells — both its declared pairs are absent), `psar_gbpjpy_daily`,
`nzdjpy_median_ma_retrace`. Under five: `smash_days` (2), `inside_bar_pinbar_combo` (2),
`engulfing_broken_level` (3), `holy_grail_pullback` (4), `trending_retracement_daily` (4).
Per brief §6.3 these are **measurement failures, not verdicts** — nine strategies, a fifth of
the fleet, have not actually been tested. Two of them (`daily_fib_retracement`,
`h4_box_breakout`) are in the "finished and accepted 15" and were never flagged.

**5. Cross-sectional strategies cannot be measured by this harness at all.**
`generate_orders` receives one pair at a time with no pair identity, so
`currency_momentum_factor` (row 43) and `strong_weak_analysis` (row 50) both had their
headline mechanism — a cross-pair ranking — replaced by the single-pair-reachable remainder,
with the ranking kept as pure, unreachable, fixture-pinned helper functions. Their verdicts
say nothing about the mechanism their authors claimed. Fixing this is a harness change (pass
a pair-keyed frame bundle), not a strategy change.

**6. The audit has no category for "built correctly, input feed absent".**
`nzdjpy_median_ma_retrace` (missing pair) is ACCEPTed with `REALDATA: SKIP`, while
`retail_sentiment_fade` (missing non-price feed, pairs present) is REJECTed at REALDATA by
`assert_no_lookahead_v2`'s "emits no orders anywhere" rule. Same condition, opposite
outcome, purely because of which input is missing. A `BLOCKED-FEED` verdict beside
`BLOCKED-OK` would close it. Related: `v2_harness` raises an unhandled `LookAheadError` in
that case rather than recording a skipped cell.

**7. Multi-timeframe context is usable only up to the decision bar's OPEN, but every spec
says "close".** The truncation probe cuts context frames at the open of the last surviving
primary bar, so any strategy reading context from inside its own decision bar emits orders
the truncated re-run cannot reproduce. All MTF strategies in the fleet therefore anchor
context one primary bar earlier than their spec's wording. The next round of specs should
say "open".

**8. Weekly boundaries cannot be detected by literal timestamp on this feed.** Measured on
two years of EUR_USD H1: **68 of 108 week openings are stamped Sunday 21:00 UTC and 40 are
stamped 22:00** (DST). Specs describing "the bar stamped Sunday 21:00" would silently
discard 37% of the sample. `sunday_breakout` and `weekly_gap_fade` detect the boundary
structurally instead.

**9. Contract v2 has no OCO, and it is now a measured effect, not a theoretical one.**
`sunday_breakout` emits paired stop orders it cannot cancel: 344 trades in ~7 OOS years on
one pair (≈49/year) against an intended ≤52 with most weeks unfilled — roughly 40% of its
trades are sibling fills the source forbids.

**11. One of the "finished and accepted 15" cannot trade at all.** `daily_fib_retracement`
emits 254 orders on EUR_USD and the position engine admits **none** of them:
`TRAILING_LEG_UNSUPPORTED`, the fractional-trailing-leg limitation that also forced the
`smashing_forex_2` spec override. Its harness artefact duly reports 0 OOS trades. It was
accepted by an earlier audit pass because the `TRADES` check post-dates it. Whatever is done
about it, it must not be counted among the 47 measured strategies — nothing about it has
been measured.

**12. The failure is broad, consistent, and not a sampling accident.** Excluding the nine
untested ids, the measured fleet spans 45 to 3,979 OOS trades per strategy and lands almost
uniformly at 0.4 ≤ PF ≤ 1.24. The two largest samples in the whole set — `amazing_crossover`
(3,979 trades, PF 0.91) and `adx_trend_pullback_ea` (3,442, PF 0.93) — are conclusive
small-negative-edge results, not noise. **47 strategies, 1 pooled pass on 113 trades, and 1
passing cell out of roughly 230.** That is the finding this exercise was built to produce,
and it is a complete one.
