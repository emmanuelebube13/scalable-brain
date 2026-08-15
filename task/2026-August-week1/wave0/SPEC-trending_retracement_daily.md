# SPEC-trending_retracement_daily
**Source:** row 9 of forex_swing_strategies.csv · https://www.forexstrategiesresources.com/trend-following-forex-strategies/142-trading-in-trending-with-retracement-trading-system-daily/
**Conviction (author's):** MODERATE

## 1. Hypothesis

After a fast smoothed-moving-average cross establishes a fresh daily trend, the first counter-trend candle that forms while price is stretched a fixed half-to-one percent beyond the smoothed mean marks a shallow pullback within an intact impulse rather than a reversal; entering on a stop order just beyond that candle's extreme captures trend resumption. The edge should persist because fast MA crosses proxy the behavioural momentum cascade — underreaction to new information followed by herding — while short-term counter-move traders provide the liquidity for continuation entries; the envelope band filters for pullbacks occurring at a consistent, moderate extension where late trend-followers re-engage and the prior swing provides a natural invalidation level.

## 2. Scope

- **primary_granularity:** D1 (source: "Daily"; CSV `timeframes` = D1)
- **context_granularities:** none (single-timeframe strategy)
- **simulate_on:** H1 (Contract Part D: D1 decisions, H1 fill resolution)
- **pairs_requested (verbatim):** "Any"
- **pairs_available:** EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD (live) · GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD (Wave-1 additions, **pending** — declared; harness skips pairs with insufficient history)
- **pairs_missing:** none. "Any" reads as any supported FX pair; XAU_USD is excluded by data policy, not requested by name, and is not a gap. **No DATA-GAP file required.**

## 3. Indicators

| Indicator | Params | Source |
|---|---|---|
| SMMA (smoothed MA) on D1 Close | n = 3 and n = 8 | **Private function** — formula below. NOT the inventory `sma`; do not add to `indicators.py` |
| Percent envelopes on SMMA8 | inner dev 0.005, outer dev 0.010 | **Private** — trivial closed-form, below |
| Confirmed swing points (D1) | period = 5 | `causal_structure.confirmed_swing_points` |
| Pip size / pip value | per pair | inventory `get_pip_value` / `calculate_pips` |

**SMMA (private, exact specification).** On the D1 Close series:
- Seed: the first SMMA value is the plain SMA of the first `n` closes: `SMMA_{n-1} = (1/n) * sum(Close_0 … Close_{n-1})` (0-based); bars `0 … n-2` are NaN.
- Recursion for `t >= n`: `SMMA_t = (SMMA_{t-1} * (n - 1) + Close_t) / n`.
- This is the MetaTrader "Smoothed MA" (a.k.a. modified MA). It is NOT `ema(period=n)` (that uses alpha = 2/(n+1)); it equals an EMA with alpha = 1/n only asymptotically, and the SMA seed differs. Values at bar `t` use only closes `<= t`: causal.

**Envelopes (private, exact specification).** Basis = SMMA8 (per the row's own pseudocode; the unexplained "5" in `data_requirements` is resolved in §10.1):
- `UI_t = SMMA8_t * 1.005` (upper inner) · `UO_t = SMMA8_t * 1.010` (upper outer)
- `LI_t = SMMA8_t * 0.995` (lower inner) · `LO_t = SMMA8_t * 0.990` (lower outer)

**Pip size.** `pip = 0.01` for JPY-quoted pairs (USD_JPY, GBP_JPY, EUR_JPY), else `0.0001`; obtained from the inventory helpers, never hard-coded per pair.

## 4. Entry — long

All conditions are evaluated on the D1 frame at the **close of decision bar `t`**; every input is knowable at that close.

1. **Trend cross (recency window 5 bars):** there exists a bar `c` with `t-4 <= c <= t` such that `SMMA3_c > SMMA8_c` AND `SMMA3_{c-1} <= SMMA8_{c-1}` (a bullish cross at `c`). This is the row's pseudocode `cross.rolling(5).max()`.
2. **Setup candle colour:** bar `t` is red: `Close_t < Open_t`.
3. **Setup candle location (whole-body containment):** `UI_t <= Close_t < Open_t <= UO_t`. For a red candle the body spans `[Close_t, Open_t]`; BOTH body extremes must lie inside `[UI_t, UO_t]`. (Stricter than the pseudocode's close-only test — §10.2.)
4. **Stop availability:** at least one confirmed swing low (§6) with confirmation bar `<= t` exists; otherwise emit nothing.
5. **Stop-position sanity:** `stop_price < entry_price`; otherwise emit nothing (Contract §2.2 validation would reject the intent).

- **Entry type:** `buy_stop`
- **Entry level:** `entry_price = High_t + 4 * pip`
- **expires_after_bars:** `1` — one D1 decision-frame bar, the source's "for next day". Arithmetic: emitted at the close of D1 bar `t`, eligible from the first H1 bar of D1 bar `t+1` (F1), cancelled after the last H1 bar of D1 bar `t+1` (F4). Pending–pending overlap is impossible: the next possible emission is at the close of `t+1`, eligible from `t+2`, after this order has expired. (Pending-vs-open-position overlap IS possible — §10.8.)

## 5. Entry — short

Mirror of §4:

1. **Bearish cross:** exists `c`, `t-4 <= c <= t`, with `SMMA3_c < SMMA8_c` AND `SMMA3_{c-1} >= SMMA8_{c-1}`.
2. **Setup candle colour:** bar `t` is green: `Close_t > Open_t`.
3. **Setup candle location:** `LO_t <= Open_t < Close_t <= LI_t` (whole green body inside `[LO_t, LI_t]`).
4. **Stop availability:** at least one confirmed swing high with confirmation bar `<= t`.
5. **Sanity:** `stop_price > entry_price`.

- **Entry type:** `sell_stop`
- **Entry level:** `entry_price = Low_t - 4 * pip`
- **expires_after_bars:** `1` (same arithmetic as §4).

Symmetric strategy — both directions traded as documented.

## 6. Stop

- **Initial stop (long):** the exact level of the most recent **confirmed swing low** on D1 from `causal_structure.confirmed_swing_points(high, low, period=5)`, restricted to swings whose **confirmation bar** `k+5 <= t` (the level itself was set at occurrence bar `k`). No buffer (§10.6). Short: most recent confirmed swing high, same rule.
- **move_to_breakeven_on:** `"BE_70"` — the auxiliary trigger leg in §7. The source rule "after 40–70 pips profit move SL to 25 pips below entry" is P&L-triggered and fill-anchored, hence not directly expressible. In-contract expression: when the `BE_70` take-profit leg fills on H1 bar `k`, the stop moves **at the close of `k`** (F8 — later than the live-trader rule, pessimistic) to:
  - long: `entry_price - 25 * pip` → `breakeven_offset_pips = -25.0` (adverse side of the DECLARED entry)
  - short: `entry_price + 25 * pip` → `breakeven_offset_pips = +25.0`
  The trigger is set at the **70-pip** end of the 40–70 range (later protection = conservative; §10.4). The move applies only if it tightens the stop — the contract forbids widening, and if the initial swing stop is already within 25 pips of entry the BE move is a no-op.
- **trail:** none (`trail_atr_multiple = None`).

## 7. Exit legs

`entry_price` is the **declared** stop-entry level (§4/§5), knowable at OrderIntent creation; F3 gap fills mean realized R ≠ declared R when the fill slips — accepted, honest (fleet rule 8).

| Label | Fraction | Kind | Level formula |
|---|---|---|---|
| BE_70 | 0.01 | take_profit | long: `entry_price + 70 * pip` · short: `entry_price - 70 * pip` — exists only to trigger `move_to_breakeven_on` (§6, §10.4) |
| TP_150 | 0.99 | take_profit | long: `entry_price + 150 * pip` · short: `entry_price - 150 * pip` |

Fractions sum to 1.0 exactly (0.01 + 0.99). Both legs lie beyond entry in the trade direction, satisfying Contract §2.2 validation; if a single H1 bar covers both, they fill nearest-first (F7). The source's other two exits — **touch of the outer envelope band** and **opposite SMMA cross** — are signal exits: the band level moves every bar and the cross time is unknowable, so neither yields a declarable absolute `price`/`pips`/`bars` at emission. Both are **rejected as inexpressible** (§10.5); the fixed TP is the only expressible exit and is taken at the conservative 150-pip end of the documented 150–300 range.

## 8. Filters

No session, news, calendar, volatility-series, or external filters exist in the source, and no non-price data exists to build any (DATA_AVAILABILITY: no rates/calendar/COT/VIX/DXY; `Volume` is tick count and is unused here). The embedded gates, all evaluated on D1 and knowable at the close of the decision bar:

- **Trend gate:** SMMA3/SMMA8 cross recency (§4.1/§5.1) — the only trend filter.
- **Location/extension gate:** the setup body must lie inside a **fixed-percent** 0.5–1.0% band around SMMA8 (§4.3/§5.3). This is NOT volatility-adaptive; the author's own reasoning warns "envelope deviation must be tuned per pair volatility". Per Contract §10 (no parameter optimisation) we do NOT tune: the fixed 0.005/0.010 deviations are applied to all pairs as documented, and the consequence (high-volatility pairs, e.g. JPY crosses, produce setups at a different effective stretch than EUR_USD) is recorded, not repaired.
- **Stop-validity gate:** §4.4/§4.5 — no confirmed swing, or a swing on the wrong side of entry, suppresses the order.
- **Cost model:** the engine applies 1.0-pip spread + 0.5-pip entry slippage (F10). No real spread series exists; the constant cost model is the system-wide standard proxy, flagged here per fleet rule 5. It is not a strategy-level invention and no alternative is obtainable.

## 9. Causality audit

Reviewers: every rule below is evaluated at the close of the stated bar using only completed data; the strategy emits on D1 and never sees H1 data (H1 is fill resolution only, Contract Part D).

| Rule | Inputs | Fully known at | Lag |
|---|---|---|---|
| SMMA3 / SMMA8 at bar `t` | Closes `<= t` | Close of D1 bar `t` | None beyond bar completion (SMA seed + backward recursion only) |
| Envelope bands at `t` | `SMMA8_t` | Close of `t` | None |
| Cross at bar `c` | SMMA at `c` and `c-1` | Close of `c`; recency test at `t` uses only `c <= t` | Close of `t` | None |
| Setup candle (colour + body containment) | OHLC of `t`, bands of `t` | Close of `t` | None |
| Entry level `High_t ± 4*pip` | `High_t`/`Low_t` | Close of `t` | None |
| **Swing stop** | Swing low/high occurring at bar `k` | **Confirmation bar `k+5`** (period = 5: five subsequent D1 bars all fail to exceed it); used only when `k+5 <= t` | **5 D1 bars — explicit** |
| Decision / OrderIntent emission | All of the above | Close of D1 bar `t`; fills eligible from D1 bar `t+1` (F1) | 1 bar decision/execution separation |
| MTF causality | — | Single timeframe; no context frames, so Contract §4 reduces to F1 | n/a |
| BE_70 stop move | Fill of the trigger leg on H1 bar `k` | **Close of H1 bar `k`** (F8) — protection arrives late vs the live rule, pessimistic | Intrabar delay, stated |
| Stop/TP fills | H1 bars within each D1 span | H1 resolution; same-bar stop+target → stop first (F5); gaps fill at open (F3/F6) | Conservative conventions |
| Expiry | — | Order dies after 1 D1 bar (F4) | None |

`detect_swing_points` (centred rolling window) is **BANNED** and is not used anywhere in this spec; all structure references go through `causal_structure.confirmed_swing_points`.

## 10. Ambiguities resolved

| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | `data_requirements` says "Envelope (5\|dev 0.5)" — the "5" is unexplained (no SMMA5 exists in the row). | Envelope basis = **SMMA8**, per the row's own pseudocode `envelope(s8, …)` and because the body-location condition is measured against the trend MA. | SMMA5 basis — contradicts the pseudocode and the indicator list ("Smoothed MA 3 / Smoothed MA 8" only); would silently move every band and manufacture a different strategy. |
| 2 | "Body lies between the upper inner and upper outer envelope" — which prices? | **Whole-body containment**: for a red candle `UI <= Close < Open <= UO` (mirror for green/lower). Fewer, cleaner setups. | Pseudocode's close-only test (`close.between(eU1,eU2)`) — admits candles whose open lies far outside the band; more setups, less faithful to "body lies between". |
| 3 | How long after the cross may the setup candle appear? | Cross within the last **5 D1 bars including `t`** — the row's pseudocode `cross.rolling(5).max()`. | (a) Unlimited wait after a cross — stale trends, more trades; (b) cross and setup on the SAME bar — far fewer trades and contradicts "wait for a red pullback candle". |
| 4 | "After 40–70 pips profit move SL to 25 pips below entry" — P&L-triggered, fill-anchored; inexpressible declaratively (contract has no unrealized-P&L trigger; legs must have fraction > 0). | Auxiliary take-profit leg **BE_70**, fraction 0.01, at **+70 pips from the DECLARED `entry_price`**; `move_to_breakeven_on="BE_70"`; stop then moves to `entry_price ∓ 25*pip` at the trigger bar's close (F8). 70 = later end of the range = later protection = conservative. Declared-entry anchor satisfies fleet rule 8; realized R ≠ declared R under F3 gap fills — honest. | (a) Dropping the rule (`move_to_breakeven_on=None`) — deletes a documented risk rule; (b) 40-pip trigger — earlier protection, flatters results; (c) zero-fraction trigger leg — contract-invalid; (d) fill-price anchoring — inexpressible at emission, rejected as inexpressible (not merely less conservative). |
| 5 | Three documented exits (outer-band touch / opposite cross / fixed 150–300 pips) — which to implement? | **Fixed TP at 150 pips only** — the sole exit expressible as a declarable absolute level; 150 caps winners and does not flatter the r-multiple distribution. | (a) Outer-band touch — band level changes every bar; no declarable price at emission; inexpressible. (b) Opposite SMMA cross — signal exit with unknowable time/price; inexpressible (no declarative signal-exit mechanism in contract v2). (c) TP = 300 pips — larger winners, flatter distribution, less conservative. (d) TP at the decision-bar snapshot of the outer band — an invented level the source never uses. **Consequence: the backtest measures the fixed-TP variant, which is not exactly the traded strategy — must be stated in the report.** |
| 6 | "SL at previous swing" — which swing, what confirmation, any buffer? | Most recent **confirmed** swing low (long) / high (short), `period=5`, exact level, **no buffer**, confirmation bar `<= t` (§9). | (a) Acting on an unconfirmed swing — look-ahead, the banned `detect_swing_points` mechanism; (b) any period other than 5 — invented; (c) a buffer beyond the swing — invented, widens risk beyond the source. |
| 7 | "Place buy stop … for next day" — order lifetime. | `expires_after_bars = 1` D1 decision-frame bar (the full next trading day, resolved on its H1 span; weekend spans simply extend the H1 count — §4 arithmetic). | (a) GTC / `None` — stale stop orders fill days later at meaningless levels: more, worse trades; (b) 1 H1 bar — a one-hour window is not "next day"; censors most documented fills. |
| 8 | Contract v2 has no OCO / cancel-on-fill / supersede; F12 caps concurrent POSITIONS (default 1) but does not gate pending fills (§3.2 step 5). Can orders overlap? | Pending–pending overlap is **impossible** by construction (1-bar expiry; §4 arithmetic). A pending order CAN fill while an earlier position is still open (the strategy never observes fills). Recorded as **residual multi-fill risk**: direction = MORE concurrent exposure than the author intended; a re-cross within 5 bars plus an opposite setup candle can even open a counter-position, partially hedging the first. Effect on pooled r-multiples is ambiguous (same-direction adds trend exposure; opposite-side hedges). No declarative fix exists; flagged, not hacked. | Pretending the first fill cancels later orders or that a new signal closes the position — mechanisms that do not exist in contract v2. |
| 9 | "Any" pair — which universe? | All 13 supported FX pairs: 5 live + 8 Wave-1 pending (declared; harness skips missing history). XAU_USD excluded by data policy. | Restricting to AUD_USD because the source's worked example is AUD/USD — arbitrary censoring of the sample. |
| 10 | "25 pips below entry" — entry = fill or declared level? | Declared `entry_price` (knowable at emission). | Fill-anchored version — inexpressible at OrderIntent creation (fleet rule 8); rejected as inexpressible. Gap fills (F3) make the realized stop distance differ from the declared 25 pips — accepted and honest. |

## 11. Expected behaviour

- **Trade frequency:** SMMA3/SMMA8 crosses occur roughly 8–20 times per D1 pair-year; requiring a same-direction setup candle within 5 bars whose WHOLE body sits inside a 0.5%-wide band cuts emissions to roughly **2–6 orders per pair-year**, of which an estimated half to two-thirds fill within the 1-day window → **~2–5 trades per pair-year, ~10–25 per year pooled over the 5 live pairs** (more once Wave-1 pairs land). Thin but not degenerate for a D1 system; expect `low_confidence` flags on some per-cell results.
- **What would make it fail the gates:** (a) thin per-fold trade counts on a selective D1 setup; (b) fixed-percent envelopes applied untuned across pairs of very different volatility (the author's own caveat) — setups fire at the wrong extension on high-vol pairs; (c) loss of the source's primary exit: the tested variant uses a fixed 150-pip TP instead of the documented outer-band touch / opposite cross, so a failure indicts the *expressible* variant, not necessarily the traded one — the report must carry this caveat; (d) SMMA3/8 whipsaw in ranging regimes — the fast cross gate admits setups in weak trends and the swing stop is wide, and F5 (stop-before-target at H1 resolution) compounds the pessimism; (e) weekend gaps through wide swing stops (F6) producing losses > 1R.
- **Is the author's MODERATE conviction justified by the rules as written?** Yes, as written: the entry is fully mechanical (pending stop orders), invalidation is explicit (confirmed swing), and a partial protection rule exists. But the conviction rests on worked chart examples with no statistical backtest, two of the three documented exits cannot be tested as documented, and the envelope parameters admittedly need per-pair tuning that the no-optimisation rule forbids. MODERATE is fair for the expressible variant; the untested discretionary exits mean the backtest, if anything, understates what the author traded — and it is the expressible variant alone that any verdict here can speak for.
