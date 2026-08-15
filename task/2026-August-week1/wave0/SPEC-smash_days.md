# SPEC-smash_days
**Source:** row 35 of forex_swing_strategies.csv · https://www.trade2win.com/threads/smash-days-in-forex.242994/
**Conviction (author's):** MODERATE

## 1. Hypothesis
A day whose close exceeds both the previous close and the highs of the preceding five sessions marks terminal exhaustion of a short-term upleg: late momentum buyers have chased price to a multi-day extreme and there is no residual bid left above them, so the path of least resistance on the following session is a snapback through the prior day's low as trapped longs liquidate and short-term mean-reversion flow dominates. This is the classic Larry Williams "smash day" reversal-of-exhaustion logic; the behavioural claim is that 5-day breakout closes are systematically overextended and prone to immediate one-to-few-day reversal rather than continuation.

## 2. Scope
- **primary_granularity:** D1
- **context_granularities:** () — none; the strategy is single-timeframe D1
- **simulate_on:** H1 (fills, stops, and the time leg are resolved on H1 bars within each D1 span per contract §5; orders are emitted from the D1 frame only)
- **pairs_requested (verbatim):** "28 leading forex pairs (e.g. GBP/NZD | NZD/CHF | AUD/USD | USD/CAD)"
- **pairs_available:** AUD_USD (live), USD_CAD (live), EUR_USD (live), GBP_USD (live), USD_JPY (live); pending Wave-1 additions: GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD
- **pairs_missing:** GBP_NZD and NZD_CHF are explicitly named by the author but are NOT in the Wave-1 addition list; the balance of the unnamed "28 leading pairs" (~15 further crosses) is likewise not planned. → **DATA-GAP-smash_days.md**

## 3. Indicators
| Indicator | Params | Source |
|---|---|---|
| Prior-5-day high | `PRIOR5_HIGH[t] = max(High[t-5..t-1])` — equivalently `donchian_channel(High, period=5).upper` shifted by 1 bar, i.e. `High.shift(1).rolling(5).max()` | Inventory `donchian_channel` with an explicit one-bar lag; the lagged form is fully causal (see §9). The raw rolling-max formula is stated here so Wave 2 may also compute it privately if preferred. |
| Day OHLC | decision bar D_t's Open/High/Low/Close | Native D1 frame |

No other indicators. No ATR, no trend filter, no swing-point machinery — this strategy does NOT use `detect_swing_points` or any confirmation-lagged pivot logic (the "5 preceding highs" is a rolling window, not a swing detection).

## 4. Entry — long
**No long entries are traded.** The source contains the phrase "smash_down mirror for longs" in the pseudocode, but the prose is unambiguous that "per OP shorts are primary," and the entry_logic_long field itself describes the mirror only as a hypothetical ("only if looking for long-side inverse"). The conservative reading — fewer trades, matching the OP's stated emphasis — is **short-only**. The two-sided mirror version is recorded as the rejected alternative in §10 (#1).

## 5. Entry — short
At the close of D1 bar D_t (the decision bar), evaluate:

1. `Close[t] > Close[t-1]` (today closed above yesterday's close), AND
2. `Close[t] > PRIOR5_HIGH[t] = max(High[t-5..t-1])` (today closed above ALL of the preceding 5 days' highs; today itself is EXCLUDED from the window — shift(1) semantics, verified against the CSV pseudocode `d['close'] > d['high'].shift().rolling(5).max()`, which at row t spans High[t-5..t-1]).

If both hold, D_t is a **smash-up day**. Emit:
- **entry:** `sell_stop`
- **entry level:** `entry_price = Low[t]` (the smash day's own low — exact, decision-bar knowable)
- **expires_after_bars:** `1` (one D1 decision-frame bar: the order is live ONLY during D1 session t+1 — "valid tomorrow only; cancel if unfilled")
- **direction:** -1
- **stop / exits:** as §6/§7

If conditions fail, emit nothing. There is no re-emission rule; each smash-up day produces at most one OrderIntent.

## 6. Stop
- **Initial stop:** `StopRule.price = High[t]` — the smash day's High (exact, decision-bar knowable, on the correct side of the sell_stop entry by construction since High[t] > Low[t]).
- **move_to_breakeven_on:** none
- **trail:** none (static structural stop for the life of the trade)

The stop is anchored to the decision bar D_t, not to the fill. Because the sell_stop fills at `min(Low[t], open)` (F3) — i.e. at or BELOW the declared entry level — realized risk `|fill − High[t]|` is ≥ declared risk `|Low[t] − High[t]|` when the session gaps through; declared R ≠ realized R in exactly that adverse direction, and F3/F6 resolve it honestly.

## 7. Exit legs
| Label | Fraction | Kind | Level formula |
|---|---|---|---|
| T_TIME5 | 1.0 | time | `bars = 5` (close the entire position at the close of the 5th D1 session after entry) |

Fractions sum to 1.0. There is NO take-profit leg: the source exit ("first profitable Close after 5 or more sessions held") is a P&L-conditional close and is **inexpressible declaratively** — a v2 ExitLeg cannot reference realized P&L or the close-versus-entry comparison. The closest expressible reading is the pure time leg at 5 sessions. Fidelity loss and bias direction are analysed in §10 (#2) and §11.

## 8. Filters
| Filter | Timeframe | When knowable | Status |
|---|---|---|---|
| Smash-up condition (§5) | D1 | At the close of D_t | **Implemented** as the entry gate itself |
| "Avoids trading during extreme volatility/event risk" (risk_management field) | D1 / calendar | Requires an economic-calendar or event feed | **DROPPED.** No calendar, news, or event data exists (DATA_AVAILABILITY.md: "No … economic calendar … no news sentiment"). The no-invented-data rule forbids a silent proxy; no ATR-volatility proxy is substituted because the source names *event* risk, not volatility level, and inventing one would change the strategy. Recorded in §10 (#4) and DATA-GAP-smash_days.md. |
| "OP limits concurrent exposure to avoid double-counting correlated AUD/NZD themes" | cross-pair, portfolio level | — | **DROPPED as inexpressible.** Contract v2 emits per-(strategy, pair) OrderIntents and has no cross-pair coordination channel; F12 caps positions per (strategy, pair, granularity) only. Recorded in §10 (#5). |

No session filter (D1 strategy; the "next session" constraint is the order expiry, §5). No trend filter.

## 9. Causality audit
| Rule | Inputs fully known at | Confirmation lag |
|---|---|---|
| §5 cond. 1 (`Close[t] > Close[t-1]`) | Close of D1 bar t | None — both closes are completed bars at decision time |
| §5 cond. 2 (`Close[t] > max(High[t-5..t-1])`) | Close of D1 bar t | None — the rolling window is `High.shift(1).rolling(5).max()`, spanning bars t-5..t-1, ALL strictly before t. **Verified:** the CSV pseudocode `d['high'].shift().rolling(5).max()` at row t = max of High[t-5..t-1]; today is excluded. This is a lagged rolling window, NOT a centred swing window; no look-ahead. (`detect_swing_points` is not used anywhere in this strategy.) |
| Sell-stop entry level `Low[t]` | Close of D1 bar t | None; order becomes fill-eligible from bar t+1 (F1) and expires after 1 D1 bar (F4), i.e. it may fill ONLY during session t+1, exactly "valid tomorrow only" |
| Initial stop `High[t]` | Close of D1 bar t | None; static for trade life |
| Time exit, 5 sessions | Counted from the fill bar forward on H1-resolved bars within D1 spans | None — a pure forward count; at no point is future information used |
| Order-of-operations | Engine §3.2: expiry → stops → legs → stop updates → pending fills → new intents | At H1 resolution, F5 (stop before target) applies within each H1 bar; the stop and the time-exit close can never conflict (time exit is at bar close, stop is intrabar) |

Multi-timeframe causality rule §4: **not applicable** — no context granularity. The strategy sees only its native D1 frame; H1 is used solely for fill resolution, never for decisions.

## 10. Ambiguities resolved
| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | Are longs traded at all? Pseudocode says "smash_down mirror for longs"; prose says "per OP shorts are primary". | **Short-only.** Fewer trades; matches the OP's stated emphasis and the entry_logic_short field. | Two-sided mirror (buy_stop at smash-down day's High, stop at its Low, same 5-session time exit). Rejected: doubles trade count on the strength of one pseudocode comment the prose subordinates. |
| 2 | Exit = "first profitable Close after 5 or more sessions held" — P&L-conditional, inexpressible declaratively. | **Pure time leg, bars = 5, fraction 1.0.** The minimum holding period in the source; the only ExitLeg kind that requires no P&L observation. | (a) "Hold until profitable" — inexpressible, not merely less conservative; the strategy never observes P&L. (b) bars = 7 — longer hold invents a parameter the source does not state. Bias note: the source exits winners between session 5 and whenever a profitable close occurs, and holds losers past 5 indefinitely; our version exits everything at 5, so we cut some later-recovering losers early (favourable) and forgo the source's "wait for green" recovery on winners held past 5 (unfavourable). Net direction is genuinely ambiguous and stated honestly in §11. |
| 3 | "Valid tomorrow only" — is the pending lifetime one D1 bar or a 24h wall-clock window? | **expires_after_bars = 1** (one D1 decision-frame bar). The order is admitted at the open of session t+1 (F1) and expires before session t+2. | GTC-until-filled or multi-day validity — directly contradicted by "cancel if unfilled" in both entry and exit fields. |
| 4 | "Avoids extreme volatility/event risk." | **Dropped entirely.** No calendar data exists; no proxy invented (no-invented-data rule). | ATR/zscore volatility gate as a silent proxy — rejected: the source says *event* risk, and substituting a volatility screen changes both the trade set and the hypothesis. Flagged in §8 and DATA-GAP. |
| 5 | "OP limits concurrent exposure to avoid correlated AUD/NZD double-counting." | **Dropped as inexpressible**; `max_concurrent_positions` left at the F12 default of 1 per (strategy, pair, granularity). | Any cross-pair exposure cap — contract v2 has no cross-pair channel. |
| 6 | Consecutive-day smash-ups: a new sell_stop can be emitted on day t+1 while the position from day t's fill (held up to 5 sessions) is still open. Pending lifetimes of 1 bar guarantee at most ONE live pending per pair at any time (order from decision bar t is live only during t+1, so two pendings never overlap), but a pending CAN fill while an earlier position is open — F12 caps positions only and does not gate pending fills (§3.2 step 5). | Risk **recorded, not suppressed** (the strategy cannot observe fills or positions, so no suppression mechanism exists). Direction: realized concurrent exposure on one pair can reach 2–5 stacked shorts during multi-day smash clusters — MORE exposure than a strict one-position reading, i.e. higher trade count and deeper correlated drawdown than T6-style results would show. Reports must state this. | Writing "a new signal supersedes/closes the open position" or "the first fill cancels later orders" — those mechanisms do not exist in contract v2 (no OCO, no cancel-on-fill, no supersede). |
| 7 | Entry/stop geometry anchored where? Source measures from "today's Low/High" (decision bar), and the fill is next session. | All levels anchored to decision bar D_t OHLC (Low[t] entry, High[t] stop) — decision-bar knowable at OrderIntent creation, per the decision-bar anchoring rule. | Fill-anchored variants (e.g. stop = High[t] measured as an offset from the actual fill) — inexpressible: the fill price is unknowable at emission. |

## 11. Expected behaviour
- **Trade frequency:** the smash-up condition (close > prior close AND close > all 5 preceding highs) fires roughly 1–3 times per month per pair on D1 — across 5 live pairs expect ~8–15 signals/month, of which perhaps half fill (the next session must trade down through Low[t] within one day). With 13 cells after Wave-1 additions, trade counts should be adequate for the gates on ~10 years of data; on the 5-pair reduced universe they will be thinner but likely still sufficient pooled.
- **What would fail the gates:** (a) the exhaustion-snapback edge decaying post-2010 as daily breakout closes more often continue (regime drift); (b) the 5-session time exit discarding the source's "wait for a profitable close" recovery mechanism — stopped trades (stop = full prior-day range above entry, often 0.5–1.5× a normal daily range away) land at −1R or worse via F6 weekend gaps, with no TP leg to offset them, so expectancy rests entirely on the win rate of the 5-day drift; (c) stacked concurrent shorts during multi-day smash clusters amplifying drawdown (§10 #6); (d) thin per-cell counts on the reduced universe.
- **Is the author's MODERATE conviction justified by the rules as written?** Broadly, yes — the setup is fully objective and the stop is structural, but the source's own live thread "shows both stopped trades and winners" with no formal backtest, and two of the strategy's three risk-management features (event-risk avoidance, correlated-exposure limits) cannot be implemented with available data and contract mechanisms. The expressible version is strictly more exposed than the traded original. MODERATE with expectancy-to-be-verified is the honest reading; this spec does not upgrade it.
