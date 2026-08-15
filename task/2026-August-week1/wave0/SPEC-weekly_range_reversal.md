# SPEC-weekly_range_reversal
**Source:** row 27 of forex_swing_strategies.csv · https://forex-station.com/simple-trading-system-t8476248.html
**Conviction (author's):** MODERATE

## 1. Hypothesis
On a two-week horizon, FX prices spend most of their time ranging (the author claims ~80%), so when price reaches the outer eighth of its trailing two-week range while the ultra-long CCI(2000) shows momentum has washed out to a stretched extreme and is now turning back, the odds favour reversion toward the middle of that range rather than an immediate range breakout. The edge should persist because breakout attempts at fortnightly extremes fail more often than they succeed in non-trending regimes, and because the 2000-period CCI — an ~4-month momentum average — filters out noise-level dips so that only genuinely stretched moves are faded; the enforced minimum 1:2 reward:risk means the strategy can be wrong more often than right and still profit.

## 2. Scope
- **primary_granularity:** H1
- **context_granularities:** none (the "two-week range" is computed on H1 bars directly, 336 bars; no MTF alignment required)
- **simulate_on:** H1 (native; fills resolved on the decision frame)
- **pairs_requested (verbatim):** `GBPCAD|GBPUSD|Other ranging major/minor pairs`
- **pairs_available:**
  - `GBP_USD` — live
  - "Other ranging major/minor pairs" mapped to the live universe: `EUR_USD`, `USD_JPY`, `AUD_USD`, `USD_CAD` — live
  - Ranging minors among Wave-1 additions: `EUR_GBP`, `EUR_AUD`, `AUD_NZD`, `EUR_CAD`, `USD_CHF` — **pending** (Wave 1; harness skips if history insufficient)
  - `GBP_JPY`, `EUR_JPY`, `NZD_USD` — pending, admissible under "other ranging pairs" though trendier; included for completeness
- **pairs_missing:** `GBP_CAD` (the author's headline pair) — **not** live and **not** in the Wave-1 addition list → see DATA-GAP-weekly_range_reversal.md

## 3. Indicators
| Indicator | Params | Source |
|---|---|---|
| CCI | period = 2000 (single declared value, midpoint of the author's "1800–2200 overlay"; see §10 #2) | inventory `cci(high, low, close, period)` |
| Two-week rolling high | `hi2w[t] = max(High[t-335 … t])`, 336 H1 bars = 2 × 168, window ends at and includes the (closed) decision bar | derivable: rolling max on H1 `High`; pseudocode: `df['high'].rolling(336).max()` |
| Two-week rolling low | `lo2w[t] = min(Low[t-335 … t])`, 336 H1 bars | derivable: rolling min on H1 `Low` |
| Range / zone levels | `rng[t] = hi2w[t] - lo2w[t]`; `zone_lo[t] = lo2w[t] + 0.125*rng[t]`; `zone_hi[t] = lo2w[t] + 0.875*rng[t]`; `mid[t] = lo2w[t] + 0.50*rng[t]` | derivable arithmetic ("Fibonacci/Gann percentage levels 12.5%/50%/87.5%" — pure price ratios, no external data) |
| Pip size | per pair, for the 1-pip stop buffer | inventory `get_pip_value(asset)` |

`RSI(1)` appears in the CSV `data_requirements` but in no entry/exit sentence and not in the pseudocode; it is **dropped** (§10 #8). No swing-point, ZigZag, pivot, or fractal detection is used anywhere in the adopted rules (the discretionary CCI trendline that would have needed it is rejected, §10 #1), so `causal_structure` is not required.

## 4. Entry — long
All conditions evaluated at the **close of decision bar t** (H1); every input is fully known at that instant (see §9).

1. **Warm-up:** at least 2000 completed H1 bars of history exist (CCI(2000) defined; this dominates the 336-bar range warm-up).
2. **Zone:** `Close[t] <= zone_lo[t]` (close in the bottom 12.5% of the trailing 2-week range).
3. **CCI cross (trigger):** `CCI[t] > 10 AND CCI[t-1] <= 10` — CCI closes back up through the 10 level on the decision bar.
4. **CCI touch (arming):** `min(CCI[t-24 … t-1]) <= 5` — CCI touched the 5 level within the prior 24 H1 bars (one trading day; §10 #9).
5. **Weekly throttle:** no OrderIntent has previously been emitted for this pair with a decision_bar in the same FX week (week opens Sunday 21:00 UTC; §10 #7).
6. **RR gate:** with anchor `A = Close[t]`, stop `SL = lo2w[t] - 1.0*pip`, target `TP = lo2w[t] + 0.50*rng[t]`: emit only if `TP - A >= 2*(A - SL)`. If violated, **no order is emitted** (§10 #4).

- **entry type:** `market` (the author: "enter Long at next candle open"; contract F2 fills at the open of bar t+1)
- **entry level:** none declared (market); all stop/TP geometry anchored to decision-bar knowable prices `Close[t]`, `lo2w[t]`, `rng[t]` (fleet rule 8)
- **expires_after_bars:** null (market entry; fills at t+1 open or never — no pending order exists, so no multi-fill overlap is possible)

## 5. Entry — short
Mirror of §4 (strategy is symmetric; both directions traded):

1. **Warm-up:** ≥ 2000 completed H1 bars.
2. **Zone:** `Close[t] >= zone_hi[t]` (close in the top 12.5% of the trailing 2-week range).
3. **CCI cross:** `CCI[t] < 90 AND CCI[t-1] >= 90` — CCI closes back down through 90.
4. **CCI touch:** `max(CCI[t-24 … t-1]) >= 95` within the prior 24 H1 bars.
5. **Weekly throttle:** same shared per-pair weekly slot as §4.5 (one setup per week per pair, either direction).
6. **RR gate:** with `A = Close[t]`, `SL = hi2w[t] + 1.0*pip`, `TP = lo2w[t] + 0.50*rng[t]`: emit only if `A - TP >= 2*(SL - A)`; else no order.

- **entry type:** `market`; **entry level:** none; **expires_after_bars:** null.

## 6. Stop
- **Initial stop (long):** `StopRule.price = lo2w[t] - 1.0 * pip_size(pair)` — 1 pip beyond the 2-week low, the "extreme of the reversal zone" (§10 #5).
- **Initial stop (short):** `StopRule.price = hi2w[t] + 1.0 * pip_size(pair)`.
- **move_to_breakeven_on:** none.
- **trail:** none (static stop; the author: "walk away and let TP/SL execute").

## 7. Exit legs
| Label | Fraction | Kind | Level formula |
|---|---|---|---|
| TP1 | 1.0 | take_profit | `price = lo2w[t] + 0.50 * rng[t]` (50% of the 2-week range, measured from its low, fixed at the decision bar) |

Fractions sum to 1.0. Single leg, so §3.2 F7 multi-leg sequencing never engages. The author's "62.5% (or 50%)" is resolved to 50% (§10 #3). No time exit: "re-set levels the following weekend" governs *new setups*, not open positions — an open trade runs to TP or SL however long that takes (§10 #6).

## 8. Filters
- **Zone filter** (§4.2/§5.2): evaluated on H1 at the decision bar; knowable at its close. This is the strategy's only trend/regime gate — it fades range edges, so it implicitly requires ranging conditions.
- **Weekly emission throttle** (§4.5/§5.5): evaluated on H1 decision-bar timestamps; the FX week boundary (Sunday 21:00 UTC) is calendar-known in advance.
- **RR floor** (§4.6/§5.6): evaluated at decision-bar close from decision-bar prices.
- **No session, news, volatility, or macro filter exists in the source** — and none could be added: no calendar, rates, or sentiment feeds exist (DATA_AVAILABILITY.md, "Non-price data — none of it exists"). Volume is OANDA tick count and is not used by this strategy.

## 9. Causality audit
| Rule | Inputs fully known at | Notes |
|---|---|---|
| `hi2w`/`lo2w`/`rng`/zones (§4.2, §5.2) | Close of decision bar t | Rolling 336-bar window ends at bar t inclusive; bar t is complete at decision time. No future data. **Confirmation lag: none** — these are trailing extrema, not swing pivots; the level `lo2w[t]` may *move* as new lows print, which is causal (a trailing window, not a centred one). |
| CCI(2000) value (§4.3, §5.3) | Close of bar t | Uses bars t-1999…t. First usable value at bar index 1999. |
| CCI cross 10/90 (§4.3, §5.3) | Close of bar t | Compares CCI[t] vs CCI[t-1]; both closed bars. |
| CCI touch 5/95 within 24 bars (§4.4, §5.4) | Close of bar t | Window t-24…t-1, all closed. |
| Weekly throttle (§4.5) | Emission time | Strategy-internal state: whether an intent was already emitted this FX week. Backward-looking only. |
| RR gate (§4.6) | Close of bar t | Arithmetic on `Close[t]`, `lo2w[t]`, `rng[t]`, declared pip buffer. |
| Market entry fill | Open of bar t+1 | F1/F2: emitted at close of t, fills at open of t+1 with adverse slippage; geometry anchored to t-close prices. |
| Stop / TP levels | Close of bar t | Absolute prices declared at OrderIntent creation; never re-anchored to the fill (realised R ≠ declared R if the t+1 open gaps — F3/F6 resolve honestly). |
| Discretionary CCI trendline | — | **Rejected** (§10 #1). Had it been kept, each CCI peak would have been knowable only `period` bars after occurrence (`confirmed_swing_points` lag), and the break test only at a closing bar; the adopted 10/90 cross needs no peaks and has zero confirmation lag. |
| Weekend re-marking | — | The author's "mark levels over the weekend" is implemented as the rolling 336-bar window (§10 #10); the market is closed Friday 21:00→Sunday 21:00 UTC, so no H1 decision occurs over a weekend anyway. |

No multi-timeframe context is used, so the §4 MTF rule (context bar must have closed) does not apply; the single frame is the decision frame.

## 10. Ambiguities resolved
| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | "Draw a trendline across the last 2 CCI peak highs / trough lows and enter when CCI breaks through it" — discretionary, no peak definition, no line-construction rule | Replaced by the CSV pseudocode's mechanical rule: enter on the CCI close crossing 10/90 after a 5/95 touch (§4.3–4.4). No trendline, no peaks, no confirmation lag. | Mechanizing the trendline via `causal_structure.confirmed_swing_points` on CCI — rejected: adds a confirmation-lagged, parameter-heavy construct the pseudocode itself omits; the simpler rule is both more conservative in intent (later, cleaner trigger) and fully reproducible. |
| 2 | CCI period given as a range "1800–2200 overlay" | Single declared value **2000** (midpoint). Contract §10 forbids parameter sweeps, so one number must be chosen; midpoint avoids cherry-picking an endpoint. | 1800 (faster, more signals — more trades, less conservative) or 2200. |
| 3 | TP = "62.5% (or 50%)" of the 2-week range | **50%** — lower target, smaller winners per trade; the less flattering reading of realised r-multiples. | 62.5% — larger winners, higher per-trade expectancy if hit; rejected as the more generous reading. |
| 4 | "never less than 1:2 reward:risk" when the 50% target fails the RR floor against the zone-edge stop | **Skip the trade** — emit no OrderIntent (fewer trades). | Raising TP to the 2R level (or to 62.5%) until the floor passes — rejected: inflates winners by stretching targets beyond the documented level. |
| 5 | Stop "just beyond the extreme of the reversal zone" — "just" undefined | 1.0 pip beyond `lo2w`/`hi2w`, sized with `get_pip_value(pair)` — deliberately the tightest reading of "just" that is still strictly *beyond* the extreme; tightest stop = most stop-outs = most pessimistic. | 0.5×ATR(14) buffer (wider, fewer stop-outs, kinder results); exactly-at-the-extreme (contradicts "beyond"). |
| 6 | "re-set levels the following weekend" — does an open position force-close at week end? | **No time exit.** "Walk away and let TP/SL execute" is literal; the weekly reset applies to marking levels for *new* setups (and the throttle). An open trade may outlive its week with its entry-week TP/SL frozen. | Force-close at Friday 21:00 UTC (time leg) — rejected: invented exit not stated in the source; also truncates the winners the 1:2 floor is designed to harvest. |
| 7 | "one setup per week per pair" — per direction or total? | **Total per pair:** one emitted OrderIntent per FX week per pair regardless of direction (fewer trades). | One long AND one short per week per pair — rejected as doubling the documented frequency. |
| 8 | `RSI(1)` listed in data_requirements | **Dropped** — absent from every entry/exit sentence and from the pseudocode; an RSI of period 1 is degenerate (±100 on up/down closes) and cannot gate anything meaningful. | Wiring RSI(1) as an extra gate — rejected: unimplementable as a meaningful filter and nowhere described. |
| 9 | "CCI has touched the 5 level" — over what lookback? | Touch must occur within the **trailing 24 H1 bars** (one trading day) before the cross — a short, declared window producing fewer, fresher setups. | "Any time since price entered the zone" (stateful, unbounded — more trades); the pseudocode's same-bar reading (logically impossible: CCI≤5 and CCI>10 cannot both hold at t). |
| 10 | "Over the weekend mark the last 2 weeks' high and low" — frozen weekly levels vs rolling | **Rolling 336-bar window recomputed at each H1 decision bar** (the pseudocode's own construction; fully causal as a trailing window). | Calendar-week-frozen levels (2×120 H1 bars fixed each Sunday 21:00 UTC) — rejected: not what the pseudocode does; frozen levels go stale mid-week and admit entries against a range that has already broken, an untestable judgement call either way. |
| 11 | R measured from the fill | Geometry anchored to the **decision close** (fleet rule 8); `OrderIntent` carries absolute stop/TP prices knowable at emission. Realised R ≠ declared R when the t+1 open gaps. | Fill-anchored stops/targets — rejected as **inexpressible** in contract v2, not merely less conservative. |

## 11. Expected behaviour
- **Trade frequency:** bounded by the throttle at ~52/pair/year; realistically **~10–35 trades/pair/year**. The zone condition (close in the outer 12.5% of a trailing 2-week range) is the binding gate; the CCI gates are weak by construction — on a 2000-period CCI, 5/10/90/95 sit near the zero line, so touches and crosses are common whenever price is at a range edge. Across 5 live + up to 8 pending pairs the pooled sample is healthy (hundreds of trades over 10 years), but per-cell counts on any single pair may brush `low_confidence`.
- **Warm-up cost:** CCI(2000) needs 2000 H1 bars ≈ 16.7 trading weeks ≈ **4 months** before its first value; the 336-bar range needs 2 more weeks beyond nothing. With 36-month anchored train folds (walk_forward.py), the first ~4 months of each fold are signal-dead; OOS cells are unaffected once history is warm. Over 10 years of H1 (~62k bars) this is a ~6% data tax, stated here so fold-level reports do not misread the silent opening months as a dead strategy.
- **What would make it fail the gates:** (a) sustained trending regimes — the strategy fades fortnightly extremes with a stop only 1 pip beyond them, so a real breakout produces a full loss each time, throttled to one per week; (b) F5 (stop-before-target on the same H1 bar) — TP and the 2-week extreme are frequently both inside one violent bar's range at range edges, and the engine always awards the stop; (c) weekend gaps (F6) blowing through a stop parked just past a 2-week extreme, producing losses > 1R that r-multiple gates see directly; (d) the weak CCI gates mean the strategy is effectively "fade the 2-week range edge once a week," an edge many pairs will not have after the 1.0-pip spread + 0.5-pip slippage cost (F10).
- **Is the author's MODERATE conviction justified by the rules as written?** Broadly yes. The documented core (zones, weekly throttle, 1:2 floor, fixed geometric exits) is fully mechanical and survives faithful translation; the one discretionary element (CCI trendline) had a mechanical pseudocode fallback, which this spec adopts. But no backtest is documented on the thread, the CCI momentum confirmation is so loose it adds little selectivity, and the entire edge rests on the "~80% ranging" claim holding per pair — a regime assumption the strategy itself cannot verify. MODERATE, neither upgraded nor downgraded.
