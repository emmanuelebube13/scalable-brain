# SPEC-inside_bar_reversal
**Source:** row 25 of forex_swing_strategies.csv · https://www.earnforex.com/forex-strategy/inside-bar-strategy
**Conviction (author's):** MODERATE

## 1. Hypothesis
An inside bar that forms against the prevailing trend, after a mature directional move, marks a volatility contraction and order-flow exhaustion: the counter-trend container bar has spent the last directional push, and the inside bar's failure to make a new trend extreme shows the dominant side can no longer attract follow-through. Traders positioned with the trend take profits and late entrants are trapped, so price mean-reverts toward the nearest structural level (the last confirmed swing in the reversal direction) more often than chance. The edge should persist because it rests on durable behavioural mechanics — profit-taking after extended moves and the informational content of range contraction — rather than on any fragile parameter.

## 2. Scope
- **primary_granularity:** D1. The source offers "D1|H4 (site allows any bare-bar chart; use swing timeframes)". D1 is chosen as primary because (a) the strategy's edge is multi-day profit-taking, which D1 resolves more cleanly than H4; (b) the author warns the pattern is rare — H4 would multiply signals but dilute the "clearly visible trend" precondition; (c) D1 is the conservative reading (fewer, slower trades).
- **context_granularities:** none. This is a single-timeframe strategy; the trend filter, pattern, stop, and target are all computed on the decision frame. No MTF causality exposure (§4 of the contract does not apply).
- **simulate_on:** H1 (contract §5 — decided on D1, fills resolved on H1 bars).
- **Also evaluated on:** H4 as a second per-cell granularity (the source names both; per contract §8, verdicts are per (pair × granularity) anyway, so H4 is run as its own cells with primary-granularity logic unchanged).
- **pairs_requested (verbatim):** "Any currency pair".
- **pairs_available:** EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD (live); GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD (Wave-1 additions — **pending**; harness skips pairs with insufficient history).
- **pairs_missing:** none. XAU_USD is not named by this row. No DATA-GAP file is required: OHLCV is the strategy's entire stated requirement ("Standard OHLCV candlestick data only (no indicators)") and that exists for the full pair universe.

## 3. Indicators
| Indicator | Params | Source |
|---|---|---|
| Trend slope `tr` | `tr[t] = mean( close[i] - close[i-10] for i in [t-4 .. t] )` — i.e. `close.diff(10).rolling(5).mean()` exactly as in the CSV pseudocode | private, fully specified here (pure pandas shift/rolling, causal; not added to shared inventory per INDICATOR_INVENTORY rule) |
| Candle colour | `bullish(b) := Close[b] > Open[b]`; `bearish(b) := Close[b] < Open[b]` | raw OHLC, no indicator |
| Inside-bar relation | strict inequalities on raw High/Low (§4) | raw OHLC, no indicator |
| Confirmed swing highs / lows | `confirmed_swing_points(high, low, period=5)`, consumed via `last_n_confirmed_highs` / equivalent rolling access | `causal_structure` (Wave-1 module; the BANNED `detect_swing_points` MUST NOT be used) |
| ATR(14) | — | **not used** (no ATR-based stop, trail, or filter in this strategy) |

## 4. Entry — long
Decision bar = bar `t` (signal evaluated at the close of bar `t`; bar `t-1` is the "container bar"). ALL conditions must hold:

1. **Trend precondition (downtrend):** `tr[t] < 0`, with `tr` as defined in §3 (smoothed 10-bar close difference, mean over the last 5 values).
2. **Container bar is bearish:** `Close[t-1] < Open[t-1]`.
3. **Inside bar (strict):** `High[t] < High[t-1]` **AND** `Low[t] > Low[t-1]`. Equal extremes fail the pattern (strict inequality, exactly as the source states).
4. **Inside bar is bullish:** `Close[t] > Open[t]`.
5. **TP level exists (declarability gate):** there exists at least one confirmed swing high with level **strictly above** `Close[t]`, where "confirmed" means a swing high occurring at some bar `k` with confirmation bar `k+5 <= t` (level = `High[k]`). If none exists, NO order is emitted (see §10 #5).

- **entry type:** `market`
- **entry level:** none declared (`entry_price = None`); fills at the open of bar `t+1` per F2.
- **expires_after_bars:** `null` (not applicable to market entries; the intent is live only for the bar `t+1` admission step per §3.2 step 6).
- **size_fraction:** 1.0.

## 5. Entry — short
Exact mirror. All conditions must hold at decision bar `t`:

1. **Trend precondition (uptrend):** `tr[t] > 0`.
2. **Container bar is bullish:** `Close[t-1] > Open[t-1]`.
3. **Inside bar (strict):** `High[t] < High[t-1]` **AND** `Low[t] > Low[t-1]`.
4. **Inside bar is bearish:** `Close[t] < Open[t]`.
5. **TP level exists:** at least one confirmed swing low with level **strictly below** `Close[t]`, confirmation bar `k+5 <= t` (level = `Low[k]`). If none exists, NO order is emitted.

- **entry type:** `market`; **entry level:** none (F2, open of `t+1`); **expires_after_bars:** `null`; **size_fraction:** 1.0.

## 6. Stop
- **Initial stop (long):** `stop.price = Low[t-1]` (Low of the container bar) — an absolute value fully knowable at decision bar `t`.
- **Initial stop (short):** `stop.price = High[t-1]` (High of the container bar).
- **move_to_breakeven_on:** `none`.
- **trail:** `none` (static stop).
- Declared R is anchored to the decision bar: risk basis = `|Close[t] - stop.price|`. The engine computes realised R from the actual fill (contract §3.3), which differs from declared R when bar `t+1` gaps (F6 resolves honestly); see §10 #4.

## 7. Exit legs
| Label | Fraction | Kind | Level formula |
|---|---|--:|---|
| TP1 | 1.0 | take_profit | **Long:** `price = min{ High[k] : High[k] > Close[t], swing high at k confirmed by bar t (k+5 <= t) }` — the nearest confirmed swing-high level strictly above the decision close. **Short:** mirror, `max{ Low[k] : Low[k] < Close[t], k+5 <= t }` |

Fractions sum to 1.0 (single leg). No minimum reward:risk filter is applied — the source specifies none and none is invented (§10 #3). The TP level can occasionally sit only marginally beyond entry or very far away; the trade is taken as written in both cases (subject only to the existence gate, §4/§5 condition 5).

## 8. Filters
| Filter | Rule | Timeframe | Knowable at |
|---|---|---|---|
| Trend direction | `tr[t] < 0` required for longs, `tr[t] > 0` for shorts (§3) | decision frame (D1 or H4) | close of decision bar `t` (uses closes `t-14 .. t` only) |
| Session / time-of-day | none | — | — |
| Volatility | none | — | — |
| News / calendar | none (no such data exists; the source does not request it) | — | — |
| TP-existence gate | at least one confirmed counter-level in the trade direction (§4/§5 condition 5) | decision frame | close of decision bar `t` (confirmation lag already embedded) |

## 9. Causality audit
| Rule | Inputs | Fully known at | Confirmation lag |
|---|---|---|---|
| Trend filter `tr` | closes of bars `t-14 … t` | close of bar `t` | **0 bars** |
| Container-bar colour | OHLC of bar `t-1` | close of bar `t-1` (hence by `t`) | **0 bars** relative to decision |
| Inside-bar relation (strict High/Low comparison) | OHLC of bars `t` and `t-1`, both closed | close of bar `t` | **0 bars** — confirmed: the 2-bar pattern carries no lag; no future bar is consulted |
| Inside-bar colour | OHLC of bar `t` | close of bar `t` | **0 bars** |
| Stop level | `Low[t-1]` / `High[t-1]` | close of bar `t-1` | **0 bars** relative to decision |
| TP level (nearest confirmed swing) | swing extreme occurring at bar `k`, level `High[k]`/`Low[k]` | bar `k+5` (period=5: five subsequent bars must fail to exceed the extreme); used only when `k+5 <= t` | **5 bars** — the level is knowable at decision bar `t` only for swings whose confirmation bar is at or before `t` |
| Market entry fill | open of bar `t+1` | bar `t+1` (F1/F2 — never on bar `t`) | n/a (execution, not signal) |

No centred windows, no `detect_swing_points`, no unshifted context frames. Single-timeframe strategy: the MTF context-bar rule (contract §4) is not exercised.

## 10. Ambiguities resolved
| # | Ambiguity | Conservative reading taken | Alternative rejected |
|--:|---|---|---|
| 1 | "After a clearly visible downtrend/uptrend" — undefined and discretionary | Exact mechanical rule from the CSV's own pseudocode: `tr = close.diff(10).rolling(5).mean()`; require `tr < 0` (long) / `tr > 0` (short). Zero parameters invented | (a) close vs EMA(50) — introduces an un-sourced parameter; (b) "two confirmed lower lows" — needs swing confirmation lag, later and fewer entries, and is not what the author coded; (c) no trend filter at all — contradicts the prose and inflates trade count |
| 2 | TP "at the nearest support/resistance level formed by the preceding trend" — S/R detection is semi-mechanical per the author's own reasoning field | Nearest **confirmed** swing extreme (period=5 via `causal_structure`) strictly beyond the decision close in the trade direction | (a) using the most recent extreme without confirmation — look-ahead (banned mechanism); (b) horizontal S/R from the *preceding trend's* origin specifically — ambiguous which pivot counts, and the nearest confirmed level is the conservative (usually closer, hence smaller TP) reading; (c) fixed ATR multiple — replaces the strategy's stated exit edge with an invented one |
| 3 | No minimum reward:risk is stated; the nearest level may be arbitrarily close to entry | Take the trade regardless of TP distance (no invented RR gate) | Requiring RR >= 1 (or any floor) — un-sourced; it would silently delete the worst-looking signals and is an interpretive lever the author did not write. Recorded, not applied |
| 4 | Entry timing: "enter Long" after the pattern — at the inside bar's close | `market` entry; fill at open of bar `t+1` (F1/F2). Stop/TP anchored to decision-bar-knowable prices (`Close[t]`, container extremes) per the decision-bar-anchoring fleet rule | (a) `buy_stop` one tick above `High[t-1]` (container high) — a plausible price-action reading, but the source neither states a stop-entry nor an offset, and it changes the pattern into a breakout-continuation variant; rejected; (b) fill-anchored R (measuring risk from actual fill) — inexpressible under contract v2 (stop must be declarable at intent creation); rejected |
| 5 | No confirmed swing level exists beyond entry (e.g. price at multi-year highs for a long) | Skip the signal entirely — no OrderIntent emitted (a take_profit leg requires an absolute declarable price) | Fallback to an ATR or fixed-pip target — invents an exit the author never wrote; unlimited-risk-style omissions are worse than a missed trade |
| 6 | Boundary equality in the inside-bar test (High equal to container High, or Low equal to container Low) | Strict inequalities — equality disqualifies the bar, exactly as written ("High < container High and Low > container Low") | Inclusive inequalities (<=, >=) — admits more, weaker patterns; contradicts the source text |
| 7 | A new signal while a position is still open | Nothing special declared: `max_concurrent_positions = 1` (F12 default) governs; additional intents are simply not admitted while a position is open. Market entries have no pending-overlap risk, so no expiry arithmetic is needed | Any "new signal closes/replaces the position" behaviour — that mechanism does not exist in contract v2 (no OCO, no supersede) and was never stated by the author |

## 11. Expected behaviour
- **Trade frequency:** low, as the author explicitly warns ("rare occurrence"). Raw inside bars occur on roughly a tenth of D1 bars; stacking the trend precondition, both candle-colour requirements, and the TP-existence gate plausibly leaves **~1–4 trades per pair per year on D1** (roughly 20–80 trades per pair over a 20-year history, before gating). H4 cells will be somewhat denser.
- **Gate prognosis:** with walk-forward folds of 6-month OOS windows, many (pair × granularity) cells will see single-digit trade counts → `low_confidence` flags are the expected norm, and the pooled result rests on a thin sample. This is arithmetic, not a defect; the report must present it as such (same caution as the W1 statistical warning in the contract).
- **Failure modes:** the strategy dies if (a) the smoothed-diff trend filter admits "trends" that are really late-stage exhaustion already reversed, so the pattern fires into fresh trends; (b) the nearest confirmed swing level is systematically closer than the stop (negative structural RR — nothing in the rules prevents a 1:0.3 trade); (c) F5 (stop-before-target intrabar convention) bites hard because stop and TP are both nearby structure levels on the same frame.
- **Is MODERATE justified by the rules as written?** Marginally. The entry and stop are fully mechanical and clean; but the edge rests entirely on an exit (nearest S/R) that the author himself calls semi-mechanical, there are no documented performance statistics, and the admitted rarity of the pattern means the backtest may never accumulate enough OOS trades to clear the confidence gates. The conviction is honest but unverifiable as documented; expect a `low_confidence` outcome rather than a decisive pass or fail.
