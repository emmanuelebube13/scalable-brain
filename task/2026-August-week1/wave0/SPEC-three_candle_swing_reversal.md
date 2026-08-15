# SPEC-three_candle_swing_reversal
**Source:** row 15 of forex_swing_strategies.csv · https://www.forexfactory.com/thread/759887-daily-chart-3-candle
**Conviction (author's):** MODERATE

## 1. Hypothesis
After a sustained multi-day decline, a three-bar pattern of ascending lows culminating in a close back through the first bar's body marks seller exhaustion: the marginal seller has been absorbed at successively higher lows and trapped shorts must cover, producing a multi-session counter-swing worth roughly 100 pips. The edge persists because daily-bar participants (the last timeframe dominated by discretionary position traders rather than HFT) anchor on prior-day bodies as reference levels, so a reclaim of the pattern's origin level triggers mechanical short-covering and fresh dip-buying. The author's MODERATE conviction is honest: win rate was never measured.

## 2. Scope
- **primary_granularity:** D1 (the strategy is named "Daily Chart 3-Candle"; D1 is the coarsest declared frame and produces the fewest, cleanest signals — conservative choice, see §10 #8)
- **context_granularities:** none for the declared D1 run. (The source's "H1 only in direction of D1 trend" variant is REJECTED as the declared implementation; its causality rule is stated in §9 regardless.)
- **simulate_on:** H1 (per contract Part D: decided on D1, fills resolved on H1 bars)
- **pairs_requested (verbatim):** `EURUSD|NZDUSD|USDCAD|USDJPY|GBPCAD|GBPNZD|XAUUSD`
- **pairs_available:** EUR_USD (live), USD_CAD (live), USD_JPY (live), NZD_USD (**pending** — Wave-1 addition, not a gap)
- **pairs_missing:** GBP_CAD (NOT in Wave-1 list → DATA-GAP), GBP_NZD (NOT in Wave-1 list → DATA-GAP), XAU_USD (excluded by policy → DATA-GAP)
- **granularity gap:** H12 is named ("D1 primary|H12|H4 confirmation") but is NOT in the allowed set {H1, H4, D1, W1} → DATA-GAP; mitigated by choosing D1 as primary (see DATA-GAP-three_candle_swing_reversal.md).

## 3. Indicators
| Indicator | Params | Source |
|---|---|---|
| Pip size | per asset (0.0001 for EUR_USD/NZD_USD/USD_CAD; 0.01 for USD_JPY) | `indicators.get_pip_value` / `calculate_pips` (inventory) |
| BAR1/BAR2/BAR3 bar references | BAR3 = decision bar t; BAR2 = t−1; BAR1 = t−2 | private, fully specified in §4 — plain OHLC shifts, no indicator needed |
| Trend filter (3-day LH/LL or HH/HL) | bars t−3, t−4, t−5 | private, fully specified in §8 — raw OHLC comparisons, no indicator needed |
| Swing-point indicator ("optional companion", 7000+ downloads) | — | **NOT USED.** The 3-bar pattern is fully mechanical from OHLC; no swing/ZigZag/fractal detection is required, so `causal_structure` is not needed and `detect_swing_points` is not touched |

No other indicators. The strategy is pure price-action on completed bars.

## 4. Entry — long
Decision bar = D1 bar **t** (BAR3), evaluated at its close. BAR2 = t−1, BAR1 = t−2. `pip` = asset pip size.

Conditions (ALL must hold at the close of bar t):
1. **Trend filter:** bars t−3, t−4, t−5 show 3 consecutive sessions of lower highs and lower lows: `high[t−3] < high[t−4]` AND `high[t−4] < high[t−5]` AND `low[t−3] < low[t−4]` AND `low[t−4] < low[t−5]`.
2. **Ascending lows across the pattern:** `low[t−1] > low[t−2]` AND `low[t] > low[t−1]` (BAR2 low above BAR1 low; BAR3 low above BAR2 low — the author's own pseudocode reading of "two bars to its left having higher lows").
3. **Trigger level:** `TRIG = min(open[t−2], close[t−2])` (equals BAR1 close if BAR1 bearish, BAR1 open if BAR1 bullish — exactly as the source states).
4. **Trigger event:** `close[t] > TRIG`.
5. **Emission suppression (order-lifecycle guard):** no long signal was emitted at decision bar t−1 or t−2 (see §10 #6 for the arithmetic).

- **Entry type:** `buy_limit`
- **Entry level:** `E_long = min(open[t−2], close[t−2])` (BAR1 open if bullish, BAR1 close if bearish — identical to TRIG, per the source). Since condition 4 gives `close[t] > E_long`, the limit is below the decision close: a valid pending order under contract §2.2 validation.
- **expires_after_bars:** **2** (order eligible from bar t+1 per F1; may fill on t+1 or t+2 = "BAR4 or BAR5"; cancelled thereafter).

## 5. Entry — short
Full mirror at the close of D1 bar t:

1. **Trend filter:** `high[t−3] > high[t−4]` AND `high[t−4] > high[t−5]` AND `low[t−3] > low[t−4]` AND `low[t−4] > low[t−5]` (3 consecutive sessions of higher highs and higher lows).
2. **Descending highs across the pattern:** `high[t−1] < high[t−2]` AND `high[t] < high[t−1]`.
3. **Trigger level:** `TRIG_S = max(open[t−2], close[t−2])` (BAR1 close if BAR1 bullish, BAR1 open if BAR1 bearish).
4. **Trigger event:** `close[t] < TRIG_S`.
5. **Emission suppression:** no short signal emitted at t−1 or t−2.

- **Entry type:** `sell_limit`
- **Entry level:** `E_short = max(open[t−2], close[t−2])` (above the decision close by condition 4 — valid pending).
- **expires_after_bars:** **2**.

Long and short filters are mutually exclusive at any decision bar (a market cannot simultaneously print 3 sessions of LH/LL and 3 sessions of HH/HL over the same bars), so two-sided pending overlap is impossible by construction.

## 6. Stop
- **Initial stop (long):** `S_long = min( E_long − 50·pip, min(low[t−2], low[t−1]) − 15·pip )` — "the greater of 50 pips or 15 pips below the swing low", with the swing low taken as the lower of BAR1/BAR2 lows (per the source's "if BAR1 has a lower low than BAR2 use BAR1 low"; note condition §4.2 forces `low[t−2] < low[t−1]`, so the min is `low[t−2]`, but the formula is written generally). Both terms are below E_long, so the stop is valid.
- **Initial stop (short):** `S_short = max( E_short + 50·pip, max(high[t−2], high[t−1]) + 15·pip )`.
- All stop inputs (E, highs/lows of t−1, t−2) are decision-bar-knowable absolute prices; R is measured from the declared entry level E, not the unknowable fill (F3/F6 resolve the fill honestly; realized R ≠ declared R on gaps — accepted, recorded in §10 #9).
- **move_to_breakeven_on:** none.
- **trail:** none (`trail_atr_multiple = null`). The source's "swing traders may hold longer" is discretionary and is not mechanised.

## 7. Exit legs
| Label | Fraction | Kind | Level formula |
|---|---|---:|---|
| TP1 | 1.0 | take_profit | long: `E_long + 100·pip` · short: `E_short − 100·pip` |

Fractions sum to 1.0. Single full-size leg. The 100-pip end of the source's "100–200 pips" range is mandatory here anyway: the source says "keep TP at 100 pips for counter-trend setups", and every signal this strategy generates is by construction counter-trend (longs fire after ≥3 down sessions; shorts after ≥3 up sessions). See §10 #4.

## 8. Filters
| Filter | Timeframe | Rule | Knowable at |
|---|---|---|---|
| Downtrend (long) / uptrend (short), ≥3 sessions | D1 | §4.1 / §5.1 — strict pairwise comparisons over bars t−3, t−4, t−5 | close of bar t (all three bars closed by then) |
| Emission suppression | D1 | no same-direction signal emitted at t−1 or t−2 — a pure function of data ≤ t−1, recomputed deterministically; the strategy never observes fills or pendings | close of bar t |
| H1 variant D1-trend filter | D1 → H1 | **REJECTED variant** (§10 #8). If ever implemented: a D1 bar stamped at open T may inform H1 decisions only from T+24h onward (`merge_asof(..., allow_exact_matches=False)` on the D1 index shifted one full D1 interval) | after the D1 bar's close |

No session, news, volatility, or spread filters exist in the source. No non-price data is required. The F10 cost model (1.0-pip spread, 0.5-pip entry slippage) is applied by the engine, not the strategy.

## 9. Causality audit
| Rule | Inputs | All inputs fully known at |
|---|---|---|
| §4.1 / §5.1 trend filter | OHLC of bars t−3, t−4, t−5 | close of bar t (latest input closed at t−3's close) |
| §4.2 / §5.2 pattern (ascending lows / descending highs) | lows/highs of t, t−1, t−2 | close of bar t |
| §4.3 / §5.3 trigger level | open/close of t−2 | close of bar t−2 |
| §4.4 / §5.4 trigger event | close of t | close of bar t — the decision bar itself; order becomes fill-eligible only from t+1 (F1) |
| §4.5 / §5.5 suppression | signal state at t−1, t−2 (function of data ≤ t−1) | close of bar t |
| §6 stop | E (open/close of t−2), high/low of t−1, t−2 | close of bar t; absolute price declared at OrderIntent creation |
| §7 TP1 | E only | close of bar t; absolute price declared at OrderIntent creation |
| Swing/ZigZag/fractal confirmation lag | **none used** | N/A — the "3-bar swing point" is a raw 3-bar inequality over fully closed bars, NOT a confirmed-swing detection. There is no hidden confirmation lag: BAR1, BAR2, BAR3 are t−2, t−1, t and ALL THREE are fully closed at the decision instant (the decision is made at the close of t, so t's OHLC is complete; t−1 and t−2 closed earlier). `detect_swing_points` is not used; no `causal_structure` function is needed. |
| MTF (rejected H1 variant) | D1 trend state | A D1 context bar may inform an H1 decision only after that D1 bar has CLOSED: D1 bar stamped T (its open) covers [T, T+24h) and is first usable at the H1 bar stamped T+24h. Bars are stamped at their open. |

No rule reads any bar later than the decision bar. Pending fills obey F1/F3/F4; stop-first ordering F5 and gap fills F6 are engine-side and pessimistic.

## 10. Ambiguities resolved
| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|--|---|---|
| 1 | "two bars to its left having higher lows" — higher than what? | Author's pseudocode reading: ascending lows across all three pattern bars (`low[t−1] > low[t−2]` AND `low[t] > low[t−1]`) — stricter, fewer signals | Looser English reading (only BAR2 low > BAR1 low, BAR3 low unconstrained) — more signals |
| 2 | "trending down ≥3 days (lower highs and lower lows)" — undefined | Strict: three fully closed pre-pattern bars (t−3, t−4, t−5) with pairwise lower highs AND lower lows | Author's weaker pseudocode (`close[t] < close[t−3]` AND `low[t] < low[t−1]`) — note his own `low[t] < low[t−1]` CONTRADICTS his pattern condition `low[t] > low[t−1]`; the pseudocode trend clause can never fire together with the pattern as written, so it was unusable verbatim |
| 3 | "enter BUY (or buy limit)" | `buy_limit` at E — fewer fills, only on a pullback to the pattern origin | `market` at next open — more fills at worse prices |
| 4 | "average TP 100–200 pips, swing traders may hold longer" | 100 pips (also mandated by the source's own counter-trend clause, which covers every signal here) | 200 pips; "hold longer" discretionary extension |
| 5 | Stop: "greater of 50 pips or 15 pips below BAR2 low", with BAR1-low override | `min(E − 50p, min(low[t−1], low[t−2]) − 15p)` — the wider (further) stop, keeping the 50-pip minimum distance always | Author's pseudocode override `where(b1.low < b2.low, b1.low − 15p, …)` which silently DROPS the 50-pip floor whenever the override fires (it always fires, given §4.2) — a tighter stop than the prose states |
| 6 | "same rules if BAR4 or BAR5 closes above BAR1 and BAR2 prices" — re-signal window | `expires_after_bars = 2` (fills on t+1/t+2 = BAR4/BAR5 exactly) PLUS emission suppression at t−1/t−2. Arithmetic: one emission per 3 decision bars per direction; expiry 2 ⇒ at most one live pending per direction; long/short filters mutually exclusive ⇒ at most one live pending total, so no multi-fill stacking is possible from pendings. A pending MAY still fill while an earlier position is open — F12 caps concurrent POSITIONS at 1 and is engine-side; residual risk: none beyond F12 semantics | Re-emitting fresh OrderIntents on BAR4/BAR5 closes beyond both BAR1 and BAR2 levels — more orders, stacking risk; and GTC expiry |
| 7 | "protect/exit if price repeatedly fails at BAR1 price or at swing rejection levels" | Dropped — "repeatedly fails" is discretionary; position rides to TP1 or stop | Any invented mechanical version (e.g., a time exit after N bars) — no defensible N exists |
| 8 | Timeframes: "D1 primary | H12 | H4 confirmation | H1 only in direction of D1 trend" | D1 primary, no context frame — coarsest, fewest trades; H12 does not exist and H4 "confirmation" role is undefined in the source | H1-with-D1-trend-filter variant — far more trades, requires MTF wiring (its causality rule is stated in §9 should Wave 2 ever run it); H12 variant — granularity does not exist (DATA-GAP) |
| 9 | R measured from fill vs from declared entry | Anchored to decision-bar-knowable E (contract fleet rule: fill price unknowable at emission); realized R ≠ declared R when the fill gaps or improves, F3/F6 resolve honestly | Fill-anchored geometry — inexpressible in contract v2, not merely less conservative |
| 10 | "win-probability grading… Best Buy/Best Sell lines for continuation entries" | Dropped — no mechanical definition of the grading or the lines; `size_fraction` stays 1.0; no continuation entries | Any guessed grading rule — pure invention |

## 11. Expected behaviour
- **Frequency:** very low. The strict 3-session trend precondition plus the 3-bar ascending/descending pattern plus the body-reclaim trigger, on D1, with 3-bar emission suppression: roughly **1–5 trades per pair per year**; over 4 available pairs and ~20 years of D1 history, expect order 100–400 trades total, split across pairs and long/short. Per walk-forward fold (6-month OOS), many cells will have 0–3 trades → `low_confidence` flags are likely; the pooled verdict will depend on pooling across pairs.
- **Geometry:** declared risk ≥ 50 pips, reward fixed at 100 pips ⇒ declared R:R ≤ 1:2, and the buy-limit fill at E is below the decision close so realized geometry matches declared geometry except on gaps. Break-even win rate ≈ 33% + costs; a genuine reversal edge must beat that on counter-trend D1 entries, which is plausible but unproven — the author never measured it.
- **What fails the gates:** thin per-cell trade counts; any regime where counter-trend D1 dips keep falling (the 50-pip-minimum stop is wide relative to the 100-pip target, so a sub-35% win rate bleeds steadily); H1-resolution vs native-resolution delta (Part D) should be small since TP/SL are far apart relative to H1 ranges — if it is large, the bar-path assumption is doing the work and the result is suspect.
- **Is MODERATE justified?** Yes — unusually for this CSV, the rules as written are almost fully mechanical (the author's own pseudocode is close to correct, with the two defects recorded in §10 #2 and #5), the thread is multi-year with heavy community usage, and the author explicitly disclaims any measured win rate. The spec is implementable exactly as declared; the open question is purely empirical.
