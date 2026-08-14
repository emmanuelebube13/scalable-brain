# SPEC-inside_bar_pinbar_combo
**Source:** row 31 of forex_swing_strategies.csv · https://dailypriceaction.com/blog/forex-pin-bar-trading-strategy/
**Conviction (author's):** MODERATE

## 1. Hypothesis
A two-bar exhaustion sequence — an inside bar (volatility compression, indecision) immediately followed by a pin bar with a pronounced rejection tail — occurring at a confirmed structural level after an extended trend leg, marks the point where the final momentum traders are trapped on the wrong side. The long tail is the footprint of aggressive absorption: breakout/panic sellers (long setup) are filled by larger participants at the level, and the strong close back into the inside bar's range confirms the failure of the push. Entering on a 50% retracement of the pin bar monetises the post-signal profit-taking dip of the trapped side before the reversal resumes. The edge should persist because it is anchored in the behavioural mechanics of stop runs and failed breakouts at widely-watched horizontal levels, not in an arbitrageable microstructure artifact.

## 2. Scope
- **primary_granularity:** D1 (source is explicit: "D1 only — patterns below daily are avoided")
- **context_granularities:** none (no MTF; all structure, trend, and level logic is evaluated on D1)
- **simulate_on:** H1 (per contract §5: decisions on D1, fills/stops/legs resolved on H1 bars within each D1 span)
- **pairs_requested (verbatim):** "Forex majors and minors (examples: AUDNZD, USDCAD)"
- **pairs_available:** EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD (live) · GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD (Wave-1 additions — **pending**; AUDNZD example is covered here)
- **pairs_missing:** none → no DATA-GAP note required. All data is OHLCV-only; `data_requirements` mentions "trend lines", which are dropped as not uniquely mechanizable (see §10 #8) — an interpretive drop, not a data gap.

## 3. Indicators
All series computed on the D1 frame. At decision bar `t`, only bars `≤ t` are used.

| Indicator | Params | Source |
|---|---|---|
| EMA of close | period 50, D1 close | inventory `ema` |
| ATR | period 14, D1 H/L/C | inventory `atr` |
| Confirmed swing points | period 5, D1 high/low | `causal_structure.confirmed_swing_points` — a swing high/low occurring at bar `k` is used only from bar `k+5` onward, carrying the level set at `k` |
| Inside bar (private) | exact formula: bar `j` is an inside bar iff `High[j] <= High[j-1]` **and** `Low[j] >= Low[j-1]` (inclusive, per the CSV pseudocode) | private — 2-line boolean, no window |
| Pin bar (private) | exact formula in §4/§5 (tail/body fractions of bar range) | private — per-bar geometry, no window |
| Strong close (private) | exact formula: `(Close[j] - Low[j]) > 0.60 * (High[j] - Low[j])` for bullish; mirror for bearish — verbatim from the CSV pseudocode | private — per-bar geometry |
| At-level proximity (private) | exact formula in §4/§5: distance of pin-bar extreme to a confirmed swing level, normalised by ATR(14) | private — combines `confirmed_swing_points` output with inventory `atr` |

`Volume` is not used. `detect_swing_points` is NOT used (banned, centered window).

## 4. Entry — long
Decision bar `t` is the **pin bar**; `t-1` is the inside-bar candidate; `t-2` is the inside bar's mother bar. All conditions evaluated at the **close of D1 bar t**.

Conditions (ALL must hold — conjunction):
1. **Inside bar at t-1:** `High[t-1] <= High[t-2]` AND `Low[t-1] >= Low[t-2]`.
2. **Bullish pin bar at t:** with `R[t] = High[t] - Low[t] > 0`, `lower_tail = min(Open[t], Close[t]) - Low[t]`, `upper_tail = High[t] - max(Open[t], Close[t])`: `lower_tail >= 0.60 * R[t]` AND `upper_tail <= 0.25 * R[t]`. (The "pronounced tail" clause mechanised; see §10 #2.)
3. **Close inside the inside bar's range:** `Low[t-1] <= Close[t] <= High[t-1]`.
4. **Strong bullish close:** `(Close[t] - Low[t]) > 0.60 * R[t]`. (Conditions 3 AND 4 — the source's "or" is resolved to the strict conjunction; see §10 #1.)
5. **Downtrend context:** `Close[t] < EMA50[t]` (EMA of D1 close, period 50).
6. **At confirmed support:** there exists a confirmed swing low with level `L` such that (a) it occurred at some bar `k` and was confirmed at bar `k+5 <= t`, (b) occurrence bar `k >= t - 250` (recency window, D1 bars), and (c) `|Low[t] - L| <= 0.25 * ATR14[t]`. (The "downtrend break of a key level / range support" clause tightened to at-level-only; see §10 #3.)
7. **Take-profit level exists:** there is at least one confirmed swing high level (same confirmation and recency rules as condition 6) strictly above the entry price `E` defined below. If none, **no trade** (skip; do not substitute an ATR target).

- **entry type:** `buy_limit`
- **entry level:** `E = (High[t] + Low[t]) / 2` — the 50% retracement (midpoint) of the pin bar. Note condition 4 guarantees `Close[t] > Low[t] + 0.60*R[t] > E`, so the limit is always below the decision close and the OrderIntent is valid (never already through the market).
- **expires_after_bars:** **2** (two D1 decision-frame bars; the limit is eligible to fill on D1 bars `t+1` and `t+2` only, per F1/F4 — i.e. the 48 H1 bars spanning those two D1 bars under H1 fill resolution). Overlap arithmetic: the earliest possible next signal needs an inside bar at `t+1` and a pin bar at `t+2`, is emitted at the close of `t+2`, and is fill-eligible from `t+3` (F1) — after this order has expired. Pending-order overlap is therefore impossible; no residual multi-fill risk. See §10 #7.

## 5. Entry — short
Exact mirror. Decision bar `t` is the pin bar. All conditions evaluated at the **close of D1 bar t**:

1. **Inside bar at t-1:** `High[t-1] <= High[t-2]` AND `Low[t-1] >= Low[t-2]`.
2. **Bearish pin bar at t:** `upper_tail = High[t] - max(Open[t], Close[t]) >= 0.60 * R[t]` AND `lower_tail = min(Open[t], Close[t]) - Low[t] <= 0.25 * R[t]`.
3. **Close inside the inside bar's range:** `Low[t-1] <= Close[t] <= High[t-1]`.
4. **Strong bearish close:** `(High[t] - Close[t]) > 0.60 * R[t]`.
5. **Up-move context:** `Close[t] > EMA50[t]`.
6. **At confirmed resistance:** exists a confirmed swing high level `L`, confirmed at `k+5 <= t`, `k >= t - 250`, with `|High[t] - L| <= 0.25 * ATR14[t]`.
7. **Take-profit level exists:** at least one confirmed swing low level strictly below `E`. If none, no trade.

- **entry type:** `sell_limit`
- **entry level:** `E = (High[t] + Low[t]) / 2` (condition 4 guarantees `Close[t] < E`).
- **expires_after_bars:** **2** (same arithmetic as §4).

## 6. Stop
- **initial stop (long):** `S = Low[t] - 0.10 * ATR14[t]` — beyond the pin-bar tail with a declared buffer of 0.10×ATR(14, D1) (see §10 #4).
- **initial stop (short):** `S = High[t] + 0.10 * ATR14[t]`.
- **move_to_breakeven_on:** none.
- **trail:** none (static stop; `trail_atr_multiple = None`).

All geometry is anchored to decision-bar-knowable values (pin-bar High/Low, ATR at close of `t`); no fill-anchored levels are used. Because entry is a limit, F3 fills at exactly `E`, so declared R equals realised R at entry (gap risk on the limit is nil by convention; exits may still gap per F6).

## 7. Exit legs
| Label | Fraction | Kind | Level formula |
|---|---|---:|---|---|
| TP1 | 1.0 | take_profit | Long: `min{ L : L confirmed swing-high level, confirmed by bar t, occurrence within trailing 250 D1 bars, L > E }` — the nearest confirmed swing-high level above entry. Short: `max{ L : L confirmed swing-low level, confirmed by bar t, occurrence within trailing 250 D1 bars, L < E }` — the nearest confirmed swing-low level below entry. |

Fractions sum to 1.0. Single-leg exit; no time stop (none in source). If no qualifying opposing level exists, the setup is skipped at entry (§4/§5 condition 7), so every emitted order always has a valid TP1. No minimum risk-to-reward gate is applied (source demands "favorable RR" but gives no number; not invented — §10 #5).

## 8. Filters
| Filter | Rule | Timeframe | Knowable at |
|---|---|---|---|
| Trend context | Long only if `Close[t] < EMA50[t]`; short only if `Close[t] > EMA50[t]` | D1 | Close of decision bar `t` |
| Level (confluence) | Pin-bar extreme within `0.25 * ATR14[t]` of a confirmed swing level (§4/§5 condition 6) | D1 | Close of decision bar `t` (level itself knowable since its confirmation bar `k+5 <= t`) |
| Tail quality ("pronounced") | Rejection tail `>= 0.60 * R[t]`, opposite wick `<= 0.25 * R[t]` | D1 | Close of decision bar `t` |

No session, volatility-band, news, or calendar filter exists in the source and none is added. No non-price data is used. The only spread representation is the harness cost model (F10: 1.0 pip spread + 0.5 pip entry slippage) — adequate for a D1 strategy whose stops are typically tens of pips; not a proxy concern.

## 9. Causality audit
Decision bar = D1 bar `t`; orders emitted at the **close** of `t`; fill-eligible from bar `t+1` onward (F1). Under H1 simulation, the D1 close of `t` corresponds to the H1 bar stamped 20:00Z of `t`'s session completing at 21:00Z; fills resolve on H1 bars strictly after that.

| Rule | Inputs | Fully knowable at |
|---|---|---|
| Inside bar at t-1 (cond 1) | OHLC of bars `t-2`, `t-1` | Close of `t-1` — strictly before decision |
| Pin bar geometry (cond 2) | OHLC of bar `t` | Close of `t` |
| Close inside IB range (cond 3) | `Close[t]`, `High[t-1]`, `Low[t-1]` | Close of `t` |
| Strong close (cond 4) | OHLC of bar `t` | Close of `t` |
| EMA50 trend filter (cond 5) | D1 closes through `t` | Close of `t` |
| At-level filter (cond 6) | Pin extreme of bar `t`; swing level set at bar `k`, **confirmed at `k+5`**; ATR14 at `t` | Close of `t` — **confirmation lag: 5 D1 bars**; only levels with `k+5 <= t` are eligible. The level value (set at `k`) may be used from `k+5` onward — legitimate per contract §6 |
| TP level (cond 7 / §7) | Confirmed opposing swing levels, `k+5 <= t`, `k >= t-250` | Close of `t` — same 5-bar confirmation lag |
| Entry price `E` | `High[t]`, `Low[t]` | Close of `t` — absolute, declarable at OrderIntent creation |
| Stop `S` | `Low[t]`/`High[t]`, ATR14 at `t` | Close of `t` — absolute, declarable |
| Expiry | `expires_after_bars = 2` counted on decision-frame bars from emission | Mechanical (F4) |

No MTF causality exposure: single timeframe. No centered windows; `detect_swing_points` is not used. No fill-anchored geometry; realized R differs from declared R only through exit-side gaps (F6) or F5 stop-first resolution, both handled honestly by the engine.

## 10. Ambiguities resolved
| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | "closes within the inside bar's range **or** with a strong bullish close" — the OR is fuzzy | Strict **conjunction**: close inside the IB range AND close in the far 40% of the pin bar's range (pseudocode's `strong_close` = `(Close-Low) > 0.6*(High-Low)`) — fewer, higher-quality trades | The source's disjunction (either condition suffices) — more trades, includes weak closes outside the IB range |
| 2 | "Only trade obvious setups with **pronounced tails**" — no number given | Exact threshold: rejection tail ≥ 60% of bar range, opposite wick ≤ 25% of range (echoing the pseudocode's 0.6 geometry) | Dropping the clause entirely (admits any pin-shaped bar); the looser classic "tail ≥ 2× body" (admits smaller absolute tails) |
| 3 | "After a downtrend **break of a key level** (or at range support)" — a break-and-reversal sequence cannot be made precise (how far beyond the level? how soon after? retest or close back?) | Tightened to **at-level only**: pin extreme within 0.25×ATR14 of a confirmed swing level, plus an explicit downtrend/up-move gate via EMA50 — the conjunction of the source's two disjuncts | Break-then-reclaim readings with any parametrisation of "break distance" (invented numbers, more setups); the disjunction "at range support OR post-break" |
| 4 | "Stop loss **beyond** the pin bar tail" — how far beyond? | Declared buffer: `0.10 * ATR14(D1)` beyond the tail extreme | Zero buffer (stop exactly at tail extreme — stop-hunt vulnerable but tighter, i.e. better R; rejected as the less conservative fill assumption); fixed-pip buffers (not pair-invariant) |
| 5 | "Require **favorable risk-to-reward**" — examples cite 3.5R/4R but no threshold is stated | **No RR gate** — do not invent a number. TP is always the nearest confirmed opposing level, whatever RR that yields | Imposing a 2R or 3R minimum inferred from the article's examples (invented parameter, and would silently censor the sample) |
| 6 | "Take profit at the next opposing key level (recent highs/lows)" — which level? | Nearest confirmed swing high/low (period 5, confirmed ≤ t, occurrence within trailing 250 bars) strictly beyond entry; **skip the trade if none exists** | Any swing within history regardless of age (stale levels); volume-profile or round-number levels (extra machinery, more setups); an ATR-multiple fallback target when no level exists (invents exits the source forbids — "skip setups not at key levels") |
| 7 | 50%-retracement limit order lifetime unspecified | `expires_after_bars = 2` (D1 bars). Arithmetic: earliest next signal (IB at t+1, pin at t+2) is fill-eligible from t+3, after this order lapses — pending overlap impossible, so contract v2's lack of OCO/cancel-on-fill is harmless | GTC / longer lifetimes (5-bar default): creates genuine multi-fill exposure across successive signals since F12 caps positions, not pending fills |
| 8 | `data_requirements` lists "trend lines" | Dropped. Trend-line construction is not uniquely definable from OHLCV without invented anchor rules; horizontal confirmed-swing levels carry the entire level logic | Any specific trendline algorithm (two-anchor, best-fit, etc.) — every variant invents parameters the source does not state |
| 9 | Inside-bar boundary: pseudocode uses `<=`/`>=` (inclusive); price-action canon often excludes equal extremes | Pseudocode verbatim (inclusive) — faithful to the row, and equality is a measure-zero event in practice | Strict `<`/`>` (marginally fewer trades; rejected as an unmotivated deviation from the given pseudocode) |
| 10 | Recency of a "key level" unspecified | Swing occurrence must lie within the trailing 250 D1 bars (~1 year) | Unlimited lookback (levels from years prior treated as live support/resistance) |

## 11. Expected behaviour
- **Trade frequency:** very low by design. The conjunction of (inside bar) × (60%-tail pin bar) × (close-in-range AND strong close) × (EMA50 trend side) × (within 0.25 ATR of a confirmed swing level) × (opposing level exists) on D1 will fire roughly 0–3 times per pair per year; pooled across 13 pairs expect ~5–25 trades/year, i.e. tens of trades per full 6-month OOS window only in aggregate, and single digits per cell.
- **Gate implications:** per-cell trade counts will frequently trip `low_confidence`; the pooled verdict rests on a thin sample even pooled. The strategy can also fail the gates if the 50%-retrace entry simply never fills in strong reversals (expired limits are not trades — this shrinks the sample further, it does not lose money). Expect a high fraction of expired orders relative to fills.
- **Conviction assessment:** MODERATE is honest, arguably generous. The documented evidence is two anecdotal real trades (3.5R, 4R); the mechanised version is stricter than what the author traded (conjunction, confirmed-level lag, at-level-only), so realised frequency will be lower than the article implies. The rules as written are fully implementable and causal, but the sample-size problem means the backtest will likely characterise *rarity* rather than edge; a pooled pass would be meaningful, per-cell verdicts mostly will not be.
