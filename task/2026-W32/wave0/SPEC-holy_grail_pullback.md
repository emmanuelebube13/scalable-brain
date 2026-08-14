# SPEC-holy_grail_pullback

**Source:** row 29 of forex_swing_strategies.csv · https://tradingstrategyguides.com/professional-trading-strategies/
**Conviction (author's):** MODERATE

## 1. Hypothesis

When ADX(14) holds above 30 the market is in a persistent, institutionally-backed directional move; a pullback to the 20-period mean is profit-taking exhaustion, not reversal, so momentum should resume once the counter-move stalls at the mean. The edge should persist because trend-following capital (CTAs, breakout systems) re-engages exactly at widely-watched mean levels in confirmed-strength regimes, and the ADX>30 gate keeps the strategy out of the ranging conditions where mean retests fail.

## 2. Scope

- **primary_granularity:** D1 (author's first-listed of "D1|H4"; the conservative choice — fewer bars, fewer setups; H4 rejected, see §10 #6)
- **context_granularities:** none (single-timeframe logic; all conditions evaluated on D1)
- **simulate_on:** H1 (fill resolution only, per contract §5; the strategy never sees H1 data)
- **pairs_requested (verbatim):** "All forex majors and minors"
- **pairs_available:** EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD (live); GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD (Wave-1 additions, **pending** — declared, harness skips if backfill incomplete). Per contract §7 the 13 pairs above are the operative reading of "all majors and minors".
- **pairs_missing:** none (no DATA-GAP file; the generic "majors and minors" phrasing is fully covered by the 13-pair universe, and exotic minors are not individually named)

## 3. Indicators

| Indicator | Params | Source |
|---|---|---|
| SMA of Close | period=20 | inventory `sma(close, 20)` — matches CSV pseudocode `close.rolling(20).mean()` |
| ADX | period=14, threshold 30 | inventory `adx(high, low, close, 14)` |
| Confirmed swing lows | period=5 | `causal_structure.confirmed_swing_points(high, low, period=5)` — low series; a swing low at bar k is knowable only at bar k+5 |
| Confirmed swing highs | period=5 | `causal_structure.confirmed_swing_points(high, low, period=5)` — high series; same 5-bar confirmation lag |
| Pip size | per pair | inventory `get_pip_value(asset)` (0.0001 for 5-digit pairs, 0.01 for JPY pairs) — used for the "+tick" entry offset and stop buffer |

ATR is **not** used: the trailing-exit alternative is rejected (§10 #4), so no trailing ATR is needed.

## 4. Entry — long

All values below are D1 bars; decision bar = bar **t** (decision made at the CLOSE of bar t).

1. **Trend-strength breakout regime.** ADX(14)[t] > 30, AND the current above-30 episode began with an observed upward cross: there exists a bar k ≤ t with ADX[k−1] ≤ 30 and ADX[k] > 30, and ADX[j] > 30 for every bar j in [k, t] (ADX has held above 30 continuously since the cross; declining within the episode is allowed). If the entire available history has ADX > 30 with no observable cross, the condition FAILS (no knowable breakout).
2. **ADX rising into the pullback** (per CSV pseudocode `adx_ok.shift(1)`): ADX[t−1] > 30 AND ADX[t−1] > ADX[t−2].
3. **Pullback touch candle at bar t** (per pseudocode `touch`): Low[t] ≤ SMA20[t] AND Close[t] > SMA20[t] — the candle trades down to/through the 20-SMA but closes back above it.
4. **Entry type:** `buy_stop`.
5. **Entry level:** High[t] + 1 pip (pseudocode `entry = high + tick`; tick defined as exactly 1 pip via `get_pip_value`).
6. **expires_after_bars:** **1** (source silent; conservative shortest non-zero lifetime — order is live only during bar t+1; see §10 #5).
7. **Structural validity gates (skip order, emit nothing, if either fails):**
   - a confirmed swing low (period=5) knowable at bar t exists and stop = (its level − 1 pip) < entry level;
   - a confirmed swing high (period=5) knowable at bar t exists and its level > entry level (TP must be beyond entry per contract §2.2 validation).

## 5. Entry — short

Exact mirror of §4:

1. ADX(14)[t] > 30 with the same observable-cross episode definition (ADX is direction-agnostic; it measures trend strength in a downtrend identically — "ADX above 30 and rising in a downtrend" per source).
2. ADX[t−1] > 30 AND ADX[t−1] > ADX[t−2].
3. **Retest candle at bar t:** High[t] ≥ SMA20[t] AND Close[t] < SMA20[t].
4. **Entry type:** `sell_stop`.
5. **Entry level:** Low[t] − 1 pip.
6. **expires_after_bars:** **1**.
7. Validity gates (skip otherwise): most recent confirmed swing **high** (knowable at t) + 1 pip > entry level (stop side); most recent confirmed swing **low** (knowable at t) < entry level (TP side).

## 6. Stop

- **Initial stop (long):** `StopRule.price` = level of the most recent confirmed swing low (period=5) knowable at decision bar t, **minus 1 pip** buffer. This is a conservative replacement for the source's "newly formed swing low after order fill", which is inexpressible in contract v2 (unknowable at OrderIntent creation — see §10 #3, prominent).
- **Initial stop (short):** most recent confirmed swing high (period=5) knowable at bar t, **plus 1 pip**.
- **move_to_breakeven_on:** `none` (source has no breakeven rule).
- **trail:** `none` (`trail_atr_multiple=None` — static stop; the source's "trail the stop" exit is the rejected alternative, §10 #4).
- Both stop and TP anchor to decision-bar-knowable absolute levels (decision-bar OHLC / confirmed structure), satisfying decision-bar anchoring; if the pending fill gaps (F3), realized R ≠ declared R and F5/F6 resolve the fill honestly.

## 7. Exit legs

| Label | Fraction | Kind | Level formula |
|---|---:|---|---|
| TP1 | 1.0 | take_profit | Long: most recent confirmed swing high (period=5) knowable at decision bar t, exact level. Short: most recent confirmed swing low (period=5) knowable at decision bar t, exact level. |

Fractions sum to 1.0. Single leg: the source's "or take profit at the most recent swing high/low" reading is taken as the sole exit; the trailing alternative is rejected (§10 #4). If the most recent confirmed swing level is not beyond the entry in the trade direction, no order is emitted (§4.7/§5.7) — the search-back-for-a-higher-swing alternative is rejected (§10 #8).

## 8. Filters

| Filter | Timeframe | When knowable |
|---|---|---|
| Trend-strength gate: ADX(14) > 30 with observable-cross episode (§4.1/§5.1) | D1 (native) | At the close of decision bar t — ADX is a causal rolling computation over completed bars |
| ADX rising into pullback (§4.2/§5.2) | D1 | At close of t (uses ADX[t−1], ADX[t−2], both completed bars) |
| Directional side of the mean: Close[t] vs SMA20[t] (built into touch condition) | D1 | At close of t |

No session, news, calendar, volatility, or volume filters exist in the source. No non-price data is required or proxied.

## 9. Causality audit

| Rule | Inputs fully known at | Confirmation lag |
|---|---|---|
| §4.1/§5.1 ADX episode (ADX > 30, cross observed, held since) | Close of decision bar t (ADX[j] for j ≤ t are all completed-bar values) | None — ADX(14) is causal (Wilder smoothing over past bars only) |
| §4.2/§5.2 ADX rising (ADX[t−1] > ADX[t−2], ADX[t−1] > 30) | Close of bar t (pseudocode's `.shift(1)` moves the evaluation one bar into the past; verified causal) | None |
| §4.3/§5.3 Touch candle (Low/High[t], Close[t], SMA20[t]) | Close of bar t (SMA20[t] = mean of Close[t−19..t], all completed) | None |
| Entry level High[t] ± 1 pip | Close of bar t; order eligible for fill only from bar t+1 (F1) — the buy stop above High[t] cannot fill on the candle that defined it | None |
| Initial stop — confirmed swing low/high (period=5) | A swing extreme **occurring** at bar k is **knowable** only at bar k+5 (five subsequent bars fail to exceed it). At decision bar t the strategy uses only swings stamped ≤ t; levels carried from their occurrence bars k ≤ t−5 | **5 bars** (period=5) |
| TP — confirmed swing high/low (period=5) | Same as above: only swings confirmed at or before bar t | **5 bars** (period=5) |
| MTF causality | Not applicable: single-timeframe (D1) decision logic. H1 is fill resolution only (contract §5); the strategy never reads H1 bars, so no context-bar alignment exists to get wrong | n/a |

Consequence worth stating: the rally top preceding the pullback is usually NOT yet confirmed at decision time (5-bar D1 lag), so the TP will typically be an older, further-away confirmed swing — or, if that older swing is below the entry, the setup is skipped entirely. This is the honest causal cost and it depresses trade count (see §11).

## 10. Ambiguities resolved

| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | "20 MA" — moving-average type unspecified in prose | **SMA(20) on Close** — the CSV pseudocode (`close.rolling(20).mean()`) is SMA, and SMA is the default reading | EMA(20) — reacts faster, hugs price closer, produces more/faster touches (more trades) |
| 2 | "ADX must break above 30 and be rising" — is a fresh cross required at/near the setup? | Current above-30 episode must originate in an **observable upward cross** and ADX must hold > 30 continuously since, PLUS pseudocode's `adx_ok.shift(1)` (ADX rising at t−1) as an extra conjunct — strictly fewer setups than either condition alone | (a) Pseudocode-literal reading without the cross requirement (ADX merely > 30 and rising at t−1 — more trades); (b) prose-loose reading "rising at breakout only, no rising requirement near the touch" (more trades); (c) strict "cross exactly at t−1" reading — rejected as contradicting the prose's "wait for price to pull back", which implies elapsed time between breakout and touch |
| 3 | **Stop "below the newly formed swing low AFTER order fill"** — the stop depends on structure that forms after entry and is therefore **unknowable at OrderIntent creation; the source's rule is inexpressible in contract v2** (not merely less faithful — there is no channel for it) | Use the most recent **confirmed** swing low (period=5, 5-bar confirmation lag) knowable at the decision bar, minus 1 pip. This is staler and typically wider than a post-fill swing → worse entries' risk, honest, expressible | Source's post-fill swing version — rejected as **inexpressible**: the strategy never observes fills (F1/§2.2) and cannot reference future structure; any attempt is look-ahead by construction. Also rejected: fill-anchored geometry generally (decision-bar anchoring mandated) |
| 4 | Exit is "trail the stop, **or** TP at the most recent swing high/low" — two exit structures offered | **TP at the most recent confirmed swing** as the single leg (fraction 1.0), static stop, no trail. Fixed TP exits earlier than a trail in a strong trend (caps winners) and needs no invented ATR multiple | ATR trailing stop — rejected: (a) source gives no multiple, so any value is invented; (b) trails let winners run further → more optimistic results; (c) mixing both would require splitting fractions arbitrarily |
| 5 | Pending-order lifetime — source silent on expiry of the buy/sell stop | **expires_after_bars = 1**: order lives only during bar t+1. Minimizes stale-level fills and pending overlap | 2 bars or GTC — rejected (more fills at staler levels, more overlap). **Residual multi-fill risk recorded:** F12 caps concurrent *positions*, not pending fills (§3.2 step 5); the strategy never sees fills, so if the order from setup at bar t fills on t+1 AND a new touch at t+1 emits a new stop that fills on t+2 while the first position is still open, two concurrent same-direction positions exist. Direction of risk: pyramiding longs in a rally (or shorts in a selloff), doubling exposure at a worse (higher/lower) price. With expiry=1 two *pending* orders can never coexist; only fill-then-reemit overlap remains, and it is accepted and disclosed rather than hidden |
| 6 | "D1|H4 (works on any swing timeframe)" — which is primary? | **D1** — author's first-listed, and fewer bars ⇒ fewer setups ⇒ conservative | H4 — rejected (≈6× more bars, more signals, more opportunities for marginal setups; inflated trade count) |
| 7 | "Price pulls back and **touch**es the 20 MA" — wick touch only, or close condition too? | Pseudocode's `touch = (low ≤ ma20) & (close > ma20)`: candle must trade to the MA **and close back above it** (longs) — a two-part condition, fewer qualifying candles | Wick-touch only (low ≤ MA20, no close condition) — rejected: more setups, includes candles that close through the MA (incipient breakdowns, worse entries) |
| 8 | Most recent confirmed swing high at decision time is **below** the entry level (common in fresh breakouts given the 5-bar confirmation lag) — TP impossible per contract validation | **Skip the setup; emit no order.** Fewest trades; uses only the genuinely most recent confirmed level | Searching back through older confirmed swings for one above the entry — rejected: more trades, uses staler structure, deviates from "most recent swing high" |

## 11. Expected behaviour

- **Trade frequency:** low. On D1, ADX(14) > 30 holds roughly 25–35% of the time on majors; a 20-SMA touch with a confirming close within that regime occurs a handful of times per year per pair, and the §4.7/§5.7 structural skips (no confirmed swing beyond entry, given the 5-bar confirmation lag on D1) remove a further material share. Expect ~2–6 trades/pair/year → ~25–75 trades/year pooled across 13 pairs, ~30–80 trades per (pair × 10y) cell.
- **Gate risk:** per-cell OOS folds (6 months ≈ 2–4 trades on D1) will almost certainly return `low_confidence`; the pooled verdict across 13 pairs is the only realistic gate path and even it is marginal on trade count. Strategy more likely fails on insufficient OOS trades than on negative edge.
- **Fill/geometry realism:** stops sit at confirmed swing lows (typically 1–3% away on D1), TPs at prior confirmed swing highs — declared R is modest (often < 1.5R); F5 (stop-before-target) will bite on wide D1 bars resolved on H1. The dual-resolution delta (native vs H1, contract §5) should be small here because stop and TP are usually far apart relative to D1 bar ranges.
- **Author's conviction (MODERATE) — justified by the rules as written.** The setup is a textbook trend-continuation pullback with an objective strength filter, and the conservative causal readings (confirmed swings, 1-bar expiry, skip-on-invalid-structure) can only reduce trade count and entry quality relative to the author's intent, never inflate it. The author's own caveat ("no documented performance, requires re-optimization") is accurate: nothing in the rules as written demonstrates edge; this spec makes the strategy testable, not validated.
