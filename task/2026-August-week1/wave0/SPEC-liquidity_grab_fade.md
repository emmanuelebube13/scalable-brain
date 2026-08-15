# SPEC-liquidity_grab_fade
**Source:** row 46 of forex_swing_strategies.csv · https://howtotrade.com/blog/liquidity-grab/
**Conviction (author's):** MODERATE

## 1. Hypothesis
In a trending market, stop orders cluster just beyond obvious structural zones — in this strategy's framing, the far edge of an order block — and large participants deliberately push price through those clusters to source counter-side liquidity before the trend resumes. A price excursion *through* the order block that fails to hold (a "liquidity grab") is therefore evidence of forced weak-hand liquidation, not genuine reversal: once the grab completes and price closes back beyond the order block's near edge, the path of least resistance is again with the trend. Entering on that recapture close buys/sells the exact moment the trapped breakout traders must unwind, with invalidation defined by the grab extreme itself. The edge should persist because stop-clustering around visible structure is a mechanically driven feature of leveraged FX markets, and the fade only triggers after the grab has demonstrably *failed* to become a reversal — it never front-runs the sweep ("do not be the liquidity").

## 2. Scope
- **primary_granularity:** H4 (source: "H1|H4 (article uses GBP/USD H1; rules scale to H4/D1)"; H4 chosen — §10 #6)
- **context_granularities:** none (all structure is computed on the H4 primary frame)
- **simulate_on:** H1 (fill resolution only, per contract Part D; the strategy never sees H1 data)
- **pairs_requested (verbatim):** "FX majors and minors (GBP/USD example on page)"
- **pairs_available:** EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD (live) · GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD (**pending** — Wave-1 additions, not gaps)
- **pairs_missing:** none. "Majors and minors" is fully covered by the 5 live + 8 pending pairs. Data requirements are "OHLCV only" (the "liquidity grab indicator" is explicitly optional and is mechanised here from OHLC). **No DATA-GAP file required.**

## 3. Indicators
| Indicator | Params | Source |
|---|---|---|
| Confirmed swing points (high/low) | `period=5` on H4 | `causal_structure.confirmed_swing_points(high, low, period=5)` |
| Last confirmed swing high/low level + confirmation bar | rolling, n=1 and n=2, H4 | `causal_structure.last_n_confirmed_highs` (and lows equivalent) |
| Trend state machine (BOS-based) | private, specified below | Not in inventory; fully specified in §4/§5 |
| Order block identification | private, lookback 20 H4 bars | Not in inventory; fully specified in §4/§5 |
| Liquidity-grab tracker (grab state + running grab extreme) | private, specified below | Not in inventory; fully specified in §4/§5 |
| Pip size | per pair | `indicators.get_pip_value(asset)` — 0.0001 non-JPY, 0.01 JPY |

No ATR, MA, oscillator, or volume indicator is used. The source's "liquidity grab indicator optional" is replaced by the explicit grab definition in §4/§5 (§10 #7).

**Private definitions (normative):** Let `CSH_t` = level of the most recently confirmed swing high whose confirmation bar ≤ t, and `CSL_t` the same for swing lows. A swing occurring at bar k is confirmed at bar k+5; before k+5 it does not exist for this strategy. `pip` = `get_pip_value(pair)`. All bar references are H4; all conditions evaluated at bar **close**.

## 4. Entry — long
An **episode** begins with a bullish break of structure; the episode supplies the order block that must later be grabbed and recaptured.

**Bullish BOS (episode trigger):** at bar b, `Close[b] > CSH_{b-1}` (close beyond the most recent swing high confirmed at or before b−1). This flips trend state to UP and starts episode b. Trend state stays UP until a bearish BOS (`Close < CSL` at the time) flips it DOWN. This is the mechanisation of the source's "uptrend (higher highs/higher lows)"; the pseudocode's `swing.diff()` variant is rejected in §10 #2.

**Order block (fixed at the BOS bar):** at BOS bar b, define
`k = max{ j : b−20 ≤ j ≤ b−1, Close[j] < Open[j] }`
(the most recent bearish candle in the 20 H4 bars preceding the BOS bar — the origin of the displacement). If no such j exists, the episode is void. `OB_high = High[k]`, `OB_low = Low[k]`. These are the "order block top line" and bottom line. (Alternative OB definitions rejected in §10 #3.)

**Grab (liquidity grab of sell-side stops):** the grab begins at the first bar j0 with `b+1 ≤ j0` such that `Low[j0] < OB_low` (price trades *through* the order block's bottom line — conservative deep-grab reading, §10 #4). The running **grab extreme** at bar t is
`G_t = min{ Low[j] : j0 ≤ j ≤ t }`.
If no grab occurs within **24 H4 bars** of bar b (4 trading days), the episode expires void (staleness cap, §10 #8). If trend state flips DOWN before the trigger fires, the episode is void.

**Trigger (the fade):** at decision bar t, all of:
1. Trend state = UP; current episode started at BOS bar b < t and has not expired.
2. The episode's order block exists (k found at b).
3. A grab has begun: j0 exists with `b+1 ≤ j0 ≤ t−1` (the grab must be on a *prior* bar, matching the pseudocode's `grab.shift(1)`).
4. `Close[t] > OB_high` — the first such close since j0: no bar in `[j0, t−1]` had `Close > OB_high` (edge-trigger: exactly one OrderIntent per episode).
5. The TP level exists (see §7): there is a confirmed swing high with confirmation bar ≤ t and level > `Close[t]`.

- **entry type:** `market` (fill at the open of bar t+1, F1/F2 — the source's "enter when price closes back above the order block top line" is acted on at the first opportunity after the confirming close)
- **entry level:** none (market); all stop/TP geometry is anchored to decision-bar-knowable prices (`Close[t]`, `OB_high`, `G_t`) per the decision-bar anchoring rule
- **expires_after_bars:** **null** (not applicable to market entries; the intent fills at t+1 open or is not admitted under F12)

## 5. Entry — short
Full mirror of §4.

**Bearish BOS:** at bar b, `Close[b] < CSL_{b-1}`. Flips trend state to DOWN, starts episode b.

**Bearish order block:** `k = max{ j : b−20 ≤ j ≤ b−1, Close[j] > Open[j] }` (most recent bullish candle in the 20 bars before the BOS bar). If none, episode void. `OB_high = High[k]`, `OB_low = Low[k]`.

**Grab (buy-side stops above the bearish resistance OB):** first bar j0 ≥ b+1 with `High[j0] > OB_high` (trade through the OB top — matches the pseudocode's `grab = high > ob_top`). Running grab extreme `G_t = max{ High[j] : j0 ≤ j ≤ t }`. Same 24-bar staleness cap; episode void if trend flips UP first.

**Trigger:** mirrors §4: trend DOWN, OB exists, j0 ∈ (b, t−1], `Close[t] < OB_low` (first close back below the OB bottom line since j0 — matches the pseudocode's `trigger = grab.shift(1) & (close < ob_bot)`), no bar in [j0, t−1] closed below OB_low, and a confirmed swing low below `Close[t]` exists for TP.

- **entry type:** `market` · **entry level:** none · **expires_after_bars:** **null**

Note the source's asymmetry is preserved: the long grab breaches the OB *bottom* and recaptures the *top*; the short grab breaches the OB *top* and recaptures the *bottom*. Both require a full traverse of the zone (§10 #4).

## 6. Stop
- **Initial stop (long):** `stop.price = G_t − 4.0·pip`, where `G_t` is the running grab extreme at decision bar t. "SL below the grab low" with a declared buffer of **3.0 pips + the 1.0-pip cost-model spread constant** as the spread-buffer proxy (no real spread series exists — flagged in §8 and §10 #5).
- **Initial stop (short):** `stop.price = G_t + 4.0·pip` ("SL just above the liquidity grab high"; pseudocode `sl = grab_high.max() + spread_buffer`).
- **move_to_breakeven_on:** **none** (single-leg structure; "move to breakeven after first target **if scaling out**" is conditional on scaling, which the conservative structure omits — §10 #9).
- **trail:** **none** (not in source).

`stop.price` is an absolute, declarable value at OrderIntent creation: `G_t` is decision-bar data (min/max of Low/High over bars ≤ t). Side check: long stop < `OB_low` ≤ `OB_high` < `Close[t]`; short mirror — the stop is always on the correct side of the decision close.

## 7. Exit legs
| Label | Fraction | Kind | Level formula |
|---|---|--:|---|
| TP1 | 1.0 | take_profit | Long: `L_tp` = level of the nearest **confirmed** swing high with confirmation bar ≤ t and `L_tp > Close[t]`. Short: nearest confirmed swing low with confirmation bar ≤ t and `L_tp < Close[t]`. **If no such confirmed opposite swing exists, no OrderIntent is emitted** (the setup is skipped, not re-targeted — "TP at next swing high/low" requires a swing that is knowable). |

Fractions sum to 1.0 (single leg). No RR floor is applied — the source specifies none for this strategy (§10 #10). TP uses the decision close as the reference (not the unknowable fill): if the market gaps up at t+1 open past `L_tp`, F3/F6-style honest resolution applies and realised R < declared R — recorded, not preventable for market entries.

## 8. Filters
- **Trend filter (BOS state machine):** evaluated on H4; the BOS at bar b is knowable at the close of bar b (its input swing was confirmed at bar ≤ b−1). No order while trend state is NONE (before the first BOS) or opposing the trade direction; a mid-episode trend flip voids the episode.
- **Grab precondition:** evaluated on H4; knowable at the close of grab bar j0 ≤ t−1. This is also the source's risk rule "avoid entering before the grab completes" — the trigger cannot fire on the grab bar itself (condition 3 forces j0 ≤ t−1, and the trigger requires a *recapture* close).
- **No session, news, volatility, or volume filter** exists in the source; none is added. The `Volume` column (OANDA tick count) is not used.
- **Spread buffer proxy (flagged per fleet rule 5):** the pseudocode's `spread_buffer` cannot use a real spread series — none exists. The 1.0-pip spread constant of the cost model (F10) is declared as the spread buffer inside the 4.0-pip stop offset. Flagged here, in §6, and in §10 #5. This is a declared constant, not a silent proxy for a data feed.

## 9. Causality audit
| Rule | Inputs fully known at | Confirmation lag |
|---|---|---|
| Swing high/low at occurrence bar k | close of bar **k+5** (period=5, H4) — stamped at confirmation per `causal_structure` | **5 H4 bars** (~20 trading hours) |
| Bullish/bearish BOS at bar b | close of bar b — uses `Close[b]` and a swing level confirmed at bar ≤ b−1 | ≥ 5 H4 bars after the broken swing's occurrence |
| Order block identification (k, OB_high, OB_low) | close of BOS bar b — OB exists only once the BOS prints; references candles at bars ≤ b−1 | compounds: ≥ 5 H4 bars after the broken swing's occurrence, plus the time the BOS took to print |
| Grab bar j0 (breach of OB far edge) | close of bar j0 — `Low[j0]`/`High[j0]` are bar-j0 data; the breached OB edge was fixed at b with the compounding lag above | OB edge lags its own candle by ≥ 5 H4 bars (via the BOS chain) |
| Running grab extreme `G_t` | close of decision bar t — min/max over bars j0..t, all ≤ t | none beyond bar t |
| Trigger (first recapture close beyond OB near edge) | close of decision bar t — `Close[t]`, `OB_high`/`OB_low` fixed at b | trigger fires at best 5+ H4 bars after the swing whose break defined the episode |
| TP level `L_tp` | close of decision bar t — swing must be *confirmed* at bar ≤ t | the TP target lags its occurrence by **5 H4 bars**; it is always historical structure, never a future swing |
| Stop level | close of decision bar t (`G_t ± 4.0·pip`) | — |
| Entry fill | open of bar t+1 (F1/F2) | 1 H4 bar after decision |
| H1 usage | none — the strategy never sees H1; H1 resolves fills only (contract Part D) | — |

The full compounding chain for a single long trade: swing high occurs at bar s → confirmed at s+5 → BOS at b > s+5 → OB fixed at b (candle k ≤ b−1) → grab bar j0 > b → recapture close at t > j0 → market fill at t+1 open. Every swing, OB edge, grab extreme, and TP target used is knowable at or before the bar that uses it. No centred window, no `shift(-1)`, no future swing is ever read. The pseudocode's `swing_hi`/`swing_lo` are mapped to `causal_structure` outputs (the source sketch inherits the standard centred-window problem class; §10 #1).

## 10. Ambiguities resolved
| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | The pseudocode's `swing_hi`/`swing_lo` are unspecified; the standard sketch implementation is a centred rolling window (the BANNED look-ahead pattern) | `causal_structure.confirmed_swing_points(period=5)` on H4; swings knowable only 5 bars after occurrence; TP and trend/BOS inputs all use confirmation-stamped swings | Any centred-window or "act at occurrence bar" reading — look-ahead, inexpressible |
| 2 | Trend definition: prose says "higher highs/higher lows"; pseudocode says `(swing_hi.diff()<0) & (swing_lo.diff()<0)` | BOS-based trend state machine (one close beyond the most recent confirmed swing flips state), consistent with the sibling spec liquidity_sweep_ob and with HH/HL structure | The pseudocode's two-consecutive-confirmed-swings diff — a *slower* trend detector, but it needs a second confirmed swing before any trend exists, voiding early episodes and diverging from the prose; rejected to keep one coherent episode model (recorded: this choice yields slightly *more* trades; the diff variant remains a valid sensitivity test for Wave 2) |
| 3 | Order-block marking is semi-discretionary in the source ("coding needs explicit OB definitions") — which candle, which edges | The most recent opposite-colour candle in the 20 H4 bars before the BOS bar, edges = its full High/Low (the widest reading of the zone: a wider OB is *harder* to traverse and recapture → fewer triggers) | Candle body edges (Open/Close) — narrower zone, easier recapture, more trades; "last down candle before the grab" — a moving, re-anchored zone that can retrofit itself to whatever just happened |
| 4 | "Price dips below the bullish OB" — how deep is the grab? | Full traverse required: `Low[j0] < OB_low` for longs (breach of the far edge), and the trigger requires a close back beyond the *near* edge (`Close[t] > OB_high`) — the deepest grab and the strongest recapture reading → fewest, latest entries | Grab = any trade below `OB_high` (into the zone), or trigger = close back above `OB_low` (re-entering the zone) — both fire earlier and far more often; the long/short asymmetry in the pseudocode (`high > ob_top` / `close < ob_bot`) confirms the full-traverse reading |
| 5 | "SL below the grab low" / `spread_buffer` — how big a buffer, and what spread? | 3.0 pips + 1.0-pip cost-model spread constant = 4.0 pips beyond the running grab extreme (wider stop = worse R, conservative); spread is a declared-constant proxy, flagged in §8 | 0–1 pip buffer (tighter stop flatters expectancy); any real-spread series (does not exist) |
| 6 | Timeframe: "H1\|H4 (article uses GBP/USD H1)" | **H4 primary.** Stop-hunt fades on H1 suffer the most false recaptures (H1 closes whip across OB edges constantly); H4 requires a 4-hour close to confirm the recapture → fewer, later, more structural signals (conservative). simulate_on = H1 for fill honesty either way | H1 primary (the article's example): ~4× the signals, earlier entries, but a different false-grab regime; rejected under the fewer-trades rule. Recorded as a legitimate Wave-2 sensitivity cell, not the spec |
| 7 | "Liquidity grab indicator optional" | Omitted entirely; the grab is defined mechanically from OHLC (§4/§5) | Depending on an unspecified external indicator that does not exist in the data |
| 8 | Episode lifetime unspecified — an OB could be grabbed months after the BOS | Episode expires void if no grab begins within **24 H4 bars** (4 trading days) of the BOS, or on trend flip — stop-hunt setups are short-lived phenomena | Unbounded episode (stale OB grabbed in a later regime, contradicting the setup's premise); a shorter cap (8 bars) would discard valid slow-developing grabs |
| 9 | "Move to breakeven after first target **if scaling out**" | No scaling out: single 100% TP leg at the next confirmed opposite swing, `move_to_breakeven_on = none`. Simpler, and avoids the F8 late-protection subtlety; the conditional clause is not triggered because we do not scale out | Two-leg 0.5/0.5 with TP1 at 1R + breakeven move on TP1 and TP2 at the swing — adds a target the source never defines ("first target" has no level) and a BE move whose protection arrives a bar late under F8 |
| 10 | TP at "next swing high/low" — which swing, and is there an RR floor? | Nearest **confirmed** opposite swing strictly beyond `Close[t]`; if none exists, **skip the trade**. No RR floor (the source specifies none for this row — unlike its sibling) | Nearest swing of any confirmation status (look-ahead); a fixed-RR fallback target (invents a level price never validated); importing the sibling's RR ≥ 2 filter (not in this row's text) |
| 11 | Market entry means the fill price is unknowable at emission (fleet rule — decision-bar anchoring) | All geometry anchored to decision-bar-knowable prices: stop to `G_t`, TP referenced against `Close[t]` (the nearest confirmed swing *above/below the decision close*, not above the fill). Realised R ≠ declared R when the t+1 open gaps (F2/F3 resolve honestly) | Fill-anchored geometry (stop = fill − x, TP = nearest swing above fill) — inexpressible at OrderIntent creation, not merely less conservative |
| 12 | Re-emission and concurrency: contract v2 has **no OCO, no cancel-on-fill, no supersede**; F12 caps concurrent *positions* (default 1) but does **not** gate pending fills | Edge-trigger: exactly one OrderIntent per episode (condition 4's "first recapture close" and one episode per BOS), and all entries are `market` — no pendings exist, so the pending-overlap hole cannot open. **Residual risk, recorded:** if an opposite-direction episode triggers while the prior position is still open, §3.2 step 6 admits new intents "subject to F12" — the conservative reading is that admission of the second market intent is blocked while a position is open (T6-matching 1-position behaviour). If the engine instead admits it, two concurrent opposite positions result; direction of bias: **more** exposure than the 1-position baseline, with hedged (partially offsetting) P&L but doubled cost drag (2× spread+slippage). The strategy does not raise `max_concurrent_positions`; the report must state the realised concurrency | Claiming "a new opposite signal closes/supersedes the open position" — that mechanism does not exist in contract v2 |

## 11. Expected behaviour
- **Trade frequency:** low-to-moderate. The chain — BOS → OB → full traverse of the OB (grab) within 24 bars → first 4-hour recapture close beyond the near edge → confirmed opposite swing beyond the decision close — is a long conjunction on H4. Expect roughly **2–5 filled trades per pair per month**, more than the sibling continuation strategy (the fade needs no limit-pullback fill and no RR floor), fewer than a raw breakout system. Across 13 pairs this yields an adequate pooled OOS count; single-pair cells may still trip `low_confidence`.
- **What makes it fail the gates:** (a) per-cell trade counts too thin; (b) the 5-bar swing-confirmation lag plus the BOS chain means the OB is always stale structure — in fast reversals the "grab" is actually a genuine trend change, the recapture never comes, and in slow grinds the recapture close arrives so late that the confirmed TP swing is nearby, capping R; (c) F5 (stop-before-target) bites when the recapture bar is large: an H1-resolution gap back through the OB can touch the 4-pip-buffered stop in the same move; (d) losing trades cluster exactly when the trend-flip void rule fires too late — the strategy's structural weakness is that a grab *is* what a real reversal looks like for its first bars.
- **Author's conviction (MODERATE):** justified by the rules as written. The trigger (failed grab + recapture close) is genuinely objective and the invalidation is structural, and the "do not be the liquidity" rule is correctly enforced by the j0 ≤ t−1 lag. But the page documents no backtest, order-block marking is semi-discretionary (here forced into one mechanical definition of several plausible ones), and the honest causal implementation — confirmation lags compounding across swing → BOS → OB → grab → recapture — strips out the visual hindsight that makes stop-hunt charts look compelling. Expect the causal H4 version to trade less often and less prettily than the blog examples.
