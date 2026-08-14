# SPEC-daily_fib_retracement

**Source:** row 16 of forex_swing_strategies.csv · https://www.forexfactory.com/thread/530477-gps-simple-daily-fibonacci-based-system
**Conviction (author's):** MODERATE

## 1. Hypothesis

In an established daily trend, the prior day's full range is a self-anchoring liquidity map: price very often retraces into the 50–61.8% band of that range during the next session (yesterday's breakout participants take profit, late entrants get squeezed, and resting limit orders cluster at round retracement levels), so a patient limit order in that band buys a pullback at a structurally favourable price with a tightly defined invalidation (75% retrace), letting the trend leg that follows pay for a high stop-out rate. The claimed persistence is behavioural — mean-reverting intraday flow within trending weeks — not informational.

## 2. Scope

- **primary_granularity:** D1 (decisions at each fully-closed D1 bar)
- **context_granularities:** none (the trend filter is computed on the D1 frame itself)
- **simulate_on:** H1 (fills/stops/legs resolved on H1 bars per contract §5)
- **pairs_requested (verbatim):** "FX majors and minors; exclude any pair with NFP or interest-rate announcements due within 24h"
- **pairs_available:** EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD (live); GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD (Wave-1 additions — **pending**, not gaps; harness skips pairs with insufficient history)
- **pairs_missing:** none. (USD/CHF- and cross-only minors are covered by the Wave-1 list.)
- **DATA-GAP:** the 24h NFP / interest-rate news filter requires an economic calendar, which does not exist in the DB → see `DATA-GAP-daily_fib_retracement.md`. The strategy is specified WITHOUT the filter (§8, §10 #5).

## 3. Indicators

| Indicator | Params | Source |
|---|---|---|
| EMA of D1 Close | period = 50 | `indicators.ema(close, 50)` on the D1 frame |
| ATR of D1 bars | period = 14 | `indicators.atr(high, low, close, 14)` on the D1 frame — used only as the trailing-leg distance unit, value frozen at decision bar |
| Prior fully-closed D1 bar High/Low/Close | shift = 1 relative to the *next* bar; i.e. the decision bar's own OHLC | Built-in frame indexing. **Not** a swing indicator: the CSV's "swing high/low" is defined by the author as the previous day's high/low, so no `causal_structure` function is needed and `detect_swing_points` is not used |
| Fibonacci retracement levels of prior day's range | levels 0.236 / 0.382 / 0.50 / 0.618 / 0.75 | Private derivation, fully specified here. Long anchor: `hi = High[k]`, `lo = Low[k]`, `rng = hi − lo`; `fibX = hi − X·rng`. Short anchor mirrors: `fibX_s = lo + X·rng`. No external indicator exists; arithmetic is exact and causal (uses only bar k's OHLC, known at bar k's close) |

## 4. Entry — long

Decision bar = D1 bar `k`, evaluated at its close (21:00 UTC per the feed's D1 boundary; see §9). All conditions use only bar k and earlier.

1. `rng[k] = High[k] − Low[k] > 0` (non-degenerate day).
2. **Trend:** `Close[k] > EMA50(Close)[k]` (uptrend, per the CSV pseudocode).
3. **Zone precondition (conservative, from the CSV pseudocode):** `Low[k] <= hi − 0.50·rng[k]` **and** `Low[k] >= hi − 0.618·rng[k]` — i.e. bar k has already dipped into the 50–61.8% retracement band but has not traded through the 61.8% level. (Author's "never chase, wait for the zone" rule, mechanised.)
4. **News gate:** NOT IMPLEMENTED — no calendar data exists. See §8 and the DATA-GAP document.

- **Entry type:** `buy_limit`
- **Entry level:** `entry_price = High[k] − 0.618·rng[k]` (the 61.8% retracement — the *deep* edge of the zone; conservative: fewer fills, later entries than the 50% edge; rejected alternatives in §10 #2)
- **expires_after_bars:** **24 H1 resolution bars** (one trading day, honouring "typically one trade per day"). Declared integer, no implementer choice. Overlap arithmetic: intents are emitted at most once per 24 H1 bars (one per D1 close) and each lives at most 24 H1 bars from the bar after decision; intent *n* is eligible on H1 bars m+1…m+24 and intent *n+1* is admitted at m+25, so at most one pending order per pair exists at any time. A Friday-close intent lives through the weekend gap into Monday and expires at Monday 21:00 UTC.
- **size_fraction:** 1.0

## 5. Entry — short

Exact mirror (the author specifies the sell side explicitly):

1. `rng[k] > 0`.
2. **Trend:** `Close[k] < EMA50(Close)[k]`.
3. **Zone precondition:** `High[k] >= Low[k] + 0.50·rng[k]` **and** `High[k] <= Low[k] + 0.618·rng[k]` — bar k has already rallied into the 50–61.8% band of its own range without exceeding the 61.8% level.
4. News gate: not implemented (as §4).

- **Entry type:** `sell_limit`
- **Entry level:** `entry_price = Low[k] + 0.618·rng[k]` (the deep edge of the retracement band, mirror of the long rule)
- **expires_after_bars:** **24 H1 resolution bars**; same no-overlap arithmetic.
- **size_fraction:** 1.0

## 6. Stop

- **Initial stop (long):** `StopRule.price = High[k] − 0.75·rng[k]` (the author's "fixed stop-loss at the 75% retracement level"). Fully knowable at the decision bar — decision-bar anchored, not fill anchored. Initial risk = 0.132·rng[k] ≈ 13% of the prior day's range (very tight; see §11).
- **Initial stop (short):** `StopRule.price = Low[k] + 0.75·rng[k]`.
- **move_to_breakeven_on:** `"TP_382"` (the ExitLeg label from §7), `breakeven_offset_pips = 0.0`. Per F8 the move happens at the **close** of the H1 bar that fills TP_382 — late and conservative.
- **trail:** the StopRule itself does NOT trail (`trail_atr_multiple = None`). The managed-exit intent lives on the trailing ExitLeg (§7). The author's four-stage, profit-proportional trailing schedule is **inexpressible declaratively** (it is path/P&L-triggered) and is approximated as documented in §10 #4.

## 7. Exit legs

| Label | Fraction | Kind | Level formula |
|---|---|---:|---|
| TP_382 | 0.5 | take_profit | Long: `High[k] − 0.382·rng[k]` · Short: `Low[k] + 0.382·rng[k]` — the 38.2% retracement level, the author's first trail trigger, converted to a hard target for half the position |
| TRAIL | 0.5 | trailing | `atr_multiple = 1.5` on D1 ATR(14), ATR value computed at decision bar k and updated per F9 (bar-close updates using completed ATR); approximates the author's progressive 50%-then-30%-of-gain trail for the runner half |

Fractions: 0.5 + 0.5 = 1.0. ✓

Note (contract §2.2 validation): TP_382 lies beyond `entry_price` in the trade direction (0.236·rng past entry), and `stop.price` lies beyond entry on the adverse side (0.132·rng), so the intent is well-formed at decision-bar prices.

## 8. Filters

| Filter | Timeframe | Knowable when |
|---|---|---|
| Trend: Close vs EMA50 (long above / short below) | D1 | At the close of decision bar k (EMA uses closes ≤ k) |
| Zone precondition (bar k already touched the 50–61.8% band, not through 61.8%) | D1 | At the close of decision bar k (uses bar k's own High/Low) |
| **News: exclude pair if NFP or interest-rate announcement due within 24h** | n/a — external calendar | **NOT KNOWABLE — no calendar data exists in the DB.** Omitted from the implementation; see `DATA-GAP-daily_fib_retracement.md`. The backtest therefore trades a **superset** of the author's setups, including event days he would skip. The F10 cost model's flat 1.0-pip spread also does not widen around events, so event-day fills are modelled *optimistically* on cost — both distortions are flagged here and in §10 #5. No silent proxy (e.g. a static NFP/FOMC schedule) is baked in; that option is analysed, and rejected for Wave 2, in the DATA-GAP document |
| Volatility: none beyond `rng[k] > 0` | D1 | Decision bar close |
| Session: implicit — one decision per day at the D1 boundary; orders expire within one trading day, so no position can be opened older than one day after its plan | D1/H1 | Structural |

## 9. Causality audit

| Rule | Inputs fully known at |
|---|---|
| Prior-day High/Low/Close and range | Close of D1 bar k — bar k is fully closed before any quantity is computed. No intraday data is ever read |
| EMA50 trend condition | Close of D1 bar k (EMA over closes of bars ≤ k) |
| ATR(14) for the trailing leg | Close of D1 bar k; thereafter updated only at H1 bar closes with completed-bar ATR per F9 |
| Fibonacci levels (0.236/0.382/0.50/0.618/0.75 of rng[k]) | Close of D1 bar k — pure arithmetic on bar k's OHLC |
| Zone precondition | Close of D1 bar k |
| "Swing high/low" language | The author's swing is *defined* as the previous day's high/low — the completed D1 bar itself is the confirmation, so **confirmation lag = 1 D1 bar, already absorbed**: levels are computed at bar k's close and acted on from bar k+1 (F1). No `detect_swing_points`-style centred window exists anywhere in this spec |
| Entry fill | H1 bars strictly after the decision bar (F1, F3); limit fills at L exactly |
| TP_382 / breakeven | TP fills at its level on later H1 bars; stop moves to breakeven at the **close** of the filling bar (F8) |
| Trailing leg | Trailing stop updates only at H1 bar closes (F9), never intrabar, never widening |
| D1 boundary vs NY close | The feed's D1 bars open and close at a fixed 21:00 UTC. NY close is 17:00 ET, which is 21:00 UTC during EDT (summer) and 22:00 UTC during EST (winter). **The feed boundary therefore coincides with NY close in summer and runs one hour early in winter.** The one-hour winter offset shifts which ticks land in which daily bar; it is a definitional difference, not look-ahead — all levels remain computed from fully-closed bars only. Accepted, recorded in §10 #6 |
| Multi-timeframe causality | Not applicable beyond the above: there is exactly one decision frame (D1) and one resolution frame (H1). No context bar ever informs a decision before its close |

## 10. Ambiguities resolved

| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | Fib anchor: "previous day high/low after NY close **or current day high/low before NY close**" | Previous **fully-closed** D1 bar k's High/Low, computed at bar k's close — the only reading knowable on D1 decision bars without intraday data | "Current day high/low before NY close" — requires reading a partial, unclosed day's extremes; ambiguous in a D1-stamped feed and produces *earlier* (less conservative) plans |
| 2 | Exact limit price "between the 50% and 61.8% levels" | The **61.8% level** — the deep edge: strictly fewer fills, later entries, deeper (worse) prices required | (a) 50% level — fills on shallow dips, far more trades; (b) midpoint (55.9%) — an invented compromise with no textual basis |
| 3 | Is the order placed every trend day, or only when price is already in the zone? | Zone precondition **required** (bar k's Low/High already inside the band, not through 61.8%), per the CSV's own pseudocode — strictly fewer setups | Prose-only reading ("place pending limit… typically one trade per day") with no zone precondition — an order every trend day, materially more trades |
| 4 | The signature 4-stage trailing stop (trail ½ of entry→38.2% pips, then ½ of 38.2%→23.6%, then ½ of 23.6%→0%, then 30% of gain beyond 0%) | **0.5 take_profit at the 38.2% level + breakeven move (at bar close, F8) + 0.5 ATR(1.5)×D1-ATR trailing leg.** Fidelity loss, stated plainly: the backtest will NOT measure (a) trailing on the whole position from the first trigger, (b) the progressive ratchet tightening at 23.6% and 0%, (c) the 30%-of-gain terminal trail — the author's profit-locking schedule is path/P&L-triggered and inexpressible in StopRule/ExitLeg. Breakeven after TP1 is strictly worse than the author's first trail stage (which stops above entry), and the ATR trail is a coarse proxy for "30% of gain". This is the strategy's claimed edge mechanism, so the result understates (or at best mis-measures) the documented system | (a) Faithful 4-stage path-triggered trail — **inexpressible** in contract v2, not merely less conservative; (b) pure TP ladder at 38.2%/23.6%/0% (0.334/0.333/0.333) — declarable but discards all trailing and all trend-capture beyond the old high, a larger distortion of intent; (c) whole-position ATR trail from entry — ignores the staged structure entirely |
| 5 | News filter has no data source | **Omit the filter** and say so everywhere (§8, DATA-GAP). Direction: the backtest includes event-day trades the author would skip (a risk overlay removed → more trades, event-noise included); simultaneously the flat 1.0-pip cost model understates event-day execution cost (mildly optimistic). Net direction is genuinely uncertain — that is precisely why it is disclosed rather than silently proxied | (a) Static hand-coded NFP/FOMC schedule as an undeclared proxy — rejected as a *silent* proxy (it is analysed as a possible future integration in the DATA-GAP document, not baked in); (b) dropping the strategy — rejected: the filter is a risk overlay, not the claimed edge |
| 6 | "NY close" vs the feed's 21:00 UTC D1 boundary | Use the feed's D1 bars as-is (§9). The boundary matches NY close in EDT months and leads it by one hour in EST months; a definitional, non-causal discrepancy affecting which ticks form "the day" | Reshifting D1 bars to 17:00 ET exactly — impossible without touching shared ingestion, and unjustifiable for a 1-hour boundary effect on a daily-range level |
| 7 | Pending-order lifetime ("typically one trade per day") | `expires_after_bars = 24` H1 bars — one trading day, then cancel (arithmetic in §4 shows no two pendings can coexist) | GTC / multi-day expiry — a stale plan filling days later contradicts the author's daily-plan discipline and allows pending-order pile-up |
| 8 | Residual multi-fill risk | **Recorded, not eliminated:** a filled position can still be open (TRAIL leg running for days) when the next day's limit fills, because contract v2 has no OCO/cancel-on-fill and F12 gates position admission, not pending fills. Direction: same-direction pyramiding — up to ~2 concurrent same-direction positions per pair, each booked as an independent trade with its own r-multiple; this *adds* trades/exposure relative to the author's one-trade-at-a-time discipline and must be stated in the Wave-2 report | Writing "the first fill cancels the other order" or "a new signal supersedes the position" — those mechanisms do not exist in contract v2 |

## 11. Expected behaviour

- **Trade frequency:** at most one entry per pair per day by construction; realistically far fewer — the zone precondition (price must already sit in the 50–61.8% band at the daily close, in an EMA50 trend) fires perhaps 1–4 times per pair per month. Across 5 live pairs expect roughly **10–40 trades/year**, so per-cell trade counts will be thin and `low_confidence` flags are likely.
- **What would make it fail the gates:** (1) the **extremely tight structural stop** — entry at 61.8% with the stop at 75% risks only 0.132·rng (≈10–13 pips on a typical 80–100-pip EUR_USD day), so the fixed 1.5-pip entry cost consumes ~12–14% of 1R on every trade and F5's stop-before-target rule will stop out a large fraction of positions on noise; (2) thin per-cell counts vs the OOS gates; (3) the fidelity loss on the trailing schedule (§10 #4) — the documented profit-locking edge is only half-measured; (4) unfiltered event days adding variance without the author's risk overlay.
- **Is the author's MODERATE conviction justified by the rules as written?** Yes, and if anything it is calibrated low-key honestly: the author explicitly declined to claim >50% win rate, and the system as mechanised is a low-win-rate, small-R-risk, trend-continuation structure whose profitability depends almost entirely on the (only partially expressible) trailing schedule. MODERATE — "logical edge, backtest required" — is the right label; the gates should be the judge, with the trailing-fidelity caveat attached to any verdict.
