# SPEC-riding_trend_retracement

**Source:** row 1 of forex_swing_strategies.csv · https://www.forexstrategiesresources.com/trend-following-forex-strategies/88-riding-the-trend-after-retracement/
**Conviction (author's):** HIGHLY_RECOMMENDED

## 1. Hypothesis

Established trends, as measured by price holding above a rising 200-day SMA, persist because the dominant order flow in the market is aligned with the prevailing direction; counter-trend retracements are profit-taking pauses, not reversals, and they tend to resolve back in the trend direction. A buy stop placed beyond the *second* consecutive higher swing high demands that the market prove resumption twice before capital is committed, filtering out the deep pullbacks that become genuine reversals. The edge should persist because it is the behavioural signature of trend-following: late, confirmed entries in exchange for a higher win rate on continuation, monetised by asymmetric scale-outs (1:2 / 1:4 / 1:6) that let the surviving third of the position harvest the tail of the move.

## 2. Scope

- primary_granularity: H4
- context_granularities: [D1]
- simulate_on: H1
- pairs_requested: ["Any majors", "examples USD/CHF", "EUR/CAD"]   # verbatim from CSV target_pairs: `Any majors|examples USD/CHF|EUR/CAD`
- pairs_available (resolved): ["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD", "USD_CHF (pending Wave-1 backfill)", "NZD_USD (pending Wave-1 backfill)", "EUR_CAD (pending Wave-1 backfill)"]
  - "Any majors" is read as the seven USD majors: EUR_USD, GBP_USD, USD_JPY, USD_CHF, AUD_USD, USD_CAD, NZD_USD. EUR_CAD is added because it is a named example.
- pairs_missing: [] — every named or implied pair is either present or in the published Wave-1 addition list (USD_CHF, NZD_USD, EUR_CAD). **No DATA-GAP file is required.** Pairs marked pending are declared and skipped by the harness if their backfill is incomplete, per DATA_AVAILABILITY.md.

## 3. Indicators

| Indicator | Params | Source |
|---|---|---|
| SMA on D1 close | period=200 | `indicators.sma(d1_close, 200)` — exists |
| SMA slope | `sma200.diff(5) > 0` (rise over 5 completed D1 bars) | trivial transform of the above; from CSV pseudocode |
| Causal ZigZag swing highs/lows on H4 | `depth=3, deviation_pips=0.5, backstep=3` | `causal_structure.zigzag_swings(high, low, depth=3, deviation_pips=0.5, backstep=3)` — exists (Wave 1). Source is MT4 ZigZag (3,5,3) = depth 3, deviation 5 **points** (= 0.5 pip on a 5-digit feed), backstep 3. See §10 #3. |
| Rolling access to last N confirmed swings | n=3 highs, n=2 lows | `causal_structure.last_n_confirmed_highs` / lows mirror — exists (Wave 1) |
| Pip size / pip value | per-pair | `indicators.calculate_pips` / `get_pip_value` — exists. 1 pip = 0.0001 for non-JPY pairs, 0.01 for JPY pairs (none requested, but the formula must route through `get_pip_value`, not a literal). |

Nothing required is absent from the inventory or `causal_structure`.

## 4. Entry — long

All inputs evaluated at the **close of an H4 decision bar t**, using only D1 bars fully closed before t and H4 swings **confirmed** at or before t.

1. **D1 trend filter (bullish):** at the most recent fully-closed D1 bar, `Close > SMA200(D1)` **and** `SMA200(today) − SMA200(5 D1 bars ago) > 0`.
2. **Swing sequence (H4):** the last three confirmed ZigZag swing highs, in order of occurrence, satisfy `H1 < H2 < H3` (strictly). H3 is "the SECOND consecutive higher high" — H2 is the first, H3 the second (matches CSV pseudocode `(sh[-1]>sh[-2])&(sh[-2]>sh[-3])`).
3. **Retracement condition:** the confirmed ZigZag pivots interleaved with H1..H3 alternate (the causal ZigZag emits alternating highs/lows by construction), i.e. a confirmed swing low exists between each consecutive pair of the three highs. Each down-leg high→low is the "counter-trend retracement". No additional depth requirement is imposed (see §10 #4).
4. **Count reset:** the rising-high count resets to zero when (a) a newly confirmed swing high is **not** strictly above the previous confirmed swing high, or (b) the D1 filter in condition 1 goes false. After a reset, three fresh confirmed highs are required.
5. **Sequence rule:** conditions 1–4 must all hold at the close of decision bar t. The order becomes eligible for fill from bar t+1 onward (F1).

- entry type: **buy_stop**
- entry level: `H3 + 2 pips + 1.0 pip` = `H3 + 3 pips` (the author's "+ spread" is taken as a literal 1.0-pip constant in the *level*; the engine's F10 spread/slippage is applied on the fill separately — see §10 #2). Convert to price via `get_pip_value`.
- expires_after_bars: **1 H4 decision bar** (= 4 H1 simulation bars under Part-D resolution). Rationale and arithmetic in §10 #6: with re-emission every decision bar and a 1-bar lifetime, each intent's only fill-eligible window is bar t+1 (F1 + F4), and the next intent (emitted at t+1, if conditions still hold) is eligible only from t+2. The eligible windows are disjoint, so **at most one pending order from this strategy is ever live per pair**, and at most one position can open per bar — no OCO, cancel-on-fill, or supersede semantics are needed or assumed, because contract v2 has none.
- **Re-emission semantics (declarative):** at each H4 decision bar the strategy emits **at most one** new `OrderIntent`, whose level is derived from swings confirmed at that bar (level = newest confirmed H3 + 3 pips; it never moves toward the market). Previously emitted intents live or die **solely** by F3 fills and F4 expiry; the strategy cannot observe fills, open positions, or live pendings, and emits nothing that cancels, amends, or supersedes a prior intent.
- Only stop orders are used; no market entry, ever ("only stop orders, never enter early").
- One open position per (strategy, pair) at a time (F12 default, stated for the report). The 1-bar expiry above guarantees this structurally rather than relying on any engine-side pending-gating: a stale pending can never coexist with a newer one, so §3.2 step 5 (which fills pendings without an F12 re-check) can never produce two fills from this strategy.

## 5. Entry — short

Exact mirror of §4. The strategy is two-sided.

1. **D1 trend filter (bearish):** most recent fully-closed D1 bar has `Close < SMA200(D1)` **and** `SMA200(today) − SMA200(5 D1 bars ago) < 0`.
2. **Swing sequence (H4):** last three confirmed ZigZag swing lows, in occurrence order, satisfy `L1 > L2 > L3` (strictly). L3 is the second consecutive lower low.
3. **Retracement condition:** confirmed swing highs interleave L1..L3 (alternating ZigZag pivots); each up-leg is the counter-trend retracement.
4. **Count reset:** as §4 (4), mirrored.
5. Entry type: **sell_stop**; entry level `L3 − 2 pips − 1.0 pip` = `L3 − 3 pips`; expires_after_bars **1** (H4 decision bar, = 4 H1 simulation bars); same declarative re-emission semantics as §4 — at most one new intent per decision bar, prior intents live or die solely by F3/F4, disjoint eligible windows guarantee at most one live pending per pair.

## 6. Stop

- initial stop (long): `max(entry_price − 100 pips, SL_conf − 20 pips)` where `SL_conf` is the level of the most recent **confirmed** H4 swing low knowable at the decision bar (confirmation lag ≥ 3 H4 bars, see §9). I.e. the 100-pip stop is used unless the swing-based stop is *closer to entry* (tighter), per the CSV's "(or 20 pips beyond recent swing if closer)". Mirror for short: `min(entry_price + 100 pips, SH_conf + 20 pips)` with `SH_conf` the most recent confirmed swing high.
- move_to_breakeven_on: **TP2** (breakeven_offset_pips = 0.0). Per F8, the move happens at the close of the bar on which TP2 fills.
- trail: **none** ("never tamper/widen stops"; no trailing is mentioned in the source). After the breakeven move the stop is static for the remaining third.

## 7. Exit legs

Levels are fixed pip distances from the actual fill price. The source's "(adjustable to nearby D1 S/R)" is **not** implemented — it is discretionary and non-mechanical (§10 #5).

| Label | Fraction | Kind | Level formula (long; mirror for short) |
|---|---|---|---|
| TP1 | 0.333 | take_profit | `entry_price + 200 pips` |
| TP2 | 0.333 | take_profit | `entry_price + 400 pips` |
| TP3 | 0.334 | take_profit | `entry_price + 600 pips` |

Fractions sum to 1.000. Any unfilled remainder closes at END_OF_DATA per F11.

## 8. Filters

| Filter | Timeframe | Rule | Knowable when |
|---|---|---|---|
| Trend direction | D1 | `Close >/< SMA200` at the last fully-closed D1 bar | A D1 bar stamped (open) `T` closes at `T + 24h`; it may first inform an H4 decision at `T + 24h`. Enforced by shifting the D1 index one full D1 interval and `merge_asof(..., allow_exact_matches=False)` per the contract's MTF rule. Example: D1 bar stamped 2026-08-05T21:00Z is knowable at 2026-08-06T21:00Z, i.e. at the H4 bar opening 2026-08-06T21:00Z at the earliest. |
| Trend slope | D1 | `SMA200.diff(5)` strictly positive (long) / negative (short); requires 6 completed D1 closes | Same knowability as above — the most recent of the 6 D1 bars must be fully closed before the H4 decision bar. |
| Retracement/resumption structure | H4 | confirmed ZigZag pivots only (§4/§5) | Pivot occurring at H4 bar k is knowable at the close of bar k + 3 (backstep=3) at the earliest; the causal implementation stamps it at its confirmation bar. |

No session, volatility, or news filters exist in the source and none are added.

## 9. Causality audit

Read first. Every rule, the bar at which its inputs are fully known, and every confirmation lag:

1. **D1 SMA200 (§8):** computable at the close of D1 bar d; knowable at the open of D1 bar d+1. H4 decisions use only D1 bars with close time ≤ H4 decision-bar open. No look-ahead possible after the index shift.
2. **D1 slope `sma200.diff(5)` (§8):** requires SMA values from 6 D1 closes; knowability governed by the most recent of the six, as in (1).
3. **H4 ZigZag pivots (§3, §4.2, §4.3, §5.2):** implemented by `causal_structure.zigzag_swings(depth=3, deviation_pips=0.5, backstep=3)`, which stamps a pivot at its **confirmation bar**, never its occurrence bar. A swing high occurring at H4 bar k is knowable no earlier than the close of bar **k+3** (backstep=3 is the minimum lag; deviation filtering can extend it). **Confirmation lag: ≥ 3 H4 bars (≥ 12 hours).** The banned `detect_swing_points` (centred window) is not used anywhere.
4. **"Second consecutive higher high" trigger (§4.2):** all three highs H1, H2, H3 must be *confirmed*; the condition is first true at the close of the H4 bar that confirms H3, i.e. ≥ 3 H4 bars after H3's occurrence. The decision bar is that confirmation close or a later bar.
5. **Buy-stop level `H3 + 3 pips` (§4):** the *level* was set at H3's occurrence bar, but it is *used* only from H3's confirmation bar onward. This is the sanctioned causal pattern (act from k+period, use the level from k) — it is what a live trader does and is not look-ahead.
6. **Retracement alternation (§4.3):** uses the same confirmed pivots; knowable at the same bars as (3)/(4).
7. **Initial stop's "recent swing" (§6):** the most recent swing low/high **confirmed at or before the decision bar** — inherently ≥ 3 H4 bars stale. Using an unconfirmed swing here would be look-ahead and is rejected (§10 #7).
8. **Order lifetime / re-emission (§4):** eligibility from decision bar t+1 (F1); expiry after 1 H4 decision bar (F4); re-emission re-derives levels from swings confirmed at the new decision bar only. This is a mechanics choice, not a data-timing input — the audit's knowability claims are unchanged: every level still derives exclusively from pivots confirmed at or before the emitting decision bar.
9. **TP1/TP2/TP3 (§7):** levels are fixed pip offsets from the fill price — no forward information.
10. **Breakeven on TP2 (§6):** triggered by the TP2 fill, applied at the **close** of that bar per F8; the trade's own history, no external data.
11. **Fill resolution:** decisions on H4, fills/stops/legs resolved on H1 bars within each H4 span (Part D); stop-before-target (F5) and gap fills at open (F3, F6) are pessimistic conventions, not data.

## 10. Ambiguities resolved

| # | Ambiguity in the source | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | "Any majors \| examples USD/CHF\|EUR/CAD" — which pairs? | The seven USD majors + EUR_CAD (named example). 5 available now; USD_CHF, NZD_USD, EUR_CAD pending Wave-1 backfill. | Only the two named examples (USD/CHF, EUR/CAD) — discards "any majors", the author's primary scope, and shrinks the sample. |
| 2 | "buy stop 2 pips + spread above the high" — spread is variable and is already charged by the engine (F10). | Level = `H3 + 2 pips + 1.0 pip` (declared constant in the level, per author's explicit formula; engine costs apply on fill separately). This makes the stop *higher* → later, worse entries: strictly conservative. | `H3 + 2 pips` only — closer to the market, earlier fills, more trades: less conservative. |
| 3 | ZigZag "(3,5,3)": parameter order and the unit of the middle parameter. | MT4 convention: depth=3, deviation=5 **points** = 0.5 pip (5-digit feed), backstep=3 → `zigzag_swings(depth=3, deviation_pips=0.5, backstep=3)`. | deviation = 5 full pips — over-filters on H4 majors, collapsing swing counts and starving signals; a distortion, not a conservative reading. |
| 4 | "Counter-trend retracement (ZigZag waves against trend)" — no depth or duration given. | Satisfied structurally: the alternating causal ZigZag guarantees a confirmed counter-leg between each pair of the three highs; no extra threshold invented. | Adding an un-stated minimum retracement depth (e.g. % of ATR) — invents a parameter the author never gave. |
| 5 | "TPs adjustable to nearby D1 S/R" | Not implemented; fixed 200/400/600-pip legs. | Snap each TP to the nearest D1 support/resistance level — discretionary (which S/R? which tolerance?), non-reproducible, and would require a level detector the source never specifies. |
| 6 | Pending-order behaviour when structure evolves before fill, order lifetime (source silent), and coexistence of re-emitted pendings. Contract v2 has **no OCO, no cancel-on-fill, no supersede**; F12 caps concurrent *positions* only and does not gate pending fills (contract §3.2 step 5 fills pendings without an F12 re-check). | **expires_after_bars = 1 H4 decision bar.** Arithmetic: intent emitted at close of bar t is fill-eligible only on bar t+1 (F1), and dies after that bar (F4); the next intent, emitted at t+1, is eligible only from t+2. Eligible windows are pairwise disjoint ⇒ at most one live pending per pair at any time ⇒ at most one fill per bar ⇒ two concurrent positions are structurally impossible, with no reliance on cancellation semantics that do not exist. This is also the more conservative expressible reading: each setup gets exactly one H4 bar to trigger, so borderline triggers are missed (fewer trades). Re-emission still re-derives the level from swings confirmed at the new decision bar; the level never moves toward the market. | (a) expires_after_bars = 5 (contract default): up to ~5 stale pendings at ratcheting levels coexist; a lower older stop can fill after a newer position opened → two concurrent positions — rejected as it would require cancel-on-fill semantics the contract does not provide, and residual multi-fill risk would contaminate the r-multiple series. (b) GTC until structure breaks: worse still — more fills from stale levels, earlier entries. Both rejected; the fleet rule's option (a) (short expiry) is taken rather than recording residual risk. Report-level note: F12 = 1 per (strategy, pair) is stated regardless, and per-cell trade counts are reported per Part G. |
| 7 | "Recent swing" for the alternative stop — which swing, known when? | Most recent **confirmed** swing (≥ 3-bar lag); used only when it yields a stop closer to entry than 100 pips. | Most recent swing including unconfirmed candidates — look-ahead (a bar cannot know it is a swing low until future bars fail to break it). |
| 8 | "SECOND consecutive higher high" — two highs or three? | Three strictly rising confirmed highs (H3 is the second HH), matching the CSV pseudocode. | Two rising highs (act on H2) — earlier entries, roughly double the triggers: less conservative. |

## 11. Expected behaviour

- **Rough trade frequency:** the CSV does not state one. Estimate: the trigger requires a D1-filtered trend plus three sequentially confirmed rising H4 swing highs (each confirmation ≥ 3 H4 bars apart in practice), so a fresh setup completes no faster than ~1–2 weeks; additionally, each setup has only a single H4 bar to trigger (§10 #6), so some confirmed setups will expire unfilled — expect roughly **1–3 trades per pair per month** in trending regimes and long flat stretches in range regimes. Across 8 pairs, plausibly 10–25 trades/month pooled.
- **What would make it fail the gates:**
  - The trigger buys the *third* rising high — entries arrive late in mature swings, so in choppy D1 trends price is often near exhaustion; TP3 (+600 pips) fills will be rare and TP1/TP2 must carry expectancy.
  - Fixed pip geometry (100-pip SL vs 200/400/600 TPs) ignores per-pair volatility: on EUR_CAD or a quiet regime 100 pips is routinely noise, inflating stop-outs; TP2→breakeven (with F8's bar-close delay) then caps many trades near 0R.
  - Multi-leg r-multiples concentrate weight on TP3's tail (1:6 on 0.334 of the position); a regime with shallow continuations degrades the pooled r-multiple even if TP1 hits often.
  - Per-cell dispersion is likely (strong on trending pairs, poor on rangy ones); pooled gates could pass or fail on composition rather than edge.
- **Is the author's HIGHLY_RECOMMENDED justified?** Not on the evidence given: the recommendation reasoning cites a worked example and a single real-account profit screenshot — anecdote, not a sample. The logic itself (trend filter + confirmed resumption + asymmetric scale-outs) is a coherent, mainstream trend-continuation design and is fully mechanisable, so it merits testing; but conviction should be treated as **unverified** until the walk-forward gates speak.
