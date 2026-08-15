# SPEC-ma_crossover_swing
**Source:** row 18 of forex_swing_strategies.csv · https://www.tradingview.com/script/uNIA4siU-Moving-Average-Crossover-Swing-Strategy/
**Conviction (author's):** MODERATE

## 1. Hypothesis

Trend-following edge: when a fast moving average crosses a slower one and price is simultaneously on the trend side of the 200-day mean with MACD momentum agreeing, the market is in the early phase of a multi-day directional move driven by herding of momentum participants and the slow re-pricing of drift; entering at the next open with a wide ATR bracket (1:2.3 reward-to-risk) and an 8-bar time stop harvests the continuation while cutting trades where the move fails to materialise promptly. The dual confirmation exists because raw MA crosses are whipsaw-prone in ranges — the edge should persist because regime (SMA200) and momentum (MACD) agreement filters out the low-quality crossings that erode the raw signal.

## 2. Scope

- **primary_granularity:** D1 (source: "designed for multi-day swing; defaults on Daily")
- **context_granularities:** none — all indicators, including the SMA200 regime filter, are computed on the D1 decision frame. (The source also lists H4 as an alternative frame; see §10 #9 — H4 is declared as an optional second evaluation cell, not required.)
- **simulate_on:** H1 (contract Part D: decide on D1, resolve fills/stops/legs on H1 bars)
- **pairs_requested (verbatim):** `EURUSD|GBPUSD|USDJPY|XAUUSD|asset-agnostic, applies to FX majors`
- **pairs_available:** EUR_USD, GBP_USD, USD_JPY (all live, D1/H4/H1 current per DATA_AVAILABILITY)
- **pairs_missing:** XAU_USD — deliberate policy exclusion (not Forex; pip/margin conventions assume FX) → see DATA-GAP-ma_crossover_swing.md. The trailing phrase "applies to FX majors" is NOT expanded to Wave-1 pending crosses (GBP_JPY, EUR_JPY, etc.); conservative reading covers only the three named live pairs (§10 #8).

## 3. Indicators

All computed on the D1 frame from `Close`/`High`/`Low`; all values at decision bar *t* use bars ≤ *t* only (trailing, causal).

| Indicator | Params | Source |
|---|---|---|
| EMA (fast signal MA) | period 5, on Close | inventory `ema(close, 5)` |
| EMA (medium signal MA) | period 10, on Close | inventory `ema(close, 10)` |
| SMA (slow regime MA) | period 200, on Close | inventory `sma(close, 200)` |
| MACD line, signal line | fast=12, slow=26, signal=9, on Close | inventory `macd(close, 12, 26, 9)` — use `macd` and `signal` outputs; histogram unused |
| ATR | period 14, True-Range | inventory `atr(high, low, close, 14)` (see §10 #5: source pseudocode used a simple mean of high−low, not True Range) |

Warm-up: no signal is valid before bar 200 of the series (SMA200 defined); EMA/MACD seed effects are absorbed by this same warm-up.

## 4. Entry — long

Decision made at the close of D1 bar *t*. All conditions evaluated on closed bars ≤ *t*.

1. `EMA5[t] > EMA10[t]` AND `EMA5[t-1] <= EMA10[t-1]` — a fresh bullish cross of the fast over the medium EMA. Because both EMAs are computed from closes, the cross is only observable once bar *t* has closed; this *is* the source's "candle-close confirmation" (no separate confirmation condition exists).
2. `Close[t] > SMA200[t]` — regime confirmation (MANDATORY, §10 #1).
3. `MACD_line[t] > MACD_signal[t]` — momentum confirmation as a state condition, per the author's own pseudocode (`conf=(df.close>ma_slow)&(macd>sig)`); MANDATORY (§10 #1, #2).
4. All three conditions must hold on the same decision bar *t*; no look-back window is permitted for conditions 2–3.

- **Entry type:** `market` (source: "enter at open of next bar" — identical to F2 market semantics).
- **Entry level:** none declared (`entry_price = None`); fill is the open of D1 bar *t+1* (resolved on H1), plus cost model per F10.
- **expires_after_bars:** `null` (market orders are not pending; no lifetime applies).

## 5. Entry — short

Shorts are ENABLED (source: "shorts off by default, enable for FX"; we trade FX, both directions are symmetric, and FX has no borrow constraint). Mirror of §4:

1. `EMA5[t] < EMA10[t]` AND `EMA5[t-1] >= EMA10[t-1]` — fresh bearish cross, close-confirmed.
2. `Close[t] < SMA200[t]`.
3. `MACD_line[t] < MACD_signal[t]`.
4. Same-bar conjunction, as in §4.

- Entry type `market`, `entry_price = None`, fill at open of bar *t+1*.
- **expires_after_bars:** `null`.

With F12 `max_concurrent_positions = 1` (default), an opposite signal while a position is open does nothing — it emits an OrderIntent that cannot be admitted until the slot is free; no "new signal closes the position" mechanism exists or is assumed (fleet rule 7). Because entries are market orders admitted on the next bar only, there are no pending orders and therefore no residual multi-fill risk.

## 6. Stop

- **Initial stop (long):** `StopRule.price = Close[t] − 1.4 × ATR14[t]`, anchored to the decision-bar close (fleet rule 8; the source's own pseudocode `sl=df.close-1.4*atr` is also close-anchored, so no fidelity is lost).
- **Initial stop (short):** `StopRule.price = Close[t] + 1.4 × ATR14[t]`.
- **move_to_breakeven_on:** `none` (source has no breakeven rule).
- **trail:** `none` (`trail_atr_multiple = None`; static stop for the life of the trade).

Note (F6): a gap through the stop fills at the bar open, so realised loss can exceed 1R; declared R uses the decision-close anchor, realised R uses the fill.

## 7. Exit legs

The source specifies a TP for the whole position OR a whole-position time exit after 8 bars. Contract v2 legs are static fractions summing to 1.0 and cannot express "whichever happens first for 100%". The conservative structure splits the position: half carries the TP, half is time-stopped (§10 #3).

| Label | Fraction | Kind | Level formula |
|---|--:|---|---|
| TP | 0.5 | take_profit | long: `Close[t] + 3.2 × ATR14[t]`; short: `Close[t] − 3.2 × ATR14[t]` (decision-bar anchor) |
| TIME | 0.5 | time | `bars = 8` — counted in primary-frame (D1) bars from the fill bar: after 8 full D1 bars in trade, this leg exits at the next bar open |

Fractions sum to 1.0. Consequences, stated for the report: the TIME half forfeits the 3.2R target even in winning trades, so blended realised R is strictly below the source's either/or semantics whenever TP would have been hit after bar 8 — pessimistic, as required. The TP half has no time stop and rides until TP or stop.

The source's "optional early exit on opposite MA cross" is a signal exit — inexpressible in contract v2 (ExitLeg kinds are take_profit / trailing / time only; the strategy never observes fills). REJECTED, not implemented (§10 #4).

## 8. Filters

| Filter | Timeframe | Rule | Knowable at |
|---|---|---|---|
| Trend regime | D1 | Long only if `Close > SMA200`; short only if `Close < SMA200` | Close of decision bar *t* (same bar as signal) |
| Momentum | D1 | Long only if `MACD_line > MACD_signal`; short if `<` | Close of decision bar *t* |
| Session/news/volatility | — | none in source; none added | — |

No multi-timeframe alignment is used, so the MTF causality rule (§4 of the contract) is trivially satisfied; every input is on the decision frame itself. No non-price data is required. Cost-model spread (1.0 pip, F10) is the only spread proxy and is applied by the engine, not the strategy — flagged here per the no-invented-data rule.

## 9. Causality audit

| Rule | Inputs | Fully known at |
|---|---|---|
| EMA5/EMA10 cross (long §4.1, short §5.1) | Closes of bars ≤ *t* | Close of bar *t* — the cross is confirmed by the close that produces it; no additional lag |
| SMA200 regime (§4.2, §5.2) | Closes of bars ≤ *t* (≥200 bars back) | Close of bar *t* |
| MACD state (§4.3, §5.3) | Closes of bars ≤ *t* | Close of bar *t* |
| ATR14 bracket anchor (§6, §7) | High/Low/Close of bars ≤ *t* | Close of bar *t*; `StopRule.price` and TP `ExitLeg.price` are absolute values declarable at OrderIntent creation |
| Market entry (§4/§5) | — | Order emitted at close of *t*, eligible for fill from bar *t+1* open (F1/F2) — never bar *t* |
| TIME leg (§7) | Fill bar (engine-side) | Engine counts 8 completed D1 bars from fill; exit at next bar open. Engine-side bookkeeping, not a strategy input |

**Swing/pivot/ZigZag/fractal rules: NONE.** This strategy references no swing points, pivots, ZigZag, or fractals; `detect_swing_points` is not used and no confirmation lag applies to any rule. All indicators are trailing window functions of closed bars. Warm-up: bars 1–199 cannot produce signals (SMA200 undefined); the implementer must emit no OrderIntent before SMA200 is defined. Decision-bar anchoring: every price in §6/§7 derives from `Close[t]`/`ATR14[t]`, both knowable at the close of the decision bar; the unknowable fill price is never referenced.

## 10. Ambiguities resolved

| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | Source calls the SMA200 and MACD confirmations "optional" ("and/or") | BOTH are mandatory on every entry — the author's pseudocode itself conjoins them (`long=cross&conf` with `conf=(close>ma_slow)&(macd>sig)`), and mandatory filters produce fewer trades | Loose reading: either confirmation optional or "and/or" selectable — more trades, contradicts the author's own code |
| 2 | "MACD bullish crossover" — fresh cross event vs state | STATE condition `MACD_line > MACD_signal` at decision close, exactly per the author's pseudocode | Fresh MACD cross coincident with the EMA cross — near-unsatisfiable on one bar, contradicts the author's code, and would strangle the strategy rather than test it |
| 3 | TP (whole position) vs time exit (whole position) — contract legs are static fractions | Split TP 0.5 / TIME 0.5: half forfeits the 3.2R target after 8 D1 bars, strictly pessimistic vs the source's either/or | (a) TP 1.0 with no time leg — drops a documented exit; (b) any whole-position "whichever first" encoding — inexpressible; fractions must sum to 1.0 |
| 4 | "Optional early exit on opposite MA cross" | Not implemented — a signal exit is inexpressible in contract v2 (no ExitLeg kind for it; strategy never observes fills/position state) | Emulating it via tighter time bars or trailing stop — invents parameters not in the source |
| 5 | Source pseudocode ATR is a simple 14-bar mean of (high−low), not True Range | Inventory `atr(high, low, close, 14)` (True Range). TR ≥ high−low, so brackets are equal or wider — equal or larger declared risk, the conservative direction, and it keeps the strategy comparable with the rest of the system | Private (high−low) rolling-mean ATR as literally coded in the source — narrower bracket, plus a duplicate indicator the inventory already covers |
| 6 | Bracket anchor: source says "entry − 1.4×ATR" (fill-anchored reading) | Decision-bar-close anchor: `Close[t] ∓ 1.4×ATR14[t]`, `Close[t] ± 3.2×ATR14[t]` — declarable at OrderIntent creation per fleet rule 8; note the author's pseudocode is also close-anchored | Fill-anchored bracket — inexpressible (fill price unknowable at emission), not merely less conservative. Realised R ≠ declared R when the fill gaps; F3/F6 resolve honestly |
| 7 | "Shorts off by default, enable for FX" | Shorts ENABLED — this system trades FX exclusively, the source explicitly instructs enabling for FX, and the logic is symmetric | Long-only — would discard half the documented strategy and untest the bearish-regime hypothesis |
| 8 | "asset-agnostic, applies to FX majors" — pair universe | Only the three named live pairs (EUR_USD, GBP_USD, USD_JPY); XAU_USD → DATA-GAP | Expanding to the 8 Wave-1 pending crosses — they are crosses, not all "majors", and declaring untested pairs inflates coverage claims; harness may add them later without spec change |
| 9 | Source lists "D1 | H4" timeframes | Primary D1 (the documented default: "defaults on Daily"). H4 is an OPTIONAL second evaluation cell with identical rules and parameters, run only as a separate (pair × H4) cell — never mixed into the D1 decision logic | Treating H4 as a context frame for D1 decisions — the source documents no MTF interaction; adding one invents structure and invites off-by-one MTF causality bugs |
| 10 | Position sizing "1% equity risk via ATR stop distance, 25% equity allocation cap" | Out of scope — System 1 never sizes; `size_fraction = 1.0`, results in r-multiples only | Implementing equity-based sizing in the strategy — forbidden by the contract (§2.2) |
| 11 | "commission and 1-tick slippage modeled in script" | Ignored at strategy level — the engine applies the fixed cost model (spread 1.0 pip, slippage 0.5 pip entry-only, commission 0; F10) | Importing the source's cost numbers — would diverge from the system's single cost model and break comparability |

## 11. Expected behaviour

- **Trade frequency:** EMA5/EMA10 crosses on D1 occur a few times per month per pair; requiring same-bar SMA200-side and MACD-state agreement removes roughly half to two-thirds of them. Expect ~5–12 trades per pair per year, i.e. roughly 300–700 trades over ~20 years × 3 pairs (D1 cell). Walk-forward OOS windows (6 months) will show single-digit trade counts per pair — per-cell `low_confidence` flags are likely; the pooled cell should still be evaluable.
- **What would make it fail the gates:** D1 FX majors spend long stretches range-bound, where close-confirmed EMA crosses whipsaw even with regime/MACD agreement; the 0.5 TIME leg bleeds expectancy in slow trends (half the position never sees 3.2R); F5 stop-before-target at H1 resolution is a minor additional drag given the wide 1.4×ATR stop. A pooled result near zero expectancy with negative dispersion in USD_JPY would be a typical failure shape.
- **Is the author's MODERATE conviction justified by the rules as written?** Yes, appropriately calibrated. The strategy as specified is a textbook trend-following cross with sensible regime and momentum gating and a positive declared RR (1:2.3), but it is one of the most-copied retail strategies in existence, the published demo is equities with no documented FX statistics, and the mandatory-conservative reading of the exits (§10 #3, #4) removes two of the author's loosenesses. MODERATE — neither dismissive nor credulous — matches the evidence.
