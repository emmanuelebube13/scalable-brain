# SPEC-adx_trend_pullback_ea

**Source:** row 38 of forex_swing_strategies.csv · https://www.mql5.com/en/code/73958
**Conviction (author's):** MODERATE

## 1. Hypothesis

In a genuinely strengthening trend (ADX above threshold *and still rising*), price oscillates around its short mean: impulsive moves carry it away from the EMA, then liquidity-taking pulls it back toward the EMA before the trend resumes. Entering with the directional DMI consensus exactly when such a pullback *completes* — i.e. at the moment price re-approaches the EMA after having stretched at least one ATR away from it — buys the trend at a locally discounted price rather than chasing extension. The edge should persist because it is the behavioural footprint of trend-following flow (breakout chasers taking profit, value buyers re-entering at the mean) combined with a volatility-adaptive stop, so the entry is only attempted when the market has demonstrably committed to directional movement.

## 2. Scope

| Field | Value |
|---|---|
| primary_granularity | **H1** (CSV: "H1 (default)") |
| context_granularities | none — all indicators computed on the H1 frame |
| simulate_on | H1 (identical to primary; fills resolved on the decision frame) |
| pairs_requested (verbatim) | `EURUSD\|GBPUSD\|USDJPY\|liquid FX majors` |
| pairs_available | **EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD** (live — the liquid majors present per DATA_AVAILABILITY) · **USD_CHF** (Wave-1 addition, **pending**) |
| pairs_missing | none → **no DATA-GAP file**. The three named pairs all exist; "liquid FX majors" is read as the five live majors plus pending USD_CHF (see §10 #5). H4/D1 are "configurable" in the CSV but the single-declared-parameter-set rule fixes H1 only (see §10 #6). |

## 3. Indicators

All indicators are computed on the H1 frame. Bars are indexed so that the **decision bar is bar k**; every value below uses only bars ≤ k.

| Indicator | Params | Source |
|---|---|---|
| EMA of Close | period 20 (Wilder/standard span-20 EMA) | inventory `ema(close, 20)` |
| ATR | period 14, Wilder smoothing | inventory `atr(high, low, close, 14)` |
| ADX | period 14, Wilder smoothing | inventory `adx(high, low, close, 14)` |
| **+DI (private)** | period 14, Wilder | **Private function, specified below** — inventory `adx()` returns ADX only |
| **−DI (private)** | period 14, Wilder | **Private function, specified below** |
| dist (derived series) | — | `dist(j) = abs(Close(j) − EMA20(j)) / ATR14(j)`, defined for any bar j |

**Private +DI/−DI specification (Wilder, period N = 14), matching the DMI construction the inventory's `adx()` is built on:**

For each bar j ≥ 1:
- `up(j) = High(j) − High(j−1)`; `down(j) = Low(j−1) − Low(j)`
- `+DM(j) = up(j)` if `up(j) > down(j)` and `up(j) > 0`, else `0`
- `−DM(j) = down(j)` if `down(j) > up(j)` and `down(j) > 0`, else `0`
- `TR(j) = max(High(j) − Low(j), |High(j) − Close(j−1)|, |Low(j) − Close(j−1)|)`

Wilder smoothing of any series X (period 14): `S(X)` initialised at bar 14 as the plain sum of `X(1..14)`; thereafter `S_t = S_{t−1} − S_{t−1}/14 + X_t`.

- `+DI(j) = 100 × S(+DM)(j) / S(TR)(j)`
- `−DI(j) = 100 × S(−DM)(j) / S(TR)(j)`

Both series are strictly causal (trailing recursion over bars ≤ j). They must be implemented privately in the strategy module; `indicators.py` is off-limits (INDICATOR_INVENTORY, "If you need something not listed"). The implementer SHOULD assert consistency with the inventory `adx()`: `ADX(j) = 100 × Wilder-smoothed mean of |+DI − −DI| / (+DI + −DI)` must reproduce inventory ADX to float tolerance; any divergence means the private DMI does not match the inventory's Wilder convention and must be fixed before running.

**Declared parameter set (single set, no optimisation — contract §10):**

| Parameter | Value | Basis |
|---|---|---|
| ADX period | 14 | CSV pseudocode `ta.adx(...,14)` |
| ADX threshold `adx_thr` | **25** | standard MT5/DMI convention for "established trend" (CSV names no value; §10 #1) |
| EMA period | 20 | CSV pseudocode `.ewm(20)` |
| ATR period | 14 | CSV pseudocode `ta.atr(...,14)` |
| Pullback ratio `pull_ratio` | **1.0** (ATR multiples) | round, conservative default (CSV names no value; §10 #2) |
| SL multiplier `sl_mult` | **2.0** | common EA default for ATR stops (CSV names no value; §10 #3) |
| Risk-reward `rr` | **2.0** | CSV exit_logic: "(e.g. 1:2+)" — the explicit number, "+" rejected (§10 #4) |

## 4. Entry — long

All conditions are evaluated on **closed H1 bars only** ("signals only on completed bars (no repaint)" — CSV risk_management). The **decision bar is bar k**; every input below is fully known at the close of bar k.

Conditions (ALL must hold):

1. **Trend strength:** `ADX(k) > 25`
2. **Trend strengthening:** `ADX(k) > ADX(k−1)`
3. **Pullback arm (two bars back):** `dist(k−1) >= 1.0`, where `dist(j) = abs(Close(j) − EMA20(j)) / ATR14(j)`
4. **Pullback release (decision bar):** `dist(k) < 1.0`
5. **Directional consensus:** `+DI(k) > −DI(k)`

Note on alignment: this is exactly the CSV prose ("ADX(prev)… vs prior bar; distance … >= pullback ratio two bars ago and dropped below it on the previous bar; +DI > −DI on previous bar → BUY at new bar") with "new bar" = bar k+1, "previous bar" = bar k, "two bars ago" = bar k−1. It is also exactly the CSV pseudocode's own alignment: `trend = (adx > adx_thr) & (adx > adx.shift(1))` and `pb = (dist.shift(1) >= pull_ratio) & (dist < pull_ratio)`, both evaluated at row k, entry acted upon at row k+1. The pseudocode's `adx.shift(1)` is a *backward* shift (past bar), so the pseudocode is already strictly causal; the spec adopts it verbatim (see §9).

Order on the bar k+1 signal:

| Field | Value |
|---|---|
| entry type | **market** (OrderIntent `entry="market"`, `entry_price=None`) |
| decision_bar | bar k (the bar whose close produced conditions 1–5) |
| fill convention | open of bar k+1, plus adverse slippage (F1, F2, F10) |
| expires_after_bars | **null** — not a pending order; lifetime field is inapplicable |

## 5. Entry — short

Mirror of §4, conditions 1–4 identical (trend strength, trend strengthening, and the pullback arm/release are direction-agnostic because `dist` uses `abs()`); condition 5 replaced by:

5′. **Directional consensus:** `−DI(k) > +DI(k)`

Order: `direction=-1`, entry type **market**, fill at open of bar k+1 (F1/F2), `expires_after_bars = null`.

## 6. Stop

Anchored to the **decision-bar close** `Close(k)` (fleet rule — decision-bar anchoring; the fill price at k+1 open is unknowable at emission):

| Field | Value |
|---|---|
| initial stop (long) | `StopRule.price = Close(k) − 2.0 × ATR14(k)` |
| initial stop (short) | `StopRule.price = Close(k) + 2.0 × ATR14(k)` |
| move_to_breakeven_on | **none** (`null`) — the source has no breakeven rule |
| trail | **none** (`trail_atr_multiple = null`) — static stop |

Declared risk distance `R_declared = 2.0 × ATR14(k)`. When the fill at k+1 open gaps away from `Close(k)`, realised R ≠ declared R; F3/F6 resolve the fill honestly and the r_multiple is computed on realised entry vs `StopRule.price` by the engine (contract §3.3).

## 7. Exit legs

| Label | Fraction | Kind | Level formula |
|---|---|---|---|
| TP1 | **1.0** | take_profit | long: `price = Close(k) + 2.0 × R_declared = Close(k) + 4.0 × ATR14(k)` · short: `price = Close(k) − 4.0 × ATR14(k)` |

Fractions sum to 1.0 (single leg). No trailing leg, no time stop. The CSV's "Take Profit = SL distance × risk-reward input" with `rr = 2.0` gives exactly this: TP distance = 2.0 × (2.0 × ATR) = 4.0 × ATR from the decision-bar close anchor.

## 8. Filters

The strategy has no session, news, volatility-cap, or higher-timeframe filter. Its only gates are the signal conditions themselves, all on H1:

| Gate | Timeframe | Knowable at |
|---|---|---|
| ADX > 25 AND ADX rising (trend-strength filter) | H1 | close of bar k (uses ADX(k), ADX(k−1)) |
| Pullback arm/release (location filter) | H1 | close of bar k (uses bars k−1, k) |
| +DI vs −DI (direction filter) | H1 | close of bar k |
| One position per (strategy, pair, granularity) | engine-level | enforced by **F12** (`max_concurrent_positions = 1`, default). The strategy emits intents unconditionally; the engine drops any intent that would exceed the cap. This is the mechanical equivalent of the CSV's "only one position per symbol; new signal evaluated only when flat" — see §10 #7. |

No non-price data is used. No spread series is consulted; the F10 cost model (1.0-pip spread, 0.5-pip entry slippage) is applied by the engine, not the strategy.

## 9. Causality audit

Decision bar = H1 bar k. The OrderIntent is emitted with `decision_bar = k`; per F1 it is eligible for fill from bar k+1 onward (market → open of k+1, F2).

| Rule | Inputs | Bars used | All closed at decision (close of k)? | Confirmation lag |
|---|---|---|---|---|
| Long/short cond. 1 (ADX > 25) | ADX(k) | ≤ k | ✅ | none beyond bar close; ADX(k) is a trailing Wilder recursion over bars ≤ k |
| Long/short cond. 2 (ADX rising) | ADX(k), ADX(k−1) | ≤ k | ✅ | one completed prior bar; strictly backward comparison |
| Long/short cond. 3 (pullback arm) | Close(k−1), EMA20(k−1), ATR14(k−1) | ≤ k−1 | ✅ | condition deliberately references the bar *two positions back from entry* (k−1 relative to decision k); fully closed one bar before the decision |
| Long/short cond. 4 (pullback release) | Close(k), EMA20(k), ATR14(k) | ≤ k | ✅ | evaluated on the decision bar's own close |
| Long/short cond. 5 / 5′ (DMI) | +DI(k), −DI(k) | ≤ k | ✅ | trailing Wilder recursion |
| Stop / TP geometry | Close(k), ATR14(k) | ≤ k | ✅ | both are absolute levels declarable at OrderIntent creation (fleet rule — decision-bar anchoring) |
| One-position cap | — | engine state | ✅ | F12 at §3.2 step 6; the strategy itself reads nothing |

- **Swing/pivot/ZigZag/fractal rules:** none. This strategy references no swing points; `detect_swing_points` is not involved and no confirmation lag beyond bar close exists anywhere in the logic.
- **MTF causality:** not applicable — single timeframe (H1). No context frame exists, so the §4 context-bar rule has nothing to bind.
- **Pseudocode alignment check (row-watch item):** the CSV pseudocode computes `adx > adx.shift(1)` and `dist.shift(1) >= pull_ratio` at the same row it emits the signal, and the EA acts "at new bar". Read strictly causally, the signal row is bar k (close), the entry is bar k+1 (open). No `.shift(-1)`, no centred window, no repaint. The pandas-ta `ta.adx` default (`lensig=14`, Wilder) matches the declared parameters.
- **Warm-up:** EMA20/ATR14/DMI14 need ≥ ~30 H1 bars of history before bar k; the engine/harness supplies trailing frames, and the strategy must emit nothing until all five indicator series are non-NaN at bar k.

## 10. Ambiguities resolved

| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | `adx_thr` has no documented value anywhere in the CSV | **25** — the universal MT5/DMI default for "established trend"; fewer trades than any lower threshold | 20 (also common; admits weaker, choppier trends → more trades → rejected) |
| 2 | `pull_ratio` has no documented value | **1.0** ATR — the pullback must have stretched a full ATR from the EMA; restrictive → fewer trades | 0.5 (a shallower excursion still "counts" → materially more signals → rejected) |
| 3 | `sl_mult` has no documented value | **2.0** — the most common EA default for ATR stops and the value consistent with surviving H1 noise; wider stop → larger R denominator → does not flatter r-multiples | 1.5 (tighter stop, more stop-outs under F5's stop-first convention; not more conservative in outcome, and less standard → rejected) |
| 4 | RR given only as "(e.g. 1:2+)" — the "+" is unbounded | **rr = 2.0 exactly** — the one explicit number in the source; also the harder target vs any "1:1.x" reading, and under F5 (stop-before-target within a bar) a farther TP is filled less often → conservative | rr > 2.0 (the "+" is not a number; inventing one is a parameter choice with zero source support → rejected); rr < 2.0 (contradicts the only number given → rejected) |
| 5 | "liquid FX majors" scope beyond the three named pairs | the five **live** majors (EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD) + **USD_CHF pending** (a true major) | Including JPY crosses / EUR crosses / NZD_AUD-style pairs as "majors" (they are crosses; broader scope = more cells = more trades, and several are Wave-1 pending → rejected) |
| 6 | "H1 (default)\|H4\|D1 configurable" — three granularities | **H1 only** — the documented default; the no-optimisation rule permits one declared set, so the configurable variants are not run | Running H4/D1 as additional cells (that is a sweep over a configurable input, i.e. optimisation-by-configuration → rejected; the T6 uniform path can still characterise the raw signal on other frames) |
| 7 | "new signal evaluated only when flat" requires observing position state, which contract v2 forbids | Strategy emits an intent on **every** signal; **F12** (`max_concurrent_positions = 1`, default) drops intents while a position is open. Because all entries are `market` (no pendings ever exist), a dropped intent leaves no residue: behaviour is *identical* to "evaluate only when flat" | Raising `max_concurrent_positions` or trying to track flatness in-strategy (impossible — no fill/P&L channel; and stacking pyramids the trade → rejected) |
| 8 | R/SL geometry: EA measures SL/TP from the *fill* ("Stop Loss = ATR × SL multiplier" attached to the executed order), which is unknowable at emission | Geometry anchored to **decision-bar close** `Close(k)`: stop `∓ 2.0×ATR(k)`, TP `± 4.0×ATR(k)` (fleet rule — decision-bar anchoring). Realised R ≠ declared R when the k+1 open gaps; F2/F6 resolve honestly | Fill-anchored geometry (inexpressible in contract v2 — `StopRule.price`/`ExitLeg.price` must be absolute at OrderIntent creation → rejected as inexpressible, not merely less conservative) |
| 9 | Pseudocode uses `df['close'].ewm(20).mean()` — pandas `com=20, adjust=True`, which is *not* a standard span-20 EMA | Inventory `ema(close, 20)` (standard span-20 EMA) — comparable to every other strategy in the system; the pseudocode is illustrative pseudocode, not the EA's MQL5 source | Replicating `ewm(com=20, adjust=True)` literally (non-standard initialisation, diverges from the MT5 EA's actual EMA and from the inventory → rejected) |

## 11. Expected behaviour

- **Trade frequency:** low-to-moderate. The triple gate (ADX > 25 *and* rising, a ≥1-ATR excursion that just released, DMI agreement) fires only in established, currently-strengthening H1 trends after a completed pullback. Expect roughly **1–5 trades per pair per month**, i.e. ~15–60 trades per pair per decade-scale year of H1 data; six cells (5 live + USD_CHF pending) should pool to a few hundred OOS trades over the full history — enough to escape the worst of the low-confidence trap, unlike the W1 strategies.
- **What would make it fail the gates:** (a) H1 ADX(14) > 25-and-rising regimes are common in *late* trends, so the pullback-release entry can systematically buy local tops just before trend exhaustion — the DMI filter does not protect against this; (b) F5's stop-before-target convention punishes the 1:2 geometry whenever a single H1 bar spans both levels, which happens often at 2-ATR stop distance on H1; (c) the stop at 2×ATR from *decision close* (not fill) means gap bars shift realised R; (d) long stretches of range-bound trade (ADX oscillating around 25) will produce clusters of whipsaw entries with the trend filter flickering.
- **Is the author's MODERATE conviction justified by the rules as written?** Yes — and only MODERATE. The mechanics are clean, fully mechanical, non-repainting, and the trend-pullback rationale is behaviourally plausible (§1); the ATR-scaled exits and single-position design avoid grid/scalp pathologies. But the source page documents **no performance** ("requires fresh Strategy Tester backtest per pair"), four of the seven parameters had no documented value and are declared here by convention (§10 #1–#4), and the edge rests on ADX-rising persistence at H1, which is exactly where mean-reverting noise is strongest. A credible candidate for the v2 harness, not a promotion candidate on the evidence of the CSV alone.
