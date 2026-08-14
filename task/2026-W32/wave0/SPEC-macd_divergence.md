# SPEC-macd_divergence
**Source:** row 24 of forex_swing_strategies.csv · https://www.earnforex.com/forex-strategy/macd-divergence-strategy
**Conviction (author's):** MODERATE

## 1. Hypothesis
Momentum leads price: when price prints a lower low but the MACD line prints a higher low, the selling pressure behind the down-leg is genuinely exhausting — fewer participants are willing to push each successive low — so the probability of a reversal or deep pullback rises. This should persist because it rests on a behavioural mechanism (crowd conviction decaying into the tail of a trend leg, visible in smoothed momentum before it is visible in price) rather than on a data-mined pattern, and because divergence failure is slow enough that a stop at the divergence low caps the loss when the trend instead continues.

## 2. Scope
- **primary_granularity:** H4 — the source offers H1|H4|D1 and the forum thread reports H4 works best; H4 is also the conservative choice versus H1 (fewer, slower, less noise-driven signals). Recorded in §10.
- **context_granularities:** none. The strategy is single-timeframe; the §4 MTF causality rule is trivially satisfied.
- **simulate_on:** H1 (fills, stops, and exit legs resolved on H1 bars within each H4 bar's span, per contract Part D).
- **pairs_requested (verbatim):** "Any currency pair"
- **pairs_available:** EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD (live); GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD (Wave-1 additions, **pending** — harness skips if backfill incomplete). "Any currency pair" is read as the full 13-pair supported universe.
- **pairs_missing:** none. No DATA-GAP file: the strategy needs only OHLCV + MACD, all available.

## 3. Indicators
| Indicator | Params | Source |
|---|---|---|
| MACD line | fast=12, slow=26, signal=9, on H4 `Close`; only the MACD line (first return value) is used; signal line and histogram are NOT used | inventory `macd(close, 12, 26, 9)` |
| Confirmed swing lows | period=5, on H4 `High`/`Low`; a swing low occurring at bar k is knowable at bar k+5 and carries level `Low[k]` | `causal_structure.confirmed_swing_points` |
| Confirmed swing highs | period=5, on H4 `High`/`Low`; a swing high occurring at bar k is knowable at bar k+5 and carries level `High[k]` | `causal_structure.confirmed_swing_points` (equivalently `last_n_confirmed_highs` / rolling access to the last 2 confirmed lows) |

Warmup: no signal may be emitted before at least 60 completed H4 bars (EMA-26 convergence plus swing history). The banned `indicators.detect_swing_points` (centred window) is not used anywhere.

## 4. Entry — long
Definitions at each H4 decision bar t (all inputs computed from bars ≤ t only):
- Let (k1, L1) and (k2, L2) be the two most recently **confirmed** swing lows, k1 < k2, with levels L1 = `Low[k1]`, L2 = `Low[k2]`. Their confirmation bars k1+5 and k2+5 must be ≤ t.
- Let c = k2 + 5 (the confirmation bar of the second low).
- MACD[k] denotes the MACD line value at the close of bar k.

Conditions (all must hold at the close of bar t):
1. c ≤ t ≤ c + 10 — the second swing low is confirmed, and the setup is at most 10 H4 bars old (staleness window; a divergence older than ~2 trading days is void).
2. L2 < L1 — price made a strictly lower low.
3. MACD[k2] > MACD[k1] — the MACD line made a strictly higher low, sampled at the two price-swing bars.
4. MACD[k1] < 0 AND MACD[k2] < 0 — both momentum lows are below the zero line (classic bear-leg divergence; conservative reading, see §10 #4).
5. Close[t] > High[c] — the trigger: first H4 close above the high of the confirmation bar. (Since Close[c] ≤ High[c] always, condition 5 forces t > c; entry is never on the confirmation bar itself.)
6. A resistance level exists: R* = min{ h : h is a confirmed H4 swing-high level, h > Close[t], knowable at t }. If the set is empty (e.g. price in all-time-high territory), no trade.

Entry type: **market**. Entry level: n/a — fills at the open of bar t+1 per F1/F2.
expires_after_bars: **null** — a market intent fills at t+1 or not at all; pending-order expiry never binds. The setup's lifetime is governed by condition 1's staleness window instead.
Guarantee: conditions 5 and swing-confirmation semantics imply Close[t] > L2 (confirmation means every bar k2+1…k2+5 had `Low` ≥ L2, so High[c] ≥ Low[c] ≥ L2 and Close[t] > High[c]), so the stop (§6) is always strictly below the decision close.

## 5. Entry — short
Exact mirror. Let (j1, H1) and (j2, H2) be the two most recently confirmed swing highs, j1 < j2, c = j2 + 5. At the close of H4 bar t:
1. c ≤ t ≤ c + 10.
2. H2 > H1 — price made a strictly higher high.
3. MACD[j2] < MACD[j1] — MACD line made a strictly lower high.
4. MACD[j1] > 0 AND MACD[j2] > 0 — both momentum highs above the zero line.
5. Close[t] < Low[c] — first H4 close below the low of the confirmation bar.
6. A support level exists: S* = max{ l : l is a confirmed H4 swing-low level, l < Close[t], knowable at t }; else no trade.
Entry type: **market**, fill at open of t+1. expires_after_bars: **null** (same reasoning as long).

## 6. Stop
- **Initial stop, long:** StopRule.price = L2 (the level of the second confirmed swing low — the divergence low itself). No buffer.
- **Initial stop, short:** StopRule.price = H2 (the level of the second confirmed swing high). No buffer.
- **move_to_breakeven_on:** none (source specifies none).
- **trail:** none (source specifies none; trail_atr_multiple = null).
Both stop levels are confirmed-swing levels knowable at decision bar t, so the geometry is fully declarable at OrderIntent creation (decision-bar anchored, not fill-anchored). Gap-through-stop resolves at the open per F6; losses may exceed 1R.

## 7. Exit legs
| Label | Fraction | Kind | Level formula |
|---|---|---:|---|
| TP1 | 1.0 | take_profit | Long: price = R* = min{ confirmed swing highs > Close[t], knowable at t }. Short: price = S* = max{ confirmed swing lows < Close[t], knowable at t } |

Fractions sum to 1.0. Single leg: the source names exactly one target ("next resistance / next support"). The "TP/SL ratio about 1.5" shown in the page's example is treated as illustrative of one instance, not a binding constraint (§10 #6) — the realised R:R is whatever the swing geometry produces.

## 8. Filters
The source specifies **no** trend, session, volatility, or news filter, and none is added. The only gate beyond the entry conditions is the MACD zero-line condition (§4 cond. 4 / §5 cond. 4), which functions as a regime gate: it restricts longs to divergences formed in genuinely bearish momentum territory. It is evaluated on H4 and is knowable at the close of the decision bar t (MACD at k1, k2 < t is history by then). No economic-calendar filter is possible (no calendar data exists), and the source does not request one — this is not a data gap.

## 9. Causality audit
| Rule | Inputs | Fully knowable at | Confirmation lag |
|---|---|---|---|
| MACD line | H4 closes through bar u | close of bar u | 0 (standard causal EMA chain); sampled only at past bars k1, k2 |
| Swing low at k2 (occurrence) | H4 Low of bars k2−5…k2+5 | close of bar c = k2+5 | **5 H4 bars** — it is look-ahead to treat k2 as a swing low before c |
| Bullish divergence (conds. 2–4) | L1, L2, MACD[k1], MACD[k2] | close of bar c | inherits the 5-bar swing lag; MACD values at k1/k2 are pure history by c |
| Trigger (cond. 5) | Close[t], High[c] | close of bar t, with t > c strictly | adds ≥ 1 further bar after c |
| Order fill | — | open of bar t+1 (F1/F2) | minimum total lag from the actual price low k2 to fill: **7 H4 bars** (5 confirmation + 1 trigger + 1 fill); typically more |
| Stop level L2 / H2 | confirmed swing level | close of bar t (confirmation bar k2+5 ≤ t) | 5-bar lag already elapsed |
| TP level R* / S* | confirmed swing levels | close of bar t (only confirmed levels are eligible; unconfirmed highs are invisible) | 5-bar lag already elapsed |
| Staleness window (cond. 1) | bar index of c | close of bar t | — |
| MTF context | none | — | single-timeframe strategy; the §4 closed-context-bar rule is trivially satisfied |

No rule uses a centred window, a future bar, or an unconfirmed swing. The MACD comparison uses MACD values at the price-swing occurrence bars (k1, k2), which are fully in the past at decision time; it does not use MACD's own swing points (which would compound a second 5-bar confirmation lag — rejected, §10 #2).

## 10. Ambiguities resolved
| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | "Enter when the downtrend leg ends (divergence confirmed)" — no bar event defined | Entry requires (a) 5-bar confirmation of the second swing low AND (b) a subsequent H4 close beyond the confirmation bar's extreme (cond. 5); fill at next bar's open — the latest entry of any plausible reading | Enter at the close of the confirmation bar c itself (one or more bars earlier; author likely traded visually on the completed divergence, i.e. earlier) |
| 2 | "MACD makes higher lows" — MACD's own swings or MACD at price swings? | MACD line sampled at the two confirmed price-swing bars (k1, k2); single 5-bar confirmation lag | Requiring MACD to form its own confirmed swing lows (compounds two confirmation lags, delays entry further, and is not what charting platforms draw) |
| 3 | Which pair of lows | The two most recent consecutive confirmed swing lows only | Any two lows within a lookback window (produces more, older, staler divergence claims) |
| 4 | Whether both MACD lows must sit below zero | Required (cond. 4) — classic bear-leg divergence; fewer trades, and matches "downtrend leg" in the prose | Plain strict-inequality-only reading (more trades, includes momentum-positive "divergences" the author would likely not have drawn) |
| 5 | "Take-profit at the next resistance" — resistance undefined | Nearest confirmed H4 swing high strictly above the decision close; no trade if none exists | Projected/pivot/Fibonacci resistances (invented data); unconfirmed recent highs (look-ahead risk); skipping the level check (TP could sit inside the entry path) |
| 6 | Page example shows TP/SL ≈ 1.5 | Treated as one illustrative instance; TP and SL placed at actual swing levels, R:R floats | Enforcing a 1.5 ratio by shifting TP off the resistance level to a computed price (contradicts "at the next resistance"; curve-fits one screenshot) |
| 7 | "Stop at the nearby support below entry" — which support, what buffer | The divergence low L2 itself, exactly, no buffer — it is the nearest confirmed support below entry by construction | A subjective "nearby" level (discretionary); subtracting an ATR buffer (invents a parameter not in the source and widens risk per trade) |
| 8 | "If an opposite divergence signal forms, close the existing position first" | **Inexpressible in contract v2** — no close-on-signal exists and F12 drops new intents while a position is open. Consequence recorded: an opposite divergence forming during an open trade is silently ignored; the open trade runs to stop or TP. Direction of effect: a reversal signal that in live trading would have cut a loser early instead rides to the stop — realized results will be modestly **worse** than the source's live behaviour in that subset, which is the conservative direction | Treating the opposite signal as an exit (no such mechanism); assuming the opposite pending order cancels the position (OCO does not exist) |
| 9 | Timeframe choice (H1/H4/D1 all offered) | H4 primary, per forum consensus and lower signal noise | H1 (more trades, more noise — the anti-conservative direction); D1 (fewer signals, no support in the thread) |
| 10 | Setup lifetime after divergence confirmation | 10 H4 bars (~2 trading days); an untriggered divergence is void afterwards | Unlimited validity (a weeks-old divergence re-entering on any rally — more, staler trades) |
| 11 | Stop/TP geometry anchored to fill or decision bar | Decision-bar knowable levels (Close[t], confirmed swings) — required because a market fill price is unknowable at emission | Fill-anchored R measurement (inexpressible under contract v2); note that a gap at t+1 open makes realised R ≠ declared geometry, resolved honestly by F3/F6 |

## 11. Expected behaviour
- **Trade frequency:** low. Requiring two confirmed opposite-side swings, a MACD zero-line gate, and a trigger close yields roughly 5–20 trades per pair per year on H4 (a confirmed swing-low pair forms every few weeks at most; many fail the zero-line or trigger conditions). Across 13 pairs this is a modest but testable sample per walk-forward fold; some cells may still flag low_confidence.
- **Likely failure modes:** (a) strong persistent trends produce repeated divergences that keep failing — the third and fourth lower lows each re-signal while price continues; (b) the stop sits exactly at the divergence low with no buffer, so noise retests stop trades out before the reversal matures; (c) F5 (stop-before-target on one bar) bites hard because TP1 can be far away (the next confirmed swing high may be a full prior leg away), giving a low win rate that the R:R must overcome; (d) the minimum 7-bar lag from the true low means entries arrive after the first impulse of the reversal, ceding exactly the move the divergence trader hoped to catch.
- **Conviction assessment:** the author's MODERATE is generous. The author admits entry/exit points are fuzzy and TP/SL indefinite, and no documented backtest exists on the page. The mechanized version here is deliberately slower and stricter than the visual method described — every conservative reading (confirmation lag, trigger close, zero-line gate, staleness window) reduces trade count and delays entries relative to what the author traded. If the edge survives this formalization and the gates, it is real; the prior should be that it qualifies only if the momentum-leads-price effect is strong enough to pay for the confirmation lag it is measured through.
