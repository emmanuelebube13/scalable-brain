# SPEC-pinbar_nose_eyes
**Source:** row 23 of forex_swing_strategies.csv · https://www.earnforex.com/forex-strategy/pinbar-trading-system
**Conviction (author's):** MODERATE

## 1. Hypothesis
A pinbar (nose) that probes well beyond the prior bar's (left eye's) extreme and is rejected — closing back inside the left eye with open and close in the far quartile — marks a failed breakout and stop-run at a structural support/resistance level. The edge should persist because the protrusion flushes weak-hand stops and breakout traders beyond the level, and when that probe attracts no follow-through the trapped breakout flow must unwind, pushing price back through the left eye. Locating the pattern at a *confirmed* swing level concentrates this behaviour where resting liquidity actually sits, which is why the author insists on strong S/R and why the conservative (stop-entry beyond the nose) version demands proof that the rejection is holding before committing.

## 2. Scope
- **primary_granularity:** H4 — the author's first-listed timeframe; the pattern is a 2-bar formation, so H4 gives ~6× the sample of D1 while remaining resolvable on H1 fills (contract §5). See §10 #11 for the rejected D1/W1 reading.
- **context_granularities:** none. The S/R structure filter is evaluated on H4 itself (confirmed H4 swing points). No multi-timeframe join is used, so the contract §4 MTF rule is not exercised by this strategy.
- **simulate_on:** H1 (fills, stops, and legs resolved on H1 within each H4 bar's span; F5 still applies at H1).
- **pairs_requested (verbatim):** "Any currency pair"
- **pairs_available:** live: EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD; pending (Wave-1 additions, NOT gaps): GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD. "Any currency pair" is read as the full 13-pair universe above; the harness skips pending pairs with insufficient history.
- **pairs_missing:** none. XAU_USD is not a currency pair and is not requested. No DATA-GAP file is written for this strategy.

## 3. Indicators
| Indicator | Params | Source |
|---|---|---|
| Confirmed swing points (high/low) | period=5, on H4 High/Low | `causal_structure.confirmed_swing_points` — swing at bar k knowable only at bar k+5 |
| Last confirmed swing low level S(t) | most recent confirmed swing low whose confirmation bar ≤ t | derived from `confirmed_swing_points` output (rolling last confirmed level; equivalent to `last_n_confirmed_highs(..., n=1)` on the low side) |
| Last confirmed swing high level R(t) | most recent confirmed swing high whose confirmation bar ≤ t | same, high side |
| ATR | period=14, on H4 High/Low/Close | `indicators.atr` (inventory) |
| Bar geometry (open/close/high/low relations) | none | raw H4 OHLC, no indicator needed |

No private indicators are required. `detect_swing_points` is NOT used (banned, centred window).

## 4. Entry — long
Bar indexing: the decision bar is `d` (the **nose** bar); the **left eye** is bar `d−1` (adjacent — see §10 #9). All conditions are evaluated at the **close of bar d**. Let `Rng(x) = High(x) − Low(x)`; require `Rng(LE) > 0` and `Rng(N) > 0` (degenerate bars skipped).

1. Left eye is a down bar: `Close(d−1) < Open(d−1)`.
2. Nose opens inside the left-eye **body**: `Close(d−1) < Open(d) < Open(d−1)`.
3. Nose closes inside the left-eye **body**: `Close(d−1) < Close(d) < Open(d−1)`.
4. Nose low protrudes well below the left-eye low: `Low(d) < Low(d−1) − 0.5 × Rng(LE)` (the CSV pseudocode's own 0.5 coefficient; §10 #2).
5. Nose open AND close sit in the top quartile of the nose bar: `min(Open(d), Close(d)) > Low(d) + 0.75 × Rng(N)`.
6. S/R filter (mandatory): `|Low(d) − S(d)| ≤ 0.5 × ATR14(d)`, where `S(d)` is the most recent confirmed H4 swing-low level knowable at bar d (§9 lag).
7. TP-validity guard: `High(d−1) + 1.0 pip > entry_price` (with entry_price as below). If the left-eye high does not sit above the entry, the setup is skipped — the contract requires TP beyond entry (§10 #6).

- **Entry type:** `buy_stop`
- **Entry level:** `entry_price = High(d) + 1.0 pip` ("just above nose high"; 1-pip buffer per §10 #12). Pip size via `get_pip_value(asset)`.
- **expires_after_bars:** `3` (H4 bars; 12 hours). Source is silent; a rejected pinbar that is not triggered within 12 h is stale, and a short expiry bounds two-sided pending overlap (§10 #5, §10 #13).

## 5. Entry — short
Mirror of §4 at the same decision bar `d`:

1. Left eye is an up bar: `Close(d−1) > Open(d−1)`.
2. Nose opens inside the left-eye body: `Open(d−1) < Open(d) < Close(d−1)`.
3. Nose closes inside the left-eye body: `Open(d−1) < Close(d) < Close(d−1)`.
4. Nose high protrudes well above the left-eye high: `High(d) > High(d−1) + 0.5 × Rng(LE)`.
5. Nose open AND close sit in the bottom quartile of the nose bar: `max(Open(d), Close(d)) < Low(d) + 0.25 × Rng(N)`.
6. S/R filter (mandatory): `|High(d) − R(d)| ≤ 0.5 × ATR14(d)`, where `R(d)` is the most recent confirmed H4 swing-high level knowable at bar d.
7. TP-validity guard: `Low(d−1) − 1.0 pip < entry_price`; otherwise skip.

- **Entry type:** `sell_stop`
- **Entry level:** `entry_price = Low(d) − 1.0 pip`
- **expires_after_bars:** `3`

## 6. Stop
- **Initial stop (long):** `stop.price = min(S(d), Low(d)) − 1.0 pip` — 1 pip behind the structural support behind the eyes, extended to sit behind the nose point if the nose itself probed below that support (the author's preferred "behind nearest support/resistance behind the eyes" reading; §10 #7).
- **Initial stop (short):** `stop.price = max(R(d), High(d)) + 1.0 pip`.
- **move_to_breakeven_on:** `none`. The author's break-even remark is honoured by recording it in §10 #8; with a single 100% exit leg a breakeven trigger is a no-op, and splitting the leg would invent structure the source does not specify.
- **trail:** `none` (static stop; stops never widen).

All stop geometry is anchored to decision-bar-knowable prices (bar-d OHLC and the confirmed level S/R(d)), satisfying the decision-bar anchoring rule; realized R may differ from declared R if the H1 fill gaps (F3/F6).

## 7. Exit legs
| Label | Fraction | Kind | Level formula |
|---|---|---:|---|---|
| TP1 | 1.000 | take_profit | long: `High(d−1) + 1.0 pip` ("just beyond left eye high"); short: `Low(d−1) − 1.0 pip` |

Fractions sum to 1.0. Single-leg exit: the conservative TP is the only mechanical target the source gives; the aggressive "next strong S/R" target is rejected as discretionary (§10 #6). The §4/§5 guard guarantees TP lies beyond entry.

## 8. Filters
| Filter | Timeframe | Knowable at |
|---|---|---|
| S/R proximity (mandatory): nose extreme within `0.5 × ATR14` of the last confirmed swing low/high (§4.6 / §5.6) | H4 | Close of decision bar d (the swing level itself was knowable from its confirmation bar k+5 onward; ATR14(d) uses bars ≤ d) |
| TP-validity guard (§4.7 / §5.7) | H4 | Close of decision bar d |

No session, volatility-regime, news, or trend filters exist in the source and none are added. There is no non-price data requirement; the source's "support/resistance levels (swing highs/lows)" requirement is fully derivable from H4 OHLC via `causal_structure`. No proxy data is used anywhere in this spec.

## 9. Causality audit
| Rule | Inputs | Fully known at |
|---|---|---|
| §4.1–4.5 / §5.1–5.5 (bar geometry: left-eye direction, inside-body open/close, 0.5× protrusion, quartile condition) | OHLC of bars d−1 and d | **Close of bar d** (the decision bar itself). No look-ahead: the decision is made at d's close and orders become eligible at d+1 (F1). |
| §4.6 / §5.6 (confirmed swing level S/R) | H4 swing low/high occurring at some bar k, plus ATR14 | The level set at bar k is knowable only at **bar k+5** (period=5 confirmation: 5 subsequent bars fail to exceed/undercut it). `confirmed_swing_points` stamps k+5, so S(d)/R(d) at decision bar d uses only swings with k ≤ d−5. ATR14(d) uses closes ≤ d. |
| §4.7 / §5.7 (TP-validity guard) | High/Low of bar d−1, entry formula | Close of bar d. |
| Entry (`buy_stop`/`sell_stop`) | High/Low of bar d + 1 pip | Declared at close of d; eligible to fill from bar d+1 (F1), resolved on H1 (F3). |
| Stop / TP1 | Bar d−1 and d OHLC, confirmed S/R(d) | Close of bar d; static thereafter (no trailing, no breakeven → no later-bar dependencies). |
| Multi-timeframe rule | — | Not exercised: single-timeframe strategy, no context frame. |

No rule requires knowing at bar k that k was a swing extreme; only levels confirmed ≥5 bars earlier are read.

## 10. Ambiguities resolved
| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | "Ideally at strong support/resistance" — mandatory or qualitative? | **Mandatory**: hard filter §4.6/§5.6 using the last confirmed H4 swing level with a 0.5×ATR14 tolerance band | Qualitative/optional S/R (rejected: produces more trades in structurally empty locations; the author himself calls S/R the hard-to-formalize core of the edge) |
| 2 | "Protrudes well below/above" — magnitude | `0.5 × Rng(LE)`, the only numeric anchor in the source (its own pseudocode) | Tightening to `1.0 × Rng(LE)` (fewer trades, but departs from the documented value); dropping the protrusion test (looser, more trades) |
| 3 | "Opens and closes inside left eye" — inside body or full range? | Inside the **body** (`[Close, Open]` of LE): conditions 2–3 | Inside the full LE range (looser — admits noses whose open/close sit in the LE wicks, more trades) |
| 4 | Two entry styles offered | **Conservative only**: stop order beyond the nose extreme (§4/§5) | Aggressive right-eye retreat entry ("when price retreats above/below the left-eye close") — requires a third bar and a discretionary "retreat" definition; fewer, later entries under the chosen reading |
| 5 | Pending-order lifetime unspecified | `expires_after_bars = 3` (12 h on H4) | `null`/GTC (rejected: stale pinbars can trigger days later and unbounded two-sided pending overlap; contract default 5 also rejected as longer than the pattern's shelf life) |
| 6 | Two TP styles; TP may not clear entry | Conservative TP `High(LE) ± 1 pip` only, plus the §4.7/§5.7 guard that **skips** setups where the left-eye extreme does not lie beyond the entry | Aggressive TP "next strong S/R" (discretionary — which level is "next strong" is not mechanically defined; rejected); filling anyway with an inverted TP (invalid under the contract) |
| 7 | Two SL styles | Structural stop behind confirmed S/R, floored by the nose point: `min(S, Low(N)) − 1 pip` (long) | "Just beyond the nose point" (`Low(N) − 1 pip`): tighter stop → smaller R denominator → *larger* r-multiples on wins → more flattering to the gates; the author himself flags it as the worse reward/risk |
| 8 | Author's "high no-loss rate when break-even is applied" | Not applied: `move_to_breakeven_on = none` | Adding a second leg purely to make breakeven meaningful (invents exit structure absent from the source); breakeven on TP1 (a no-op — the position is already flat) |
| 9 | Left-eye position: pseudocode uses `shift(2)` (an unconstrained bar between LE and nose) | **Adjacent** pattern: LE = d−1, nose = d — the canonical eyes/nose/eyes formation and the stricter reading | `shift(2)` layout with a free intervening bar (ambiguous bar identity, admits non-canonical shapes) |
| 10 | Nose bar's own direction unspecified | No requirement on `Close(d)` vs `Open(d)` beyond the inside-body and quartile conditions | Requiring the nose to close in the trade direction (invents a rule not in the source; noted, not applied — direction is recorded here so the implementer adds nothing) |
| 11 | Timeframes "H4\|D1\|W1" | Primary H4, single timeframe | D1 (fewer trades — superficially "more conservative" — but the source lists all three as equals, H4 is listed first, and D1/W1 trade counts under the mandatory S/R filter would be statistically thin: 36-month W1 train folds ≈ 156 bars); W1 additionally stale ~8 weeks |
| 12 | "Just above/beyond" buffer size | `1.0 pip` on entry, stop, and TP | `0` buffer (earlier fills, tighter geometry); any larger buffer is unjustified by the source |
| 13 | Two-sided pending overlap (fleet lifecycle rule: no OCO/cancel-on-fill) | Expiry of 3 bars bounds overlap: a buy_stop and a later sell_stop can coexist at most 3 H4 bars, and F12 (max 1 concurrent position) prevents simultaneous holdings | Residual risk recorded, not eliminated: if position 1 exits within ≤3 bars of its fill, an opposite pending emitted meanwhile can still fill, producing a rapid reversal trade the discretionary author would likely have skipped. Direction of bias: **more** trades in chop (conservative for performance, inflates count). Arithmetic: opposite patterns require 2 adjacent qualifying bars each; coexistence needs both patterns within a 5-bar window — possible but rare outside ranging markets. No mechanism exists to cancel it, so it is declared here rather than hidden. |

## 11. Expected behaviour
- **Frequency:** the formation is 2 bars and common, but the mandatory confirmed-swing S/R filter (§4.6/§5.6) plus the TP-validity guard removes the majority of occurrences. Expect roughly 3–15 trades per pair per year on H4 — of the order of 30–150 trades per live pair over the 10-year research window; pooled across 13 pairs (when Wave-1 backfill lands) the sample is adequate for the gates, but per-cell counts on quiet pairs may still flag `low_confidence`.
- **What would make it fail the gates:** choppy H4 regimes where protrusions at swing levels are routinely re-run (F5 stop-first resolution punishes exactly this pattern: the H1 bar that triggers the buy stop often retraces into the stop); the structural stop being far away when the nose probed deep below support (large R denominator, small r-multiples); and the residual two-sided overlap (§10 #13) adding losing reversal trades in ranges. Weekend gaps through the 1-pip-buffered stop (F6) will occasionally produce losses > 1R, especially on H4 bars straddling the Sunday open.
- **Conviction check:** MODERATE is justified as written. The pattern geometry is fully mechanical once S/R is pinned to confirmed swings, the conservative entry demands confirmation before committing, and the structural stop is honest; but the author provides no performance statistics, admits S/R formalization is the strategy's hard part, and the edge rests on a liquidity-flush narrative that the backtest, not the prose, must confirm.
