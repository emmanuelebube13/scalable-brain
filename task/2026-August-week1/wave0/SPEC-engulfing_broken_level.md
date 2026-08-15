# SPEC-engulfing_broken_level

**Source:** row 32 of forex_swing_strategies.csv · https://dailypriceaction.com/blog/how-to-trade-the-bearish-engulfing-pattern/
**Conviction (author's):** MODERATE

## 1. Hypothesis

When a daily bearish (or bullish) engulfing candle forms at a previously confirmed swing extreme *and* closes through a nearby key level, it marks the point where the last group of breakout/trend-continuation traders is trapped on the wrong side of a level that has already proven itself. The edge claimed is that large-range daily engulfing candles at well-tested levels represent genuine institutional order-flow reversal rather than noise: daily candles aggregate a full session of participation, so a range that swallows the prior day's range and closes through a level forces a broad cohort of positions underwater, whose exits fuel the move toward the next level. It should persist because level memories and trapped-trader liquidation are structural features of how FX flow works, not an arbitrageable micro-pattern; the D1-only restriction is the author's explicit defence against the noise that swamps the pattern on lower timeframes.

## 2. Scope

- **primary_granularity:** D1 (all signal logic; "ignore all engulfing patterns below the daily timeframe")
- **context_granularities:** none. The source's optional "H4 pin-bar retest entry" is **rejected** (§10 #5); the strategy as specified here is single-timeframe D1.
- **simulate_on:** H1
- **pairs_requested (verbatim):** "Forex majors and minors (example: NZDUSD daily)"
- **pairs_available:** EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD (live) · GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD (**pending** — Wave-1 additions; harness skips pairs with insufficient history)
- **pairs_missing:** none. "Majors and minors" is fully covered by the 5 live + 8 pending FX pairs. No DATA-GAP file is required.

## 3. Indicators

| Indicator | Params | Source |
|---|---|---|
| Confirmed swing highs/lows | `period=5`, on D1 high/low | `causal_structure.confirmed_swing_points` — stamped at confirmation bar k+5, carrying the level set at k |
| Rolling access to historical confirmed swing levels | levels + confirmation-bar timestamps, full history (strategy filters by level & recency itself) | derived from `confirmed_swing_points` output (no new indicator needed) |
| ATR | `period=14`, on D1 H/L/C | `indicators.atr` (inventory) |

No other indicators. `detect_swing_points` is BANNED and is not used. Candle arithmetic (engulfing inequalities, midpoint) is plain bar data, not an indicator.

## 4. Entry — long

All references below are to D1 bars. Decision bar = bar **t**, evaluated at its close. `ATR14` = ATR(14) value at bar t.

**Structural levels knowable at the close of bar t** (see §9 for confirmation lags):

- `L_swing` = level of the most recent confirmed swing **low** whose confirmation bar ≤ t−1. If none exists in history, no long signal.
- `R_break` = min{ level ℓ of confirmed swing **highs** : ℓ > low_t, confirmation bar ≤ t−1 }. (The nearest confirmed swing-high level lying above the current candle's low — the "key resistance" to be broken.) If the set is empty, no long signal.

**Conditions (all at close of D1 bar t):**

1. Bullish candle: close_t > open_t.
2. Range engulfing: high_t ≥ high_{t−1} AND low_t ≤ low_{t−1}.
3. Body engulfing (strict version, §10 #1): close_t ≥ open_{t−1} AND open_t ≤ close_{t−1}.
4. Closes beyond prior candle's extreme (strict version): close_t > high_{t−1}.
5. Forms at a confirmed swing low: low_t ≤ L_swing (the candle's low touches or undercuts the last confirmed swing-low level).
6. Breaks the key resistance by **close**: close_t > R_break.
7. A valid take-profit level exists (§7): the set { confirmed swing-high levels ℓ : ℓ > entry_price, confirmation bar ≤ t } is non-empty.

**Entry type:** `buy_limit`
**Entry level:** `entry_price = low_t + 0.5 × (high_t − low_t)` (the 50% retracement / midpoint of the engulfing candle's range — identical to the source pseudocode's `high − 0.5×(high−low)`).
**expires_after_bars:** **24**, counted in simulation-frame (H1) bars = exactly one D1 bar. Emitted at the close of D1 bar t, eligible from the first H1 bar of D1 bar t+1 (F1), cancelled unfilled at the end of D1 bar t+1. This makes harmful pending overlap impossible — the next possible OrderIntent has decision_bar ≥ t+1 and is eligible only from bar t+2, after this order has expired (§10 #8).

## 5. Entry — short

Exact mirror. Same structural definitions, with `H_swing` = level of the most recent confirmed swing **high** whose confirmation bar ≤ t−1, and `S_break` = max{ level ℓ of confirmed swing **lows** : ℓ < high_t, confirmation bar ≤ t−1 } (nearest confirmed swing-low level below the candle's high — the "key support" to be broken). If either does not exist, no short signal.

**Conditions (all at close of D1 bar t):**

1. Bearish candle: close_t < open_t.
2. Range engulfing: high_t ≥ high_{t−1} AND low_t ≤ low_{t−1}.
3. Body engulfing: close_t ≤ open_{t−1} AND open_t ≥ close_{t−1}.
4. Closes beyond prior candle's extreme: close_t < low_{t−1} (the source's "best if body engulfs and closes below prior low" refinement — adopted as mandatory).
5. Forms at a confirmed swing high: high_t ≥ H_swing.
6. Breaks the key support by **close**: close_t < S_break.
7. A valid take-profit level exists: { confirmed swing-low levels ℓ : ℓ < entry_price, confirmation bar ≤ t } is non-empty.

**Entry type:** `sell_limit`
**Entry level:** `entry_price = high_t − 0.5 × (high_t − low_t)` (same midpoint formula).
**expires_after_bars:** **24** H1 simulation bars (= 1 D1 bar), same overlap-free arithmetic as the long side.

A single bar cannot satisfy both the long and short candle conditions (a bar cannot be both bullish and bearish), so each decision bar emits at most one OrderIntent.

## 6. Stop

- **Initial stop (long):** `stop = low_t − 0.5 × ATR14` (below the engulfing candle's low, buffer = 0.5×ATR(14) at decision bar).
- **Initial stop (short):** `stop = high_t + 0.5 × ATR14`.
- **move_to_breakeven_on:** none.
- **trail:** none.

The stop is an absolute price declarable at OrderIntent creation from decision-bar data (Fleet Rule 8 satisfied: entry/stop/TP are all anchored to bar t's OHLC and pre-confirmed levels, never to the unknowable fill price).

## 7. Exit legs

| Label | Fraction | Kind | Level formula |
|---|---|--:|---|---|
| TP1 | 1.0 | take_profit | long: `TP = min{ confirmed swing-high levels ℓ : ℓ > entry_price, confirmation bar ≤ t }` (nearest confirmed resistance above the entry limit price) · short: `TP = max{ confirmed swing-low levels ℓ : ℓ < entry_price, confirmation bar ≤ t }` (nearest confirmed support below the entry limit price) |

Fractions sum to 1.0. The level set is frozen at decision bar t; it is NOT re-anchored to the eventual fill price (Fleet Rule 8). Note the deliberate asymmetry: the TP search space is anchored on `entry_price` (the limit level), while the break level in §4/§5 is anchored on the candle's extreme — both are knowable at the close of bar t. Condition 7 of each entry guarantees this set is non-empty, so every emitted order has a TP strictly beyond entry in the trade direction (OrderIntent validation-safe).

## 8. Filters

| Filter | Timeframe | When knowable |
|---|---|---|
| Timeframe gate: "ignore all engulfing patterns below the daily timeframe" | structural — strategy only ever reads D1 | n/a (design decision, not a runtime filter) |
| Swing-extreme proximity (condition 5) | D1, confirmed swings period=5 | close of bar t (confirmation of the referenced swing occurred ≤ bar t−1) |
| Key-level break (condition 6) | D1 | close of bar t |
| Valid-target-exists (condition 7) | D1 | close of bar t |
| Risk 1–2% per trade | — | **Not implemented.** Contract v2 does no position sizing (`size_fraction` is relative leg allocation only; sizing is System 3's job). Recorded here so the source field is not silently dropped. Results are in r-multiples. |

No session, volatility, news, or spread filters exist in the source and none are added. The 1.0-pip cost-model spread is applied by the engine (F10), not by the strategy — no proxy invented.

## 9. Causality audit

| Rule | Inputs | Fully known at | Confirmation lag |
|---|---|---|---|
| Candle direction / range engulf / body engulf / close-beyond (cond. 1–4) | OHLC of D1 bars t and t−1 | close of D1 bar t | none (completed bars only) |
| `L_swing` / `H_swing` (cond. 5) | `confirmed_swing_points(period=5)` | close of D1 bar t | a swing at bar k is knowable at k+5; we additionally require confirmation bar ≤ **t−1**, so no swing confirmed on the signal bar itself is used (conservative; §10 #9). The *level* used was set at occurrence bar k — legitimate per the causal-swing semantics |
| `S_break` / `R_break` (cond. 6) | confirmed swing levels, confirmation ≤ t−1 | close of D1 bar t | same +5-bar lag, same ≤ t−1 requirement |
| TP level set (§7) | confirmed swing levels, confirmation ≤ t | close of D1 bar t | +5-bar lag on every level in the set |
| ATR14 buffer (§6) | D1 bars t−13 … t | close of D1 bar t | none |
| Entry/stop/TP geometry | bar t OHLC + above levels | all absolute, declarable at OrderIntent creation at close of bar t | — |
| Fill resolution | OrderIntent eligible from H1 bars of D1 bar t+1 onward (F1) | — | pending limit fills only after the decision bar; H1 simulation respects §4 MTF rule trivially because the strategy never reads H1 |
| Expiry (24 H1 bars) | — | order dead at end of D1 bar t+1 | next possible intent (decision_bar = t+1) is eligible only from t+2 ⇒ no two pending orders of this strategy on one pair are ever live simultaneously |

No rule uses any bar stamped after t. No centred windows. `detect_swing_points` is not used. There is no MTF context (H4 retest rejected), so the §4 context-bar rule has nothing to bite on — stated explicitly so reviewers can verify it was considered.

## 10. Ambiguities resolved

| # | Ambiguity | Conservative reading taken | Alternative rejected |
|--:|---|---|---|
| 1 | "Range fully engulfs" vs "best if body engulfs and closes below prior low" — the pseudocode only checks range | Strict version adopted as mandatory: range engulf AND body engulf AND close beyond prior candle's opposite extreme (cond. 2–4). Fewer, higher-quality trades | Pseudocode's range-only test (more trades, but the author's own "best if" refinement dropped) |
| 2 | "Forms at a swing high/low" — how near is "at"? | Exact touch: candle extreme must reach/undercut the last confirmed swing level (high_t ≥ H_swing / low_t ≤ L_swing). No tolerance band | A 0.25×ATR proximity tolerance (would admit candles merely near the level — more trades, invented parameter) |
| 3 | "Breaks below/above a key level" — wick or close? | Close beyond the level (cond. 6) | Wick beyond the level (looser; intrabar spikes through support that close back inside would qualify) |
| 4 | "Key support/resistance level" is semi-subjective in the source | Mechanized as the nearest confirmed swing-extreme level on the far side of the signal candle (S_break/R_break definitions); recency = most recent by confirmation time, no lookback cap | Discretionary hand-drawn levels (inexpressible); a fixed lookback cap such as "levels confirmed within 120 bars" (invented parameter, would discard valid older levels) |
| 5 | Two entry variants offered: blind 50% retracement limit OR H4 pin-bar retest confirmation | Blind 50% limit on D1 — fully mechanical, single-timeframe, no pattern discretion | H4 pin-bar retest: requires mechanizing "pin bar" (wick ratios — invented parameters), adds an MTF causality surface, and is a second entry style the source presents as an alternative, not a complement. Choosing ONE variant as instructed; the blind limit is also the one the source's own pseudocode implements |
| 6 | "Skip setups whose target is too close for acceptable R" — no number given; the 3R in the source is the worked example, not a rule | **No minimum-R filter; all setups with a valid TP beyond entry are kept.** Any numeric threshold would be an invented parameter; realized R distribution must be reported instead. Acknowledged as the *less* trade-restrictive reading, taken because the only alternative is fabrication | A stated minimum such as TP ≥ 1.5R (defensible economically but has zero support in the source text; would also make results non-comparable to the strategy as documented) |
| 7 | Stop buffer "above the high" — size unspecified | 0.5 × ATR(14) at decision bar. On D1 candles a fixed few-pip buffer sits inside normal retest noise; 0.5 ATR is the standard "beyond the level with room" reading and is decision-bar knowable | Fixed 10 pips (noise-level on D1 for JPY vs non-JPY pairs); no buffer (stop exactly at candle extreme — most stop-outs) |
| 8 | Pending-order lifetime unspecified; contract default is 5 (frame-ambiguous) | 24 H1 simulation bars = exactly one D1 bar, with proof that pending lifetimes of consecutive signals can never overlap (§9). Shortest defensible lifetime = fewest fills, and eliminates all residual multi-fill risk under the no-OCO contract (Fleet Rule 7) | Longer lifetimes (48–72 H1): more fills but re-introduces overlapping pendings on consecutive signal days, which F12 does not gate — residual same-direction double-position risk |
| 9 | May a swing confirmed *on* the signal bar t be used as the "at a swing" reference? | No — confirmation bar must be ≤ t−1 for cond. 5 and 6. A swing confirmed at t is knowable at the close of t and would technically be legal, but excluding it is strictly more conservative and removes any doubt about within-bar ordering of confirmation vs signal evaluation | Allowing confirmation ≤ t (marginally more trades) |
| 10 | 50% retracement of *which* range — candle range or body? | Full high–low range midpoint (matches source pseudocode `high − 0.5×(high−low)`) | Body midpoint (no textual support) |
| 11 | Realized R vs declared R | All geometry anchored at decision bar t; the limit fill occurs at exactly entry_price (F3: limits fill at L, no improvement), so realized risk equals declared risk *unless* the position later gaps through its stop (F6) — reported per trade via `gapped` flag, no strategy-side handling | Fill-anchored re-computation of stop/TP after fill — inexpressible in contract v2 (strategy never observes fills), rejected as a mechanism, not merely as less conservative |

## 11. Expected behaviour

- **Trade frequency:** low. Four candle conditions + swing proximity + level break + valid target on D1 is a demanding conjunction. Estimate 1–5 signals per pair per year; across 13 pairs over ~20 years of D1 history, roughly 300–900 emitted orders, of which perhaps 60–80% fill within the 1-day expiry. Per (pair × granularity) cells will often have single-digit trade counts in 6-month OOS windows — expect `low_confidence` flags at cell level; the pooled verdict is the meaningful one.
- **What would make it fail the gates:** the entry is a 50% retracement *into* a candle that just broke a level — in choppy, mean-reverting daily regimes the retracement fills and the level re-breaks against the position repeatedly, and with TP at the *nearest* next level (often < 1.5R away given no minimum-R filter, §10 #6) the payoff asymmetry may not cover a sub-50% win rate after costs. Weekend gaps through D1-scale stops (F6) will produce occasional losses > 1R. If confirmed-swing levels prove to be poor proxies for the author's hand-drawn levels (§10 #4), the strategy tested is not quite the strategy documented — that divergence is a finding in itself.
- **Is MODERATE justified by the rules as written?** Yes, and the rules as mechanized here are arguably *more* credible than the source: the three-requirement filter is now fully objective, every level is causally confirmed, and the single-anecdote evidence base (one 3R NZDUSD trade) is honestly flagged. Nothing in the mechanization adds optimism — every discretionary element was resolved toward fewer trades, later confirmation, and worse fills. If this strategy fails the gates, it fails honestly.
