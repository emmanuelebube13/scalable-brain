# SPEC-inside_bar_continuation_ea

**Source:** row 39 of forex_swing_strategies.csv · https://www.mql5.com/en/code/73884
**Conviction (author's):** MODERATE

## 1. Hypothesis

A large, high-commitment candle (the Main Bar: wide range relative to ATR, body dominating its range) marks a burst of directional order flow; when the very next bar is fully contained inside it and small (the Signal Bar), the market is pausing to absorb that flow rather than reversing it, so a breakout through the Main Bar's extreme in the direction of the original burst is a continuation with favourable odds. The edge should persist because inside bars after impulse moves are a footprint of short-term volatility compression and trapped counter-trend entries whose stops cluster just beyond the mother bar's extremes, fuelling the breakout once it triggers.

## 2. Scope

- **primary_granularity:** H4
- **context_granularities:** none (single-timeframe strategy)
- **simulate_on:** H1
- **pairs_requested (verbatim):** "FX majors|FX minors (multi-market framework)"
- **pairs_available:** EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD (live); GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD (Wave-1 additions, **pending**)
- **pairs_missing:** none under the project's 13-pair FX majors/minors universe. An exhaustive reading of "all FX minors" (e.g. NZD_JPY, GBP_AUD, CHF crosses) is outside the project universe and is rejected in §10. **No DATA-GAP file is required.**

**Justification for H4 over D1:** the source says "H4|D1 (any TF; pattern research tool)" — the pattern is declared timeframe-agnostic. H4 is chosen because it yields roughly 6× the setup count of D1, which materially improves per-cell trade counts and walk-forward fold statistics, while still being a swing chart with negligible intrabar noise relative to the pattern's size gates (Main Bar ≥ 1.5×ATR). D1 as the primary frame is recorded as the rejected alternative in §10.

## 3. Indicators

| Indicator | Params | Source |
|---|---|---|
| ATR (Wilder) | period = 14, computed on the H4 frame using only bars ≤ decision bar | inventory `atr(high, low, close, period=14)` |
| Bar range | `rng[k] = High[k] − Low[k]` | trivially derived from OHLC; specified here, not an inventory item |
| Bar body | `body[k] = abs(Close[k] − Open[k])` | trivially derived from OHLC; specified here, not an inventory item |

No swing, ZigZag, pivot, or fractal constructs are used. `detect_swing_points` is not referenced.

## 4. Entry — long

Decision bar = bar **t** (the Signal Bar), evaluated at its **close**. Main Bar = bar **t−1**. All conditions below use only bars t and t−1 and ATR through bar t, so every input is fully known at the close of bar t.

1. **Main Bar bullish:** `Close[t−1] > Open[t−1]`
2. **Main Bar body dominance:** `body[t−1] >= 0.5 × rng[t−1]`
3. **Main Bar size filter (ATR filter ON):** `rng[t−1] >= 1.5 × ATR14[t]` where `ATR14[t]` is computed over bars ≤ t
4. **Signal Bar strictly inside Main Bar:** `High[t] < High[t−1]` **and** `Low[t] > Low[t−1]` (strict inequalities; touching extremes disqualify)
5. **Signal Bar size constraint:** `rng[t] <= 0.5 × rng[t−1]`

If all five hold:

- **entry type:** `buy_stop`
- **entry level:** `entry_price = High[t−1]` exactly (the Main Bar high; no buffer)
- **expires_after_bars:** `1` (the order is fillable only on bar t+1, per F1, then cancelled per F4)
- Validity note: the contract requires a pending buy_stop not to be already through the market at decision close; `Close[t] <= High[t] < High[t−1]` by condition 4, so this always holds.

## 5. Entry — short

Mirror of §4. Conditions:

1. **Main Bar bearish:** `Close[t−1] < Open[t−1]`
2. `body[t−1] >= 0.5 × rng[t−1]`
3. `rng[t−1] >= 1.5 × ATR14[t]`
4. `High[t] < High[t−1]` **and** `Low[t] > Low[t−1]` (strict)
5. `rng[t] <= 0.5 × rng[t−1]`

If all five hold:

- **entry type:** `sell_stop`
- **entry level:** `entry_price = Low[t−1]` exactly (the Main Bar low; no buffer)
- **expires_after_bars:** `1`

Direction is one-sided per setup, fixed by the Main Bar's close direction — there is never a simultaneous buy_stop and sell_stop from the same setup.

## 6. Stop

- **initial stop (long):** `stop.price = entry_price − 0.62 × rng[t−1]` (the documented default fraction of the Main Bar range, measured from the declared pending entry level)
- **initial stop (short):** `stop.price = entry_price + 0.62 × rng[t−1]`
- **move_to_breakeven_on:** `none`
- **trail:** `none` (static stop; `trail_atr_multiple = None`)

Anchoring: because the entry is a declared pending level, all geometry is anchored to `entry_price = High[t−1]` / `Low[t−1]`, which is knowable at the decision bar. Declared risk `R = 0.62 × rng[t−1]`. Realized R equals declared R except on gap fills (F3 fills at the open when the bar gaps through the level), which are resolved honestly by the engine and flagged via `gapped`.

Note: the stop sits **inside** the Main Bar's range (0.38×rng above the Main Bar low for a long). This is the source's documented design, not an error.

## 7. Exit legs

| Label | Fraction | Kind | Level formula |
|---|---|---:|---|---|
| TP1 | 1.0 | take_profit | long: `entry_price + 1.0 × 0.62 × rng[t−1]` · short: `entry_price − 1.0 × 0.62 × rng[t−1]` |

Fractions sum to 1.0. Declared RR = 1:1 (see §10 row 1: the source parameterises TP as `SL × RR` with "0 disables TP" but gives no canonical RR; the conservative declared value is 1.0).

## 8. Filters

All filters are pattern-quality gates evaluated on the **H4 decision bar t at its close**, and every input is knowable at that instant:

| Filter | Rule | Timeframe | Knowable at |
|---|---|---|---|
| ATR size filter | `rng[t−1] >= 1.5 × ATR14[t]` | H4 | close of bar t (ATR uses bars ≤ t only) |
| Min body % | `body[t−1] >= 0.5 × rng[t−1]` | H4 | close of bar t−1 (hence known at t) |
| Max inside-bar size % | `rng[t] <= 0.5 × rng[t−1]` | H4 | close of bar t |
| Inside containment | strict inequalities on High/Low | H4 | close of bar t |

There are **no** session, trend, news, calendar, or higher-timeframe filters in the source. Volume is not used. No proxy data is introduced anywhere in this spec; the cost model's 1.0-pip spread / 0.5-pip slippage (F10) is applied by the engine, not the strategy.

## 9. Causality audit

| Rule | Inputs | Bar at which inputs are fully known | Confirmation lag |
|---|---|---|---|
| Main Bar direction (§4.1/§5.1) | Open/Close of t−1 | close of t−1 | none (completed bar) |
| Body dominance (§4.2/§5.2) | OHLC of t−1 | close of t−1 | none |
| ATR size filter (§4.3/§5.3) | rng[t−1]; ATR14 over bars ≤ t | close of t | none — ATR uses completed bars only; no centred window |
| Inside containment (§4.4/§5.4) | High/Low of t and t−1 | close of t | none — strict bar-to-bar comparison, not a swing point |
| Signal-bar size (§4.5/§5.5) | rng[t], rng[t−1] | close of t | none |
| Entry level | High[t−1] / Low[t−1] | close of t−1 | none |
| Stop / TP formulas | entry_price, rng[t−1] | close of t | none |

- **No swing/pivot/ZigZag/fractal rule exists in this strategy**, so there is no swing-confirmation lag to declare; the Main Bar high/low are raw bar extremes, knowable at that bar's own close, not "swing highs" requiring subsequent-bar confirmation. This was explicitly checked against the row-39 prose and pseudocode.
- **Order timing:** the OrderIntent is emitted with `decision_bar = t`; per F1 it becomes fill-eligible from bar t+1 onward; with `expires_after_bars = 1` its only fill window is bar t+1 (§3.2 step 5), and it is cancelled at step 1 of bar t+2 (F4).
- **MTF causality:** not applicable — no context granularity is used. Fill resolution on H1 (§5 of the contract) is engine-side and introduces no information into decisions.

## 10. Ambiguities resolved

| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | "TP = SL distance × RR input (0 disables TP)" — no canonical RR given | **RR = 1.0** (single TP leg at 1R). Smaller TP caps winners at the smallest sensible multiple, depressing expectancy — the conservative direction; disabling TP (RR=0) is inexpressible as a pure take-profit plan (no ExitLeg would ever exit except the stop, making every trade −1R or END_OF_DATA, which measures the harness not the strategy) | RR = 2.0 or 3.0 (inflates r-multiples per winner); RR = 0 / no TP |
| 2 | Pending-order lifetime unspecified in prose ("place Buy Stop") | **expires_after_bars = 1** (EA-style next-bar-only). Fewest fills; a breakout that does not trigger immediately after an inside bar is statistically a different, weaker event | 5 bars (contract default) or GTC — both admit stale breakouts far from the compression event |
| 3 | "optional filter: Main Bar range ≥ 1.5 × ATR" | **Filter ON**, per the pseudocode's declared set (`rng.shift(1) >= 1.5*df['atr']`). Fewer trades | Filter OFF — admits quiet-market inside bars with no impulse, more trades, contradicts the declared pseudocode |
| 4 | Inside-bar containment: strict vs touching extremes | **Strict** (`High[t] < High[t−1]`, `Low[t] > Low[t−1]`), matching the pseudocode's `<`/`>` | Inclusive (`<=`/`>=`) — admits equal-high/low bars, more setups |
| 5 | Entry level: exact Main Bar extreme vs buffered | **Exact level** (`High[t−1]` / `Low[t−1]`), matching `entry=df['high'].shift(1)` | +1 pip buffer beyond the extreme (common EA practice; later/worse entries but not in the documented code) |
| 6 | SL fraction "configurable (default example 0.62)" | **0.62** exactly, the only documented value | Any other fraction (e.g. 0.5 or 1.0) — undocumented; 1.0 (stop at Main Bar opposite extreme) widens risk and changes declared R |
| 7 | ATR reference bar for the 1.5× filter (pseudocode uses unshifted `df['atr']` at bar t) | **ATR14[t]** computed over bars ≤ t — causal, matches pseudocode | ATR14[t−1] — marginally different threshold; both causal, pseudocode value taken |
| 8 | Signal Bar direction/body: must the inside bar agree in direction or have a min body? | **No constraint** — the source imposes none; only containment and max size | Requiring Signal Bar close in Main Bar direction (undocumented extra gate) |
| 9 | Primary timeframe: "H4\|D1 (any TF)" | **H4** (≈6× D1's setup count → viable fold statistics) | D1 as primary (fewer trades, thinner OOS cells); running both as separate strategies (out of scope — one declared parameter set) |
| 10 | "FX majors\|FX minors" universe | **The project's 13-pair universe** (5 live + 8 Wave-1 pending) | Exhaustive reading incl. NZD_JPY, GBP_AUD, CHF crosses — outside the ingest plan, would force a data gap the source does not specifically demand |
| 11 | Residual multi-fill/overlap risk (fleet lifecycle) | Two-sided pendings from one setup are impossible (direction fixed by Main Bar). Consecutive-setup pendings **cannot share a fill window**: order from setup at bar t is fillable only on t+1; filling requires `High[t+1] ≥ High[t−1] > High[t]`, which violates the containment `High[t+1] < High[t]` a new setup at t+1 would need — so setup and stale-pending fill are mutually exclusive. **Residual risk recorded:** a *new* pending may fill while a *prior position* from an older setup is still open; F12 (default 1) gates admission of new intents but, per the fleet rule, not pending fills, so concurrent positions can occur. Direction of effect: increased same-idea exposure (a later setup can be opposite-directed if a bearish Main Bar forms while a long is open), adding variance in both directions; accepted and disclosed rather than "solved" with a nonexistent cancel mechanism | "First fill cancels other pendings" / "new signal closes the old position" — mechanisms that do not exist in contract v2 (no OCO, no supersede) |

## 11. Expected behaviour

- **Trade frequency:** the triple gate (Main Bar ≥ 1.5×ATR, body ≥ 50%, next bar strictly inside and ≤ 50% of range) is restrictive. Expect roughly 2–5 setups per pair per month on H4; across the 5 live pairs ≈ 10–25 setups/month, rising to ≈ 25–60/month once the 8 Wave-1 pairs land. A meaningful fraction of pendings will expire unfilled on the single next bar, so filled trades will be fewer than setups.
- **What would make it fail the gates:** (a) the 1:1 RR with the stop sitting *inside* the Main Bar range — re-entry into the mother bar is common, so win rate must clear ≈ 50% plus costs (1.0 pip spread + 0.5 pip slippage per F10) just to break even; (b) F5 (stop-before-target) penalises exactly this geometry, since the stop lies between entry and TP in a congested region; (c) gap-through-stop events (F6) at weekend opens can push losses beyond 1R.
- **Conviction assessment:** MODERATE is justified by the rules as written. The pattern is a legitimate, mechanically specified volatility-compression continuation setup with structural risk definition, and the declared filters (impulse-sized Main Bar, small Signal Bar, next-bar-only entry) are the quality gates that distinguish tradeable inside bars from noise. But the source attaches a Strategy Tester report with no quoted summary statistics, the edge is one of the most widely published (and hence most arbitraged) retail patterns, and the 1:1 RR leaves no room for a sub-50% win rate. Independent re-testing, as the author effectively concedes, is the correct stance.
