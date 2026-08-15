# SPEC-janus_swing_system
**Source:** row 6 of forex_swing_strategies.csv · https://www.forexstrategiesresources.com/trend-following-forex-strategies/109-forex-swing-system/
**Conviction (author's):** MODERATE

## 1. Hypothesis
After a multi-day decline into a well-tested demand zone, a strong-bodied bullish day (a "straight bar" closing in its upper half) marks the point where momentum sellers are exhausted and value buyers defending the level take control; entering on a retracement to that day's midpoint captures the mean-reversion swing back away from support. The edge should persist because round-tripped daily ranges at visible swing lows reflect real order-flow: breakout sellers are trapped below the level, and their covering plus fresh buying from level-watchers produces a multi-day bounce. It is a behavioural fade-of-weakness edge, not a statistical one, which is why the author rates it only MODERATE and supplies narrative examples rather than a backtest.

## 2. Scope
- **primary_granularity:** D1
- **context_granularities:** none (single-timeframe strategy; all inputs are D1)
- **simulate_on:** H1 (fills, stops, and trailing leg resolved on H1 bars within each D1 span, per contract §5)
- **pairs_requested (verbatim):** EUR/USD | EUR/CAD | EUR/AUD | EUR/JPY | AUD/USD | AUD/NZD | USD/CAD | GBP/USD | GBP/JPY | USD/JPY | NZD/USD (11 pairs)
- **pairs_available:** EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD (live) · EUR_JPY, GBP_JPY, NZD_USD, EUR_CAD, EUR_AUD, AUD_NZD (Wave-1 additions, **pending** — harness skips until backfill lands; NOT gaps)
- **pairs_missing:** none. All 11 requested pairs are live or Wave-1 pending. D1 is available and current for all live pairs. **No DATA-GAP file is required for this strategy.**

## 3. Indicators
| Indicator | Params | Source |
|---|---|---|
| Confirmed swing lows | `confirmed_swing_points(high, low, period=5)` on D1, low side only for longs | `causal_structure.confirmed_swing_points` (Wave 1). Level set at occurrence bar k, knowable only from bar k+5. |
| Confirmed swing highs | same function, high side, period=5, for shorts | `causal_structure.confirmed_swing_points` |
| Bar midpoint | mid(t) = (High(t) + Low(t)) / 2 | trivial private computation, no inventory entry needed |
| Pip conversion | `calculate_pips(price_change, asset)` / `get_pip_value(asset)` per pair (handles JPY conventions) | inventory `calculate_pips`, `get_pip_value` |
| Down/up-day counter | sign of Close(t) − Close(t−1); no indicator, exact comparison of consecutive closes | private, fully specified in §4/§5 |

No ATR, no moving averages, no other indicators are used. The 5-pip stop buffer and 10-pip S/R tolerance are fixed pip values converted per pair via `calculate_pips`.

## 4. Entry — long
All conditions are evaluated on the **decision bar t** = the most recently CLOSED D1 bar (the "prior day" of the source). Notation: O,H,L,C = Open/High/Low/Close of bar t; mid = (H+L)/2.

1. **Bullish straight bar:** O(t) > mid(t) AND C(t) > mid(t) AND C(t) > O(t). (Third clause is the CSV's stated conservative filter; note O>mid and C>O jointly imply C>mid, so the binding conditions are O(t) > mid(t) and C(t) > O(t).)
2. **Three prior down days:** C(t−1) < C(t−2) AND C(t−2) < C(t−3) AND C(t−3) < C(t−4) — three strictly consecutive down closes ENDING at bar t−1, i.e. the decline precedes the signal bar and does not include it.
3. **At support:** let L_sl = the level of the most recent D1 swing low CONFIRMED at or before bar t (a swing low occurring at bar k is confirmed at bar k+5; require k+5 ≤ t). Condition: |L(t) − L_sl| ≤ 10 pips (pip size per pair via `calculate_pips`).
4. **Re-emission guard (no-OCO mitigation):** do not emit if any OrderIntent for this (strategy, pair) was emitted at any decision bar in [t−3, t−1]. The strategy knows its own emission history without observing fills, so this is causal. With expires_after_bars = 3, an order emitted at t0 is live during t0+1…t0+3; suppressing emissions until t0+4 guarantees at most one live pending order per pair at any time.

- **Entry type:** `buy_limit`
- **Entry level:** entry_price = mid(t) = (H(t)+L(t))/2. (Bar t closed above mid, so the limit is below the decision close — passes the contract's "not already through the market" validation.)
- **expires_after_bars:** **3** (D1 decision-frame bars; conservative end of the source's "3–4 days"). Wave 2 must translate to simulation bars if the engine counts H1 bars (3 D1 bars = 72 H1 bars) — see §10 #6.
- **decision_bar:** close timestamp of D1 bar t; order eligible for fill from the next bar onward (F1).

## 5. Entry — short
Full mirror of §4 on the same decision bar t:

1. **Bearish straight bar:** O(t) < mid(t) AND C(t) < mid(t) AND C(t) < O(t).
2. **Three prior up days:** C(t−1) > C(t−2) > C(t−3) > C(t−4).
3. **At resistance:** let L_sh = the level of the most recent D1 swing HIGH confirmed at or before t (occurrence k, knowable from k+5, k+5 ≤ t). Condition: |H(t) − L_sh| ≤ 10 pips.
4. Same re-emission guard as §4.4.
- **Entry type:** `sell_limit` at entry_price = mid(t) (above the decision close, since C(t) < mid(t)).
- **expires_after_bars:** 3 D1 bars.

Long and short signals on the same bar are mutually exclusive by construction (conditions 1 cannot both hold).

## 6. Stop
- **Initial stop (long):** stop.price = L(t) − 5 pips. **(short):** stop.price = H(t) + 5 pips. Exact formula, fixed at emission; pip conversion per pair.
- **Declared risk R** = |entry_price − stop.price| = mid(t) − L(t) + 5 pips (long) / H(t) + 5 pips − mid(t) (short). Author's "typical risk 30–70 pips" is descriptive only, not a filter (no min/max gate is applied — see §10 #7).
- **move_to_breakeven_on:** none.
- **trail:** implemented as the exit leg in §7 (a fixed-distance trailing leg whose distance equals R). StopRule.trail_atr_multiple = None — an ATR-multiple trail cannot express a fixed pip distance and is rejected (§10 #3). Note: at emission the trailing leg's initial level (entry − R for longs) coincides exactly with the initial stop, so the trail never starts wider than StopRule; stops never widen (contract test 12).

## 7. Exit legs
| Label | Fraction | Kind | Level formula |
|---|---|---|---|
| TRAIL | 1.0 | trailing | pips = R_pips = calculate_pips(|entry_price − stop.price|, asset) — a fixed pip distance equal to the declared initial risk, trailing from the extreme favourable price after fill, updated at bar close (F9) |

Fractions sum to 1.0. There is no take-profit leg: the source says "trail stop … until stopped out". Positions still open at end of data close per F11 and are flagged. The source's breakeven ALTERNATIVE is rejected, not layered on top (§10 #3).

## 8. Filters
- **Straight-bar body filter** (entry condition §4.1/§5.1, including the CSV's conservative close>open / close<open clause): evaluated on D1 bar t, fully knowable at the close of bar t.
- **Trend-precondition filter** (3 consecutive down/up days): evaluated on D1 closes t−4…t−1, knowable at the close of bar t.
- **S/R proximity filter** (10-pip band around most recent confirmed swing point): evaluated on D1, knowable at close of bar t subject to the 5-bar confirmation lag (§9).
- **No session, news, volatility, spread, or higher-timeframe filters exist in the source** and none are added. No non-price data is required.
- The 1.0-pip spread in the cost model (F10) is used only by the engine for fills; it is NOT used as a proxy for any signal input. No invented data anywhere in this spec.

## 9. Causality audit
| Rule | Inputs | Fully known at | Confirmation lag |
|---|---|---|---|
| Straight bar (§4.1/§5.1) | OHLC of D1 bar t | close of bar t | 0 bars (decision bar itself) |
| 3 prior down/up days (§4.2/§5.2) | D1 closes t−4…t−1 | close of bar t | 0 bars |
| Support/resistance level (§4.3/§5.3) | swing low/high OCCURRING at bar k, confirmed at k+5; most recent with k+5 ≤ t; plus H(t)/L(t) | close of bar t | **5 D1 bars** — the level used at t was set at k ≤ t−5. Acting from k+5 onward on the level recorded at k is the legitimate causal_structure semantics; the spec never identifies bar k as a swing at bar k. |
| 10-pip band | fixed per pair via calculate_pips | constant | none |
| Entry price, stop, R, trail distance | H(t), L(t) only | close of bar t | 0 bars — all OrderIntent fields are declarable absolute values at creation (decision-bar anchored; no fill-price dependence) |
| Re-emission guard (§4.4) | strategy's own emission timestamps t−3…t−1 | close of bar t | 0 bars; uses no fill information |
| Fill eligibility | — | from bar t+1 (F1) | engine-enforced |
| Expiry | — | order cancelled after 3 decision-frame bars unfilled (F4) | engine-enforced |

**MTF causality:** not applicable — single decision frame (D1). H1 is used only by the engine to RESOLVE fills within D1 spans (contract §5); the strategy never reads H1 data, so no cross-timeframe leakage channel exists. Trailing-leg and any stop updates occur at H1 bar closes using completed H1 bars only (F9), inside the D1 span — engine-side, causal by construction.

## 10. Ambiguities resolved
| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | "Price just hit a support level" is wholly discretionary (author admits S/R placement is the discretionary part) | Mechanized: signal bar's extreme (L for long, H for short) within **10 pips** of the most recent CONFIRMED swing low/high (causal_structure period=5, 5-bar lag in §9). Fixed 10-pip band is tight → fewer signals. | 0.5×ATR(14) adaptive band (looser, ~2× wider on typical daily ATR → more trades, less conservative); volume_profile_levels (adds an inventory indicator the source never mentions); requiring the level to be recently confirmed (invents a recency gate). |
| 2 | "Cancel if not filled within 3–4 days" | expires_after_bars = **3** D1 bars (fewer fills, less conservative-risk of stale fills). | 4 bars — the generous end of the author's range. |
| 3 | "Trail stop at distance equal to initial risk" vs the author's own "alternative: move stop to breakeven after price gains initial risk + spread, then let it run" | Primary rule, expressed exactly: ExitLeg kind="trailing", pips = R (fixed pip distance), fraction 1.0; StopRule.trail_atr_multiple = None. Fixed-distance trailing IS expressible via ExitLeg.pips, so faithfulness and expressibility coincide. | (a) StopRule trail_atr_multiple = R/ATR14(t) — distance drifts with ATR after emission, not the documented rule; (b) the author's BE alternative — explicitly labelled "alternative" by the author, and inexpressible faithfully anyway: contract BE moves trigger only on an ExitLeg FILL (F8), which would force an invented scale-out leg at +R+spread. |
| 4 | "Pair declined at least 3 prior days" — window boundaries; pseudocode `rolling(3).sum()>=3` evaluated at t includes the signal bar's own close-to-close move | Three strictly consecutive down closes at t−1, t−2, t−3 (decline strictly PRECEDES the signal bar; stricter, fewer signals). | Pseudocode's inclusive rolling window (a bullish reversal bar that still closed below the prior close could count toward its own preceding decline — internally contradictory). |
| 5 | Straight-bar definition strength | All three clauses enforced (O>mid, C>mid, C>O per CSV's "conservative filter: close>open"); binding form O>mid AND C>O. | Relaxed pin-bar reading without the close>open clause (more signals; CSV itself supplies the conservative clause, so dropping it would be non-conservative). |
| 6 | No OCO / cancel-on-fill / supersede in contract v2; a 3-day pending order could overlap a later signal or an open position | Re-emission guard §4.4: ≥1 signal per 4 D1 bars per pair. Arithmetic: order from t0 lives t0+1…t0+3; next legal emission t0+4 → **pending-pending overlap impossible**. | Allowing concurrent pendings (would permit two fills from two orders; F12 caps positions only at admission, §3.2 step 6, and does NOT gate pending fills at step 5). |
| 7 | Residual overlap that the guard cannot remove: order from t0 FILLS (position open), then a legal signal at t0+4 fills while the trailed position is still open | Recorded, not patched: the strategy is declarative and cannot observe fills, so it cannot know a position is open. Direction of risk: a second same-direction position doubles exposure and duplicates trade count; each trade's r_multiple is still computed against its own declared risk, so pooled-R scale is not distorted, but position-count concurrency can exceed the F12 default of 1. Report must state this. | Raising max_concurrent_positions (would legitimise the overlap rather than disclose it); suppressing signals for N bars after ANY fill (requires observing fills — impossible under the declarative contract). |
| 8 | expires_after_bars counted in which frame — decisions are D1, simulation is H1 | Declared as 3 **decision-frame (D1) bars** = the author's "3 days". | Literal 3 H1 bars (≈3 hours — would void the author's intent almost entirely); if the engine only counts simulation bars, Wave 2 must emit expires_after_bars = 72 H1 bars and note the translation in its report. |
| 9 | "Typical risk 30–70 pips" | Descriptive only; no min/max risk gate applied. | Filtering out signals whose R falls outside 30–70 pips (invents a filter; would also interact with the fixed 5-pip buffer in untestable ways). |
| 10 | "SL 5 pips beyond signal-bar low/high" | Exactly 5.0 pips, converted per pair via calculate_pips (JPY pairs handled by the pair's pip size). | ATR-fraction buffer (invented); 5 pips on the entry side of the extreme (wrong side — would sit inside the signal bar's range). |

## 11. Expected behaviour
- **Frequency:** author claims ~12 signals/year/pair traded as an 11-pair basket. As mechanized here — strict straight bar + 3 strictly prior counter-moves + 10-pip band around a swing point that is already 5 bars stale + 1-signal-per-4-bars guard — expect materially fewer: roughly 3–8 signals/year/pair, i.e. ~40–90 trades/year across the basket once Wave-1 pairs land, ~15–40/year on the 5 live pairs. On a single pair over a 6-month OOS window this is single-digit trade counts; `low_confidence` flags per cell are likely and honest.
- **Holding time:** bimodal — quick stop-outs (−1R, occasionally worse via F6 weekend gaps on D1-held positions) versus long trailing holds that can run for weeks; END_OF_DATA closes (F11) will appear in every fold and must be flagged, not silently counted.
- **What would fail the gates:** (a) too few trades per fold (mechanized S/R + guard are deliberately strict); (b) F5 stop-before-target pessimism at H1 resolution hurts a strategy whose exit is a wide trail; (c) if the edge lives in the author's discretionary S/R eyeballing rather than in confirmed swing lows, the mechanized version measures something weaker — the native-vs-H1 delta (contract §5) plus T6-harness comparison will show whether the bespoke trail carries the edge.
- **Is the author's MODERATE conviction justified by the rules as written?** Yes — arguably generous. The candle, entry, and stop math are fully documented, but the core edge (S/R selection) is discretionary in the source and is the element this spec had to mechanize most aggressively (§10 #1); there is no statistical backtest behind the claims. The mechanization choices are all on the conservative side, so a pass under this spec is meaningful evidence; a fail does not refute the discretionary original.
