# SPEC-bb_midline_break
**Source:** row 28 of forex_swing_strategies.csv · https://tradingstrategyguides.com/swing-trading-strategy/
**Conviction (author's):** MODERATE

## 1. Hypothesis
After price stretches to or beyond a 2σ Bollinger Band — a statistically extreme excursion relative to the last 20 bars — and then a large-bodied candle closes back across the 20-bar mean with its close at the candle's extreme, the move marks exhaustion of the band-side move and the start of a momentum swing away from the band. The edge should persist because Bollinger extremes are where short-term mean-reversion flow (profit-taking from the prior move, plus breakout-fade orders resting at round statistical levels) meets stopped-out late entrants; a decisive close back through the widely-watched 20-period mean forces the band-side crowd to unwind simultaneously, giving the reversal follow-through rather than a one-bar blip. The author rates it MODERATE: the rules are fully mechanical but no backtest is documented on the source page.

## 2. Scope
- **primary_granularity:** H4 (the source's declared preference: "H4 (preferred)|D1|W1")
- **context_granularities:** none. The strategy has no multi-timeframe filter; D1 and W1 are sanctioned *alternative primaries* (variant runs), not context frames. The declared implementation is H4 only (§10 #9).
- **simulate_on:** H1 (contract Part D: decided on H4, fills/stops/legs resolved on H1 bars; also run native-H4 resolution and report the delta)
- **pairs_requested (verbatim):** `All forex majors and minors`
- **pairs_available:** EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD (live) · GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD (**pending** — Wave-1 additions, NOT gaps). This covers all 7 USD majors and 8 crosses.
- **pairs_missing:** no pair is individually named. The generic phrase "all … minors" nominally also covers crosses outside the 13 (e.g. AUD_JPY, CAD_JPY, CHF_JPY, NZD_JPY, GBP_AUD, GBP_CAD, GBP_CHF, GBP_NZD, EUR_CHF, EUR_NZD, AUD_CAD, AUD_CHF, NZD_CAD, NZD_CHF, CAD_CHF). Per contract Part F, generic "majors/minors/any pair" language maps onto the 13-pair universe; this is a universe-coverage note, **not** a data gap — **no DATA-GAP file is written**. The backtest verdict applies to the covered 13-pair universe and the strategy is pair-agnostic, so the reduced universe remains informative.
- **granularity note:** W1 is stale ~8 weeks (Wave-1 refresh item, not a gap) and is only an alternate primary here; H4 and D1 are current. M15/M30 are not requested.

## 3. Indicators
| Indicator | Params | Source |
|---|---|---|
| Bollinger Bands | period=20, std_dev=2.0 → (upper, mid, lower) | `indicators.bollinger_bands` (inventory) — used as-is, including its std convention (§10 #6) |
| Candle body | `body[t] = abs(close[t] − open[t])` | private, plain OHLC arithmetic, specified in §4 |
| Average body | `avg_body[t] = sma(body, 20)[t]`, window **includes bar t** (per source pseudocode `body.rolling(20).mean()`) | private, maps to `indicators.sma` applied to the derived body series |
| Close-location quartile | `range[t] = high[t] − low[t]`; close in top/bottom 0.25 of range | private, plain OHLC arithmetic, specified in §4 |
| Band-touch state | touch on any of bars t−5…t−1 (rolling 5-bar OR, shifted 1 bar) | private, plain arithmetic on High/Low vs the inventory bands |

No swing/ZigZag/pivot/fractal detection is used anywhere in this strategy; `causal_structure` is not needed and `detect_swing_points` is not touched. Volume is not used.

## 4. Entry — long
Decision bar = H4 bar **t**, all conditions evaluated at the **close** of bar t. `upper/mid/lower` are the Bollinger(20, 2.0) values; all series subscripts refer to the H4 frame.

Conditions (ALL must hold):
1. **Prior band touch (state):** there exists a bar j ∈ {t−5, …, t−1} with `low[j] ≤ lower[j]` (touch or exceed the lower band, each bar judged against its OWN contemporaneous band value). Strictly before bar t — bar t itself does NOT qualify as the touch bar (§10 #2). Mechanically: `max over j∈[t−5,t−1] of (low[j] ≤ lower[j]) == true` — this is the source pseudocode's `(low <= lower).rolling(5).max().shift(1)` mirrored for longs.
2. **Midline cross-up on bar t:** `close[t] > mid[t]` AND `close[t−1] ≤ mid[t−1]` (the close crosses from at/below the midline to above it ON the decision bar; an already-above-midline close is not a signal).
3. **Big body:** `body[t] > 1.5 × avg_body[t]` where `body[t] = abs(close[t] − open[t])` and `avg_body[t] = mean(body[t−19 … t])` (20-bar window including bar t, per pseudocode; §10 #10).
4. **Close near candle high (top quartile):** `close[t] ≥ high[t] − 0.25 × (high[t] − low[t])`.
5. **Bullish candle (prose requirement, added):** `close[t] > open[t]` (§10 #3). Strictly stricter than the pseudocode; conditions 2–4 nearly imply it, so the practical effect is small.

- **Entry type:** `market` (the source's "buy at the close of that breakout candle" is realised as: decision at close of t, market OrderIntent emitted, fill at the OPEN of bar t+1 per F1/F2 — filling at close[t] itself is impossible under the contract; §10 #8)
- **Entry level:** none (market). Geometry anchor for stop/TP is the decision close `C = close[t]` (fleet rule: fill price unknowable at emission).
- **expires_after_bars:** **null** — N/A for market entries; the intent is admitted at bar t+1 (§3.2 step 6, subject to F12) or never.

## 5. Entry — short
Full mirror at the close of H4 bar t:

1. **Prior band touch:** ∃ j ∈ {t−5,…,t−1}: `high[j] ≥ upper[j]` (source pseudocode: `(high >= upper).rolling(5).max().shift(1)`).
2. **Midline cross-down on bar t:** `close[t] < mid[t]` AND `close[t−1] ≥ mid[t−1]` (exactly the source's `close < mid & close.shift(1) >= mid.shift(1)`).
3. **Big body:** `body[t] > 1.5 × avg_body[t]` (same definitions as long).
4. **Close near candle low (bottom quartile):** `close[t] ≤ low[t] + 0.25 × (high[t] − low[t])` (source's `near_low`).
5. **Bearish candle (prose requirement, added):** `close[t] < open[t]`.

- **Entry type:** `market`; fill at open of t+1 (F1/F2). Anchor `C = close[t]`.
- **expires_after_bars:** **null**.

Long and short signals are mutually exclusive at any decision bar (condition 2 requires close > mid vs close < mid), and same-direction signals on consecutive bars are impossible (a cross requires the previous close on the opposite side of the midline). All entries are market orders, so there are no live pendings and no pending-overlap risk; if a new signal fires while a position is open, F12 (max 1 concurrent position per strategy/pair/granularity) governs admission engine-side (§10 #7).

## 6. Stop
- **Initial stop (long):** `S_long = low[t]` — the exact low of the breakout (decision) candle.
- **Initial stop (short):** `S_short = high[t]` — the exact high of the breakout candle (source: "protective stop loss above the high of the breakout candle for shorts (below the low for longs); a break of that candle extreme invalidates the setup as a fake breakout").
- No buffer is added (§10 #5). Both are absolute prices fully knowable at the decision bar's close; declared R is measured from the anchor `C = close[t]`: `R = |C − S|`. Note `R ≥ 0.75 × range[t]` for both directions by the quartile conditions, so R is always positive and non-trivial.
- **move_to_breakeven_on:** none.
- **trail:** none (`trail_atr_multiple = null`). The source defines no stop movement.

## 7. Exit legs
| Label | Fraction | Kind | Level formula |
|---|---|---:|---|
| TP1 | 1.0 | take_profit | long: `C + 1.5 × R` · short: `C − 1.5 × R`, where `C = close[t]` and `R = |C − S|` from §6 |

Fractions sum to 1.0 (single full-size leg). **This is a substitute exit** — the documented exit ("take profit when price breaks and closes back across the middle band against the position") is a close-on-condition exit against a *moving* level and is INEXPRESSIBLE in contract v2: `take_profit` needs an absolute price declarable at emission, `trailing` is ATR-based, `time` is a bar count; no kind closes on a midline cross. The fixed 1.5R take-profit anchored to the decision close is the chosen conservative expressible structure: it caps winners the documented exit would have let run, and 1.5R sits at the lower end of the plausible mean-reversion envelope (the midline-to-opposite-band distance is 2σ, while R ≈ 0.75–1.0× the breakout candle's range). The fidelity loss is material and is recorded in §10 #4; realized R ≠ declared R when the t+1 open gaps (F2/F6 resolve the fill honestly).

## 8. Filters
| Filter | Timeframe | Rule | Knowable at |
|---|---|---|---|
| — none — | — | The source defines NO trend, session, volatility, news, or spread filter. Entry conditions §4/§5 are the complete gate. | — |

No non-price data is required (no calendar, rates, COT, VIX, DXY, real volume). The F10 cost model (1.0-pip spread, 0.5-pip slippage on entry only, commission 0) is applied by the engine, not the strategy. No proxy substitutions are made anywhere in this spec.

## 9. Causality audit
| Rule | Inputs | All inputs fully known at |
|---|---|---|
| §4.1 / §5.1 band-touch state | low/high and band values of bars t−5…t−1; each `lower[j]`/`upper[j]` is a trailing 20-bar rolling function of closes ≤ j | close of bar t−1 (latest possible touch bar). **The 1-bar shift is explicit and verified:** the rolling 5-bar window is `.shift(1)`ed in the source pseudocode, so bar t can NEVER serve as its own touch bar — no same-bar touch+break. Allowing same-bar would be a looser, different strategy (§10 #2) |
| Band values at any bar j | closes of bars j−19…j (trailing rolling mean/std, includes j) | close of bar j — causal; using bar j's own close in the band tested against bar j's high/low is legitimate (both are complete at j's close) |
| §4.2 / §5.2 midline cross | close[t], close[t−1], mid[t], mid[t−1] | close of bar t (decision instant; order fill-eligible only from t+1 per F1) |
| §4.3 / §5.3 big body | open/close of t; bodies of t−19…t | close of bar t. Self-inclusion of bar t in avg_body is causal (known at t's close) and conservative — it RAISES the threshold on big bars (§10 #10) |
| §4.4 / §5.4 close quartile | high/low/close of t | close of bar t |
| §4.5 / §5.5 candle direction | open/close of t | close of bar t |
| §6 stop | high/low of t | close of bar t; absolute price declared at OrderIntent creation |
| §7 TP1 | close[t] and S (both ≤ t) | close of bar t; absolute price declared at OrderIntent creation |
| Swing/pivot/ZigZag/fractal confirmation lag | **none used** | N/A — no structure detection anywhere in the strategy; there is no hidden confirmation lag to declare |
| Multi-timeframe | none in the declared H4 implementation | N/A — single frame. (If Wave 2 runs the D1/W1 variants, each is likewise single-frame on its own granularity; no context bar ever informs a lower-timeframe decision) |

No rule reads any bar later than the decision bar. Fills obey F1/F2 (market entry at t+1 open plus adverse slippage); stop-first ordering F5 and gap fills F6 are engine-side and pessimistic; H1 fill resolution per contract Part D is engine-side (the strategy never sees H1 data).

## 10. Ambiguities resolved
| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|--|---|---|
| 1 | "Price first touches or exceeds the … band" — how far back may the touch be? | 5-bar lookback (bars t−5…t−1), taken verbatim from the source pseudocode `(…).rolling(5).max().shift(1)` | Prose-implied unbounded/"recent" lookback (more signals, unimplementable without a cutoff); tightening to 3 bars (arbitrary, less faithful) |
| 2 | May the touch occur ON the breakout bar itself? | No — the shifted window excludes bar t; touch must be strictly before the breakout bar. Verified in the pseudocode (`.shift(1)`) and stated in §9 | Same-bar touch+break allowed — looser, more signals, a different strategy |
| 3 | "big bold bullish/bearish candle" — is candle direction required, or only body size? | Direction required (`close>open` long / `close<open` short) per the prose — strictly stricter, fewer signals | Pseudocode-literal reading (absolute body only) — the prose's "bullish/bearish" would be unenforced |
| 4 | Documented exit is a close back across the moving midline — inexpressible as an ExitLeg | Single `take_profit` leg at 1.5R anchored to decision close C (caps winners the documented runner-exit would let run). Fidelity loss acknowledged: the documented exit typically exits within a few bars on the first adverse close and has no fixed target; the backtest measures a fixed-RR variant, not the literal strategy | (a) `time` leg after N bars — no defensible N, holds losers to the stop and decouples exit from price entirely; (b) TP at the decision-bar-frozen opposite band — a different trade thesis (band-to-band), distance unbounded in R terms; (c) 1.0R — caps winners even harder but materially alters the R:R character; (d) any fill-anchored variant — inexpressible (fill price unknowable at emission), not merely less conservative |
| 5 | Stop "above the high / below the low of the breakout candle" — buffer size unspecified | Exact candle extreme, zero buffer — the tightest reading, most stop-outs | Any buffer (1 pip, 0.25×ATR, …) — size is invented, and any buffer widens the stop (more favourable) |
| 6 | Bollinger std convention: pandas `.rolling(20).std()` defaults to ddof=1; inventory implementation may differ | Use `indicators.bollinger_bands` exactly as implemented (comparability with the live path; no reimplementation) | Private ddof=1 reimplementation to match the pseudocode letter-for-letter — diverges from the shared inventory for a <1% band-width difference |
| 7 | Order lifecycle with back-to-back signals | No suppression needed: market entries only (no pendings, hence no pending-overlap), long/short mutually exclusive per bar, same-direction crosses cannot occur on adjacent bars; residual concurrency (new signal while a position is open) is capped by F12 engine-side. Residual risk: none beyond F12 semantics | Re-emitting pendings, OCO-style "first fill cancels the other", or signal-supersedes-position logic — none of these mechanisms exist in contract v2 |
| 8 | "buy at the close of that breakout candle" | `market` OrderIntent at decision bar t → fill at open of t+1 (F1/F2), with F10 slippage — later and worse than the prose's close-fill | Assuming a fill at close[t] — impossible under the contract and systematically optimistic |
| 9 | Source lists "H4 (preferred)|D1|W1" | Declared implementation is H4 primary only; D1/W1 are optional variant runs of the SAME single-frame rules, never combined into an MTF filter. (If the W1 variant is run, the Part F statistical warning applies: ~156 W1 training bars, single-digit trades per fold → `low_confidence` by arithmetic) | Running all three granularities as one pooled strategy (granularity-mixing) or inventing an MTF confirmation the source does not define |
| 10 | avg_body window: include the signal bar itself or not? | Include (per pseudocode `body.rolling(20).mean()` at bar t) — raises the 1.5× threshold exactly when the signal candle is large → fewer signals | Shifted window (bodies t−20…t−1) — lower threshold, more signals, less faithful |

## 11. Expected behaviour
- **Frequency:** moderate. The two-phase gate (band touch within 5 bars, then an immediate midline cross with a >1.5×-average body and extreme-quartile close) is selective but fires regularly on H4: expect roughly **5–15 trades per pair per year**; across the 13-pair universe and ~20 years of H4 history, order 1,500–4,000 trades total. Per-cell 6-month OOS folds should mostly carry 3–8 trades — thin but usually above the worst low-confidence territory; the D1 variant will be ~4× thinner and the W1 variant statistically vacuous (see §10 #9).
- **Geometry:** stop at the breakout candle's extreme with R ≥ 0.75× the candle range, TP capped at 1.5R → declared R:R = 1:1.5, break-even win rate ≈ 40% + costs. The big-body condition guarantees wide stops relative to ordinary bars, so F5 (stop-before-target on the same bar) and F2 slippage bite harder than average; expect the H1-resolution vs native-resolution delta (Part D) to be non-trivial — a large delta means the result is carried by bar-path assumptions and is suspect.
- **What fails the gates:** strong one-way trends (band touches in a persistent trend produce crosses that immediately fail — the substitute fixed TP cannot bail out early the way the documented midline-crossback exit would, so the spec version should underperform the documented one in trends, which is the conservative direction); choppy band-riding regimes where 2σ is not extreme; any pair where 1.5R is routinely unreachable before the stop.
- **Is MODERATE justified by the rules as written?** Yes. The rules are fully mechanical end-to-end (the author's own pseudocode is close to correct — causally shifted touch window, explicit cross, explicit body and quartile tests), the mean-reversion-from-statistical-extreme rationale is economically plausible, and the author honestly documents no backtest. The one serious caveat is the exit: the strategy's documented exit is inexpressible in contract v2, so the tested artefact is a fixed-1.5R variant; the gates will measure that variant, and the fidelity loss (§10 #4) must be quoted in any report.
