# SPEC-weekly_gap_fade

**Source:** row 3 of forex_swing_strategies.csv (CSV line 4) · https://www.earnforex.com/forex-strategy/forex-gap-strategy
**Conviction (author's):** HIGHLY_RECOMMENDED

## 1. Hypothesis

When the forex market reopens after the weekend, the opening price sometimes gaps away from
the prior Friday's close; these gaps are frequently faded because the weekend produces no new
fundamental flow proportionate to the price jump — the gap is largely an artefact of thin
Sunday-night liquidity, retail order imbalances accumulating over the close, and dealers
re-quoting spreads at the open. Mean reversion should persist because the gap is not
information-driven in most weeks: once normal weekday liquidity returns, price gravitates
back toward the pre-weekend consensus (Friday's close). The edge is structural (a fixed,
recurring liquidity discontinuity at the weekly session boundary) rather than predictive, and
the strictly mechanical time exit removes discretionary stop placement that gap-fade traders
typically get stop-hunted on.

## 2. Scope

- primary_granularity: **H1** — the contract requires decisions at a bar *close*, and the gap
  (week open vs. prior Friday close) is first fully knowable at the close of the first H1 bar
  of the week (stamped Sunday 21:00 UTC). W1 cannot be the decision frame: at a W1 decision
  close (Friday 21:00 UTC) the coming week's open does not yet exist, so the entry condition
  is unevaluable on W1. D1 as decision frame would delay entry to Monday 21:00 UTC (~24 h
  late). H1 is the minimal-delay causal frame. See §10 #3.
- context_granularities: [D1] — ATR(14) on D1 for the catastrophic stop anchor only (§6).
  Joined with the standard one-full-D1-interval forward shift (`merge_asof`,
  `allow_exact_matches=False`); the last usable D1 value at the decision bar is the close of
  the Thursday-stamped D1 bar (closes Friday 21:00 UTC).
- simulate_on: H1
- pairs_requested (verbatim from CSV `target_pairs`):
  `["GBP/JPY preferred", "Other JPY pairs", "All major pairs tradeable simultaneously"]`
- pairs_available:
  - now: **USD_JPY** (only JPY pair present), plus majors **EUR_USD, GBP_USD, AUD_USD, USD_CAD**
  - pending Wave-1 backfill: **GBP_JPY** (the author's *preferred* and only documented pair),
    **EUR_JPY** ("other JPY pairs"), **NZD_USD, USD_CHF** (remaining majors). Declare them;
    the harness skips pairs with insufficient history.
- pairs_missing: [] permanently — but GBP_JPY/EUR_JPY are not yet in the DB, and the CSV's
  `data_requirements` names "Average spread per pair", which **does not exist** (OHLCV only).
  → **DATA-GAP-weekly_gap_fade.md** (spread feed + GBP_JPY timing risk). W1 staleness is a
  non-issue: this spec deliberately uses no W1 data.

## 3. Indicators

| Indicator | Params | Source |
|---|---|---|
| `calculate_pips` | `(price_change, asset=<pair>)` | inventory — converts gap size and the 5.0-pip threshold to price units per pair (handles JPY 0.01 pip size) |
| `atr` | `(high, low, close, period=14)` on **D1** | inventory — catastrophic stop distance only (§6); causal at decision bar per §2 shift |
| Week-boundary detection | timestamp arithmetic: first H1 bar of week = bar stamped **Sunday 21:00 UTC**; prior week-final bar = bar stamped **Friday 20:00 UTC** | not an indicator; specified precisely in §4/§9. Uses only bar timestamps, no data invention |

No swing/pivot/ZigZag logic → `causal_structure` not needed. No W1 data used → the stale-W1
warning does not affect signal generation (it does affect how results are *labelled* — §11).

## 4. Entry — long

Evaluated once per week, at the **close of the week-start bar W0** = the H1 bar stamped
Sunday 21:00 UTC (covers Sunday 21:00 → 22:00 UTC), decision time Sunday 22:00 UTC.

1. **Week-boundary check:** W0 is stamped Sunday 21:00 UTC **and** the immediately preceding
   H1 bar in the feed is stamped Friday 20:00 UTC (its close = Friday 21:00 UTC session
   close). If either fails (holiday-shortened week, data hole), **no trade this week**.
2. `prior_week_close` = `Close` of that Friday-20:00-stamped H1 bar (knowable since Friday
   21:00 UTC).
3. `week_open` = `Open` of W0 (knowable since Sunday 21:00 UTC; used at W0's close — causal).
4. `gap_pips = calculate_pips(week_open - prior_week_close, asset=<pair>)`.
5. **Gap filter:** `gap_pips <= -5.0` (gap down of at least 5× the 1.0-pip spread proxy, §8).
6. Emit one `OrderIntent`: `direction=1`, `entry="market"`, `entry_price=None`,
   `decision_bar` = close of W0, `size_fraction=1.0`, `tag="weekly_gap_fade"`.

- Entry type: **market** (fills at the open of the next H1 bar — stamped Sunday 22:00 UTC —
  per F1/F2, plus the F10 cost model: 1.0 pip spread + 0.5 pip adverse slippage on entry).
- Entry level: `Open` of the H1 bar stamped Sunday 22:00 UTC (not known at decision time;
  engine-determined per F2). Effective entry ≈ 60 minutes after the true week open.
- expires_after_bars: **1** — market orders fill at the next bar open per F2, so expiry never
  binds; the value is defensive only.
- At most one OrderIntent per pair per week (F12 `max_concurrent_positions=1` default
  retained; simultaneous positions *across different pairs* are intended by the source).

## 5. Entry — short

Mirror of §4. At the close of W0 (H1 bar stamped Sunday 21:00 UTC):

1. Same week-boundary check (§4 step 1); no trade if it fails.
2. Same `prior_week_close` and `week_open` definitions.
3. `gap_pips = calculate_pips(week_open - prior_week_close, asset=<pair>)`.
4. **Gap filter:** `gap_pips >= +5.0` (gap up).
5. Emit one `OrderIntent`: `direction=-1`, `entry="market"`, `entry_price=None`,
   `decision_bar` = close of W0, `size_fraction=1.0`, `tag="weekly_gap_fade"`.

Entry type/level/expiry identical to §4 (open of the Sunday-22:00-stamped H1 bar; F2/F10).

## 6. Stop

The source explicitly declares **"No stop-loss and no take-profit"** — but `OrderIntent`
REQUIRES a `StopRule`, and `r_multiple` is defined as realised P&L ÷ `|entry − stop.price|`,
so the stop must exist and also defines the risk unit. Conservative resolution: a
**catastrophic stop** that behaves like "no stop" in ordinary weeks but bounds tail risk and
supplies an honest, wide R.

- initial stop (anchored to a **decision-bar-knowable price** — the fill is unknowable when
  the `OrderIntent` is emitted, so all stop geometry anchors to the decision bar, per the
  fleet rule):
  - long: `stop.price = W0_close - 5.0 × ATR_D1`
  - short: `stop.price = W0_close + 5.0 × ATR_D1`
  - where `W0_close = Close` of the decision bar W0 (the H1 bar stamped Sunday 21:00 UTC,
    knowable at its close, Sunday 22:00 UTC — the decision instant), and
    `ATR_D1 = atr(High, Low, Close, 14)` on D1, valued at the close of the
    Thursday-stamped D1 bar (closes Friday 21:00 UTC — fully knowable before the Sunday
    decision per the §2 shift). 5× daily ATR ≈ 1.7–2.5× a typical full-week range for these
    pairs: rarely touched inside a 5-day hold, yet a genuine disaster stop (e.g. a
    weekend-news trend week that never reverts).
  - The true fill (Sunday-22:00 bar open + F10 costs) will differ from the `W0_close`
    anchor — occasionally beyond the declared stop if the Sunday-22:00 bar gaps further.
    The engine resolves this honestly: a fill already through the stop behaves per F3/F6
    gap conventions, so the realised R can differ from the declared R and any such case
    is reportable (`gapped=True`). The anchor choice never requires knowledge of the fill.
- move_to_breakeven_on: **none** (no scale-out legs exist to trigger it; a naked breakeven
  rule would contradict the author's time-exit-only design).
- trail: **none** (`trail_atr_multiple=None`; static catastrophic stop).

Tension recorded in §10 #1: this changes the r-multiple scale (all trades' |r| is compressed
by the wide denominator). That is honest — the strategy genuinely risks the full holding
period — but it means gate metrics are not comparable to 1–2×ATR-stopped strategies without
commentary.

## 7. Exit legs

| Label | Fraction | Kind | Level formula |
|---|---|---|---|
| W-END | 1.0 | time | `bars = 117` in a standard week — exit at the **close of the H1 bar stamped Friday 19:00 UTC** (20:00 UTC, ≈60 min before the 21:00 UTC session close). General formula, computed at decision time: `bars = (number of H1 bar opens strictly after the entry-fill bar (Sunday 22:00 UTC stamp) up to and including the coming Friday 19:00 UTC stamp)`. In a holiday-shortened week this count is smaller; compute it from the calendar at decision time, never hard-code 117 blindly. If the coming Friday 19:00 UTC stamp does not exist (e.g. Friday is a full holiday — but then §4 step 1 already vetoed the trade), the position falls through to F11 END_OF_DATA handling. |

Fractions sum to **1.0** ✓. Rationale for 117: entry fills at the open of the bar stamped
Sunday 22:00 UTC; counting bar opens Sun 22:00 → Fri 19:00 = 24×4 + 21 = 117 bars. The
author's "5 minutes before session end" (Friday 20:55 UTC) is not representable on the H1
grid; 20:00 UTC is the latest bar close that does **not exceed** the author's exit time.
The alternative (close of the Friday-20:00 bar at 21:00 UTC = session close, bars=118) is
rejected in §10 #4.

## 8. Filters

**The ≥ 5× average-spread gap filter** (it is the entire entry condition, §4 step 5 / §5 step 4):

- The CSV's `data_requirements` names "Average spread per pair". **No spread series exists** —
  the DB holds OHLCV only (DATA_AVAILABILITY.md: "Non-price data — none of it exists").
- **Conservative proxy (fixed, no data invented):** `avg_spread = 1.0 pip`, the single
  sanctioned spread figure in the system (F10 cost model, used to produce the live
  `fact_trade_outcomes`). Threshold = `5 × 1.0 = 5.0 pips`, converted to price via
  `calculate_pips` per pair.
- Direction-of-conservatism caveat: 5.0 pips is *less* restrictive than a historically
  accurate GBP/JPY spread (2–4 pips in the author's 2010 sample ⇒ 10–20 pip threshold), so
  this proxy admits **more** trades than the author traded. This is flagged in §10 #5 and in
  the DATA-GAP note; it is the only defensible constant because inventing a per-pair spread
  history violates the no-invented-data rule.
- **Knowability:** the spread proxy is a static constant (always knowable). `prior_week_close`
  is knowable from **Friday 21:00 UTC** (close of the Friday-20:00-stamped H1 bar — note this
  bar *is* the week's last bar; the market is then closed until Sunday 21:00 UTC, so nothing
  newer can contaminate it). `week_open` is knowable from **Sunday 21:00 UTC** (the open
  print of W0). Both are therefore fully knowable at the decision bar close, Sunday 22:00 UTC.
  The filter is never evaluated with the still-forming Friday D1 bar: the "Friday close D1
  bar" is the **Thursday-stamped** D1 bar (covers Thursday 21:00 → Friday 21:00 UTC), which
  is complete before the week ends — there is no Friday-stamped D1 bar in this feed.

## 9. Causality audit

Feed facts relied on: bars are stamped at their **open**; the market is closed Friday 21:00 →
Sunday 21:00 UTC; a trading week therefore contains exactly five D1 bars (stamped Sun/Mon/
Tue/Wed/Thu 21:00 UTC) and, in a standard week, 120 H1 bars (stamped Sunday 21:00 UTC through
Friday 20:00 UTC). **"Monday open" in this feed = the open of the bar stamped Sunday 21:00
UTC** (the first tradeable price after the weekend). **"Friday close" = the close of the bar
stamped Friday 20:00 UTC (H1) = the close of the Thursday-stamped D1 bar**, knowable at
Friday 21:00 UTC.

| Rule | Inputs | Bar at which inputs are fully known |
|---|---|---|
| §4/§5 step 1 — week-boundary check | timestamps of W0 and its predecessor | Close of W0 (Sunday 22:00 UTC) — both stamps exist by then |
| §4/§5 step 2 — `prior_week_close` | Close of H1 bar stamped Friday 20:00 UTC | **Friday 21:00 UTC** (previous week) — 25 h before the decision |
| §4/§5 step 3 — `week_open` | Open of W0 | **Sunday 21:00 UTC** (the open print), used at W0's close — causal |
| §4/§5 gap filter — threshold | static 1.0-pip proxy × 5, `calculate_pips` | always (compile-time constant) |
| §6 — stop geometry | `W0_close` (Close of W0) and `ATR_D1` from D1 OHLC through the Thursday-stamped D1 bar | Both at the decision instant: `W0_close` is knowable at the close of W0 (Sunday 22:00 UTC); `ATR_D1` is knowable from **Friday 21:00 UTC** (that D1 bar's close) and first usable at Sunday 21:00 UTC per the §2 shift. The fill price is **not** an input — see §10 #8 |
| §4/§5 — entry fill | Open of H1 bar stamped Sunday 22:00 UTC | formed **after** the decision (F1/F2) — no look-ahead; price unknown at decision time by construction |
| §7 — time-exit bar count | exchange calendar (coming Friday 19:00 UTC stamp) | known at decision time; no market data involved |
| F8/F9 breakeven/trailing | — | not used |
| W1 frame | — | **not used anywhere** (avoids the ~8-week-stale W1 series entirely) |

No rule consumes a bar at or after the decision bar's close except the engine-determined fill
(F2) and the calendar. The whole edge lives at the weekend boundary, and every boundary input
is an already-closed bar or an open print that predates the decision.

## 10. Ambiguities resolved

| # | Ambiguity in the source | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | "No stop-loss" vs. contract-required `StopRule` (and r_multiple needs a risk unit) | Catastrophic static stop at `W0_close ∓ 5.0 × ATR(14, D1)` (anchor per #8) — behaves like no-stop in normal weeks, bounds tails, defines an honestly wide R. Recorded: r-multiples are compressed vs. ATR-harness strategies; reports must say so. | (a) 1×ATR tactical stop — contradicts the author's explicit no-SL design and his "time exit removes stop-hunt risk" rationale; (b) time-exit-only with a synthetic R — impossible, the dataclass raises without a stop. |
| 2 | "Monday open" in a feed whose week opens **Sunday 21:00 UTC** | Week open = open of the H1 bar stamped Sunday 21:00 UTC (the first post-weekend print). | Monday 00:00 UTC open — the source's "Monday" is broker-convention language; the true reopening print is Sunday 21:00 UTC, and using Monday 00:00 would miss 3 h of the gap. |
| 3 | Decision frame: CSV says "W1 (D1 bars used for Mon open vs Fri close)", but the gap is unknowable at a W1 decision close (Friday 21:00 UTC, next week's open doesn't exist yet) | Decide on **H1**: first H1 bar of the week (W0) closes Sunday 22:00 UTC; both gap legs are knowable then; market entry fills at the Sunday-22:00 bar open (~60 min after the true open — later = conservative). | (a) W1 decision frame — entry condition literally unevaluable under F1; (b) D1 decision frame — entry Monday 21:00 UTC, ~24 h late, distorts the strategy beyond recognition; (c) unconditional market order placed Friday to fill at the Sunday open — drops the ≥5×-spread filter, which is the strategy. |
| 4 | "Close 5 minutes before the end of the weekly session" on an H1-resolution simulator | Exit at the close of the H1 bar stamped **Friday 19:00 UTC** (20:00 UTC; `bars=117` standard week) — the latest H1 close that does not exceed the author's 20:55 target. | Close of the Friday-20:00 bar at 21:00 UTC (`bars=118`) — 5 min *later* than the author's exit and relies on the final print of the week; rejected per conservative rule. |
| 5 | "Average spread per pair" — no spread series exists (OHLCV only) | Fixed proxy 1.0 pip (F10 cost model) ⇒ 5.0-pip threshold; flagged here and in DATA-GAP. This proxy is *less* restrictive than the author's historical GBP/JPY reality, so it errs toward more trades — the one place conservatism and the no-invented-data rule conflict; the no-invented-data rule wins, and the gate reviewer is warned. | Per-pair historical spread estimates (2–4 pips ⇒ 10–20 pip threshold) — no such data exists; inventing it violates rule 3. |
| 6 | "GBP/JPY preferred" — GBP_JPY is not in the DB (Wave-1 pending) | Declare GBP_JPY (and EUR_JPY, NZD_USD, USD_CHF) in metadata; harness skips until backfill lands; run now on USD_JPY + EUR_USD/GBP_USD/AUD_USD/USD_CAD. The author's +1,612-pips claim is GBP/JPY-specific and is **not** assumed to transfer. | Silently substituting USD_JPY as a proxy for the documented GBP/JPY edge — rejected; DATA-GAP note filed instead. |
| 7 | Holiday-shortened weeks (e.g. Christmas, New Year) break the standard Sun-21:00/Fri-20:00 pattern | §4 step 1 vetoes the trade unless the full standard pattern holds (fewer trades = conservative). | Trading partial weeks on a "closest available open" basis — introduces an unmoored gap reference (e.g. a Wednesday open vs. a Friday close); rejected. |
| 8 | Stop anchor for a **market** entry: `StopRule.price` must be an absolute float when the `OrderIntent` is emitted, but the fill (next bar open, F2) is unknowable then | Anchor to the decision bar's close: `stop.price = W0_close ∓ 5.0 × ATR_D1`. The true fill may land beyond the anchor (Sunday-22:00 bar gapping further); the engine then applies the F3/F6 gap conventions, so realised R can differ from declared R and stays honest (`gapped=True` reported) — no implementer discretion remains. | Anchoring to `entry_price` — impossible: `entry="market"` means `entry_price=None`; the order could not be constructed and Wave 2 would have had to invent the anchor. |

## 11. Expected behaviour

- **Trade frequency:** at most 1 trade per pair per week, and only in weeks where the weekend
  gap is ≥ 5 pips. Weekend gaps of that size occur in roughly half to two-thirds of weeks on
  JPY crosses (fewer on EUR_USD/USD_CAD), so expect ~20–35 trades per pair per year, i.e.
  ~400–700 trades per pair over the ~20-year H1 history, and only qualifying weeks are traded.
- **Gate risk:** this is a weekly-frequency strategy, so the DATA_AVAILABILITY W1 statistical
  warning applies in spirit even though W1 *data* is unused: a 6-month OOS fold ≈ 26 weeks ≈
  **~10–17 trades per pair per fold** — low per-cell counts, so per-cell `low_confidence`
  flags are likely and pooled folds must carry the verdict (per Contract Part G). Three more
  gate hazards are specific to this spec: (i) the catastrophic stop compresses |r| values
  (a typical week closes out at ±0.05–0.4R), so r-multiple thresholds see a muted scale;
  (ii) the 5.0-pip threshold is looser than the author's reality, so the backtest trades
  *more, smaller* gaps than the documented sample — expect lower per-trade edge than the
  marketing page implies; (iii) Friday-20:00 (illiquid) prints and the F6 gap-through-stop
  convention can produce occasional large negative r in runaway weeks — these must be visible,
  not averaged away.
- **Is HIGHLY_RECOMMENDED justified?** No — not on the evidence given. The documented sample
  is **6 of 7 gaps correct, +1,612 pips, 7 weeks, one pair (GBP/JPY), year 2010** — a
  single-digit sample from a 15-year-old microstructure regime (wider spreads, different
  Sunday-open liquidity). The author's own reasoning field says "sample is small/old so
  re-test on modern data before live use". Treat the conviction as a prioritisation hint
  only; the strategy enters the pipeline as effectively EXPERIMENTAL until pooled OOS folds
  on modern data (including GBP_JPY once backfilled) say otherwise. The honest prior: a real
  but modest structural anomaly whose edge may not survive the F10 cost model on 5-pip-minimum
  gaps.
