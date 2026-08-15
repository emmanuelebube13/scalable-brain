# SPEC-ema_cross_h4_filter_bot

**Source:** row 41 of forex_swing_strategies.csv · https://github.com/igormoondev/forex-meta-trader-trading-bot
**Conviction (author's):** MODERATE

## 1. Hypothesis

Fast/slow EMA crosses on H1 capture the early phase of short-horizon momentum bursts, and requiring price to be on the correct side of the H4 EMA200 suppresses the counter-trend whipsaws that destroy naked crossover systems. The claimed persistence mechanism is behavioural: medium-horizon trend-following profits from the under-reaction and herding of market participants around established H4 regimes, so H1 crosses aligned with the dominant regime should have positive expectancy at a 1:2 reward-to-risk bracket, while crosses against the regime are mostly noise and are skipped.

## 2. Scope

- **primary_granularity:** H1 (the entry timeframe; CSV: "H1 entry | H4 trend filter (M15-D1 selectable)" — H1 taken as the named default; see §10 #6)
- **context_granularities:** H4 (EMA200 regime filter only)
- **simulate_on:** H1
- **pairs_requested (verbatim):** EUR/USD | GBP/USD | USD/JPY | USD/CHF | USD/CAD | AUD/USD | NZD/USD | EUR/GBP | EUR/JPY | GBP/JPY
- **pairs_available:** EUR_USD, GBP_USD, USD_JPY, USD_CAD, AUD_USD (live); USD_CHF, NZD_USD, EUR_GBP, EUR_JPY, GBP_JPY (pending — Wave-1 additions, NOT gaps; harness skips pairs with insufficient history)
- **pairs_missing:** none. No DATA-GAP file is required: every named pair is live or Wave-1 pending, and the only unavailable feed (live spread) belongs to an *optional* gate that is dropped, not substituted (see §8 and §10 #4).

## 3. Indicators

| Indicator | Params | Source |
|---|---|---|
| EMA fast (H1 close) | period 9 | inventory `ema(close, 9)` |
| EMA slow (H1 close) | period 21 | inventory `ema(close, 21)` |
| EMA regime (H4 close) | period 200 | inventory `ema(close, 200)` computed on the H4 frame |
| Session clock | UTC hour of the H1 decision-bar close | derivable from the bar index (bars are UTC open-stamped); no external feed |
| Pip size per pair | 0.0001 non-JPY, 0.01 JPY-quoted | inventory `get_pip_value` / `calculate_pips` |

No swing/ZigZag/pivot/fractal logic is used; nothing from `causal_structure` is needed and `detect_swing_points` is not touched.

## 4. Entry — long

Decision is made at the close of H1 bar `t` (stamped at its open; its close is time `t+1h`). All conditions are evaluated on data fully known at that instant:

1. `ema9[t] > ema21[t]` AND `ema9[t-1] <= ema21[t-1]` — a fresh H1 bullish cross exactly on bar `t` (not merely "ema9 above ema21").
2. H4 regime filter is bullish: on the most recent H4 bar `T` that is **fully closed before H1 bar `t` opened** (i.e. `T + 4h <= t`), `H4 close[T] > ema200_H4[T]`.
3. Session gate: the UTC hour of the decision instant `t+1h` is in `[07:00, 21:00)` (London through New York; see §8).
4. No further conditions. The source's optional spread gate is dropped (§10 #4).

- **Entry type:** `market`
- **Entry level:** none (fill at the open of H1 bar `t+1` per F1/F2, plus adverse slippage per F10)
- **expires_after_bars:** `1` — a market intent fills at the next bar's open or not at all; this prevents any stale intent lingering if the fill is somehow skipped (e.g. F12 concurrency).

## 5. Entry — short

Mirror of long:

1. `ema9[t] < ema21[t]` AND `ema9[t-1] >= ema21[t-1]` — fresh H1 bearish cross on bar `t`.
2. H4 regime filter bearish: on the most recent fully-closed H4 bar `T` with `T + 4h <= t`, `H4 close[T] < ema200_H4[T]`.
3. Same session gate: decision hour in `[07:00, 21:00)` UTC.
4. Entry type `market`, fills at open of `t+1`, expires_after_bars `1`.

## 6. Stop

All geometry is anchored to the **decision-bar close** `C = H1 close[t]` (fleet rule: the market fill price is unknowable at emission; see §10 #2).

- **Initial stop (long):** `StopRule.price = C - 50 * pip`
- **Initial stop (short):** `StopRule.price = C + 50 * pip`
- **move_to_breakeven_on:** none
- **trail:** none (static stop; `trail_atr_multiple = None`)

## 7. Exit legs

| Label | Fraction | Kind | Level formula |
|---|---|---:|---|---|
| TP1 | 1.0 | take_profit | long: `C + 100 * pip` · short: `C - 100 * pip` |

Fractions sum to 1.0. The 50-pip stop / 100-pip target is the source's declared "default hard SL 50 pips, TP 100 pips (1:2 RR)". The source's primary exit — close on the opposite EMA9/21 cross — is a signal exit and is **inexpressible** in contract v2 (ExitLeg kinds are take_profit / trailing / time only); it is rejected, not approximated (§10 #1).

## 8. Filters

| Filter | Rule | Timeframe | Knowable when |
|---|---|---|---|
| H4 trend regime | long only if `H4 close > H4 ema200`, short only if `H4 close < H4 ema200`, on H4 bar `T` with `T + 4h <= t` | H4 | At time `T+4h`; i.e. only after the H4 bar has fully closed. An H4 bar stamped `T` is knowable at `T+4:00`. |
| Session | decision instant (`t+1h`, close of H1 bar `t`) must fall in `[07:00, 21:00)` UTC — the union of London (07:00–16:00) and New York (12:00–21:00), their overlap included | H1 (clock) | At the decision instant; the bar timestamp is known with certainty. |
| Weekend | none needed — the market is closed Fri 21:00 → Sun 21:00 UTC, so no H1 bars exist there | — | — |
| Spread | **DROPPED.** The CSV's "max spread check" / "spread below max" requires a live spread series, which does not exist in the data. No proxy is invented. Costs are handled by the engine's F10 fixed model (1.0-pip spread + 0.5-pip entry slippage, commission 0), which is *more* conservative than the bot's typical 2.0-pip gate on majors during liquid hours, but cannot reproduce a live gate that blocks entries in thin/spiky-spread conditions. This is flagged prominently: the backtest will take some entries a live bot with a 2-pip gate would have refused. | — | — |

## 9. Causality audit

| Rule | Inputs | Fully known at |
|---|---|---|
| H1 EMA9 / EMA21 values at bar `t` | H1 closes up to and including bar `t` | close of bar `t` (the decision instant) |
| H1 cross detection (`ema9[t]>ema21[t]` & `ema9[t-1]<=ema21[t-1]`) | closes of bars `t` and `t-1` | close of bar `t` |
| H4 EMA200 regime value | H4 closes up to and including H4 bar `T` | close of H4 bar `T`, i.e. time `T+4h` (bars stamped at open) |
| H4→H1 join | H4 bar `T` used only for H1 decisions on bars `t` with `T + 4h <= t` | the H4 bar is fully closed **before the H1 decision bar even opens** — one H1 bar stricter than the minimum legal rule (closed by the decision instant), chosen conservatively (§10 #5). Mechanical form per contract §4: shift the H4 frame's index forward by one full H4 interval (4h) and `merge_asof(..., direction="backward", allow_exact_matches=False)` onto the H1 decision-bar index. |
| Session gate | UTC timestamp of the decision instant | the decision instant itself; no lag |
| Entry fill | emitted at close of `t`, eligible from bar `t+1` (F1), market fill at open of `t+1` (F2) | n/a — engine convention |
| Stop / TP levels | decision-bar close `C` and pip size | close of bar `t`, at OrderIntent creation |

**Swing/pivot/ZigZag/fractal confirmation lag:** not applicable — this strategy uses none. There is no confirmation-lag-bearing construct anywhere in the spec.

## 10. Ambiguities resolved

| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | Exit logic: "close LONG when EMA9 crosses back below EMA21" vs "default hard SL 50 pips, TP 100 pips" — the CSV lists both | Hard SL 50 / TP 100 bracket as a single 1.0-fraction take_profit leg + static stop. The cross-exit is a *signal* exit; contract v2 has no exit-on-signal kind, so it is **inexpressible, not merely less convenient**. Consequence: trades no longer exit early on regime decay — winners that would have been cut at +30 pips by a back-cross now run to +100 or reverse into the −50 stop. Expected effect is fewer, larger-swing outcomes; direction of bias vs the live bot is ambiguous, so the fixed bracket is taken as the only honest expressible structure. | Signal-based opposite-cross exit — inexpressible in OrderIntent/ExitLeg; rejected. |
| 2 | SL/TP measured from fill price (pseudocode: `sl=entry-50*pip`) — the fill of a market order is unknowable at emission | Anchored to the decision-bar close `C`: SL = `C − 50 pip`, TP = `C + 100 pip`. Realised R ≠ declared R when the `t+1` open gaps away from `C`; F2/F6 resolve the fill honestly and the gap is visible in reports. | Fill-anchored SL/TP — inexpressible under decision-bar anchoring; rejected. |
| 3 | Session filter is "optional"; session boundaries (London/NY/overlap) are unnamed clock times | Filter **included** (fewer trades = conservative): decision hour ∈ `[07:00, 21:00)` UTC, the London∪New York union. Exact hours are a convention; recorded here so the implementer has no choice to make. | (a) Omit the filter entirely — more trades, less conservative. (b) Overlap-only (12:00–16:00) — stricter but not what "London/NY/overlap" enumerates; rejected as over-reading. |
| 4 | "Spread below max" / "max spread check" gate — no live or historical spread series exists | Gate dropped. F10's fixed 1.0-pip spread + 0.5-pip slippage is applied by the engine as the cost model; it is not a substitute gate and is never used to veto entries. Flagged in §8: backtest takes entries a live 2-pip-gated bot would skip. | Proxy gate using the fixed 1.0-pip cost as if it were a measured spread — invented data; rejected. |
| 5 | MTF boundary: may an H4 bar closing exactly at the H1 decision instant inform that decision? | No. The H4 bar must be closed **before the decision H1 bar opens** (`T + 4h <= t`), adding up to one H1 bar of extra staleness. Later information = conservative. | "Closed by the decision instant" (`T + 4h <= t+1h`) — legal under contract §4 but uses fresher information; rejected as the less conservative reading. |
| 6 | "H1 entry ... (M15-D1 selectable)" — the entry timeframe is configurable in the bot | H1 fixed, as the named default and the granularity the whole system simulates on. | D1 or H4 entry variants — would be a different strategy; rejected. M15/M30 are stale and out of scope per DATA_AVAILABILITY. |
| 7 | "Trend filter confirms uptrend" could mean more than close > EMA200 (e.g. EMA9>EMA21 on H4, or EMA200 slope rising) | Exactly the pseudocode condition: `H4 close > H4 ema200` (strict inequality). | Slope-of-EMA200 or H4-cross confirmations — not in the pseudocode; rejected. |
| 8 | Re-emission: a fresh same-direction cross can occur while a position is still open (whipsaw back and forth within 50 pips) | No special handling — the strategy emits an intent on every qualifying cross bar. F12 caps concurrency at 1 position per (strategy, pair, granularity); intents arriving while a position is open cannot increase exposure. Because entries are `market` with `expires_after_bars = 1`, no pending-order overlap is possible (a market intent fills at the next open or dies). Residual risk: none beyond re-entry churn after a stop-out, which is the strategy's intended behaviour. | "A new signal closes/supersedes the open position" — that mechanism does not exist in contract v2; rejected. |
| 9 | "2% equity risk per trade with pip-based position sizing" | Out of scope: System 1 never sizes. `size_fraction = 1.0`; results are reported in r-multiples with initial risk = `|fill − stop|` as computed by the engine. | Any sizing emulation in the strategy — forbidden by the contract; rejected. |

## 11. Expected behaviour

- **Trade frequency:** fresh EMA9/21 crosses occur several times per week per pair on H1; after the H4-regime veto (which blocks roughly half of crosses in mixed regimes) and the session gate (~63% of hours admitted), expect roughly **1–4 entries per pair per week**, fewer when F12's one-position cap overlaps signals. Across 5 live pairs that is of order 250–1,000 trades over a 10-year lookback — adequate for the gates per-cell, though JPY/CHF/pending pairs add cells only after Wave-1 backfill.
- **Holding time:** with a 50-pip stop and 100-pip target on H1, typical holds are hours to ~2 days; F11 END_OF_DATA closures should be rare.
- **What would make it fail the gates:** (a) whipsaw churn when H4 price hovers around the EMA200 — crosses keep firing with the regime flip-flopping bar to bar; (b) the 1:2 bracket on H1 noise needs a win rate above ~33% plus costs; naked H1 EMA9/21 crosses are a well-mined signal with no obvious residual edge, and F5 (stop-before-target) plus the 1.5-pip round-trip cost on a 50-pip risk unit (≈3% of 1R per trade) is a heavy drag; (c) the dropped live-spread gate and the missing cross-exit both mean the backtest is *not* measuring the bot as deployed — the bracket-only version is systematically different (§10 #1).
- **Conviction verdict:** the author's MODERATE is **generous**. The README openly states there is no profitability evidence, the rules as written are an unoptimized textbook crossover with a regime filter, and the expressible subset (hard bracket, no cross-exit, no live-spread gate) is further from the deployed bot than the prose suggests. Treat any passing result as a hypothesis for walk-forward confirmation, not as validation of the GitHub bot.
