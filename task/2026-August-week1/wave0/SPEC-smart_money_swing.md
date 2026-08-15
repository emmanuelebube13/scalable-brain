# SPEC-smart_money_swing
**Source:** row 17 of forex_swing_strategies.csv · https://www.tradingview.com/script/q3yuMvq5-Smart-Money-Swing-Strategy-All-in-One/
**Conviction (author's):** MODERATE

## 1. Hypothesis
In an established trend (fast EMA above slow EMA on the swing frame, confirmed one timeframe higher by price above its EMA50, RSI above midline, and a rising EMA50), a shallow pullback that stalls inside the EMA20–EMA50 corridor and is then reclaimed by a close back above EMA20 marks the point where counter-trend profit-taking is exhausted and trend-following flow resumes; entering there, with the stop under the recent 10-bar extreme, buys trend continuation at a locally favourable price. The edge should persist because it monetises two durable behavioural patterns: herd re-entry by trend traders who sat out the pullback (the reclaim cross is their trigger too) and the liquidation of weak counter-trend positions when the corridor holds, while the higher-timeframe gate filters out the range regimes where EMA pullbacks are noise.

## 2. Scope
- **primary_granularity:** H4
- **context_granularities:** ("D1",) — one level up, per the source's explicit "4H->D" mapping.
- **Additional declared cells (same rules, re-parametrised):** H1 primary with H4 context ("one level higher"), and D1 primary with W1 context ("D->W"). For the D1-primary cell the W1 context series is **derived by causal resampling of the D1 frame** (W1 bar = Sun 21:00 UTC → Sun 21:00 UTC week of D1 closes), NOT read from the stored W1 frame, which is stale ~8 weeks (see §9 and §10 #5).
- **simulate_on:** H1 (contract §5: decided on the native frame, fills resolved on H1).
- **pairs_requested (verbatim):** `EURUSD|GBPUSD|AUDUSD|USDJPY|USDCAD|any FX majors (symbol-agnostic)`
- **pairs_available:** EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD (live, full history). The "any FX majors" clause is covered by Wave-1 additions — GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD — all marked **pending** (declared; harness skips until backfill lands). These are NOT gaps.
- **pairs_missing:** none. (XAU_USD not named by this row.)
- **DATA-GAP:** none required. All five named pairs are live; W1 staleness is handled by D1-derived weekly context; the optional volume filter is dropped rather than proxied (§10 #4).

## 3. Indicators
All indicators map to the existing inventory (`src/layer0/data_access/indicators.py`); no private indicators are needed. No swing-point / ZigZag / fractal logic is used by this strategy (the 10-bar rolling extreme for the stop is a plain rolling min/max, not a swing detector — `detect_swing_points` is NOT involved).

| Indicator | Params | Source |
|---|---|---|
| EMA fast (primary frame) | `ema(close, 20)` | inventory `ema` |
| EMA slow (primary frame) | `ema(close, 50)` | inventory `ema` |
| RSI (primary frame) | `rsi(close, 14)` | inventory `rsi` |
| ATR (primary frame; trailing stop only) | `atr(high, low, close, 14)` | inventory `atr` |
| 10-bar lowest low (long stop) | `low.rolling(10).min()` | derivable: `donchian_channel(low-side, 10)` lower band, or a one-line private rolling min — specify as `min(Low[t-9 … t])` |
| 10-bar highest high (short stop) | `high.rolling(10).max()` | mirror: `max(High[t-9 … t])` |
| EMA50 (context frame) | `ema(close_htf, 50)` | inventory `ema` applied to the closed context-frame closes |
| RSI (context frame) | `rsi(close_htf, 14)` | inventory `rsi` applied to the closed context-frame closes |
| EMA50 5-bar slope (context frame) | `ema(close_htf, 50)[d] − ema(close_htf, 50)[d−5]` | arithmetic on inventory `ema`; strictly positive = rising |

**Not used:** Volume SMA(20) filter — dropped, see §8 and §10 #4.

## 4. Entry — long
Evaluated at the **close of decision bar `t`** on the primary frame (H4 in the reference cell). All indexed values below are on the primary frame unless labelled HTF. The HTF values come from the **last fully closed context bar** per the contract §4 mechanical form (see §9).

1. **Trend:** `EMA20[t] > EMA50[t]`.
2. **Pullback:** the previous bar closed strictly inside the corridor: `EMA50[t−1] < Close[t−1] < EMA20[t−1]` (strict inequalities, per the source pseudocode).
3. **Reclaim cross:** `Close[t] > EMA20[t]` **and** `Close[t−1] <= EMA20[t−1]` (equality permitted on the below side, per pseudocode `<=`). Note conditions 2 and 3 jointly imply the cross is from inside the corridor, which is the intended setup.
4. **RSI zone:** `40 <= RSI14[t] <= 60` (inclusive both ends, per pandas `.between(40, 60)` in the pseudocode).
5. **HTF confirmation** on the last fully closed D1 bar `d` (reference cell): `Close_d > EMA50_d` **and** `RSI14_d > 50` **and** `EMA50_d − EMA50_{d−5} > 0`.

**Entry type:** `market` (fills at open of bar `t+1` per F1/F2, plus adverse slippage per F10).
**Entry level:** n/a — market order; the decision-bar close `Close[t]` is the reference price for all geometry below.
**expires_after_bars:** `null` — not applicable; this is a market order with no pending lifetime.
**Concurrency:** `max_concurrent_positions = 1` (F12 default). Additional signals emitted while a position is open are not admitted (§3.2 step 6, subject to F12); there are no pending orders, so no multi-fill overlap exists.

## 5. Entry — short
Exact mirror of §4:

1. **Trend:** `EMA20[t] < EMA50[t]`.
2. **Pullback from above:** `EMA20[t−1] < Close[t−1] < EMA50[t−1]` (strict).
3. **Reclaim cross down:** `Close[t] < EMA20[t]` **and** `Close[t−1] >= EMA20[t−1]`.
4. **RSI zone:** `40 <= RSI14[t] <= 60` (inclusive).
5. **HTF confirmation** on last fully closed D1 bar `d`: `Close_d < EMA50_d` **and** `RSI14_d < 50` **and** `EMA50_d − EMA50_{d−5} < 0`.

**Entry type:** `market`. **Entry level:** n/a. **expires_after_bars:** `null`. Same F12 concurrency rule.

## 6. Stop
Let `S = min(Low[t−9 … t])` for longs (10-bar lowest low, inclusive of the decision bar — causal by construction) and `S = max(High[t−9 … t])` for shorts. Let `R = |Close[t] − S|` (decision-bar-anchored initial risk, per the fleet decision-bar-anchoring rule).

- **initial stop (exact formula):** long: `StopRule.price = min(Low[t−9 … t])`; short: `StopRule.price = max(High[t−9 … t])`. No buffer (see §10 #2).
- **move_to_breakeven_on:** `"TP1"` (stop moves to breakeven at the close of the bar on which TP1 fills, per F8; `breakeven_offset_pips = 0.0`).
- **trail:** `trail_atr_multiple = 2.0` on ATR(14) of the primary frame, updated at each bar close per F9; the trail only ever tightens the stop (never widens), and models the source's "ATR(14)×2.0 trailing stop manages the remainder" under the contract's single-StopRule model (§10 #6).

`R` is anchored at the decision bar because a market fill at `t+1` open is unknowable at emission; realised R ≠ declared R whenever the fill gaps (F3/F6 resolve the actual fill honestly). The fill-anchored reading is rejected as inexpressible (§10 #3).

## 7. Exit legs
Fractions sum to 1.0 (0.5 + 0.5). Levels are declarable absolutes at OrderIntent creation, computed from the decision-bar close and the §6 stop.

| Label | Fraction | Kind | Level formula |
|---|---|---|---|
| TP1 | 0.5 | take_profit | long: `Close[t] + 1.0 × R` · short: `Close[t] − 1.0 × R` |
| TP2 | 0.5 | take_profit | long: `Close[t] + 2.0 × R` · short: `Close[t] − 2.0 × R` |

The ATR(14)×2.0 trail and the TP1-triggered breakeven move live on the `StopRule` (§6), not as exit legs — this is the contract-native representation of "TP1 at 1R closes 50%; final TP at 2R; BE after +1R; ATR trail manages the remainder". If neither TP2 nor the stop is reached, remaining legs close at end of data per F11.

## 8. Filters
| Filter | Timeframe evaluated on | When it becomes knowable |
|---|---|---|
| Trend gate: `EMA20 > EMA50` (long) / `<` (short) | primary (H4 ref) | at close of decision bar `t` (EMAs use closes ≤ `t`) |
| RSI zone: 40 ≤ RSI14 ≤ 60 | primary | at close of `t` |
| Pullback corridor (condition 2) | primary | at close of `t` (uses only bar `t−1` values) |
| HTF trend gate: close vs EMA50, RSI14 vs 50, EMA50 5-bar slope | context (D1 ref; W1 for D1 cell) | **only after the context bar has CLOSED** — contract §4 mechanical form: shift context index forward one full context interval, `merge_asof(..., direction="backward", allow_exact_matches=False)`. A D1 bar closing exactly at the H4 open `t` is NOT usable for the decision at `t`'s close (strict inequality — conservative). |
| Volume filter (`Volume > 1.5 × SMA(Volume, 20)`) | — | **DROPPED.** It is explicitly "optional" in the source, and `Volume` here is OANDA **tick count**, not traded volume — an unvalidated proxy for the intended activity spike. Keeping it would inject proxy noise; dropping it is the faithful reading of "optional". Flagged per inviable rule 5; see §10 #4. |
| Session / news / calendar gates | — | none in the source; none added (no such data exists anyway) |

## 9. Causality audit
Bars are stamped at their OPEN; "known at close of `t`" means computable from OHLC of bars ≤ `t`. Decision at close of `t`; fill eligibility from `t+1` (F1). No rule in this strategy uses swing points, ZigZag, pivots, or fractals, so no confirmation-lag construct from `causal_structure` is needed; the only structural level (10-bar extreme) is a rolling window over **closed** bars with **zero** confirmation lag.

| Rule | Inputs fully known at | Lag / notes |
|---|---|---|
| EMA20/EMA50 trend (primary) | close of `t` | 0 bars; EMA is causal (recursive over past closes only) |
| Pullback corridor (bar `t−1` close between EMAs) | close of `t` | uses only `t−1` values; 1-bar look-back, fully causal |
| Reclaim cross (`Close[t]` vs `EMA20[t]`, `Close[t−1]` vs `EMA20[t−1]`) | close of `t` | 0 bars beyond the completed bar `t` |
| RSI14 zone (primary) | close of `t` | 0 bars; RSI is causal |
| 10-bar lowest low / highest high (stop) | close of `t` | 0 bars; `min`/`max` over `Low/High[t−9 … t]`, all closed bars. NOT a swing detector; no confirmation lag by construction |
| ATR14 (trail) | close of each bar `k ≥ t+1` as it completes | F9: trail updates at bar close using that bar's completed ATR |
| TP1/TP2 levels | close of `t` | arithmetic on `Close[t]` and stop, both known at decision |
| **HTF close > EMA50 (D1 ref cell)** | the context bar's **close**: a D1 bar stamped `s` (open) covers `[s, s+24h)` and is knowable only from `s+24h` onward | Mechanical form: D1 index shifted +1 D1 interval, then `merge_asof(h4, d1, backward, allow_exact_matches=False)`. An H4 decision bar `t` sees only D1 bars with `s + 24h < t` (i.e., strictly closed before the H4 bar even opens — one full bar more conservative than "closed before the H4 decision"). Worst-case information age: up to 48h old (a D1 bar closing just after `t` must wait for the next H4 decision). |
| **HTF RSI14 > 50, EMA50 5-bar slope** | same as above — all three HTF conditions use the same last-fully-closed context bar `d`; the slope additionally needs context bar `d−5`, already closed by definition | same lag as above |
| **W1 context (D1-primary cell only)** | Derived from D1: weekly value at D1 bar `u` = resample of D1 closes ≤ `u` into the Sun 21:00 → Sun 21:00 UTC week, using only weeks whose final D1 close ≤ `u` has occurred. A derived W1 bar is "closed" only when its last constituent D1 bar has closed, then shifted +1 W1 interval per §4 before informing D1 decisions. | Knowability horizon: honest bound = up to 7 days + 1 day of staleness vs. a naive weekly join, PLUS zero extra staleness from the DB (unlike stored W1, which is ~8 weeks stale near the live edge — rejected, §10 #5). |

## 10. Ambiguities resolved
| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | "Previous bar closed between EMA20 and EMA50" — are touches of the EMAs included? | **Strict** inequalities (`EMA50[t−1] < Close[t−1] < EMA20[t−1]`), matching the pseudocode `<` / `>`; equality cases produce no signal | Inclusive bounds — more signals, includes marginal "pullbacks" that never entered the corridor |
| 2 | "Initial SL **beyond** swing low / 10-bar lowest low" — how far beyond? | Exactly at the 10-bar extreme (pseudocode `low.rolling(10).min()`); "beyond" would require inventing an unstated buffer, and no-buffer is the tighter stop → more stop-outs → conservative | Adding a buffer (e.g., 1 pip or an ATR fraction "beyond") — invents a parameter the author never quantified |
| 3 | Is R measured from the actual fill or the decision close? | **Decision-bar close** `Close[t]` (fleet rule: market fill is unknowable at emission; all geometry must be declarable at OrderIntent creation). Realised R ≠ declared R on gapped fills; F3/F6 keep fills honest | Fill-anchored R (source's "TP1 at 1R" most naturally reads from fill) — **inexpressible** in contract v2, not merely less conservative |
| 4 | "Optional volume > 1.5×SMA(volume,20)" — keep or drop, given Volume is OANDA tick count? | **Dropped.** The source itself marks it optional; tick count is an unvalidated proxy for traded-volume spikes and the filter's sign of effect on trade quality is unknown | Keeping it with tick volume as a silent proxy — banned by inviable rule 5; would also arbitrarily cut trade count based on a quantity the strategy's edge does not rest on |
| 5 | W1 context for the D1-primary cell: stored W1 is stale ~8 weeks | **Derive weekly context causally from the D1 frame** (resample; a derived W1 bar closes only when its last constituent D1 bar closes, then §4 shift). Current, exactly causal, zero extra parameters | Using stored W1 as-is — near the live edge the "last closed week" could be ~8 weeks + 6 days old, silently degrading the filter to near-constant; also `ffill` of stale data masks the staleness |
| 6 | Does the ATR trail apply to the whole position or only the post-TP1 "remainder"? | Contract-native: single `StopRule` with `trail_atr_multiple=2.0` active from entry (F9, never widens) and `move_to_breakeven_on="TP1"`. Early in the trade `Close − 2×ATR` is usually below the 10-bar-low stop, so the practical effect ≈ trail-on-remainder | A two-stop model (trail only after TP1) is inexpressible in the contract's single-StopRule-per-intent design; activating the trail from entry can only tighten the stop sooner → conservative |
| 7 | Reclaim cross: must `Close[t−1]` be **strictly** below EMA20? | `Close[t−1] <= EMA20[t−1]` (equality allowed) per pseudocode `rec=(df.close>ef)&(df.close.shift(1)<=ef.shift(1))`; condition 2 already forces `Close[t−1] < EMA20[t−1]` in practice, so this reading is identical whenever the corridor condition holds | Strict `<` on the cross term alone — redundant given condition 2 and would only create an inconsistent pair of definitions |

## 11. Expected behaviour
- **Trade frequency:** this is a selective trend-pullback system. On H4 with the triple D1 gate, expect roughly **2–6 trades per pair per month** in trending years and long silent stretches in ranges (the corridor + cross + RSI-zone conjunction is restrictive; the HTF gate typically vetoes 30–60% of primary-frame signals). Across 5 live pairs × H4 that is plausibly 100–300 OOS trades over a 10-year backtest; the D1-primary cell will be materially thinner (~1–2/month/pair). The H1-primary cell trades most often but is the most whipsaw-prone.
- **What would make it fail the gates:** (a) prolonged mean-reverting regimes where price oscillates across both EMAs — the reclaim cross fires into failed trends and the 10-bar-extreme stop (often 1.5–3× ATR away on H4) loses full R repeatedly; (b) the RSI 40–60 zone blocking entries on strong momentum pullbacks (RSI > 60), leaving only the weaker setups; (c) F5 stop-before-target pessimism at H1 resolution, which is material because TP1 at 1R and the stop can sit inside one H4 bar's H1-resolved range; (d) gap-through-stop losses > 1R (F6) on weekend opens, visible via `gapped=True`.
- **Is the author's MODERATE conviction justified by the rules as written?** Yes — appropriately calibrated. The logic is fully mechanical, non-repainting, and every component is causal as specified; the 1R/2R scale-out with BE-after-TP1 and ATR trail is a coherent, defensible exit structure that maps onto contract v2 with no leftover interpretive slack. But the author documents no backtest, the edge rests entirely on EMA-corridor pullbacks (a crowded, well-arbitraged pattern), and the MODERATE (not HIGHLY_RECOMMENDED) tag correctly reflects "sound construction, unproven expectancy" — exactly what the Wave-2 backtest is for.
