# SPEC-three_ducks

**Source:** row 12 of forex_swing_strategies.csv · https://www.forexstrategiesresources.com/trend-following-forex-strategies/71-3-duck-s/
**Conviction (author's):** MODERATE

> ⚠ **EXECUTION BLOCKED.** The trigger timeframe is M5. No M5 data exists in
> `fact_market_prices`, and "M5" is not in contract v2 `VALID_GRANULARITIES`
> ("H1","H4","D1","W1"). Every M5-dependent rule below is marked **[M5-BLOCKED]**.
> This spec is written for the strategy **as documented** so Wave 2 can implement it
> the day M5 lands. See `DATA-GAP-three_ducks.md`. No H1 substitute is specified
> anywhere in this document; that would be a different strategy.

## 1. Hypothesis

When the H4, H1, and M5 timeframes all agree on direction via the same 60 SMA, order flow
across positional, intraday, and tactical horizons is aligned behind one trend; entering on
the smallest timeframe's resumption of that trend (a fresh cross plus a 20-bar breakout)
buys momentum continuation at a locally early point inside an established move. The edge
should persist because participants underreact to sustained imbalances and herd into
established trends, while the triple-alignment gate keeps the system out of the range
regime where M5 noise and mean-reversion dominate and a bare M5 cross would be whipsawed.

## 2. Scope

- **primary_granularity:** **M5** (documented trigger frame) — **[M5-BLOCKED]**: not in
  contract v2 `VALID_GRANULARITIES`; zero M5 bars in the database. Execution is blocked
  pending data; the harness must SKIP this strategy, not simulate it on another frame.
- **context_granularities:** H4 (duck 1, trend), H1 (duck 2, confirmation). Both are live
  and current to 2026-08-07 per DATA_AVAILABILITY.md — fully supported today.
- **simulate_on:** M5 native, once data lands. The contract §5 "decide native, resolve on
  H1" mechanism is **inapplicable** here: the native frame is *finer* than H1, so fills
  resolve on M5 bars directly (F5 still applies at M5 resolution). The required both-ways
  delta report becomes native-M5 vs H1-aggregated, if desired.
- **pairs_requested (verbatim):** `EUR/USD|GBP/USD|any`
- **pairs_available:** EUR_USD ✅ live, GBP_USD ✅ live. The trailing "any" is unbounded;
  the conservative reading restricts coverage to the two named pairs (§10 #7). Wave-1
  additions (GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD) are
  **pending**, not gaps, and are out of scope for this strategy as specified.
- **pairs_missing:** none by name. The genuine gap is the **M5 granularity for EUR_USD and
  GBP_USD** → `DATA-GAP-three_ducks.md`.

## 3. Indicators

| Indicator | Params | Source |
|---|---|---|
| SMA of H4 Close | period 60, closed H4 bars only | inventory `sma` |
| SMA of H1 Close | period 60, closed H1 bars only | inventory `sma` |
| SMA of M5 Close **[M5-BLOCKED]** | period 60 | inventory `sma`, applied to M5 frame |
| Donchian upper, M5 **[M5-BLOCKED]** | period 20, lagged 1 bar: `max(High[t-20 … t-1])` | inventory `donchian_channel` upper band, 1-bar shift (matches the author's pseudocode `m5['high'].rolling(20).max().shift()`) |
| Donchian lower, M5 **[M5-BLOCKED]** | period 20, lagged 1 bar: `min(Low[t-20 … t-1])` | inventory `donchian_channel` lower band, 1-bar shift |

No swing/ZigZag/fractal indicator is used. The author's own pseudocode operationalises
"the last M5 swing high" as a 20-bar trailing-high break, which is fully causal with
**zero confirmation lag** (§9; the literal confirmed-swing reading and its lag are the
rejected alternative, §10 #1). `detect_swing_points` is not used. Pip conversion via
inventory `calculate_pips` / `get_pip_value` (EUR_USD, GBP_USD).

## 4. Entry — long  **[M5-BLOCKED]**

All conditions are evaluated at the close of M5 decision bar *t*:

1. **Duck 1 (H4 trend):** Close of the most recently **closed** H4 bar > SMA60(H4 Close).
   An H4 bar stamped T covers [T, T+4h) and is knowable only from T+4h onward (§9).
2. **Duck 2 (H1 confirm):** Close of the most recently **closed** H1 bar > SMA60(H1 Close),
   knowable from its stamp +1h onward.
3. **Duck 3 cross (M5 trigger):** `Close[t] > SMA60_M5[t] AND Close[t-1] <= SMA60_M5[t-1]`
   — an actual cross event, not merely the state of being above (§10 #2).
4. **M5 breakout:** `Close[t] > max(High[t-20 … t-1])` (20-bar Donchian upper, lagged 1).
5. F12 default `max_concurrent_positions = 1` per (strategy, pair) applies.

- **Entry type:** `market`.
- **Entry level:** n/a for market entries; fills at the **open of bar t+1** (F1/F2) with
  +1.0 pip spread and +0.5 pip slippage on entry (F10, engine-applied).
- **expires_after_bars:** **null** (declared explicitly; not applicable to market entries).
- **Decision-bar anchor:** all stop/target geometry is anchored to `A = Close[t]`, the M5
  decision close — knowable at OrderIntent creation (fleet rule on decision-bar anchoring).
- **Order lifecycle:** entries are market-only; there are no pending orders, so no OCO /
  cancel-on-fill / supersede semantics are needed and none are assumed. Re-emission while
  flat after a loss is inherent to the design and harmless under F12=1.

## 5. Entry — short  **[M5-BLOCKED]**

Exact mirror; both sides documented in the source (no long-only restriction):

1. Most recently closed H4 Close < SMA60(H4 Close).
2. Most recently closed H1 Close < SMA60(H1 Close).
3. `Close[t] < SMA60_M5[t] AND Close[t-1] >= SMA60_M5[t-1]` (actual downward cross).
4. `Close[t] < min(Low[t-20 … t-1])` (20-bar Donchian lower, lagged 1).
5. Entry type `market`; fill at open of t+1 (F1/F2); expires_after_bars null; anchor
   `A = Close[t]`.

## 6. Stop

- **Initial stop (long):** `StopRule.price = A − 25 pips`, where A is the M5 decision
  close. **Short:** `A + 25 pips`. 25 pips is the tight end of the documented "fixed
  25–30 pips" option — the most mechanical and most pessimistic of the three documented
  stop choices (§10 #4). Anchored to the decision close, not the fill: realised R ≠
  declared R when the t+1 open gaps from A (F2/F6 resolve the fill honestly; `gapped`
  is reported).
- **move_to_breakeven_on:** `none` (not documented).
- **trail:** `none` (not documented). The stop is static and never widens.

## 7. Exit legs

| Label | Fraction | Kind | Level formula |
|---|---|---:|---|
| TP1 | 1.0 | take_profit | long: `A + 50 pips` (= 2.0 × the 25-pip declared risk); short: `A − 50 pips` |

Fractions sum to **1.0**. The source's "targets at support/resistance levels" is
discretionary with no mechanical definition; a single static 2R leg is the conservative
substitute (§10 #5). The source's **optional** early cut ("price closes back beyond the
M5 60 SMA by 10 pips against the trade") is **omitted** — optional in the source and not
expressible as a contract v2 `ExitLeg`/`StopRule` without an engine extension (§10 #3).

## 8. Filters

- **Trend filter (duck 1, H4 60 SMA):** evaluated on H4. Knowable only after each H4 bar
  **closes**: bars are stamped at their open, so an H4 bar stamped T first informs an M5
  decision at the M5 bar opening at T+4h. Mechanical form: `merge_asof(m5, h4,
  direction="backward", allow_exact_matches=False)` after shifting the H4 index forward
  by one full H4 interval (contract §4 rule).
- **Confirmation filter (duck 2, H1 60 SMA):** identical mechanics with one H1 interval.
- **Pair filter:** EUR_USD and GBP_USD only (§2, §10 #7).
- **Session / news / volatility filters:** none documented, and no non-price data exists
  to implement any (DATA_AVAILABILITY.md) — nothing added.
- **Spread:** no spread series exists; the 1.0-pip spread is a cost-model constant (F10),
  not data. On a 25-pip declared risk, 1.5 pips of round-trip cost is 6% of risk per
  trade — flagged here and in §11, not gated. Not a proxy substitution: it is the live
  cost model the engine already applies.

## 9. Causality audit

| Rule | Inputs fully known at | Confirmation lag |
|---|---|---|
| Duck 1: H4 Close > SMA60(H4) | Close of H4 bar stamped T → usable by M5 decisions with decision time ≥ T+4h (the M5 bar opening at T+4h) | One full H4 interval, enforced by shifted `merge_asof`; SMA60 needs 60 closed H4 bars (~10 trading days of warmup) |
| Duck 2: H1 Close > SMA60(H1) | Close of H1 bar stamped T → usable from T+1h | One full H1 interval; 60 closed H1 bars warmup |
| Duck 3 cross: `Close[t]` vs `SMA60_M5[t]`, `Close[t-1]` vs `SMA60_M5[t-1]` | Close of M5 decision bar t | None beyond bar close; SMA uses closes t−59…t only |
| Breakout: `max(High[t-20 … t-1])` / `min(Low[t-20 … t-1])` | Open of bar t (used at its close) | **Zero** — this is a trailing window, not a swing detector. This is precisely why the pseudocode proxy was chosen: it needs no confirmation |
| Literal "last M5 swing high/low" (REJECTED alternative, §10 #1) | A swing high occurring at bar k is knowable only at k+period; with period 5 that is k+5, i.e. 25 minutes after the swing formed | 5 M5 bars; rejected in favour of the zero-lag Donchian proxy |
| Stop `A ∓ 25 p`, TP `A ± 50 p` | Close of M5 bar t (anchor A = `Close[t]`) | Zero; absolute prices declarable at OrderIntent creation |
| Entry fill | Open of bar t+1 (F1/F2) | One M5 bar decision/execution separation |
| (Omitted) early cut via M5 close vs SMA60 ∓ 10 p | Would have been knowable at each M5 close — causal, but omitted as unimplementable under contract v2 (§10 #3) | n/a |

No centred windows anywhere; `detect_swing_points` is not used; every context-frame input
is lagged by one full context-bar interval.

## 10. Ambiguities resolved

| # | Ambiguity | Conservative reading taken | Alternative rejected |
|--:|---|---|---|
| 1 | "ideally with a break of the last M5 swing high" — "ideally" makes the breakout optional, and "swing high" is undefined | Breakout is **mandatory**, defined via the author's own pseudocode: `Close[t] > max(High[t-20 … t-1])` — causal, zero-lag, and stricter (fewer trades) than a typical last-swing level | (a) Treating "ideally" as optional (more trades, inflates results); (b) literal confirmed swing via `causal_structure.confirmed_swing_points(period=5)`: 5-bar confirmation lag, and the confirmed swing level typically sits below the 20-bar high → earlier, more frequent entries |
| 2 | "buy when price crosses above its 60 SMA" — cross event vs above-state | Actual cross required: `Close[t-1] <= SMA[t-1] AND Close[t] > SMA[t]` — one intent per crossing, far fewer trades | "Price is above" state, re-emitting every M5 bar while aligned (order-of-magnitude more intents; would also spam the engine pointlessly under F12=1) |
| 3 | "optional early cut if price closes back beyond the M5 60 SMA by 10 pips against the trade" | **Omitted.** It is optional in the source, and a close-conditional indicator exit is not expressible as a contract v2 `ExitLeg` (take_profit/trailing/time) or `StopRule` (static/breakeven/ATR-trail) without an engine extension | Approximating it intrabar (e.g. treating SMA60 ∓ 10 p as a dynamic stop) fabricates a rule the author marked optional and mis-models a close-based exit with intrabar fills — pessimistic in the wrong, unfaithful way |
| 4 | SL: "below M5/H1 swing low (short-term) or H4 swing low (positional) or fixed 25–30 pips" — three options, two of them swing-based and frame-ambiguous | **Fixed 25 pips**: the only fully mechanical option; the tight end; most stop-outs = most pessimistic; declarable at the decision bar | Swing-low stops: require confirmed-swing machinery (5-bar lag), variable risk per trade, and an undocumented choice among M5/H1/H4 frames; 30 pips fixed: looser than the documented minimum |
| 5 | "Targets at support/resistance levels" — S/R never defined mechanically | Single static take-profit at **+2.0R** (A ± 50 p), fraction 1.0 — static, declarable, and the standard stand-in for undocumented discretionary targets | (a) Nearest confirmed swing-high/low target: immediately after a 20-bar breakout no confirmed swing level exists *above* entry, so this forces an invented fallback anyway; (b) open-ended runner: inexpressible without a trailing rule the source never defines |
| 6 | Risk measured from fill vs decision bar (source silent; a live trader thinks in fill terms) | All geometry anchored to decision close A — the fill price is unknowable at emission (fleet rule). Realised R ≠ declared R when the t+1 open gaps (F2/F6) | Fill-anchored stop/TP: **inexpressible** in contract v2, not merely less conservative |
| 7 | "`any`" in target_pairs | Restrict to the two named pairs, EUR_USD and GBP_USD | Running the full 13-pair fleet on an unbounded "any" — undocumented for this system and dilutes per-cell confidence |
| 8 | "sizing discretionary per trader style" | `size_fraction = 1.0`; System 1 never sizes — r-multiples only | Any sizing rule would be invented |

## 11. Expected behaviour

- **Trade frequency:** triple SMA alignment + fresh cross + 20-bar breakout is restrictive;
  expect roughly 1–4 trades per pair per week in trending regimes and multi-week dry
  spells in ranges. Over ~20 years of M5 (~1.5M bars/pair) that still yields hundreds of
  trades per pair — comfortably above the trade-count gates, unlike the W1 strategies.
- **What would fail the gates:** choppy H4/H1 conditions where price straddles the 60 SMA
  produce repeated M5 crosses and whipsaw −1R stop-outs; a 25-pip stop is small relative
  to GBP/USD M5 noise, so the win rate lives or dies on the H4/H1 filter's discrimination.
  Costs of 1.5 pips round trip are 6% of declared risk per trade — material. F5
  (stop-before-target intrabar) bites hard with tight stops and 2R targets.
- **Is the author's MODERATE conviction justified by the rules as written?** Yes, as
  written: a textbook MTF trend-alignment system with a plausible behavioural basis, but
  no documented performance and discretionary exits that this spec had to mechanise
  (§10 #4, #5). The honest verdict is also currently **untestable**: until M5 is ingested
  the strategy emits zero orders, and any result produced on H1 would measure a different
  strategy wearing this one's name (see `DATA-GAP-three_ducks.md`).
