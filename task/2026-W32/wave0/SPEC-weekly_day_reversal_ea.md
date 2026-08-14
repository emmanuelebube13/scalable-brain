# SPEC-weekly_day_reversal_ea

**Source:** row 40 of forex_swing_strategies.csv · https://www.mql5.com/en/code/74137
**Conviction (author's):** MODERATE

## 1. Hypothesis
FX majors exhibit a weekday-calendar reversal anomaly: after a directional day, the following configured weekday tends to retrace part of that move rather than continue it, because short-horizon positioning built up during the prior session is unwound by mean-reverting flow (profit-taking, liquidity rebalancing at the start of a new trading day) before fresh information arrives. The sibling EA on the same author's page tests the documented "Turnaround Tuesday" effect, and calendar anomalies of this kind persist in the academic literature because they are too small and too capacity-limited to be arbitraged away by large players. The author himself publishes no performance statistics and states the edge "must be re-validated per pair and weekday" — the strategy is a research framework for isolating the raw day-of-week effect, and the force-close at CloseHour exists precisely so the measured P&L is attributable to that weekday and nothing else.

## 2. Scope
- **primary_granularity:** D1 (signals emitted on the daily frame only)
- **context_granularities:** none (no MTF filter; everything is computed on D1)
- **simulate_on:** H1 (fills, stop, and the intraday time leg are resolved on H1 bars per Contract §5)
- **pairs_requested (verbatim):** `FX majors (research framework also tests commodities|indices)`
- **pairs_available:**
  - Live: `EUR_USD`, `GBP_USD`, `USD_JPY`, `AUD_USD`, `USD_CAD`
  - Wave-1 additions that are FX majors: `USD_CHF`, `NZD_USD` — **pending** (harness skips if history insufficient; NOT a gap)
- **pairs_missing:** none among FX. `commodities|indices` are non-FX instrument classes with no `dim_asset` rows and no ingest path — deliberately out of scope (the FX majors universe fully covers the strategy's core claim; the author's own parameter documentation uses FX-style point/ATR examples). No DATA-GAP file is written: the missing instrument classes are an optional research-framework extension, not required by the strategy as documented, and the two absent majors (`USD_CHF`, `NZD_USD`) are Wave-1 pending, which DATA_AVAILABILITY.md says are NOT gaps.

## 3. Indicators
| Indicator | Params | Source |
|---|---|---|
| ADR — Average Daily Range, `ADR14[t] = SMA(High − Low, 14)[t]` on D1 | period = 14 | **Private** (specify, do not add to inventory): simple rolling mean of the daily high−low range over the trailing 14 D1 bars ending at bar t inclusive. This is the CSV pseudocode's own construction (`atr_d = (high−low).rolling(14).mean()`), NOT the inventory `atr()` which uses true range. Distinct because gaps (weekend) make true range ≥ high−low range; the author measures *intraday* range. See §10 #4. |
| Previous-day direction, `dir[t] = sign(Close[t] − Open[t])` ∈ {−1, 0, +1} | — | trivially derivable from OHLC; no indicator needed |
| Day-of-week of bar open-stamp, `dow[t] = timestamp[t].dayofweek` (UTC, Monday=0 … Sunday=6) | target_dow = **1 (Tuesday)** | calendar attribute of the bar timestamp; knowable arbitrarily far in advance. Declared value Tuesday per the sibling EA's documented "Turnaround Tuesday" and the author's own filter example ("trade only if Monday's range exceeds…" — i.e. previous day = Monday, entry day = Tuesday). See §10 #1. |

No swing/ZigZag/pivot/fractal constructs are used; `causal_structure` is not needed.

## 4. Entry — long
Definitions: bar **T** = the D1 bar whose UTC open-stamp has `dayofweek == 1` (Tuesday). Bar **D** = the D1 bar immediately preceding T (stamped Monday 21:00 UTC). The **decision bar is D**: all conditions below are evaluated at the close of D (Tuesday 21:00 UTC), at which instant every input is fully known.

1. `dow[T] == 1` — knowable at D's close (calendar).
2. Previous day bearish: `Close[D] < Open[D]` (strict; a doji `Close[D] == Open[D]` produces NO trade — §10 #10).
3. Volatility filter ON: `(High[D] − Low[D]) >= 1.5 × ADR14[D]`, where `ADR14[D]` includes D itself (per the pseudocode's `.shift(1)` applied at T). `>=` per the pseudocode.
4. If 1–3 all hold: emit OrderIntent at decision_bar = D, direction = +1.

- **entry type:** `market` (`entry_price = None`)
- **entry level:** n/a for market; fills at the open of the first H1 bar of T's span — the H1 bar stamped Tuesday 21:00 UTC — per F1/F2, plus adverse slippage (F10). This **is** "BUY at the day open": the open of the configured day's D1 bar (§9).
- **expires_after_bars:** `null` — a market order fills at the next bar open by construction; the field is inapplicable. Declared, not left to the implementer.

## 5. Entry — short
Mirror, with the same decision bar D:

1. `dow[T] == 1` (calendar-known at D's close).
2. Previous day bullish: `Close[D] > Open[D]` (strict).
3. Same volatility filter: `(High[D] − Low[D]) >= 1.5 × ADR14[D]`.
4. If all hold: OrderIntent at decision_bar = D, direction = −1, entry `market`, fill at the open of the Tuesday-21:00-UTC H1 bar per F1/F2. `expires_after_bars = null`.

The source's `Direction=Direct` continuation mode (bearish previous day → SELL, bullish → BUY) is **rejected** (§10 #2): one declared parameter set only, and the EA's name and hypothesis are the *reversal*.

## 6. Stop
- **Initial stop (exact formula):** `risk = 0.5 × ADR14[D]`, anchored to the decision-bar close (fleet rule 8 — the market fill price is unknowable at emission):
  - long: `stop.price = Close[D] − 0.5 × ADR14[D]`
  - short: `stop.price = Close[D] + 0.5 × ADR14[D]`
  `ADR14[D]` is the value at the decision bar D (the pseudocode's `.shift(1)` at T). Using T's own ADR (which would include T's range) is look-ahead and is rejected (§10 #5). Because D's close and T's open are the same continuous-market tick except across holidays/weekends, declared R ≈ realized R; where they differ, F3/F6 resolve the fill honestly and realized R ≠ declared R.
- **move_to_breakeven_on:** none
- **trail:** none (`trail_atr_multiple = None`; static stop for the ≤23-hour life of the trade)

The source allows `kDailyATR = 0` (SL disabled) as its raw-research posture; contract v2 **requires** a StopRule, so the documented example value `kDailyATR = 0.5` is declared regardless (§10 #8).

## 7. Exit legs
| Label | Fraction | Kind | Level formula |
|---|---|---|---|
| TIME_CLOSE | 1.0 | time | `bars = 23`, counted on the H1 simulation frame with the fill bar as bar 1: fill at the open of the H1 bar stamped Tuesday 21:00 UTC (bar 1); the position is closed at the **close of the 23rd H1 bar**, i.e. the bar stamped Wednesday 19:00 UTC, closing at **20:00 UTC Wednesday** — the declared `CloseHour = 20:00` (§10 #7). |

Fractions sum to 1.0 (single leg).

**Take-profit:** `rrTP = 0` — TP **disabled**, a configuration the author explicitly documents ("0 disables Take Profit"). Two independent reasons: (a) the contract requires ExitLeg fractions to sum to 1.0, so a full-size TP leg cannot coexist with the full-size time leg that defines this strategy, and any split-fraction encoding changes the trade economics (a TP touch would close only part of the position and strand the remainder past CloseHour); (b) the force-close is the strategy's defining feature — it isolates the raw day-of-week effect. The documented example `rrTP = 2.0` is the rejected alternative (§10 #6).

## 8. Filters
| Filter | Timeframe | When knowable | Status |
|---|---|---|---|
| Volatility/range filter `FilterATR = ON`, `MinCheckDayATR = 1.5`: previous day's range ≥ 1.5 × ADR14 | D1, evaluated on bar D | At the close of D (the decision bar) — both `High[D]−Low[D]` and `ADR14[D]` use only completed bars | **Implemented** (§4.3/§5.3). ON is the conservative reading — fewer trades; the OFF alternative is rejected (§10 #3). |
| Weekday gate (`DayOfWeek = Tuesday`) | D1, on bar T's open-stamp | Calendar — knowable in advance; evaluated at D's close | Implemented as §4.1/§5.1. |

No session, trend, news, or macro filter exists in the source, and none is invented. No non-price data is required: the "Day-of-week calendar" in `data_requirements` is the bar timestamp's `dayofweek` attribute, not an economic-calendar feed. `Volume` (OANDA tick count) is not used. Costs are engine-applied per F10 (1.0-pip spread, 0.5-pip slippage on entry) and are a reasonable proxy for majors; no proxy substitution is needed anywhere in this strategy.

## 9. Causality audit
| Rule | Inputs fully known at | Notes / confirmation lag |
|---|---|---|
| Weekday gate `dow[T] == 1` | Close of D (and any earlier time) | Calendar attribute of the next bar's open-stamp; no market data, no lag. |
| Previous-day direction `sign(Close[D] − Open[D])` | Close of D | D is a completed D1 bar at decision time. Lag: none beyond the one-bar shift. |
| Range filter `(High[D]−Low[D]) >= 1.5 × ADR14[D]` | Close of D | `ADR14[D]` = SMA of (High−Low) over D-13…D inclusive — all completed. Matches the pseudocode's `.shift(1)` relative to T. |
| Stop distance `0.5 × ADR14[D]` | Close of D | Decision-bar value; never recomputed after emission. |
| Market entry fill | Open of the H1 bar stamped Tuesday 21:00 UTC | F1/F2 mapping of "at the day open": OrderIntent emitted at decision_bar D (close = Tuesday 21:00 UTC) becomes eligible from the next bar and fills at its open, which IS the open of the configured day's D1 bar T. The strategy never sees the fill price. |
| Stop/TP geometry anchoring | Close of D | All levels are absolute prices declarable at OrderIntent creation from `Close[D]` and `ADR14[D]` (fleet rule 8). Fill-anchored R is inexpressible and rejected (§10 #9). |
| Time leg `bars = 23` | Emission | Pure bar-count from the fill bar; no market input at all. Exit at 20:00 UTC Wednesday. |
| Swings/pivots/ZigZag/fractals | — | **None used.** No confirmation-lag construct exists in this strategy. |

No multi-timeframe context is used, so the §4 MTF rule does not apply; the D1 decision frame is also the only data frame the strategy reads. Warm-up: first tradable signal requires 14 completed D1 bars for ADR14 plus the previous-day bar — 15 D1 bars.

## 10. Ambiguities resolved
| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | `DayOfWeek` is configurable; the CSV names no canonical day (the sibling tests "Turnaround Tuesday") | **Tuesday** (`target_dow = 1` on the UTC open-stamp, exactly the pseudocode's convention; corroborated by the author's own filter example where the checked previous day is Monday) | Any other weekday (no sweep allowed — one declared parameter set); NY-session Tuesday (which would be `dow == 0` on 21:00-UTC-stamped bars — rejected: departs from the pseudocode's literal `df.index.dayofweek` convention) |
| 2 | `Direction = Revers` vs `Direct` (continuation) | **Revers only** — the EA's name, the hypothesis, and the "Turnaround Tuesday" anomaly are all reversal | Direct mode — rejected: a second, untested-by-us parameter set; contract §10 forbids sweeps |
| 3 | `FilterATR` optional on/off | **ON**, `MinCheckDayATR = 1.5` (the pseudocode's and page's example value) — fewer trades, only after genuinely large days | OFF — rejected: more trades, dilutes the documented configuration |
| 4 | "Daily ATR" definition | **ADR14 = SMA(High−Low, 14)** — the pseudocode's literal construction; measures intraday range as the EA's point-based examples imply | Inventory `atr(14)` (true range) — rejected: not the author's formula; true range ≥ high−low range, so it would raise the filter threshold (fewer trades) and widen stops — a defensible alternative but not what the source computes |
| 5 | ATR value used for SL/filter sizing at the entry bar T | Value at the **decision bar D** (the pseudocode's `.shift(1)`); T's own range is never read | Using `ADR14[T]` — rejected: includes T's (future) range = look-ahead |
| 6 | `rrTP` value | **0 (TP disabled)** — author-documented disablement; forced independently by the fraction-sum rule, since the defining time leg must carry 1.0 | `rrTP = 2.0` (page example) — rejected: inexpressible alongside a full-size time leg (fractions must sum to 1.0); split-fraction encodings (e.g. TP 0.5 / TIME 0.5) distort economics and strand residual size past CloseHour |
| 7 | `CloseHour` value — configurable, no canonical value in source | **20:00 UTC**, one hour before the 21:00 UTC daily close, realized as `bars = 23` on the H1 simulation frame (fill bar = bar 1 at 21:00 UTC Tuesday; close of bar 23 = 20:00 UTC Wednesday) | 21:00 UTC / `bars = 24` (close at the daily close — also defensible; rejected as later exit = slightly longer exposure, and the D1-frame reading `bars = 1` would be coarser); any other hour (undocumented) |
| 8 | Source allows `kDailyATR = 0` (SL disabled) as raw-research posture | **0.5 kept** — contract v2 requires a StopRule; the documented example value is declared | SL disabled — rejected: inexpressible (StopRule.price is mandatory); recorded here as the author's probable research posture |
| 9 | Risk measured from the fill price (MT5 EA places SL from actual entry fill) | Geometry anchored to the **decision-bar close** `Close[D]` (fleet rule 8); realized R ≠ declared R if the fill gaps (rare intraweek; F3/F6 resolve honestly) | Fill-anchored stop/TP — rejected as **inexpressible** in contract v2, not merely less conservative |
| 10 | Previous day closes exactly flat (doji) | **No trade** (strict `<` / `>`) — fewest trades | Mapping doji to either direction — rejected: invents a signal |
| 11 | "FX majors" pair mapping; "research framework also tests commodities\|indices" | Live 5 majors + pending `USD_CHF`, `NZD_USD` (majors by standard definition); crosses (`EUR_GBP`, `GBP_JPY`, …) NOT auto-included | Including all 13 pairs (crosses are not "majors"); commodities/indices — rejected as out of scope: no instrument class exists in `dim_asset` (no DATA-GAP written — extension, not core requirement) |
| 12 | Frame on which the time leg's `bars` are counted | **H1 simulation frame** (`bars = 23`) — required to express an intraday CloseHour at all on a D1 strategy | Primary-frame count (`bars = 1` D1 = close at 21:00 UTC daily close) — rejected: cannot express the declared 20:00 UTC CloseHour and changes holding time by an hour; flagged for the Wave-2 implementer to confirm the engine counts time-leg bars on the simulation frame |

## 11. Expected behaviour
- **Trade frequency:** at most one signal per pair per week (Tuesdays only) → ≤ ~52/pair/year before the filter. The 1.5× ADR range filter is binding — a day's range exceeding 1.5× its 14-day average occurs on roughly 15–25% of days — so expect **~8–15 trades/pair/year**, i.e. ~80–150 trades per pair over 10 years, ~400–750 pooled across the 5 live pairs. Per-(pair × fold) cells will frequently brush `low_confidence`; the pooled sample is adequate. Warm-up cost is trivial (15 D1 bars).
- **What would make it fail the gates:** the anomaly is small by construction. The 0.5× ADR stop sits well inside a normal day's remaining range after entry, so stop-outs are frequent and winners are capped by the 20:00 UTC force-close rather than by a target — realized expectancy rests entirely on a modest average reversal drift within ~23 hours, net of 1.5 pips of round-trip cost. Any regime where Tuesdays trend *with* Monday (continuation) produces steady small losses. Thin per-cell trade counts may also trip `low_confidence`/OOS gates mechanically.
- **Is the author's conviction justified by the rules as written:** MODERATE is honest and arguably generous — the author publishes no statistics and frames the EA as a hypothesis-testing harness ("edge must be re-validated per pair and weekday"). As specified (Tuesday-only, reversal-only, filter ON, TP disabled, 20:00 UTC force-close), the rules are a clean, contamination-free measurement of one specific calendar cell; whether that cell has persistent edge on these five pairs is exactly what the backtest must decide. Nothing in the rules as written flatters the result: entries are at the day open with adverse costs, stops are tight, and exits are at market.
