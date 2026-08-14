# SPEC-kpl_donchian_breakout

**Source:** row 22 of forex_swing_strategies.csv · https://www.tradingview.com/script/4mz6xvnK/
**Conviction (author's):** MODERATE

## 1. Hypothesis

A daily close beyond the extreme of the prior 20 trading days marks the start (or resumption) of a directional trend rather than random noise, because FX trends are persistent: central-bank policy divergence, interest-rate differentials, and risk-sentiment regimes adjust over weeks to months, and herding among momentum participants plus the underreaction of fundamental capital to new information causes price to keep moving after a visible extreme is broken. A mechanical close-confirmed 20-day Donchian breakout with a volatility-scaled stop harvests this persistence by cutting failures quickly and letting confirmed trends run — the classic Turtle template, which has survived decades of markets precisely because it monetises the fat right tail of trend continuation rather than predicting direction. The edge should persist as long as macro regimes persist and breakout levels remain watched liquidity magnets; it degrades in extended mean-reverting, range-bound regimes where breakouts systematically fail.

## 2. Scope

| Field | Value |
|---|---|
| primary_granularity | **D1** (all signals decided on the D1 frame) |
| context_granularities | none (single-timeframe strategy) |
| simulate_on | **H1** (fills/stops/legs resolved against H1 bars inside each D1 span, per contract §5) |
| pairs_requested (verbatim) | `EURUSD|GBPUSD|USDJPY|AUDUSD|FX majors and crosses (asset-agnostic)` |
| pairs_available | **Live:** EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD. **Wave-1 pending** (declare; harness skips if history absent, NOT a gap): GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD. Rationale: the 4 named pairs are all live; the "FX majors and crosses (asset-agnostic)" clause is mapped onto the full 13-pair FX universe defined by DATA_AVAILABILITY (see §10 #5). |
| pairs_missing | none. XAU_USD is not named and is excluded by data policy anyway; no non-price feeds are required. **No DATA-GAP file.** |

Data requirement per source: "OHLC only | 20-bar Donchian channel (highest high / lowest low of prior 20 days)" — fully satisfiable from `fact_market_prices`.

## 3. Indicators

| Indicator | Params | Source |
|---|---|---|
| Donchian upper band, **prior-20-day, signal bar excluded** | period=20, computed as `donchian_channel(High, Low, 20)` then **shifted by 1 bar** before use: `DCU(t) = max(High[t-20 … t-1])`. The shift(1) is mandatory and is part of the definition, not an optional tweak — it matches the source pseudocode `df.high.shift(1).rolling(20).max()` and is causal by construction (§9). | inventory `donchian_channel`, with explicit `.shift(1)` applied in the strategy module |
| Donchian lower band, **prior-20-day, signal bar excluded** | period=20, shifted by 1 bar: `DCL(t) = min(Low[t-20 … t-1])`. Same shift requirement as above. | inventory `donchian_channel`, with explicit `.shift(1)` |
| ATR | period=14, on D1 `High/Low/Close`, Wilder smoothing as implemented in inventory. `ATR(t)` is the completed value at the close of bar t. | inventory `atr` |

The Donchian midline from the inventory is **not used** (see §10 #3). No swing/pivot/ZigZag/fractal indicators are used, so `causal_structure` is not required.

## 4. Entry — long

Decision is made at the **close of D1 bar t** using only data available at that close:

1. `DCU(t) = max(High[t-20 … t-1])` is fully known (it excludes bar t entirely).
2. **Breakout event (not state):** `Close(t) > DCU(t)` **AND** `Close(t-1) <= DCU(t-1)` — i.e. a fresh close-crossover above the prior-20-day high. Emitting only on the crossover event prevents re-entry churn after a stop-out inside a persistent trend; see §10 #2.
3. If both conditions hold, emit exactly one `OrderIntent` with `decision_bar = t`.

- **Entry type:** `market` (close-confirmed breakout; the source buys "when daily close breaks above", i.e. on/after the confirming close).
- **Entry level:** `entry_price = None` — fill at the **open of D1 bar t+1** (first H1 bar of the next D1 span under H1 resolution), plus adverse slippage, per F2.
- **expires_after_bars:** `null` (irrelevant — a market intent fills at t+1 open by F2; there is no pending order whose lifetime needs bounding).
- `size_fraction = 1.0` (single idea, single unit; the author's "1% equity risk" is System 3 sizing, out of scope for System 1 — results are r-multiples against the declared 2×ATR risk unit).

## 5. Entry — short

Exact mirror of §4:

1. `DCL(t) = min(Low[t-20 … t-1])` fully known at close of bar t.
2. **Breakdown event:** `Close(t) < DCL(t)` **AND** `Close(t-1) >= DCL(t-1)`.
3. Emit one `OrderIntent`, `direction = -1`, `decision_bar = t`.

- **Entry type:** `market`; **entry level:** `None` (open of D1 bar t+1 per F2); **expires_after_bars:** `null`; `size_fraction = 1.0`.

## 6. Stop

- **Initial stop (long):** `StopRule.price = Close(t) − 2.0 × ATR14(t)`, where `Close(t)` and `ATR14(t)` are the decision bar's close and completed ATR. Anchored to the decision-bar close (decision-bar-knowable), NOT to the fill, which is unknowable at emission — per the decision-bar anchoring rule. Realized R ≠ declared R when the t+1 open gaps away from Close(t); F3/F6 resolve the actual fill honestly.
- **Initial stop (short):** `StopRule.price = Close(t) + 2.0 × ATR14(t)`.
- **move_to_breakeven_on:** `none` (no breakeven mechanism in the source; there is no TP leg to trigger it).
- **trail:** `trail_atr_multiple = 2.0`. Mechanism, per F9 (updates at bar close with the completed ATR, never widens):
  - long: `trail(t) = max(trail(t-1), Close(t) − 2.0 × ATR14(t))` — a close-anchored ratchet, initialised at the initial stop;
  - short: `trail(t) = min(trail(t-1), Close(t) + 2.0 × ATR14(t))`.

Source basis: the CSV prescribes this production overlay verbatim — "recommended production overlay: 1% equity risk with 2xATR(14) initial stop" — because "original script lacks any stop loss so an ATR overlay is mandatory". The stop-and-reverse / no-stop original is rejected as inexpressible; see §10 #1.

## 7. Exit legs

| Label | Fraction | Kind | Level formula |
|---|---|---|---|
| TRAIL | 1.0 | trailing | `atr_multiple = 2.0` (close-anchored ratchet as defined in §6; the position exits when price closes/ranges back through the trailing stop) |

Fractions sum to **1.0**. There is **no take-profit leg**: the source states "profits left open", so the trend runs until the 2×ATR trailing stop or the stop takes it out. A fixed TP was considered and rejected (§10 #3). The opposite-breakout reversal exit of the original is **not expressible** and is deliberately omitted (§10 #2): an opposite signal while a position is open produces an intent that F12 drops, so the open trade simply rides its trail.

## 8. Filters

**None.** The source contains no trend, session, volatility, or news filter — the Donchian breakout is the entire signal. Specifically:

- No higher-timeframe trend gate (D1 is already the top frame; no W1 context is requested or added).
- No session/time-of-day gate (D1 bars, entries at daily open).
- No volatility gate (ATR is used for stop sizing, not as an entry veto — adding one would deviate from the source; recorded here so no implementer adds one silently).
- No news/calendar gate (no such data exists; the source does not ask for one).

Consequently there are no filter inputs whose knowability needs auditing beyond §9.

## 9. Causality audit

All decisions occur at the **close of D1 bar t**; all fills occur from bar t+1 onward (F1). Bar-by-bar knowability:

| Rule | Inputs | Fully known at | Confirmation lag |
|---|---|---|---|
| DCU(t) = max(High[t-20…t-1]) | Highs of bars t-20 … t-1 | **open of bar t** (all inputs strictly precede t; the shift(1) excludes bar t by construction) | 0 bars beyond the built-in 1-bar shift; this IS the confirmation mechanism — the channel level the close must beat is frozen before bar t begins, so the "close-confirmed breakout" compares today's close against yesterday's known ceiling. Proof of causality: every index in the window is ≤ t-1; no bar-t-or-later value enters the level. |
| DCL(t) = min(Low[t-20…t-1]) | Lows of bars t-20 … t-1 | open of bar t | same as above |
| Long event: Close(t) > DCU(t) AND Close(t-1) ≤ DCU(t-1) | Close(t), Close(t-1), both channel values | close of bar t | 0 |
| Short event: mirror | Close(t), Close(t-1), both channel values | close of bar t | 0 |
| ATR14(t) (stop + trail anchor) | High/Low/Close of bars t-13 … t (Wilder) | close of bar t | 0 — used only at/after the close of t |
| Initial stop price | Close(t), ATR14(t) | close of bar t (decision-bar anchor; the fill at t+1 open is never referenced) | 0 |
| Trail update | Close(k), ATR14(k) for each subsequent bar k | close of bar k; applied to stops from bar k+1's range checks onward (F9 / §3.2 step 4 ordering) | 0 — uses completed bars only |

- **No swing/pivot/ZigZag/fractal rules exist in this strategy**, so no confirmation-lag construct from `causal_structure` is needed. `detect_swing_points` is not used.
- **No multi-timeframe causality exposure:** signals are generated from the D1 frame only; H1 is used exclusively by the position engine to resolve fills/stops/trails inside each D1 span (contract §5). The strategy never reads H1 data, and no context timeframe informs decisions, so the §4 context-bar rule is trivially satisfied.
- **Fill separation:** an intent emitted at the close of D1 bar t (21:00Z stamp boundary) fills at the open of D1 bar t+1 at the earliest (F1/F2). The confirming close and the fill are in different bars by construction.
- **Weekend gaps** (Friday 21:00Z → Sunday 21:00Z) are normal per DATA_AVAILABILITY; F6 resolves any gap-through-stop at the open honestly.

## 10. Ambiguities resolved

| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | Original has **no stop loss at all** ("profits left open, losses limited via position sizing"); contract v2 mandates a `StopRule`. | Adopted the CSV's own prescribed production overlay: initial stop `Close(t) ∓ 2×ATR14(t)`, anchored to the **decision-bar close** (knowable at emission). | (a) No-stop original — **inexpressible**, contract requires StopRule.price; (b) fill-anchored stop ("entry − 2×ATR" as in the pseudocode) — inexpressible, fill is unknowable at emission per the decision-bar anchoring rule; recorded as rejected-inexpressible, not merely less conservative. Realized R ≠ declared R under gaps (F6). |
| 2 | Original is **stop-and-reverse, always in market** ("position reversed on opposite breakout signal"). | Decomposed into **fresh market entries on crossover events only** (§4/§5 condition 2). While a position is open, an opposite signal's intent is dropped by F12 (max 1 position), so the open trade rides its trail; after a stop-out, re-entry requires a NEW crossover event. This yields fewer trades and no re-entry churn. | (a) Atomic reverse — **inexpressible**: contract has no OCO/supersede/reverse, and the strategy never observes fills or open positions; (b) state-based re-emission every bar the condition holds — more trades, re-enters immediately after stop-outs into whipsaws, closer to the original but less conservative and prone to churn; (c) "first fill cancels the other order" — mechanism does not exist, never written here. **Consequence recorded:** the always-in-market property is lost; the backtest is flat whenever stopped out between crossover events, which understates the original's exposure in V-shaped reversals and overstates idle time in trends that continue after a 2×ATR shakeout. |
| 3 | Exit structure: source offers "ATR or channel-midline trailing stop" as options; original has no TP. | **2×ATR close-anchored trailing stop on 100% of the position, no TP** (§6/§7) — faithful to "profits left open" and fully expressible as `StopRule.trail_atr_multiple` + one `trailing` ExitLeg. | (a) Channel-midline trail — **inexpressible**: `StopRule` trails by ATR multiple only; the midline moves non-monotonically relative to an ATR ratchet and cannot be declared as an absolute ExitLeg price either (it updates per bar); (b) any fixed TP (e.g. 2R/3R) — contradicts the author's explicit "profits left open" design and would inject an arbitrary level the source never names; (c) breakeven move — no TP leg exists to trigger it and the source doesn't mention it. |
| 4 | "Buy when daily close breaks above" — market vs pending entry. | `market` at next bar open (F2), because the confirmation IS the close itself; by the decision bar's close price is already through the level, so a `buy_stop` at DCU would violate the contract's "pending entry_price not already through the market" validation. | Buy-stop at DCU(t) or at the breakout bar's high — adds a re-confirmation delay the source does not describe, and is contract-invalid at emission time (through the market). |
| 5 | "FX majors and crosses (asset-agnostic)" — which pairs exactly? | Mapped to the full declared FX universe: 5 live + 8 Wave-1-pending pairs (§2). The 4 named pairs anchor the set; the asset-agnostic clause explicitly extends it, and the harness skips pending pairs lacking history rather than failing. | (a) Restricting to the 4 named pairs only — discards the author's explicit universality claim without cause; (b) adding XAU_USD — excluded by data policy (not Forex; pip/margin conventions assume FX). |
| 6 | "Prior 20 days" — does the window include the signal bar? | **Excludes it** (`shift(1)`, §3) — matches the source pseudocode verbatim and is the only causally clean reading. | Including bar t in the window — self-defeating (Close(t) can never exceed a max that contains High(t), so the long signal could essentially never fire) and conceptually contaminated (the level would move with the bar being tested). |

**Order-lifecycle residual risk:** none. Only `market` intents are emitted, at most one per D1 bar per direction; there are no pending orders, no two-sided setups, and no overlap to bound. The only interaction with F12 is the intentional drop of opposite-signal intents while a position is open (§10 #2).

## 11. Expected behaviour

- **Trade frequency:** low, as designed. A fresh 20-day close-crossover on D1 occurs roughly 4–10 times per pair-year per direction combined (Turtle systems historically ~5–8 round trips/year/market). Across the 5 live pairs that is ~25–50 entries/year; across the full 13-pair universe ~65–130/year. With ~20 years of D1 history and 36-month walk-forward folds, per-fold trade counts should be adequate on pooled cells but may approach `low_confidence` on single-pair cells — per-cell reporting (contract §8) matters here.
- **Character:** classic trend-following profile — win rate ~35–45%, average winner several R via the trail, losers cut near −1R (occasionally worse through weekend gaps, F6). Equity comes in clumps aligned with macro trend regimes (2008, 2014–15 USD, 2021–22 rates) and bleeds slowly in range regimes (e.g. EUR_USD 2015–2019).
- **What would make it fail the gates:** (1) the 2×ATR initial stop is tight relative to D1 noise on the JPY crosses — repeated stop-outs in choppy folds could sink pooled expectancy; (2) the loss of always-in-market exposure (§10 #2) means the backtest systematically captures less trend than the author traded, biasing results downward in exactly the regimes where the strategy is supposed to shine; (3) post-2010 D1 breakout edge on majors is documented to have decayed, so late OOS folds are the risk. A strategy that fails pooled gates here but passes in trending cells would be a dispersion finding, not necessarily a dead edge.
- **Is the author's MODERATE conviction justified by the rules as written?** Yes, and arguably the honest grade. The entry is one of the most robust templates in the literature and is fully objective; but the source page documents **no performance**, the original omits any stop (the single most important risk decision is therefore ours, not the author's), and the expressible version is a degraded, not-always-in-market approximation of what the author actually ran. MODERATE — not HIGHLY_RECOMMENDED — correctly reflects "robust template, unproven instance, mandatory overlay not of the author's choosing".
