# REPORT-bb_midline_break

> Transcribed verbatim by the orchestrator from the authoring agent's returned text. The
> agent could not write this file itself: this harness refuses subagent writes to `.md`
> report files, and it correctly did not route around the guard.

**Strategy:** `src/layer0/strategies/research/bb_midline_break.py` — class `BollingerMidlineBreak`
**Fixture:** `src/layer0/strategies/research/tests/test_bb_midline_break_fixture.py`
**Spec:** `task/2026-W32/fleet/upload/wave2/specs/SPEC-bb_midline_break.md` (CSV row 28)

| Check | Result |
|---|---|
| `black` (both files) | pass |
| `mypy --ignore-missing-imports --follow-imports=silent` (strategy only) | `Success: no issues found in 1 source file` |
| `pytest test_bb_midline_break_fixture.py -q` | **11 passed** |
| Central real-data `assert_no_lookahead_v2` (orchestrator) | **PASS** on all 5 pairs — 235/253/213/259/282 orders, two-sided |

---

## Implemented

Single-frame H4 `StrategyV2`. Everything is a vectorised trailing computation followed by
one forward pass over bars `[warmup_bars, n)`; nothing reads past bar `t`.

- **§3 indicators** — `indicators.bollinger_bands(Close, 20, 2.0)` used as-is including its
  `rolling().std()` (ddof=1) convention, per §10 #6. Body = `|Close - Open|`;
  `avg_body = indicators.sma(body, 20)` with the window **including bar t** (§10 #10).
  No swing/pivot detection at all, so `causal_structure` is not imported and
  `detect_swing_points` is never touched (§3, §9).
- **§4.1 / §5.1 band-touch state** — `(Low <= lower).astype(float).rolling(5).max().shift(1)`
  (and the `High >= upper` mirror). Each bar `j` is judged against its **own**
  contemporaneous band value; the `.shift(1)` is what makes bar `t` unable to serve as its
  own touch bar (§9, §10 #2). NaN bands compare `False`, so warmup never manufactures a touch.
- **§4.2 / §5.2** midline cross evaluated as the literal two-part inequality on
  `close[t], mid[t], close[t-1], mid[t-1]`.
- **§4.3–§4.5 / §5.3–§5.5** big body (`> 1.5 x avg_body`), extreme-quartile close, and the
  prose-required candle direction, all as written.
- **§4/§5 entry** — `entry="market"`, `entry_price=None`, `expires_after_bars=None`,
  `decision_close=close[t]` carried for the engine's admission record (§10 #8).
- **§6 stop** — `StopRule(price=low[t])` long / `high[t]` short, zero buffer (§10 #5), no
  breakeven, no trail. `R = |close[t] - stop|`.
- **§7 exit** — one `ExitLeg(fraction=1.0, kind="take_profit", label="TP1")` at `C ± 1.5 R`,
  anchored to the decision close. Fractions sum to exactly 1.0. This is the spec's
  acknowledged **substitute** for the documented midline-crossback exit, which contract v2
  cannot express (§10 #4) — the artefact that gets measured downstream is a fixed-1.5R
  variant, not the literal published strategy, and that fidelity loss must be quoted in any
  backtest write-up.

**Where the spec was thinner than the code needed** (all three under Uncertainties; none
changes a documented rule):

1. `warmup_bars` — the spec states no value. Derived, not chosen:
   `BB_PERIOD + TOUCH_LOOKBACK = 25`. The first bar whose every input is defined is
   `BB_PERIOD - 1 + TOUCH_LOOKBACK = 24`, so 25 starts one bar past that.
2. A `risk > 0` guard before emitting. §6 argues `R >= 0.75 x range[t] > 0` always, so the
   guard is unreachable in practice (a zero-range bar has body 0 and already fails §4.3); it
   exists so a degenerate/synthetic bar is skipped rather than emitted with `R <= 0`.
3. `tag` and `strategy_id` string values — cosmetic, not specified.

The reference's four NOTES are each addressed in the module docstring with the reason they
do or do not bind (NOTE 1: no context frame exists, so `closed_context_frame` is moot;
NOTE 2: no swing structure; NOTE 3: market entries have no pending level; NOTE 4: no
breakeven leg is named).

## Deviations

- **None functional.** The only textual change: the `hypothesis` string is §1 with `2σ`
  written `2-sigma` and the em-dashes written as ASCII hyphens, so the module stays
  ASCII-clean. Wording is otherwise verbatim and clears the contract's word-count gate.

## Uncertainties (reviewer decides — not resolved silently)

1. **`pairs` = the 5 live pairs only** (`EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD`).
   §2 lists 8 further pairs as "**pending** — Wave-1 additions, NOT gaps", and the source
   asks for "all forex majors and minors". The run brief's Metadata rule is explicit
   ("never a pair the spec lists as missing/pending"), so I excluded them — but the spec's
   own intent is clearly the 13-pair universe. **If the Wave-1 pairs have since landed in
   `fact_market_prices`, this list should be widened to 13 before the backtest runs**,
   otherwise the strategy is measured on 5 pairs instead of 13. One-line change; the
   reviewer's call, not mine.
2. **`granularities=["H4"]` only.** §2/§10 #9 sanction D1 and W1 as *alternative primaries*
   for variant runs. One `StrategyMetadataV2` cannot express "three separate single-frame
   variants", and pooling them would be granularity-mixing, which §10 #9 rejects. So the
   D1/W1 variants are simply not declared here. If the fleet wants them, they are separate
   registrations (subclasses overriding `primary_granularity`), and the W1 one is
   statistically vacuous by §10 #9's own arithmetic.
3. **`warmup_bars = 25`** as derived above. Low-stakes (real H4 history is ~30k bars), but it
   is a number the spec did not give.
4. **Band value NaN ⇒ no touch.** During warmup the bands are undefined; I treat that as
   "no touch" rather than skipping the bar by an explicit NaN test. Same outcome, but it is
   an implicit reading of §4.1 rather than a stated one.
5. **Not load-bearing but worth flagging:** because the entry is `market`
   (`entry_price=None`), `OrderIntent.__post_init__` performs **no** stop-below-entry or
   TP-beyond-entry validation. Those invariants are therefore only enforced by my fixture,
   not by the contract. Nothing to fix — just so the reviewer knows where the guarantee
   actually lives for every market-entry strategy in the fleet.

## Fixture rationale

Two hand-built 20-bar H4 series (**40 literal OHLC bars total**), because §4.2/§5.2 are
mutually exclusive (`close > mid` vs `close < mid`) and one series cannot fire both sides.

**The design trick that makes it hand-checkable:** every bar except the breakout bar has a
body of 8 or 10 pips against an average body of 8–21 pips, so **exactly one bar in twenty
clears the §4.3 big-body gate**. The "exactly one order" assertions therefore need no band
arithmetic on the 19 quiet bars; bands only have to be evaluated at bar 11 (the touch) and
bar 12 (the breakout), and that arithmetic is written out in the file.

- **Long series** — a clean 10-pip/bar linear downtrend (bars 0–10, 8-pip bearish bodies,
  3-pip wicks: for a 5-bar linear ramp `lower[j] = close[j] - 11.62 pips` while
  `low[j] = close[j] - 3 pips`, so no touch and no big body anywhere). Bar 11 is a small
  bearish candle with a 25-pip lower wick: `mid = 1.11090`, `std = sqrt(305) = 17.46 pips`,
  `lower = 1.10741`, `low = 1.10600` ⇒ **§4.1 touch, 14 pips of margin** — and its body of
  8 pips vs a 12-pip threshold means the touch bar itself emits nothing. Bar 12 is a 65-pip
  bullish engulfing candle: `mid = 1.11130`, `close = 1.11500 > mid`,
  `close[11] = 1.10850 <= mid[11] = 1.11090`, body 65 > 29.1, close in the top quartile
  (`1.11500 >= 1.11340`), bullish ⇒ **one long order**. Bars 13–19 are gentle 10-pip
  follow-through that all fail §4.3, proving the strategy does not re-fire while the move
  runs. Hand-derived plan: `C = 1.11500`, `S = low = 1.10800`, `R = 0.00700`,
  `TP1 = C + 1.5R = 1.12550`.
- **Short series** — the exact reflection about 1.1000 (`p -> 2.2000 - p`, High/Low swapped).
  Reflection reflects every rolling mean and leaves every rolling std unchanged, so
  `mid' = 2.2000 - mid` and `upper' = 2.2000 - lower`: each §4 inequality becomes its §5
  mirror with the identical margin, and the whole short case is derivable from the long
  arithmetic. Fires **one short** at bar 12: `C = 1.08500`, `S = high = 1.09200`,
  `R = 0.00700`, `TP1 = C - 1.5R = 1.07450`.
- **Two negative tests**, each a single-field edit of `BARS_LONG` with the change stated,
  and each verified non-vacuous (a variant blind to the rule under test *would* fire):
  - touch removed (bar 11 low `1.1060 -> 1.1097`) ⇒ **0 orders** (§4.1 is a real gate).
  - touch moved onto the breakout bar (bar 11 low `-> 1.1097`, bar 12 low `-> 1.1060`, which
    puts bar 12's own low under `lower[12] = 1.10642`) ⇒ **0 orders**. This is the test for
    §9 / §10 #2 — an implementation missing the `.shift(1)` fires here.
- `assert_no_lookahead_v2` runs on **both** series. With n = 20 and `warmup_bars = 10` the
  windowed probes cover no bars, so the contract falls through to its FIX-S1-013 path and
  re-emits at the actual firing bar from a truncated `[0:13]` prefix — a stronger check than
  the windowed comparison, and it only works because the fixture genuinely fires.
- Fixture subclass shrinks **periods only**: `BB_PERIOD` and `BODY_PERIOD` 20 → 5 (20 bars
  cannot warm a 20-period band). `TOUCH_LOOKBACK=5`, `BODY_MULTIPLE=1.5`,
  `CLOSE_QUARTILE=0.25`, `TP_R_MULTIPLE=1.5` are production values, untouched — those are
  logic, not lookback. `warmup_bars` is derived, so it follows to 10 by itself.

## Shared files: found, deliberately NOT edited

- `src/layer0/data_access/indicators.py:452` `detect_swing_points` still uses `center=True`
  (the known look-ahead trap). Not used by this strategy; left alone.
- `indicators.bollinger_bands` uses `close.rolling(period).std()`, i.e. pandas ddof=1. This
  **matches** the source pseudocode, so §10 #6's concern does not bite here. No change
  needed; noting it so the reviewer does not have to re-check.
- No other shared file was read into a change. Only the deliverable files were created; no
  `__init__.py`, no edits to `contract_v2.py`, `causal_structure.py`, `indicators.py`, or any
  other agent's strategy.
- The aborted-run draft in `task/2026-W32/wave2/aborted-run1-partials/bb_midline_break.py`
  was consulted as a second opinion only. It was substantively right; the differences in the
  delivered file are: `warmup_bars` derived from the lookbacks instead of `2 x BB_PERIOD`,
  explicit `float()` narrowing at the `StopRule`/`ExitLeg` boundary (mypy), unused
  `upper`/`lower` array extractions dropped, and the NOTE-by-NOTE justification added.
