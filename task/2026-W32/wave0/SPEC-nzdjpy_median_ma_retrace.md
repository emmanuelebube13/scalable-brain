# SPEC-nzdjpy_median_ma_retrace
**Source:** row 37 of forex_swing_strategies.csv · https://www.trade2win.com/threads/trading-strategy-advice.241661/
**Conviction (author's):** MODERATE

## 1. Hypothesis

Counter-trend-within-strength edge: when the fast median-price average dips below the slow median-price average (a short-term retrace) during the London morning window, price is statistically more likely to resume the prevailing direction than to keep falling, because London session open flow concentrates institutional continuation orders at round hours and the (H+L)/2 median filters out wick noise that fakes genuine weakness. The claimed persistence is behavioural — session-timed liquidity and round-hour order clustering — not a pure curve pattern; however the source's own evidence (backtest 2013–2020 plus a 2020-onward forward test) exists only as chart images in the thread and is not machine-verifiable, and the below-1:1 reward:risk means the edge must rest on a high win rate that the rules alone do not guarantee.

## 2. Scope

- **primary_granularity:** H1 (source `timeframes`: "H1")
- **context_granularities:** none — all logic, including the session filter, is evaluated on the H1 decision frame itself
- **simulate_on:** H1 (decision frame is H1; fills resolve natively on H1 — the Part-D native-vs-H1 dual run is trivially identical for this strategy)
- **pairs_requested (verbatim):** `NZD/JPY`
- **pairs_available:** **NONE.** NZD_JPY is not one of the 5 live pairs (EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD) and is **not** among the 8 Wave-1 additions (GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD). This is a genuine gap, not a Wave-1 pending item.
- **pairs_missing:** NZD_JPY → **DATA-GAP-nzdjpy_median_ma_retrace.md**. Do **not** substitute a proxy pair: NZD_USD and GBP_JPY share a leg with NZD_JPY but have different rate differentials, session behaviour, and volatility character; a proxy backtest would measure a different strategy (§10 #7).

## 3. Indicators

All computed on the H1 frame from `High`/`Low`; all values at decision bar *t* use bars ≤ *t* only (trailing, causal).

| Indicator | Params | Source |
|---|---|---|
| Median price series | `med[t] = (High[t] + Low[t]) / 2` per bar | Private derived series, fully specified here (source: `data_requirements` "MA(5) and MA(50) computed on median price (H+L)/2"; pseudocode `med=(df['high']+df['low'])/2`). Not added to the shared inventory. |
| Fast MA | SMA, period 5, on `med` | inventory `sma(med, 5)` |
| Slow MA | SMA, period 50, on `med` | inventory `sma(med, 50)` |
| Session clock | bar timestamp hour ∈ {7,…,13} UTC, minute == 0 | Derived from the bar index (deterministic); see §8 |

Warm-up: no signal is valid before bar 50 of the series (SMA50 on median defined). No ATR, no swing/pivot/ZigZag/fractal, no other indicator is used.

## 4. Entry — long

Decision made at the close of H1 bar *t*. All conditions evaluated on closed bars ≤ *t*.

1. **Fresh downward cross (documented signal — see §10 #1):** `MA5[t] < MA50[t]` AND `MA5[t-1] >= MA50[t-1]` — the fast median MA crosses the slow median MA **from above to below** on bar *t*. Both MAs are functions of bars ≤ *t*, so the cross is knowable at the close of bar *t*. This is the source's "buy-the-retrace in prevailing strength": a downward cross triggers a BUY. Implemented exactly as documented in both the prose (`entry_logic_long`) and the author's pseudocode (`buy=(ma5<ma50)&(ma5.shift()>=ma50.shift())`); NOT "corrected" to a trend-following reading.
2. **Round-hour session filter:** decision bar *t*'s open-stamped timestamp (UTC) has `hour ∈ {7, 8, 9, 10, 11, 12, 13}` and `minute == 0` — i.e. the bar opens on a round hour in the fixed UTC window 07:00–13:00 inclusive, standing in for "07:00–13:00 London" (§10 #2). On H1 data every bar opens at minute 0, so the minute condition is a no-op guard; the operative condition is the hour set.
3. Conditions 1 and 2 must hold on the **same** decision bar *t* (per the author's pseudocode, which conjoins `ok_hour` with the cross on the same row — §10 #3).

- **Entry type:** `market` (source: "at the open of a new H1 bar" — identical to F1/F2 market semantics: OrderIntent emitted at close of *t*, fill at open of bar *t+1* plus adverse slippage per F10).
- **Entry level:** none declared (`entry_price = None`); fill is the open of H1 bar *t+1*.
- **expires_after_bars:** `null` (market orders are not pending; no lifetime applies).

## 5. Entry — short

Mirror of §4, per `entry_logic_short` ("Enter SELL when MA5 crosses MA50 from below within the same round-hour filter window") and pseudocode `sell=(ma5>ma50)&(ma5.shift()<=ma50.shift())`:

1. **Fresh upward cross:** `MA5[t] > MA50[t]` AND `MA5[t-1] <= MA50[t-1]` — fast median MA crosses **from below to above**; this triggers a SELL (sell-the-rally, mirror of the retrace-buy).
2. **Round-hour session filter:** identical to §4.2 (decision bar opens at hour ∈ {7,…,13} UTC, minute == 0).
3. Same-bar conjunction, as in §4.

- Entry type `market`, `entry_price = None`, fill at open of bar *t+1*.
- **expires_after_bars:** `null`.

**Order-lifecycle note (fleet rule 7):** entries are market orders only — there are no pending orders, hence no OCO/cancel-on-fill/multi-fill risk exists. With F12 `max_concurrent_positions = 1` (default, kept), a signal emitted while a position is open produces an OrderIntent whose single eligible bar (t+1) is blocked by the open position; the intent lapses — there is no queue, no supersede, and no "opposite signal closes the position" mechanism, and none is assumed. Signals during open trades are therefore silently skipped, which strictly reduces trade count (conservative). Given the bracket size (0.4%/0.5%), most trades resolve within hours, so this skip rate is low but nonzero; it is recorded, not modelled away.

## 6. Stop

- **Initial stop (long):** `StopRule.price = Close[t] × (1 − 0.005)` — 0.5% below the **decision-bar close** (fleet rule 8 anchor; source says "SL 0.5% from entry price", the fill-anchored reading is inexpressible and rejected — §10 #4).
- **Initial stop (short):** `StopRule.price = Close[t] × (1 + 0.005)`.
- **move_to_breakeven_on:** `none` (source has no breakeven rule).
- **trail:** `none` (`trail_atr_multiple = None`; static stop for the life of the trade).

Gap note (F6): a bar opening beyond the stop fills at the open, so realised loss can exceed the declared 0.5%; declared geometry uses the decision-close anchor, realised R uses the fill — the two diverge whenever the fill gaps away from `Close[t]`.

## 7. Exit legs

Single leg; fractions sum to 1.0.

| Label | Fraction | Kind | Level formula |
|---|--:|---|---|
| TP | 1.0 | take_profit | long: `Close[t] × (1 + 0.004)`; short: `Close[t] × (1 − 0.004)` — 0.4% from the decision-bar close (§10 #4) |

No trailing, no time exit. If bar *t+1* opens beyond the TP level (gap in the trade's favour), the engine resolves the leg per F7 at the first bar whose range covers the level; if it opens beyond the stop, F6 fills the stop at the open. Declared reward:risk is 0.4:0.5 = 0.8R per win vs −1R per loss **before costs**.

## 8. Filters

| Filter | Timeframe | Rule | Knowable at |
|---|---|---|---|
| Session (round-hour) | H1 | Decision bar's open-stamped UTC timestamp: `hour ∈ {7,8,9,10,11,12,13}` AND `minute == 0` | The timestamp is deterministic — knowable at (indeed before) the decision bar's open; zero causality risk |
| Trend / volatility / news | — | none in source; none added | — |

**Spread/cost caveat (flagged per no-invented-data rule 5):** the engine's fixed cost model (F10: spread 1.0 pip, slippage 0.5 pip entry-only) is the only spread series that exists — there is no per-pair spread data. Real NZD/JPY retail spreads are typically 1.5–3 pips (it is a thin JPY cross), so the mandated 1.0-pip cost model **understates** this strategy's costs against a ~35-pip target. This is a mandated constant (do not change; F10), not a strategy-level choice, but it biases results optimistically for this pair specifically and must be stated in every report. Also flagged in §10 #6 and the DATA-GAP.

**Weekend note:** the market is closed Friday 21:00 → Sunday 21:00 UTC; H1 bars simply do not exist in the gap, so the hour filter cannot fire there. Friday 07:00–13:00 UTC signals are valid.

## 9. Causality audit

| Rule | Inputs | Fully known at |
|---|---|---|
| Median price `med` (§3) | High/Low of bar *t* | Close of bar *t* (trailing; no future data) |
| MA5 / MA50 on median (§3) | `med` of bars ≤ *t* | Close of bar *t*; undefined for first 49 bars → warm-up blocks all signals before bar 50 |
| Down-cross → BUY (§4.1) | MA5/MA50 at *t* and *t−1* | Close of bar *t* — the cross is confirmed by the close that produces it; no additional lag |
| Up-cross → SELL (§5.1) | MA5/MA50 at *t* and *t−1* | Close of bar *t* |
| Round-hour filter (§4.2, §5.2) | Bar *t* timestamp | Deterministic; knowable in advance |
| Stop/TP geometry (§6, §7) | `Close[t]` | Close of bar *t*; both are absolute prices declarable at OrderIntent creation (fleet rule 8) — the unknowable fill price is never referenced |
| Market entry (§4/§5) | — | Emitted at close of *t*, eligible for fill from open of bar *t+1* only (F1/F2) — never on bar *t* |

**Swing/pivot/ZigZag/fractal rules: NONE.** This strategy references no swing points, pivots, ZigZag, or fractals; `detect_swing_points` is not used and no confirmation lag applies to any rule. Every input is a trailing-window function of closed H1 bars plus a deterministic timestamp. **Multi-timeframe: NONE** — there are no context granularities, so the MTF causality rule (contract §4) is trivially satisfied; all inputs live on the H1 decision frame itself. Decision-bar anchoring: every declared price in §6/§7 derives from `Close[t]`, knowable at the close of the decision bar.

## 10. Ambiguities resolved

| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | **Signal direction is counterintuitive:** "BUY when MA5 crosses MA50 from above" — a *downward* cross triggering a BUY reads like a trend-follower's error, but the prose gloss "(buy-the-retrace in prevailing strength)" and the author's own pseudocode (`buy=(ma5<ma50)&(ma5.shift()>=ma50.shift())`) both confirm the retrace reading | Implemented **exactly as documented**: fresh cross-DOWN → BUY, fresh cross-UP → SELL. Judged intentional retrace logic (prose + code agree), not a source typo | "Fixing" it to the trend-following reading (cross-down → SELL) — a silent reinterpretation that would test a strategy the author never described; any such variant is a different strategy and out of scope |
| 2 | "07:00–13:00 London time" — the DB is UTC; London is UTC+0 (GMT, winter) or UTC+1 (BST, summer). Which clock? | **Fixed UTC hours 07:00–13:00 inclusive, all year** (`hour ∈ {7,…,13}`, `minute == 0`), per the author's pseudocode which applies `df.index.hour.isin(range(7,14))` directly to (UTC) data with no DST adjustment. Deterministic, reproducible, matches the code | BST-adjusted window (UTC 06:00–12:00 during British summer) — shifts ~7 months/year of signals by one hour, adds a DST calendar dependency the source never specifies, and cannot be validated against the author's unverifiable chart images |
| 3 | Does the hour filter apply to the **decision bar** (cross bar) or the **entry bar** (open of the next bar)? The prose ("at the open of a new H1 bar on a round hour between 07:00 and 13:00") suggests the entry bar; the pseudocode conjoins `ok_hour` with the cross on the same row, i.e. the decision bar | **Decision bar**, per the pseudocode: cross and hour filter on the same bar *t*, entry at open of *t+1* (so fills occur at 08:00–14:00 UTC opens). The author's code is the only machine-checkable statement; deviating from it is the larger fidelity risk | Entry-bar reading (cross confirmed on bars opening 06:00–12:00, fill at 07:00–13:00 opens) — contradicts the author's code and merely shifts the admitted hour set by one; neither reading is provably fewer trades, so the tie is broken toward the code |
| 4 | "TP 0.4% and SL 0.5% **from entry price**" — measured from the fill or from a decision-time price? | Anchored to the **decision-bar close**: stop `Close[t] ∓ 0.5%`, TP `Close[t] ± 0.4%`, both absolute and declarable at OrderIntent creation (fleet rule 8). Realised R ≠ declared R whenever the fill gaps away from `Close[t]`; F2/F6 resolve the fill honestly | Fill-anchored bracket (source-literal) — **inexpressible**, not merely less conservative: the fill price is unknowable at emission for a market order |
| 5 | "MA(5) and MA(50)" — MA type unspecified in prose | **SMA**, per the author's pseudocode (`rolling(5).mean()`, `rolling(50).mean()`), via inventory `sma` | EMA or any other MA type — would diverge from the author's code without evidence |
| 6 | Cross strictness: pseudocode uses `ma5 < ma50` with `ma5.shift() >= ma50.shift()` — the prior-bar condition admits exact equality | Kept **exactly as coded** (`>=` / `<=` on the prior bar). Exact float equality of two rolling means is measure-zero in practice, so the conservative-vs-literal distinction has no practical effect; deviating from the author's comparison operators is the bigger risk | Strict `>` / `<` on the prior bar — marginally fewer signals (the conservative direction on paper) but a silent edit of the author's code for a case that essentially never occurs |
| 7 | Only pair is NZD/JPY, which is unavailable — substitute a related pair? | **No substitution.** NZD_JPY goes to DATA-GAP; the strategy is backtested only if NZD_JPY is ingested, otherwise not at all | Proxying with NZD_USD (Wave-1 pending) or GBP_JPY — different rate differential, session behaviour, and pip scale; a proxy result would be attributed to a strategy it does not measure |
| 8 | Signal while a position is open (F12, max 1 concurrent) | The OrderIntent is emitted but cannot be admitted on its single eligible bar; it **lapses** (market orders have no pending lifetime). Trade count is strictly reduced | Queuing the intent, pyramiding (raising F12), or treating an opposite cross as a close-and-reverse — none of these mechanisms exist in contract v2 (fleet rule 7) |
| 9 | Source's evidence is backtest 2013–2020 + 2020-forward "as chart images"; RR is below 1:1 | Conviction kept at author's MODERATE but treated as **unverified** in §11; no parameter changes are made to chase the claimed results | Upgrading confidence or tuning (0.4%/0.5%, 5/50, hour window) to match the images — the images are not machine-verifiable and tuning is forbidden (contract §10) |

## 11. Expected behaviour

- **Trade frequency:** SMA(5)/SMA(50) crosses on H1 median price occur roughly 2–8 times per month on a JPY cross; the 7-of-24-hour filter retains perhaps a third of them (crosses cluster in active hours, so London morning likely captures more than the naive 29%). Expect **~1–4 trades/month**, i.e. a few hundred trades over the 2006–2026 H1 history — an adequate sample size *if* NZD_JPY data is ingested, on exactly one pair (per-cell verdict only; the pooled verdict equals the single cell).
- **Breakeven arithmetic (the whole strategy rests here):** declared win = +0.4% ≈ +0.8R, declared loss = −0.5% = −1R. Gross breakeven win rate = 0.5 / (0.4 + 0.5) = **55.6%**. On NZD/JPY (~88.00 nominal), 0.4% ≈ 35 pips and 0.5% ≈ 44 pips; the mandated entry cost (1.0 pip spread + 0.5 pip slippage ≈ 0.017% of price) lifts the net breakeven win rate to roughly **57–58%** — and F5 (stop deemed hit before target on any bar touching both) pushes the *realised* win rate below the theoretical one further still. The strategy only works if short-horizon retrace continuation in the London morning window is reliable enough to sustain ~58%+ winners on H1 noise, which is a high bar that the rules as written do not evidence.
- **What would make it fail the gates:** realised win rate below ~57% net (the most likely failure); a cluster of gapped stops (F6, common around JPY event risk and Sunday opens — though Sunday opens are outside the filter window, Friday-window entries can carry weekend exposure); OOS inconsistency across walk-forward folds given the thin single-pair sample; and the understated NZD/JPY spread in the fixed cost model (§8), which flatters results that already have no room for error at 0.8R.
- **Is the author's conviction justified by the rules as written?** MODERATE is generous. The mechanism story (session-timed continuation flow at round hours, median-price noise filtering) is plausible and fully mechanical, but the edge is curve-fit to a single thin cross, rests entirely on an unverified high win rate, uses negative reward:risk, and its only supporting evidence is unverifiable chart images. The rules as written define a clean, testable, causally safe strategy — they do not, by themselves, establish that it has edge. The backtest's job is precisely to measure whether ~58% is attainable.
