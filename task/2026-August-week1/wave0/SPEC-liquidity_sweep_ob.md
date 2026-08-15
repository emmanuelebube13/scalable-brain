# SPEC-liquidity_sweep_ob
**Source:** row 45 of forex_swing_strategies.csv · https://howtotrade.com/blog/liquidity-sweep/
**Conviction (author's):** MODERATE

## 1. Hypothesis
In a trending market, institutional order flow clusters at the origin of a break-of-structure move (the "order block"), and stop orders accumulate just beyond obvious swing highs/lows ("liquidity"). Price frequently runs those stops — sweeping the swing level — before resuming the trend, because large participants need counter-side liquidity to fill size. Entering at the order block only after a confirmed stop-run therefore buys the trend's continuation at the exact point where weak hands were just forced out, giving a structural stop location and asymmetric reward. The edge should persist because stop-clustering at round swing levels is a stable, mechanically driven feature of leveraged FX markets, not a sentiment anomaly.

## 2. Scope
- **primary_granularity:** H4
- **context_granularities:** none (D1 structure mentioned in source is collapsed into the H4 primary frame — see §10 #6)
- **simulate_on:** H1 (fill resolution only, per contract Part D; the strategy never sees H1 data)
- **pairs_requested (verbatim):** "FX majors and minors (GBP/USD example on page)"
- **pairs_available:** EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD (live) · GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD (**pending** — Wave-1 additions, not gaps)
- **pairs_missing:** none. "Majors and minors" is fully covered by the 5 live + 8 pending pairs. **No DATA-GAP file required.**

## 3. Indicators
| Indicator | Params | Source |
|---|---|---|
| Confirmed swing points (high/low) | `period=5` on H4 | `causal_structure.confirmed_swing_points(high, low, period=5)` — replaces the CSV's BANNED `rolling(10, center=True)` (see §10 #1) |
| Last confirmed swing high/low level + confirmation bar | rolling, H4 | `causal_structure.last_n_confirmed_highs` (and its lows equivalent), n=1 |
| Trend state machine (BOS-based) | private, specified below | Not in inventory; fully specified in §4/§5 |
| Order block identification | private, lookback 20 H4 bars | Not in inventory; fully specified in §4/§5 |
| Pip size | per pair | `indicators.get_pip_value(asset)` — 0.0001 for non-JPY pairs, 0.01 for JPY pairs |

No ATR, MA, oscillator, or volume indicator is used. The source's "optional FVG marking" is omitted (optional in source; §10 #8).

**Private definitions (normative):** Let `CSH_t` = level of the most recently confirmed swing high whose confirmation bar ≤ t, and `CSL_t` the same for swing lows. A swing high occurring at bar k is confirmed at bar k+5; before k+5 it does not exist for this strategy. `pip` = `get_pip_value(pair)`.

## 4. Entry — long
An **episode** begins with a bullish break of structure. All conditions are evaluated at the close of H4 decision bar t.

**Bullish BOS (episode trigger):** at bar b, `Close[b] > CSH_{b-1}` (close beyond the most recent swing high confirmed at or before b−1). This flips trend state to UP and starts episode b. Trend state stays UP until a bearish BOS (Close below the then-most-recent confirmed swing low) flips it DOWN.

**Order block (fixed at the BOS bar):** at the BOS bar b, define
`k = max{ j : b−20 ≤ j ≤ b−1, Close[j] < Open[j] }`
(the most recent bearish candle in the 20 H4 bars preceding the BOS bar). If no such j exists, the episode is void. `OB_high = High[k]`, `OB_low = Low[k]`.

**Liquidity-sweep precondition (the source's "invalidated if no liquidity zone exists"):** there must exist at least one swing low confirmed at or before bar t; if no confirmed swing low exists at all, **no order**. Furthermore the sweep must have occurred: there exists a bar j with `b+1 ≤ j ≤ t` such that, letting L = the most recent swing-low level confirmed at or before j,
`Low[j] < L`  AND  `Close[j] > L`
(wick through the confirmed swing low, close back above it).

**Emission conditions at decision bar t (all must hold):**
1. Trend state = UP, with current episode started at BOS bar b ≤ t.
2. The episode's order block exists (k found).
3. The sweep precondition above holds for some j in (b, t].
4. `Close[t] > OB_high` (price is above the OB upper edge, so the buy limit is legitimately below the market — required by the OrderIntent validator).
5. No order has yet been emitted for episode b (edge-trigger: one OrderIntent per BOS episode; if conditions hold on consecutive bars, only the first emits).

- **entry type:** `buy_limit`
- **entry level:** `entry_price = OB_high` (upper edge of the bullish order block, exactly)
- **expires_after_bars:** **12** H4 bars (48 hours; SMC pullback setups go stale fast — §10 #4)

## 5. Entry — short
Full mirror of §4.

**Bearish BOS:** at bar b, `Close[b] < CSL_{b-1}`. Flips trend state to DOWN, starts episode b.

**Bearish order block:** `k = max{ j : b−20 ≤ j ≤ b−1, Close[j] > Open[j] }` (most recent bullish candle in the 20 bars before the BOS bar). If none, episode void. `OB_high = High[k]`, `OB_low = Low[k]`.

**Sweep precondition:** a confirmed swing high must exist (else no order — invalidation rule), and there exists j in (b, t] with, L = most recent swing-high level confirmed at or before j:
`High[j] > L`  AND  `Close[j] < L`.

**Emission conditions:** mirror of §4 (trend DOWN, episode OB exists, sweep holds, `Close[t] < OB_low − 1.0·pip`, no prior emission for episode b).

- **entry type:** `sell_limit`
- **entry level:** `entry_price = OB_low − 1.0·pip` ("just below the bearish order block" — the 1.0 pip offset is a declared constant, §10 #7)
- **expires_after_bars:** **12** H4 bars

## 6. Stop
- **Initial stop (long):** `stop.price = OB_low − 4.0·pip` — "a few pips" declared as **3.0 pips** plus the **1.0-pip cost-model spread convention** as the spread buffer (§10 #5; flagged as a proxy — no real spread series exists).
- **Initial stop (short):** `stop.price = OB_high + 4.0·pip`.
- **move_to_breakeven_on:** none (source specifies no breakeven move).
- **trail:** none (source specifies no trailing stop).

All levels are decision-bar-knowable: OB edges were fixed at BOS bar b ≤ t. StopRule.price is an absolute declarable value at OrderIntent creation.

## 7. Exit legs
| Label | Fraction | Kind | Level formula |
|---|---|--:|---|---|
| TP1 | 1.0 | take_profit | Long: `L_tp` = level of the nearest confirmed swing high with confirmation bar ≤ t and `L_tp > entry_price`. Short: nearest confirmed swing low confirmed ≤ t with `L_tp < entry_price`. |

**RR floor (source's own "reward:risk ≥ 1:2"):** compute `RR = |L_tp − entry_price| / |entry_price − stop.price|`. If no confirmed opposite swing exists beyond entry, or `RR < 2.0`, **no OrderIntent is emitted** (the setup is skipped, not re-targeted — §10 #3). Fractions sum to 1.0 (single leg).

## 8. Filters
- **Trend filter (BOS state):** evaluated on H4; the BOS at bar b becomes knowable at the close of bar b (its input swing was confirmed at or before b−1). No trade is emitted while trend state is NONE (before the first BOS) or opposing.
- **Liquidity precondition:** evaluated on H4; knowable at the close of the sweep bar j ≤ t. If no confirmed opposite-side swing exists to sweep, the setup is void (this is the source's invalidation rule, implemented as an entry precondition).
- **No session, news, volatility, or volume filter** exists in the source; none is added. The `Volume` column (OANDA tick count) is not used.
- **Spread buffer proxy (flagged per rule 5):** the source says "SL … with spread buffer". No historical spread series exists in the data. The 1.0-pip spread constant of the cost model (F10) is used as the declared spread buffer inside the 4.0-pip stop offset. This is a proxy, flagged here, in §6, and in §10 #5.

## 9. Causality audit
| Rule | Inputs fully known at | Confirmation lag |
|---|---|---|
| Swing high/low at occurrence bar k | close of bar **k+5** (period=5, H4) — stamped at confirmation per `causal_structure` | **5 H4 bars** (~20 trading hours) |
| Bullish/bearish BOS at bar b | close of bar b — uses Close[b] and a swing level confirmed at bar ≤ b−1 | ≥ 5 H4 bars after the broken swing's occurrence |
| Order block identification | close of BOS bar b — OB is only identifiable once the BOS exists; it references candles at bars ≤ b−1 | compounds: ≥ 5 H4 bars after the swing occurrence, plus however long the BOS took to print |
| Sweep bar j | close of bar j — the swept level L must be a swing confirmed at bar ≤ j; High[j]/Low[j]/Close[j] are bar-j data | the swept level lags its own occurrence by 5 H4 bars |
| Emission conditions 1–5 | close of decision bar t | — |
| entry_price, stop.price, TP1 price | close of decision bar t — all are fixed levels set at or before t | — |
| RR ≥ 2 check | close of decision bar t — TP swing must be confirmed at bar ≤ t | the TP target lags its occurrence by 5 H4 bars (it is a *historical* swing, never a future one) |
| H1 usage | none — strategy never sees H1; H1 resolves fills only (contract Part D) | — |

No centred window, no `shift(-1)`, no future swing is ever read. The CSV pseudocode's `rolling(10, center=True)` is replaced wholesale (§10 #1).

## 10. Ambiguities resolved
| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | CSV pseudocode detects swings with `rolling(10, center=True)` — the BANNED look-ahead pattern | `causal_structure.confirmed_swing_points(period=5)` on H4; swings knowable only 5 bars after occurrence | Keeping any centred-window or "act at occurrence bar" reading — look-ahead, inexpressible |
| 2 | Trend definition: prose says "confirmed by break of structure"; pseudocode says `close < rolling(50).mean()` | BOS-based trend state machine (prose is the primary description; the SMA50 appears only in the sketch pseudocode) | SMA(50) trend filter — a different, weaker strategy than the page describes |
| 3 | TP is "next opposite swing point **or** fixed RR ≥ 1:2" | TP must be the nearest **confirmed** opposite swing beyond entry; if that gives RR < 2.0 (or none exists), **skip the trade** (fewer trades) | Falling back to a fixed 2R target when the swing is too near (more trades, invents a target the price never validated) |
| 4 | Pending-order lifetime unspecified; SMC setups go stale fast | `expires_after_bars = 12` H4 bars (48 h) | Longer/GTC window — stale OBs fill in a later regime, contradicting the setup's premise |
| 5 | SL buffer is "a few pips … with spread buffer" | 3.0 pips + 1.0-pip cost-model spread constant = 4.0 pips beyond the OB edge (worse fill = conservative); spread is a proxy, flagged in §8 | 1–2 pips with no spread term (tighter stop flatters win rate); any real-spread series (does not exist) |
| 6 | Source uses "H4\|D1 structure; H1 for fine execution" — three timeframes | Single primary frame **H4**; H1 is the contract's `simulate_on` fill-resolution only; the strategy never sees H1 or D1 data | H1 execution variant (rejected: H1 structure signals would be a different strategy with 4× the bars and different swing semantics; contract forbids the strategy seeing simulation-frame data) |
| 7 | Short entry is "just below the bearish order block" — no number | `OB_low − 1.0·pip`, a declared constant (later/worse fill than entering at OB_low itself) | `OB_low` exactly, or "a few pips" below |
| 8 | "optional FVG marking" | Omitted — it is explicitly optional and would only add an unbacktested gate | Adding a fair-value-gap confluence requirement not defined anywhere in the source |
| 9 | Re-emission while a prior limit is pending: contract v2 has **no OCO, no cancel-on-fill, no supersede**; F12 caps concurrent *positions* (default 1) but does **not** gate pending fills | Edge-trigger per BOS episode (condition 5: one OrderIntent per episode) plus 12-bar expiry. **Residual risk, recorded:** a *second* BOS episode (e.g. trend flips and a new opposite setup forms) within the 12-bar life of an unfilled limit leaves two live pendings; both can fill → two concurrent positions despite the F12 default. Direction of bias: **more** exposure than T6-style 1-position results, both positions sharing correlated structure levels, so losses cluster. The strategy does not raise `max_concurrent_positions`; the overlap is possible but bounded by the 12-bar expiry and the rarity of two full episodes inside 48 h | Claiming "first fill cancels the other" or "a new signal closes the old position" — those mechanisms do not exist in contract v2 |
| 10 | Long entry "at upper edge of OB" vs short "just below OB" | Asymmetric as written (long: `OB_high` exactly; short: `OB_low − 1.0·pip`) — the source's own words, not harmonised | Symmetrising both to "at the edge" — would edit the source without evidence |

## 11. Expected behaviour
- **Trade frequency:** low. The full chain — BOS → OB → post-BOS sweep → pullback to the OB edge within 12 bars → RR ≥ 2 to a confirmed opposite swing — is a long conjunction on H4. Expect roughly **1–4 filled trades per pair per month**, with many episodes dying at the sweep precondition, the 12-bar expiry (pullback never reaches the OB), or the RR floor. Across 13 pairs this still yields a usable OOS trade count, but per-cell counts on single pairs may trip `low_confidence`.
- **Most likely gate failures:** (a) too few trades per cell; (b) the 5-bar swing-confirmation lag means the swept level and TP target are always stale structure — in fast trends the RR ≥ 2 filter kills most setups, skewing the survivors toward slower, mean-reverting episodes; (c) F5 (stop-before-target) bites hard because the stop sits only ~4 pips beyond the OB edge, and the entry pullback that fills the limit can continue through it.
- **Author's conviction (MODERATE):** justified by the rules as written. The checklist is genuinely mechanizable and the stop-hunt logic is sound market microstructure, but the page documents no backtest, and the honest causal implementation (confirmation lags on swings, OB, swept level, *and* TP target) strips out precisely the visual hindsight that makes SMC charts look compelling. Expect the causal version to trade far less often and less prettily than the blog examples.
