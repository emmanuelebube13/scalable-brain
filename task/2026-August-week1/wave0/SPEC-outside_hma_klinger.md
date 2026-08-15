# SPEC-outside_hma_klinger
**Source:** row 20 of forex_swing_strategies.csv · https://www.tradingview.com/script/v5vo0vNc-Advanced-OutSide-with-HMA-and-Klinger-Forex-Swing-strategy/
**Conviction (author's):** MODERATE

## 1. Hypothesis

An outside bar that engulfs the prior bar's entire range and then closes bullish is a two-sided liquidity sweep resolved in favour of buyers: both sides' stops have been triggered, the losing side is trapped, and the bar's close reveals which side won the auction. Requiring price above the Hull MA (a low-lag trend proxy) restricts entries to the direction of the prevailing multi-day drift, and requiring the Klinger oscillator positive demands that tick-activity flow — a proxy for real volume flow — confirms that participation, not just price, supports the move. The edge should persist because range-expansion bars in FX cluster at the start of directional legs (position liquidation and breakout entry are self-reinforcing for several bars), while volume-flow and trend agreement filter out the large population of outside bars that are mere noise around data releases. (The short side mirrors this on inside bars — see §10, row 3, for the documented asymmetry.)

## 2. Scope

- **primary_granularity:** H4 ("H4 and higher (published on EURUSD H4)" — H4 taken, the published and most conservative-to-implement choice; see §10, row 8)
- **context_granularities:** none — single-timeframe strategy
- **simulate_on:** H1
- **pairs_requested (verbatim):** `EURUSD (published)|GBPUSD|USDJPY|other FX majors`
- **pairs_available (13):**
  - Live now (5): EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD
  - Wave-1 additions, **pending** backfill (8): GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD
  - ("other FX majors" is read as the full 13-pair major set per contract §7's coverage note: the 5 live pairs plus the 8 Wave-1 additions; no pair beyond that set is a plausible "FX major" — see §10, row 7.)
- **pairs_missing:** none → **no DATA-GAP file** (see §8/§10, row 5: the tick-volume caveat is a prominent flag, not a gap — `Volume` exists in `fact_market_prices` and DATA_AVAILABILITY explicitly calls tick volume "a usable proxy for activity, but say so").

## 3. Indicators

| Indicator | Params | Source |
|---|---|---|
| Signed volume `SV` | per H4 bar t: `SV[t] = +Volume[t]` if `Close[t] >= Close[t-1]`, else `SV[t] = −Volume[t]`. `Volume` is OANDA **tick count**, not traded volume (flag: §8, §10 row 5). The `>=` tie-break (unchanged close counts as positive) is the author's own pseudocode (`close.diff()>=0`). | Private composition on the raw `Volume` column |
| Klinger Volume Oscillator `KVO` | `KVO = ema(SV, 34) − ema(SV, 55)`, where `ema` is the inventory function (pandas `ewm(span=n, adjust=True).mean()` semantics, matching the author's pseudocode exactly; see §10, row 6). This is the simplified close-diff variant the author mechanised, NOT the canonical Klinger trend/volume-force formula — the author's mechanisation is authoritative. | Private — NOT in inventory. Composition of inventory `ema` over the private `SV` series; define in own module. |
| KVO signal line `KVO_sig` | `KVO_sig = ema(KVO, 13)`. **Defined for completeness (the source names it) but used NOWHERE in entry or exit logic** — the documented conditions are `KVO>0` / `KVO<0` only (§10, row 9). | Private — same module |
| Hull Moving Average `HMA` on H4 close | n = 27. Definition: `W1 = WMA(Close, 13)`; `W2 = WMA(Close, 27)`; `RAW[t] = 2×W1[t] − W2[t]`; `HMA[t] = WMA(RAW, 5)`. Integer rounding: `half = floor(27/2) = 13`, `root = floor(sqrt(27)) = 5` (floor/integer-division convention of standard implementations — TradingView `ta.hma`, pandas-ta; see §10, row 4). `WMA(P, m)[t] = Σ_{i=0..m-1} (m−i)·P[t−i] / (m(m+1)/2)` — linear weights, newest bar heaviest. | Private — NOT in inventory; no inventory WMA exists either. Specify in own module exactly as above. |
| Previous-bar OHLC | `Open/High/Low/Close[t-1]` | raw frame |

## 4. Entry — long

All conditions evaluated on **closed H4 bars** at decision bar **t** (its close). `KVO[t]` and `HMA[t]` are trailing functions of closes/volumes ≤ t.

1. **Outside bar:** `High[t] > High[t-1]` AND `Low[t] < Low[t-1]` (strict inequalities, per author's pseudocode).
2. **Bullish close:** `Close[t] > Open[t]`.
3. **Volume-flow confirmation:** `KVO[t] > 0`.
4. **Trend filter:** `Close[t] > HMA[t]`.

All four at bar t; no arming state, no re-entry restriction beyond F12.

- **Entry type:** `market`
- **Entry level:** `entry_price = None`; fill at `Open[t+1]` plus adverse slippage (F1, F2, F10). The source says "enter long at bar close" — inexpressible under F1; the market intent at decision bar t filling at t+1 open is the contract's mechanical equivalent (§10, row 1). All stop/TP geometry is anchored to the decision-bar anchor **`A = Close[t]`** (fleet anchoring rule; the fill price is unknowable at emission).
- **expires_after_bars:** `null` — a market intent fills at bar t+1 or not at all; no pending order ever lingers, so no multi-fill overlap exists (fleet lifecycle rule satisfied trivially).

## 5. Entry — short

**Asymmetric as documented — NOT a mirror** (conservative: keep the source's rules verbatim; mirroring invents rules; §10, row 3).

1. **Inside bar:** `High[t] < High[t-1]` AND `Low[t] > Low[t-1]` (strict inequalities).
2. **Bearish close:** `Close[t] < Open[t]`.
3. **Volume-flow confirmation:** `KVO[t] < 0`.
4. **Trend filter:** `Close[t] < HMA[t]`.

Entry type `market`, anchor `A = Close[t]`, `expires_after_bars = null`. Note: the source uses an **inside bar** for shorts vs an **outside bar** for longs. This asymmetry is almost certainly a quirk (or defect) of the Pine source, but it is what is documented and is implemented as written.

## 6. Stop

- **Initial stop (long):** `SL_long = A × (1 − 0.0120) = A × 0.9880`, where `A = Close[t]`.
- **Initial stop (short):** `SL_short = A × (1 + 0.0150) = A × 1.0150`.
- Fixed-percentage bracket, anchored to the **decision-bar close**, not the fill (§10, row 2 — the author's pseudocode `sl=entry*0.988` measures from the fill, which is unknowable at emission; the fill-anchored reading is rejected as **inexpressible**, not merely less conservative). Declared R = `|A − SL|`; realised R ≠ declared R when the t+1 open gaps/slips (F2/F6 resolve the fill honestly).
- **move_to_breakeven_on:** `none`
- **trail:** `none` — static stop for the life of the position.

## 7. Exit legs

| Label | Fraction | Kind | Level formula |
|---|---|---|---|
| TP1 | 1.0 | take_profit | long: `A × 1.0060` · short: `A × (1 − 0.0075) = A × 0.9925`, where `A = Close[t]` |

Single leg, fractions sum to 1.0. **The bracket is negative reward:risk as documented** (long risks 1.2% to make 0.6%; short risks 1.5% to make 0.75%). Per the "no parameter optimisation" rule and the orchestrator's instruction, the author's bracket is kept verbatim — the v2 path evaluates the strategy AS DOCUMENTED. The author's own `risk_management` field flags this: "default bracket risks 2x the reward per trade, i.e. win-rate-dependent negative RR by default" and the reasoning field says it "needs ATR-based retuning before use". See §11 for the win-rate arithmetic.

**Signal exit (stop-and-reverse) — inexpressible, recorded, NOT implemented:** the source's "also exits on opposite entry signal (stop-and-reverse)" cannot be expressed in contract v2: the strategy never observes open positions, there is no close-position mechanism, and an opposite `OrderIntent` would open a NEW position (dropped by F12 anyway while one is open). Conservative resolution: **the position runs to SL or TP only** (§10, row 10).

## 8. Filters

| Filter | Timeframe | When knowable | Status |
|---|---|---|---|
| Trend gate — close vs HMA(27) | H4 | close of decision bar t | implemented — this IS entry condition 4 |
| Volume-flow gate — KVO sign | H4 | close of decision bar t | implemented — entry condition 3. **PROMINENT FLAG: `Volume` is OANDA tick count, not traded volume.** The Klinger oscillator's economic meaning ("volume force") degrades to "tick-activity force". DATA_AVAILABILITY states tick volume "is a usable proxy for activity, but say so" — this spec says so here, in §10 (row 5), and in §11. No real-volume feed exists in the system and none is substituted. Because the proxy data DOES exist, this is **not** a DATA-GAP; it is a fidelity caveat the report must carry. |
| Spread/news/session filters | — | — | **none specified by the source.** The fixed-cost model (F10: 1.0-pip spread) stands in for the spread component of any real-world execution filter; this is the engine's uniform convention, not a strategy rule, and is noted only to pre-empt misreading. |
| Risk sizing — "100% equity sizing in script (must be replaced with fractional risk sizing)" | account-level | — | **out of scope for v2**: System 1 never sizes (contract §2.2); results are r-multiples only. `size_fraction = 1.0`. The source itself marks its sizing as not-for-production. |

## 9. Causality audit

Reviewers: read this first. Decision bar = H4 bar t; "known at close of t" means computed from bars ≤ t only. **This strategy is single-timeframe — no MTF causality issue exists, and no swing/pivot/ZigZag/fractal identification is performed anywhere, so the k+period confirmation-lag rule is NOT APPLICABLE (stated explicitly per audit requirement).** `detect_swing_points` is NOT used; no `causal_structure` function is needed.

| # | Rule | Inputs | Fully known at | Confirmation lag |
|---|---|---|---|---|
| 1 | Outside bar (long) | `High/Low[t]`, `High/Low[t-1]` | close of H4 bar t | none — comparison of two completed bars |
| 2 | Inside bar (short) | `High/Low[t]`, `High/Low[t-1]` | close of H4 bar t | none |
| 3 | Bullish/bearish close | `Open[t]`, `Close[t]` | close of H4 bar t | none |
| 4 | Signed volume `SV[t]` | `Close[t]`, `Close[t-1]`, `Volume[t]` | close of H4 bar t | none — tick count of bar t is final at its close |
| 5 | KVO (EMA34−EMA55 of SV) | `SV` history ≤ t (recursively, closes/volumes ≤ t) | close of H4 bar t | none — trailing EMAs; warmup note: EMA55 needs ~55+ bars to stabilise; the loader's 10-year lookback makes boundary effects negligible, and any warmup NaN bars simply emit no orders |
| 6 | HMA(27) | closes ≤ t (three nested trailing WMAs, longest window 27) | close of H4 bar t | none — WMA is a trailing weighted sum over completed bars; warmup = 27 bars before first defined value |
| 7 | Stop & TP arithmetic | `Close[t]`, constants 0.9880/1.0150/1.0060/0.9925 | close of H4 bar t | none — arithmetic on known values |
| 8 | Emission → fill | OrderIntent at decision bar t | eligible from bar t+1 (F1); market fill at `Open[t+1]` (F2) | one H4 bar, by contract |
| 9 | Exit-leg resolution | H1 bars within each H4 span (simulate_on=H1) | engine-side; F5 stop-first applies at H1 resolution | n/a — execution convention |

No rule in this strategy reads data at or after the decision bar's close, and no context bar exists to be used early.

## 10. Ambiguities resolved

| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | "Enter long at bar close" — fill at the close of signal bar t? | Market `OrderIntent` at decision bar t, filled at `Open[t+1]` + slippage (F1/F2). Filling at the close of t is inexpressible under F1 and would bake in a zero-lag execution the contract forbids. | "Fill at `Close[t]` exactly" — inexpressible/optimistic; rejected. |
| 2 | TP/SL percentages measured from what price? | Anchored to the **decision-bar close** `A = Close[t]`, declared as absolute levels at OrderIntent creation (fleet anchoring rule). | Anchoring to the realised fill (author's pseudocode `tp=entry*1.006`) — **inexpressible**, not merely less conservative: the fill price is unknowable at emission. Realised R ≠ declared R when the t+1 open gaps/slips; F2/F6 resolve the fill honestly. |
| 3 | Short-side trigger is an INSIDE bar while the long side uses an OUTSIDE bar — mirror, or keep the asymmetry? | **Kept exactly as documented** (inside-bar shorts). The conservative rule for Wave 0 is to not invent rules; a mirrored outside-bar short is a different strategy the author did not publish, and (empirically) inside bars are LESS frequent triggers with conditions stacked, not obviously more. | Mirroring to outside-bar shorts (invents a rule); or "fixing" the asymmetry by also allowing outside-bar shorts (adds trades the author never documented). The report must carry this asymmetry verbatim so reviewers can judge whether it is intentional or a Pine-script defect. |
| 4 | HMA integer rounding for n/2 and sqrt(n) at n=27 | `floor(27/2) = 13`, `floor(sqrt(27)) = 5` — the integer-division convention of TradingView `ta.hma` and pandas-ta, i.e. what the Pine source itself computed. | Round-half-up (14, 5) — diverges from the published script's own arithmetic and is no more principled. |
| 5 | `Volume` is OANDA **tick count**, not traded volume — Klinger's "volume force" runs on a proxy | **Proceed on tick volume, flagged prominently** (here, §8, §11). DATA_AVAILABILITY explicitly sanctions this: "Tick volume is a usable proxy for activity, but say so." The sign convention (±) is driven by price direction, so the proxy's information loss is in the magnitude column only. No DATA-GAP file: the data exists; the caveat is fidelity, not availability. | Treating the strategy as having a volume-data gap and deferring it — rejected: no FX venue provides centralised traded volume, so the "gap" is unobtainable in principle for spot FX, and the available proxy is documented as usable. Substituting a synthetic volume series — no invented data. |
| 6 | EMA smoothing convention for KVO | pandas `ewm(span=n, adjust=True).mean()` — exactly the author's pseudocode (`ewm(span=34).mean()`), which is the inventory `ema` semantics. | Wilder-style `alpha=1/n` — a different oscillator from the one published; rejected as unfaithful. |
| 7 | "other FX majors" — which pairs? | The 13-pair set of contract §7 (5 live + 8 Wave-1 pending), which the contract defines as covering the CSV's "majors"/"any pair" language. No DATA-GAP: nothing requested falls outside that set (no XAU_USD, no exotics named). | Restricting to the 3 explicitly named pairs — under-coverage of a verbatim request; or adding crosses beyond the 13 (e.g. GBP_CHF) — outside the Wave-1 plan and not clearly a "major". |
| 8 | "H4 and higher" — which granularity? | **H4** — the published frame ("published on EURUSD H4"). | Running D1 as well — the source gives one parameter set and one published frame; adding a second granularity doubles the verdict cells on an untested frame and is effectively parameter exploration, which contract §10 forbids. |
| 9 | KVO signal line (EMA13) — used anywhere? | **No.** Computed but unused: the documented conditions are `KVO>0`/`KVO<0` vs zero, never vs the signal line. | Requiring `KVO` above/below its signal line as an extra gate — fewer trades (superficially "conservative") but unfaithful: it adds a condition the author never wrote, changing what the backtest measures. Rejected as invented, not conservative. |
| 10 | "Also exits on opposite entry signal (stop-and-reverse)" | **Not implemented — position runs to SL/TP only.** Contract v2 has no close-position mechanism; the strategy cannot observe fills or open positions; an opposite intent while in a position is dropped by F12, and one emitted after exit would open a NEW trade, not close the old one. | Emitting an opposite market intent at the opposite signal (opens a new/inverse position or is silently dropped — neither is "close"), or a fixed-bar time leg (invents a parameter). Consequence stated plainly: the backtest measures a strictly worse variant than the author's script — losers that the source would have cut early run to the full 1.2%/1.5% stop. A gate failure must be read with that handicap (§11). |
| 11 | Order overlap / lifecycle risk | Market intents only, `expires_after_bars = null`, `max_concurrent_positions = 1` (default). Residual risk: **none** from pending overlap (no pendings exist). Residual behaviour: while a position is open (potentially many H4 bars, given a 1.2% stop and 0.6% target), further signals are emitted and dropped at admission (F12) — this depresses trade frequency vs the author's script, which would reverse. Accepted and reported, not engineered around. | Raising F12 concurrency to emulate stop-and-reverse — non-comparable with the T6 fleet and a fiction (concurrent opposite positions are not a reversal); rejected. |

## 11. Expected behaviour

- **Trade frequency:** outside bars occur on roughly 10–20% of H4 bars on majors; the stacked conditions (directional close, KVO sign ~50/50, close vs HMA ~50/50) cut this to perhaps 1–3% of bars for longs; inside-bar shorts are somewhat rarer. Naively that is ~1–4 signals per pair per month, but F12 (one position at a time) drops every signal that fires while a trade is open, and with a 0.6–0.75% target vs a 1.2–1.5% stop on H4, many trades resolve within a day or two but some run much longer. Realistic estimate: **~10–30 trades per pair per year**; on the 5 live pairs ~50–150 trades/year → roughly **500–1,500 pooled trades over a 10-year lookback, ~100–300 per cell** — comfortably above `low_confidence` thresholds. With the 8 Wave-1 pairs backfilled, coverage roughly doubles.
- **The arithmetic that decides this strategy:** the documented bracket needs a raw win rate of **1.2/(1.2+0.6) = 66.7% (longs)** and **1.5/(1.5+0.75) = 66.7% (shorts)** just to break even before costs. After the fixed 1.5-pip entry cost (F10) — which on a ~60–75 pip round trip to TP is a further ~2–2.5% drag on the reward side — the required win rate is roughly **68–71%**. F5 (stop-first whenever one H1 bar spans both levels) is maximally punitive at this geometry: a stop twice as far as the target is touched by far more bar ranges. For this to pass the gates, the outside/inside + HMA + KVO confluence must be genuinely, strongly predictive of next-bar direction — a 2:1-accuracy edge, not a marginal one. **What would make it fail the gates:** win rate anywhere near 50–60% (negative expectancy at this RR), the missing stop-and-reverse exit (§10 row 10 — the source would cut some losers before the full stop), and cost/F5 drag stacking on the negative RR.
- **Is the author's MODERATE conviction justified by the rules as written?** The rules as written are coherent (structure + trend + activity-flow confirmation is a sensible confluence), but the author's own metadata undercuts the bracket: "risks 2x the reward per trade… needs ATR-based retuning before use", and no performance statistics are documented. MODERATE is therefore **not justified for the strategy as documented** — it is the right conviction for the *entry logic with exits to be redesigned later*, which is exactly what the author says. The v2 path per its mandate evaluates the documented bracket: a gate PASS under a negative-RR, 67%-breakeven bracket would be exceptionally strong evidence for the entry confluence (and would justify a retuned variant as a follow-on); a gate FAIL is the expected outcome and convicts the bracket more than the entry logic — the report must separate the two (e.g. by comparing with the T6 uniform-harness run of the same signals) rather than presenting a single verdict on the TradingView script.
