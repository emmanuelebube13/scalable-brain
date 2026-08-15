# SPEC-h4_crossover_21_89_macd
**Source:** row 13 of forex_swing_strategies.csv · https://www.forexfactory.com/thread/264293-4h-crossover-swing-trading
**Conviction (author's):** MODERATE

## 1. Hypothesis

A 21-EMA / 89-SMA cross on H4 marks a regime change in the dominant multi-day trend; the first pullback after the cross (visible as the MACD histogram flipping against the new trend) is profit-taking by early entrants, and the histogram's first flip BACK to trend colour marks the resumption of that regime. Entering on resumption — rather than at the cross itself — buys the new trend at a pullback price with momentum re-confirming. The edge should persist because FX trends are driven by slow-moving macro and rate-differential flows that do not reverse in days, while pullbacks are behavioural (profit-taking, late-entry fades) and therefore temporary; the moving-average pair and histogram are just a mechanical proxy for "regime changed, pause over." Stops anchored to D1 structure (the extreme of the prior substantial move) sit beyond the noise band of the new trend, so ordinary pullbacks do not stop the position out.

## 2. Scope

- **primary_granularity:** H4
- **context_granularities:** (D1,) — used ONLY for stop-structure location, never for entry timing
- **simulate_on:** H1
- **pairs_requested (verbatim):** `EURUSD|GBPUSD|AUDUSD|USDCAD|EURGBP|EURAUD|EURJPY|GBPJPY|USDJPY|GBPCHF|USDCHF|EURCHF` (12 pairs)
- **pairs_available (10):**
  - Live now (5): EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD
  - Wave-1 additions, **pending** backfill (5): EUR_GBP, EUR_AUD, EUR_JPY, GBP_JPY, USD_CHF
- **pairs_missing (2):** GBP_CHF, EUR_CHF — not live and NOT in the Wave-1 addition list → **DATA-GAP-h4_crossover_21_89_macd.md**

## 3. Indicators

| Indicator | Params | Source |
|---|---|---|
| EMA of H4 close | period 21 | inventory `ema(close, 21)` |
| SMA of H4 close | period 89 | inventory `sma(close, 89)` |
| MACD histogram of H4 close | fast 12, slow 26, signal 9; use the `hist` output | inventory `macd(close, 12, 26, 9)` |
| D1 rolling extreme (stop structure), private | window 20 D1 bars; long-side extreme = `min(Low)` over the last 20 **fully closed** D1 bars; short-side extreme = `max(High)` over the same window. "Fully closed" per §4 mechanical form (see §9): D1 frame index shifted forward by one D1 interval, then `merge_asof(..., direction="backward", allow_exact_matches=False)` onto H4 decision bars. | Private — specify in own module. Inventory `donchian_channel` is NOT used: it operates on a single frame and its window includes the current (possibly unclosed) bar, whereas this indicator must live on the D1 frame with strict closed-bar alignment. No swing-point identification is performed (trailing extreme over closed bars only), so no `causal_structure` function is required and `detect_swing_points` is not touched. |
| Pip size conversion | `get_pip_value(asset)` → 0.01 for `*_JPY`, 0.0001 otherwise; used for the 4-pip stop buffer | inventory `get_pip_value` |

## 4. Entry — long

All conditions are evaluated on **closed H4 bars** at the **decision bar t** (its close). Let `EMA[t]`, `SMA[t]`, `hist[t]`, `Close[t]` be values at bar t.

1. **Arming event:** there exists a closed H4 bar c ≤ t with `EMA[c] > SMA[c]` and `EMA[c-1] ≤ SMA[c-1]` (a 21/89 cross-up), and no cross-down (`EMA < SMA` after `EMA ≥ SMA`) has occurred at any bar in (c, t]. The arming becomes active at the close of bar c.
2. **One trade per cross:** no OrderIntent has yet been emitted under this arming. The arming is consumed by emission (condition 6 below firing) or cancelled by the next cross-down, whichever comes first. There is no time-based arming expiry (see §10, row 6).
3. **Pull-back-and-resume trigger (mechanised "turns back green"):** `hist[t] > 0` AND `hist[t-1] ≤ 0` — a strict sign change of the MACD histogram between the two most recent closed H4 bars. `hist[t-1] ≤ 0` IS the pullback bar, so the source's "price climbs then retraces with MACD histogram turning red" is satisfied by construction; no separate pullback state is tracked.
4. **Close beyond EMA21:** `Close[t] > EMA[t]`.
5. **Trend alignment:** `EMA[t] > SMA[t]`.
6. **Stop-side sanity:** `SL_long(t) < Close[t]`, where `SL_long(t)` per §6. If violated, emit **no order** for this arming (the arming is still consumed — conservative: a stop that would sit above the anchor is not a trade the author could have placed).
7. **Holiday filter:** the UTC calendar date of bar t is not on the static US-holiday list (§8).

- **Entry type:** `market`
- **Entry level:** `entry_price = None`; fill at `Open[t+1]` plus adverse slippage (F2, F10). All geometry is anchored to the decision-bar anchor `A = Close[t]` (fleet anchoring rule; the fill price is unknowable at emission).
- **expires_after_bars:** `null` — a market intent fills at bar t+1 or not at all; no pending order ever lingers, so no multi-fill overlap exists (fleet lifecycle rule satisfied trivially).

## 5. Entry — short

Exact mirror. Arming event: cross-down (`EMA[c] < SMA[c]` and `EMA[c-1] ≥ SMA[c-1]`), active from close of bar c until consumed or until the next cross-up. Trigger: `hist[t] < 0` AND `hist[t-1] ≥ 0` ("turns back red"). Conditions: `Close[t] < EMA[t]`; `EMA[t] < SMA[t]`; `SL_short(t) > Close[t]` else no order (arming consumed); holiday filter per §8. Entry `market`, anchor `A = Close[t]`, `expires_after_bars = null`.

## 6. Stop

- **Initial stop (long):** `SL_long(t) = min(Low of the last 20 fully closed D1 bars known at decision bar t) − 4 × pip(pair)`
- **Initial stop (short):** `SL_short(t) = max(High of the last 20 fully closed D1 bars known at decision bar t) + 4 × pip(pair)`
- `pip(pair)` via `get_pip_value`: 0.01 for JPY crosses, 0.0001 otherwise. Window = 20 D1 bars (~4 trading weeks, the author's own pseudocode value); buffer = 4 pips, the tight end of the author's "4-10 pips" range (conservative — see §10, row 2).
- **move_to_breakeven_on:** `none`
- **trail:** `none` — the stop is static for the life of the position.

## 7. Exit legs

| Label | Fraction | Kind | Level formula |
|---|---|---|---|
| TP1 | 1.0 | take_profit | long: `A + (A − SL_long(t))` · short: `A − (SL_short(t) − A)`, where `A = Close[t]` (decision-bar anchor) |

Single leg, fractions sum to 1.0. This is the author's "take-profit at 1:1 of stop distance", declared at the decision-bar anchor, not the fill (§10, row 4): declared R = `|A − SL|`; realised R will differ when the fill gaps or slips (F2/F6 resolve the fill honestly).

**Signal exit (inexpressible — recorded, not implemented):** the source's "if a 21/89 cross occurs before TP or SL, close on that candle close" cannot be expressed in contract v2: the strategy never observes open positions, there is no close/cancel mechanism, and an opposite `OrderIntent` would open a NEW position (blocked by F12 anyway). Conservative resolution: **the position runs to SL or TP.** See §10, row 5, and §11 — the source credits this rule with cutting ~2/3 of losers early, so the backtest measures a strictly worse variant than the author's manual system.

## 8. Filters

| Filter | Timeframe | When knowable | Status |
|---|---|---|---|
| Trend regime gate (21 EMA vs 89 SMA) | H4 | close of decision bar t — this IS the arming/alignment logic (§4 conditions 1, 5) | implemented |
| Holiday gate — "no trading on major US holidays" | calendar date (UTC) of decision bar t | known a priori (dates are deterministic) | **implemented as a static, derivable calendar**: the 11 US federal holidays — New Year's Day (Jan 1), MLK Day (3rd Mon Jan), Washington's Birthday (3rd Mon Feb), Memorial Day (last Mon May), Juneteenth (Jun 19), Independence Day (Jul 4), Labor Day (1st Mon Sep), Columbus Day (2nd Mon Oct), Veterans Day (Nov 11), Thanksgiving (4th Thu Nov), Christmas (Dec 25) — computed from date arithmetic only. **No external calendar feed exists** (DATA_AVAILABILITY: no calendar data); this static list is a derivable proxy and is flagged here and in §10, row 7 — it is not a silent substitution. Including the filter is the conservative direction: fixed-cost fills (F10: 1.0-pip spread) on thin-liquidity holidays would otherwise flatter results. |
| Fundamental check — "~10-15 min daily fundamental check" | discretionary, daily | — | **dropped**: inherently non-mechanical and no fundamental/news feed exists. No proxy is substituted (rule: no invented data). Noted in the DATA-GAP file as a secondary item. |
| Risk sizing — "risk 1-2% of balance, target 1-2%, max DD 16%, min $5000 capital" | account-level | — | **out of scope for v2**: System 1 never sizes (contract §2.2); results are r-multiples only. `size_fraction = 1.0`. |

No session filter, no volatility filter, no news filter is specified by the author beyond the above.

## 9. Causality audit

Reviewers: read this first. Decision bar = H4 bar t; "known at close of t" means computed from bars ≤ t only.

| # | Rule | Inputs | Fully known at | Confirmation lag |
|---|---|---|---|---|
| 1 | EMA(21), SMA(89) on H4 | H4 closes ≤ t | close of H4 bar t | none — trailing averages |
| 2 | 21/89 cross detection | EMA/SMA at t and t−1 | close of bar t | none — first bar at which the cross is knowable is t itself (the cross "occurs" between t−1 and t and is detected at t's close; no future bars are read) |
| 3 | Arming state machine (armed/consumed/disarmed) | cross history ≤ t, emission history ≤ t | close of bar t | none — pure trailing state, deterministically re-derivable from a truncated frame (truncation-probe safe) |
| 4 | MACD histogram | H4 closes ≤ t (EMA 12/26/9 chain) | close of bar t | none |
| 5 | Histogram re-flip trigger | `hist[t]`, `hist[t-1]` | close of bar t | none |
| 6 | Close >/< EMA21; EMA21 vs SMA89 | bar t values | close of bar t | none |
| 7 | **D1 rolling 20-bar extreme (stop structure)** | D1 Low/High of the 20 most recent **fully closed** D1 bars | close of H4 bar t | **D1 causality (MTF rule §4, mechanical form):** the D1 index is shifted forward by one D1 interval and joined with `merge_asof(direction="backward", allow_exact_matches=False)`. Consequence: a D1 bar is usable only by H4 decisions whose close is **strictly after** the D1 bar's own close. The D1 bar closing at the same instant as the decision bar (the 21:00 UTC H4 close) is EXCLUDED — the freshest usable D1 close is up to ~28 hours old at that bar. **Swing-confirmation lag: not applicable and stated explicitly** — no swing/pivot/ZigZag/fractal identification is performed anywhere in this strategy; a trailing min/max over already-closed bars is causal by construction (the k+period rule governs knowing WHICH bar was a pivot; we never ask that question). `detect_swing_points` is NOT used; no `causal_structure` function is needed. |
| 8 | Stop & TP arithmetic | `Close[t]`, D1 extreme from row 7, static pip value | close of bar t | none — arithmetic on known values |
| 9 | Holiday gate | UTC date of bar t | known a priori | none |
| 10 | Emission → fill | OrderIntent at decision bar t | eligible from bar t+1 (F1), market fill at `Open[t+1]` (F2) | one H4 bar, by contract |

No rule in this strategy reads data at or after the decision bar's close, and no context bar is used before it has fully closed.

## 10. Ambiguities resolved

| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | "MACD turns back green/red" — how much of a flip counts? | Strict sign change between consecutive closed H4 bars: `hist[t] > 0 & hist[t-1] ≤ 0` (long), per the author's own pseudocode; the first such flip under the arming triggers, and `hist == 0` counts as off-trend (matches pseudocode `<=`/`>=`). | Requiring a margin above zero, or N consecutive off-trend bars before the flip — both invent parameters absent from the source. |
| 2 | Stop buffer "4-10 pips" — which value? | **4 pips** (tightest stop in the author's range). With fixed costs (F10) and a 1:1 target, tighter geometry makes the 1.5-pip entry cost a larger fraction of R and maximises exposure to F5 stop-first resolution — the least flattering in-range choice. | 5 pips (the pseudocode's midpoint choice) and 10 pips — both inside the author's range but kinder to expectancy. |
| 3 | "Previous substantial move (200-400 pips, located on D1)" — how to locate it, and is 200-400 a gate? | Rolling extreme over the last 20 fully closed D1 bars (the author's own pseudocode: `d1['low'].rolling(20).min()`); the "(200-400 pips)" phrase is treated as **descriptive** of what such stops typically look like, NOT as an eligibility gate. | Gating entries on the 20-bar D1 range lying within [200, 400] pips — would produce fewer trades (superficially "conservative") but invents a rule the author's own mechanisation omits, makes low-volatility pairs (e.g. EUR_GBP) permanently untradeable, and conflates a stop-location hint with an entry filter. Rejected as unfaithful, not merely less conservative. |
| 4 | R and TP measured from what price? | Anchored to the decision-bar close `A = Close[t]`: TP = A ± |A − SL|, declared at OrderIntent creation. | Anchoring to the realised fill (what a manual trader does) — **inexpressible**, not merely less conservative: the fill price is unknowable at emission (fleet anchoring rule). Note: realised R ≠ declared R when the t+1 open gaps/slips; F2/F6 resolve the fill honestly. |
| 5 | "If a 21/89 cross occurs before TP or SL, close on that candle close" | **Not implemented.** The position runs to SL or TP. Contract v2 has no close-position mechanism: the strategy cannot observe open positions, no ExitLeg kind expresses "exit on a future signal", and an opposite OrderIntent would open a NEW position (F12 caps at 1, blocking even that). | Emitting an opposite market intent at the cross (opens a second/inverse position or is silently dropped — neither is "close"), or a fixed-bar time leg (invents a parameter). Consequence, stated plainly: the source credits this rule with cutting ~2/3 of losers early (avg winner = 1.34× avg loser); the backtest will therefore show materially WORSE expectancy than the author's manual 2009-2010 log, and a gate failure must be interpreted with that handicap in view (§11). |
| 6 | How long does a cross's arming last? | Until consumed by an entry OR cancelled by the next opposite 21/89 cross, whichever first. No time-box; "only one trade per 21/89 cross" is the author's exact wording. | Time-boxing the arming (e.g. N bars) — invents a parameter; or allowing re-entry on each subsequent hist re-flip under one arming — directly contradicts "only one trade per cross" and produces more trades. |
| 7 | "No trading on major US holidays" — which holidays, from what data? | Static list of the 11 US federal holidays (§8), computed by date arithmetic — derivable without any external feed, and flagged prominently here and in §8. | Dropping the filter entirely — rejected because fills on thin-liquidity holiday sessions would be modelled at the fixed 1.0-pip spread (F10), flattering the strategy; subscribing to a calendar feed — no such feed exists in the system (secondary DATA-GAP note). The boundary choice ("major" = federal holidays) is itself an interpretation; Good Friday, the one genuinely FX-closed day, simply has no bars to signal on. |
| 8 | D1 bar closing at the same instant as the H4 decision bar (21:00 UTC) — usable? | **Excluded.** Contract §4's canonical mechanical form (shift + `merge_asof(allow_exact_matches=False)`) admits a D1 bar only to H4 decisions strictly after its close. | The prose reading of §4 ("may first influence at 21:00Z") — rejected per the contract's own instruction that the mechanical form is the operative one; the exclusion is the more conservative of the two. |
| 9 | F12 concurrency vs. the missing cross-exit | `max_concurrent_positions = 1` (default, T6-comparable). Because exits are SL/TP-only, positions run longer than the author's, and signals armed and triggered while a position is open are dropped by the engine (the arming is still consumed at emission). This is accepted and reported, not engineered around. | Raising concurrency — would make results non-comparable with the T6 fleet and contradicts the one-trade-per-cross spirit; suppressing emission while "probably in a position" — the strategy cannot observe fills (declarative contract), so any such suppression would be guesswork and is not expressible. |

## 11. Expected behaviour

- **Trade frequency:** 21/89 crosses on H4 majors occur roughly 3-10 times per pair per year; many armings never see a histogram re-flip with conditions 4-6 satisfied. Expect **~2-6 trades per pair per year**. On the 5 live pairs: ~10-30 trades/year → over a 10-year lookback roughly **100-300 pooled trades, ~20-60 per cell** — several per-cell `low_confidence` flags are likely; pooled statistics should be adequate. With the Wave-1 pairs backfilled (10 of 12 pairs), pooled count roughly doubles. Stops are D1-extreme scale (typically 150-400 pips on majors), so with a 1:1 target, holding times of days to weeks are normal — F12 blocking (§10, row 9) will further reduce realised frequency relative to the author's log.
- **What would make it fail the gates:** a 1:1 reward-to-risk with a fixed 1.5-pip entry cost needs a win rate clearly above 50% plus cost drag; F5 (stop-first on any H1 bar covering both levels) is maximally punitive exactly at 1:1 geometry; and the inexpressible cross-exit (§10, row 5) removes the author's documented loser-cutting edge. Any of these alone could sink expectancy; all three stack.
- **Is the author's MODERATE conviction justified by the rules as written?** Yes, and if anything generous. The documented evidence is a self-reported 2009-2010 hand-compiled log whose headline stat (avg winner = 1.34× avg loser) is explicitly attributed to the one rule this spec cannot express. The v2 backtest therefore measures a **strictly worse variant** of the manual system: a gate PASS would be strong evidence for the core entry logic (edge survives without the discretionary exit), while a FAIL is genuinely inconclusive about the author's manual system — it convicts only the fully-mechanical remainder. Both outcomes are informative and the report must say so rather than presenting either as a verdict on the source thread.
