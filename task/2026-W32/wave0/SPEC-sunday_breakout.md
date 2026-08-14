# SPEC-sunday_breakout

**Source:** row 4 of forex_swing_strategies.csv · https://forums.babypips.com/t/sunday-breakout-strategy/23165
**Conviction (author's):** HIGHLY_RECOMMENDED

## 1. Hypothesis

The weekend close (Friday 21:00 → Sunday 21:00 UTC) interrupts price discovery while news and positioning accumulate; when the market reopens, the first hours of the week form an initial balance (the "Sunday candle") whose range encodes the opening week's unresolved order flow. A decisive break of that range by 10 pips signals that opening-week momentum is resolving in one direction, and the move tends to extend a meaningful fraction of the week's normal travel (half the weekly ATR). The edge should persist because it is structural — it rests on the fixed weekly close/reopen cycle of the FX market and the tendency of opening-range resolution to attract follow-through — not on any fitted parameter. Regime caveat: the author himself posted on 2010-07-30 that the method "is NOT working in the current market conditions", so persistence is regime-conditional, not guaranteed.

## 2. Scope

- primary_granularity: H4
- context_granularities: [W1]            # weekly ATR(14) for the TP distance
- simulate_on: H1
- pairs_requested: [GBP/USD, EUR/JPY]    # verbatim from CSV target_pairs: "GBP/USD | EUR/JPY"
- pairs_available: [GBP_USD (available now); EUR_JPY (pending — Wave 1 addition, backfill is an overnight operator job and may be incomplete; harness skips pairs with insufficient history)]
- pairs_missing: [] — but EUR_JPY is not yet queryable, and W1 is stale ~8 weeks while this strategy requires weekly ATR → see DATA-GAP-sunday_breakout.md

## 3. Indicators

| Indicator | Params | Source |
|---|---|---|
| Weekly ATR | `atr(W1.High, W1.Low, W1.Close, period=14)` | `indicators.atr` (existing inventory) applied to the W1 frame |
| Sunday candle high / low | max/min of the single H4 "Sunday candle" bar (definition in §9) | plain bar fields, no indicator |
| Pip size | `get_pip_value(asset)` | existing inventory; 0.0001 for GBP_USD, 0.01 for EUR_JPY. "10 pips" = `10 * get_pip_value(pair)` in price units |

**Weekly ATR(14) — exact computation and knowability.**
Compute `atr()` on the W1 frame with period 14 (the inventory's standard TR/Wilder implementation, unmodified). W1 bars are stamped at their open and a bar may inform a decision only after it has closed (Contract §4 rule). Mechanical alignment: shift the W1 index forward by one full weekly interval (7 days), then `merge_asof` into the H4 decision frame with `direction="backward", allow_exact_matches=False`. Consequence: at the Sunday-candle decision bar of week *W* (closes Monday 01:00 UTC), the ATR value used is the one whose last constituent W1 bar is the week that **ended** at the Sunday 21:00 UTC reopen — i.e. 14 fully completed weeks, no partial week. The ATR value is locked at decision time and reused for the TP leg regardless of what later weeks do. The DB's W1 stamps observed in DATA_AVAILABILITY (2005-12-30, 2026-06-12 — both Fridays) suggest the stamp convention may not be Sunday-open; this is irrelevant to correctness *provided* the shift-by-one-interval + no-exact-match alignment above is applied, and it is flagged in §10.

## 4. Entry — long

Evaluated once per trading week, at the close of the Sunday candle (decision bar, defined in §9):

1. Let `sun_high` = High of the Sunday candle (H4 bar stamped Sunday 21:00 UTC).
2. Let `pip10 = 10 * get_pip_value(pair)`.
3. Entry type: `buy_stop` (pending).
4. Entry level: `entry_price = sun_high + pip10`.
5. Both this order and the §5 short order are emitted at the same decision bar and remain live **independently** until F3 fill or F4 expiry. Contract v2 has no OCO, no cancel-on-fill, and no supersede; the strategy is declarative and never learns which order filled, so no sibling-cancellation is specified or implied. The one-trade-per-week intent of the CSV is therefore only partially enforceable — the residual second-fill risk is recorded in §10.8.
6. `expires_after_bars = 29`, measured in **decision-frame (H4) bars** from the decision bar. Arithmetic: the decision bar is the Sunday candle (H4 stamped Sunday 21:00 UTC); per F1 fills are eligible from the next H4 bar (stamped Monday 01:00 UTC); the trading week ends Friday 21:00 UTC and the last H4 bar of the week is stamped Friday 17:00 UTC (covers 17:00–21:00). The H4 bars from Monday 01:00 through Friday 17:00 inclusive number **29** (Mon–Thu 6 each = 24, plus Fri 01/05/09/13/17 = 5). An order unfilled after those 29 bars is cancelled at the Friday 21:00 UTC close and can never survive into the next week's Sunday candle.
7. Validation holds by construction: `entry_price > sun_high >= decision-bar close`, so the buy stop is never through the market at decision time (Contract §2.2 invariant).

## 5. Entry — short

Mirror of §4, evaluated at the same decision bar:

1. Let `sun_low` = Low of the Sunday candle.
2. Entry type: `sell_stop` (pending).
3. Entry level: `entry_price = sun_low - pip10` (same `pip10` as §4).
4. Emitted simultaneously with the §4 long order; both pendings stay live independently until F3 fill or F4 expiry (no OCO exists in contract v2 — see §4.5 and §10.8).
5. Same expiry as §4.6: `expires_after_bars = 29` decision-frame (H4) bars, dying at the Friday 21:00 UTC close of the entry week.
6. `entry_price < sun_low <= decision-bar close`, so the sell stop is never through the market at decision time.

## 6. Stop

- initial stop: **long** → `stop.price = sun_low` (Sunday candle low). **short** → `stop.price = sun_high` (Sunday candle high). Initial risk in price units, computed off the *declared* entry level (the only price knowable at decision time): `R = |entry_price − stop.price| = (sun_high − sun_low) + pip10`, identical for both directions.
- move_to_breakeven_on: **"BE_2R"** — the label of the auxiliary trigger leg defined in §7. The source rule is "move SL to breakeven once profit reaches 2× initial stop distance". The contract's `StopRule.move_to_breakeven_on` only accepts an `ExitLeg.label`, and `ExitLeg.fraction` must be > 0, so a zero-size trigger is not expressible. The in-contract expression is a take-profit leg of fraction 0.01 placed at exactly +2R whose fill triggers the BE move. Two honest mismatches result and are recorded in §10: (a) the leg is not truly zero-size; (b) per F8 the stop moves at the **close** of the bar that touches +2R, not intrabar — strictly later than the live-trader rule, i.e. pessimistic. `breakeven_offset_pips = 0.0` (exact entry level; note the engine's r-multiple accounting uses the actual fill, which may be worse than the declared level under F3 gap fills — accepted, honest).
- trail: **none** (`trail_atr_multiple = None`).

## 7. Exit legs

`ATR_w` = weekly ATR(14) value locked at the decision bar (§3). Levels are computed from the **declared** entry level `entry_price` (§4/§5), because the actual fill price is unknowable when the OrderIntent is emitted. `R = |entry_price − stop.price|`.

| Label | Fraction | Kind | Level formula |
|---|---|---|---|
| BE_2R | 0.01 | take_profit | long: `entry_price + 2*R` · short: `entry_price − 2*R` (exists only to trigger `move_to_breakeven_on`; see §6 and §10.3) |
| TP | 0.99 | take_profit | long: `entry_price + 0.5*ATR_w` · short: `entry_price − 0.5*ATR_w` |

Fractions sum to 1.0 exactly. Both legs lie beyond entry in the trade direction, satisfying Contract §2.2 validation. If `0.5*ATR_w < 2*R`, TP is nearer than BE_2R: per F7 both can fill in one bar (nearest first) and the BE trigger may never fire before the position closes — this matches the source's economic logic (a trade that reaches target before +2R never needed the BE move). Stops/TP are static once declared; no trailing. If neither leg nor stop is hit, the position carries until one is — including across subsequent weekend gaps (F6 applies) — see §10.6 for the rejected Friday-close alternative.

## 8. Filters

1. **One trade per week per pair — intended, partially enforceable** (CSV `risk_management`). Evaluated on: H4 decision frame. What the strategy controls: OrderIntents are emitted only at the Sunday-candle decision bar (exactly one decision, hence exactly one long and one short pending, per trading week), and no further orders are emitted until the next week's decision bar. What the engine controls: F12 (`max_concurrent_positions = 1` per (strategy, pair, granularity)) caps *concurrent* positions, so the two pendings can never both be open at once, and a new week's pendings cannot fill while a prior week's position is still open. What **neither** controls: contract v2 has no OCO/cancel-on-fill, and F12 does not gate pending fills (§3.2 step 5) — after a mid-week stop-out, the surviving sibling stop-order remains live and CAN fill within its 29-bar expiry, producing a second sequential same-week trade the CSV forbids. This residual risk is recorded in §10.8 and must be flagged in the report. Knowable: entirely at/after the decision bar; no future data.
2. **Correlation note** (CSV `risk_management`: "avoid stacking highly correlated pairs"). Not expressible at the single-(strategy, pair) level of the v2 engine — it is a portfolio-construction concern, and System 1 never sizes. GBP_USD and EUR_JPY are historically only moderately correlated, and the source author ran exactly these two pairs (with undocumented modified EUR/JPY rules — §10.7). Disposition: **not implemented as a gate**; recorded here so the report can state per-cell results without implying portfolio-level independence. Evaluated on: N/A.

## 9. Causality audit

The crux: **what is the "Sunday candle" in THIS data?** The market is closed Friday 21:00 → Sunday 21:00 UTC. On the expected 21:00-aligned H4 grid (stamps 21:00, 01:00, 05:00, 09:00, 13:00, 17:00 UTC, matching the D1 21:00Z stamp convention in DATA_AVAILABILITY), exactly **one** H4 bar exists on a Sunday: the bar **stamped Sunday 21:00 UTC**, covering Sunday 21:00 → Monday 01:00 UTC. That bar IS the Sunday candle. Mechanical definition robust to grid alignment: *the Sunday candle of trading week W is the first H4 bar whose open timestamp is ≥ W's reopen (Sunday 21:00 UTC).* Its high/low are **fully knowable only at its close: Monday 01:00 UTC**.

| Rule | Inputs fully known at |
|---|---|
| §3 Weekly ATR(14) | At the decision bar (Monday 01:00 UTC): the ATR's last W1 bar is the week that ended Sunday 21:00 UTC, which closed 4 h before the decision bar. The one-interval index shift + `allow_exact_matches=False` guarantees no partial/current week enters. Note: the decision could in principle be made at Sunday 21:00 UTC + ε using this same ATR — but the Sunday candle's high/low cannot, so the decision bar is the binding constraint. |
| §4/§5 Sunday candle high/low, entry levels | Monday 01:00 UTC (close of the H4 bar stamped Sunday 21:00 UTC). This is the `decision_bar` of both OrderIntents. Per F1 the orders become fill-eligible from the next bar (H4 stamped Monday 01:00; in H1 resolution, the H1 bar stamped Monday 01:00) — never on the Sunday candle itself. |
| §4/§5 one-trade-per-week intent | Emission state at and after the decision bar (one decision per week; no future data). Concurrency enforced engine-side by F12; the absence of OCO/cancel-on-fill is a contract limitation, not an information-timing issue — residual same-week second-fill risk recorded in §10.8. |
| §6 initial stop | Monday 01:00 UTC (same bar as entry levels). Static thereafter. |
| §7 BE_2R and TP levels | Locked at the decision bar from `entry_price`, `sun_high/low`, and the already-knowable `ATR_w`. The BE stop-move itself is engine-side: triggered only by a *later* H1-resolution bar touching +2R, applied at that bar's close (F8). No look-ahead. |
| §7 fills of legs/stop | Resolved by the position engine on H1 bars strictly after entry (F3/F5/F6/F7). The strategy never sees fill data. |
| §4.6 expiry | Calendar deadline (Friday 21:00 UTC of entry week) fixed at decision time. |

Explicit non-uses: the D1 bar stamped Sunday 21:00 UTC (covers the full 24 h to Monday 21:00) is **not** the Sunday candle — using it would delay entries to Monday 21:00 UTC and discard the strategy's premise (rejected alternative, §10.1). No H1 data is visible to the strategy (Contract Part D): decisions come from H4 + shifted W1 only.

## 10. Ambiguities resolved

| # | Ambiguity in the source | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | "Sunday candle" assumes a broker feed with a Sunday 20:00 GMT candle (source names IBFX); our feed reopens Sunday 21:00 UTC and stamps H4 bars at open. Which bar is the Sunday candle? | The single H4 bar stamped Sunday 21:00 UTC (covers 21:00→01:00 Mon), knowable at Monday 01:00 UTC; defined mechanically as the first H4 bar at/after the weekly reopen. | (a) The D1 bar stamped Sunday 21:00 (24 h; knowable Monday 21:00 — destroys the early-week entry that is the strategy's premise); (b) the H1 bar stamped Sunday 21:00 (captures only 1 h of opening flow — range too narrow, more fills, more noise); (c) reconstructing a synthetic 20:00 GMT candle — impossible, no data exists before the 21:00 UTC reopen. |
| 2 | Weekly ATR knowability: W1 bars are stamped at open, and the DB's observed W1 stamps are Fridays (2005-12-30, 2026-06-12), so the stamp convention is not literally "Sunday open". When may a W1 bar's value be used? | A W1 bar may inform decisions only from 7 days after its stamp (shift index +1 weekly interval, `merge_asof` backward, no exact matches). Only fully completed weeks ever enter the ATR, whatever the true stamp convention. | Using the W1 bar stamped at the start of the current (incomplete) week — reads up to 6 days of the future relative to early-week decisions; classic FIX-S1-005-class look-ahead. |
| 3 | Source moves SL to breakeven intrabar at +2R unrealized profit; the contract only supports label-triggered BE (an `ExitLeg.label`), legs must have fraction > 0, and F8 moves the stop at bar close. | Auxiliary take-profit leg "BE_2R", fraction 0.01, at exactly +2R from the declared entry; `move_to_breakeven_on="BE_2R"`, offset 0. BE arrives at the triggering bar's close (F8) — later than the live rule, pessimistic. | (a) `move_to_breakeven_on=None` (drops a documented risk rule — fewer protected trades, and untestable as documented); (b) BE triggered by the real TP leg (wrong level — TP is 0.5×ATR_w, not 2R); (c) a zero-fraction leg — contract-invalid. |
| 4 | CSV and source specify no pending-order expiry. | `expires_after_bars = 29` decision-frame (H4) bars from the Sunday-candle decision bar, so the order dies at the Friday 21:00 UTC close of the entry week (arithmetic in §4.6). The setup references *this* week's Sunday candle; a breakout in a later week is a different signal. | (a) GTC / `expires_after_bars=None` — a stale order can fill weeks later on a meaningless level (more, worse trades); (b) the 5-bar default — truncates the documented week-long setup horizon (unfaithful, arbitrarily fewer trades). |
| 5 | CSV says "single trade per week per pair"; the source FAQ says "once long and once short… never more than twice per week" and discusses taking a second trade after a stop-out. Direct conflict. | CSV (the assigned primary source): at most **one** entry per pair per trading week is the intent — enforced only as far as contract v2 allows (single weekly emission + F12 concurrency cap); the residual enforcement gap is recorded in §10.8. | The source FAQ's two-trade version — more trades, and the FAQ's second-trade conditions ("not after Wednesday", "not if the first trade exceeded 40% of ATR before stopping") require intra-week state that a declarative v2 strategy cannot express without invention. |
| 6 | Source FAQ: "I would close the trade on Friday if it hadn't hit my profit target." CSV omits any Friday close-out. | No time exit. Open positions carry across weekends; gap-through-stop losses are realized honestly via F6 (and F11 at data end). The contract's `ExitLeg(kind="time", bars=N)` counts bars from an unknowable fill time, so a fixed calendar exit (Friday 21:00) is not expressible exactly. | Encoding `bars=116` H1 as an approximation — correct only for Monday fills; a Thursday fill would exit the following week (wrong trades in both directions of error). Faithful calendar exits would need a contract extension; flagged, not invented. |
| 7 | Source: "slightly different set of rules for EUR/JPY… to lower the correlation", linked but not reproduced in the CSV row. | Apply the identical mechanical rules to both pairs. The CSV row — the assigned authority — specifies one rule set; the EUR/JPY variant is not documented anywhere in the provided materials. | Inventing EUR/JPY modifications (e.g., different pip offset or TP fraction) — prohibited fabrication. Recorded so reviewers know the source's live EUR/JPY results are not exactly what is being tested. |
| 8 | CSV forbids a second same-week trade, but contract v2 has no OCO, no cancel-on-fill, and no supersede; F12 caps concurrent positions only and does not gate pending fills (§3.2 step 5). After a mid-week stop-out, the surviving sibling stop-order remains live and CAN fill within its 29-bar expiry — a second sequential same-week trade. | Keep the faithful 29-bar weekly expiry and record the residual risk. The only expiry that makes a second same-week fill impossible is 1 H4 bar (fill on bar 1, stop on bar 2, sibling already expired) — chosen against, because it would discard the author's documented week-long setup horizon and test a strategy that is not this one; recording the deviation is the more conservative *expressible and faithful* reading. **Direction of the deviation: MORE trades than the author intended** (up to 2 per pair per week, sequential — never concurrent, per F12), biased toward whipsaw weeks where a stop-out precedes an opposite break; expected effect is anti-conservative on trade count and likely pessimistic on r-multiples (second entries after a stop-out are continuation-fade prone). Must be flagged in the report; if the deviation proves material, a contract extension (cancel-on-fill / OCO group id) is the correct fix, not a strategy-level hack. | Shortening `expires_after_bars` to 1 (or any small) bar — eliminates the second fill but amputates the weekly setup horizon (most documented entries occur Tuesday–Friday), i.e. fewer trades by censorship of the signal rather than by the strategy's own rules; rejected as less faithful and *less* conservative in what it measures. |

## 11. Expected behaviour

- **Trade frequency:** intended 1 entry per pair per week; realized up to 2 per pair per week (sequential, never concurrent — §10.8 residual second-fill risk, flagged for the report). Many weeks produce no fill (price must travel 10 pips beyond the Sunday range), so expect roughly 15–35 filled trades per pair per year under the intended rule — i.e. ~50%±20% weekly fill rate — with a realized hard cap of ~104 if every stopped-out week produced a sibling fill (implausible; treat ~52 as the practical ceiling). Per 6-month OOS fold that is ≤26 trades per cell, plausibly single digits: expect `low_confidence` flags and possible failure of OOS-duration gates. This is arithmetic, not a bug (Contract §7 statistical warning applies in spirit even though decisions are H4).
- **What would make it fail the gates:** (1) Regime dependence — the author himself announced on 2010-07-30 that the method "is NOT working in the current market conditions"; low-volatility or mean-reverting regimes turn opening-range breaks into fades, and the system "depends on the few big winners to offset the large number of small losers" (author's words), so any regime that truncates the right tail is fatal. (2) Post-2010 market structure: thinner Sunday liquidity, narrower weekend gaps, and faster opening-week resolution may have eroded the edge. (3) Small per-fold trade counts (above). (4) The 10-pip buffer and 0.5×ATR_w target are 2008-era GBP/USD calibrations; EUR/JPY Sunday ranges and volatility differ structurally (Tokyo open dominates), and the source's own EUR/JPY variant is undocumented (§10.7). (5) Pessimistic conventions F5/F8 will shave exactly the marginal winners the system lives on.
- **Is HIGHLY_RECOMMENDED justified?** Only partially. In its favour: fully mechanical, ~30% live return in 2009, manual backtest to Oct 2004, a structural (non-fitted) rationale, and a small parameter set that resists overfitting. Against: the author's own regime-failure admission, a track record confined to 2004–2010 and primarily one pair, manual (unaudited) backtesting, and the unresolved EUR/JPY variant. Treat the conviction as *promising hypothesis requiring modern out-of-sample re-validation across volatility regimes* — precisely what the walk-forward harness is for — not as evidence of current edge.
