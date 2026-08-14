# SPEC-smashing_forex_2

**Source:** row 7 of forex_swing_strategies.csv · https://www.forexstrategiesresources.com/trend-following-forex-strategies/63-smashing-forex-system-2/
**Conviction (author's):** MODERATE

## 1. Hypothesis

When price closes beyond its 60-period EMA while the 14-period CCI simultaneously exceeds ±100, an established directional move with above-average displacement is already underway, and trend-following entries taken at that point capture continuation because CCI ±100 filters out weak, mean-reverting drifts that a bare EMA cross would accept. The edge should persist because it exploits herding behaviour in sustained order flow: the first lot banks a fixed 200-pip profit to de-risk the trade, and the breakeven-protected runner monetises the fat right tail of trend days that fixed-target systems forfeit. The system survives on asymmetry — many small scratches and 1R-ish wins, occasional large runner gains.

## 2. Scope

- **primary_granularity:** H4. Justification: the source names H4|D1 with no ranking. H4 is chosen as primary because a fixed 200-pip target/stop geometry fires far more often on H4 than D1, giving the walk-forward gates a usable trade count (~3–8 trades/pair/year vs ~1–3 on D1), while H4 is still coarse enough that a 200-pip target is a multi-bar swing objective, not noise.
- **context_granularities:** none. The source contains no cross-timeframe dependency; each timeframe is an independent instance of the same rules.
- **D1 instance:** the D1 variant is emitted as a **separate (strategy, pair, granularity) cell** under contract v2 metadata (`primary_granularity: D1`), with identical rules and its own gate evaluation per Part G. It shares this spec; nothing in the logic differs except the frame.
- **simulate_on:** H1 (contract §5: decided on the native H4/D1 frame, fills resolved on H1 bars).
- **pairs_requested (verbatim):** "Any"
- **pairs_available:** EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD (live) · GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD (**pending** — Wave-1 additions; harness skips pairs with insufficient history)
- **pairs_missing:** none. "Any" is read as the full available + pending FX universe (13 pairs). XAU_USD is deliberately excluded from the platform and is not considered named by "Any" (see §10 #7). **No DATA-GAP file is required.**

## 3. Indicators

| Indicator | Params | Source |
|---|---|---|
| EMA of Close | period 60, on native frame (H4 or D1) | `indicators.ema(close, 60)` — inventory |
| CCI | period 14, typical price (H+L+C)/3 | `indicators.cci(high, low, close, period=14)` — inventory (pass 14, not the 20 default) |
| Pip size | per pair: 0.0001 for all non-JPY pairs, 0.01 for *_JPY pairs | `indicators.calculate_pips` / `get_pip_value` — inventory conventions |

No swing-point, ZigZag, pivot, or fractal logic is used in the chosen reading (the swing-trail alternative is rejected — §10 #4), so `causal_structure` is not needed. **Warmup:** no OrderIntent is emitted before 120 completed native bars, so EMA60 is fully stabilised and CCI14 is well-defined (§10 #8).

## 4. Entry — long

Evaluated at the **close of native decision bar `t`** (H4 or D1); all inputs are values at bar `t`.

1. `Close[t] > EMA60[t]`
2. `CCI14[t] > +100`  (corrected sign — the source page has a typo in the buy rule; §10 #1)
3. Fresh-signal gate (conservative reading): NOT (`Close[t-1] > EMA60[t-1]` AND `CCI14[t-1] > +100`). I.e. emit only on the first bar the joint condition becomes true. §10 #5.
4. Warmup: at least 120 completed native bars precede `t`.

- **Entry type:** `market` (source: "enter at market"). Fill at open of bar `t+1` plus adverse slippage (F1, F2).
- **Entry level:** none declared (`entry_price = None`); the **declared geometry anchor** for all stop/TP levels below is `C[t]`, the decision-bar close (fleet rule: decision-bar anchoring; fill-anchored version rejected in §10 #6).
- **expires_after_bars:** null (market orders are not pending; not applicable).
- **size_fraction:** 1.0 — "2 lots" is expressed as two 0.5 exit legs of one standard unit, not two units (no position sizing; §10 #2).

## 5. Entry — short

Exact mirror, evaluated at the close of native decision bar `t`:

1. `Close[t] < EMA60[t]`
2. `CCI14[t] < -100`
3. Fresh-signal gate: NOT (`Close[t-1] < EMA60[t-1]` AND `CCI14[t-1] < -100`).
4. Warmup as in §4.

- **Entry type:** `market`, `entry_price = None`, anchor = `C[t]`.
- **expires_after_bars:** null.
- **size_fraction:** 1.0 with two 0.5 legs.

## 6. Stop

"SL just beyond EMA60 or 200 pips, whichever is less risky."

- **Mechanical definition of "less risky":** the stop with the **smaller distance from the anchor** (tighter stop, less capital at risk). Rejected alternative (wider stop = "less likely to be hit") in §10 #3.
- **"Just beyond EMA60":** on the far side of EMA60 from price — **below** EMA60 for a long, **above** for a short — plus a fixed buffer of **5 pips** (§10 #3).

**Long:**
- `dist_ema = (C[t] − EMA60[t]) + 5×pip`  (positive by entry condition 1)
- `dist_cap = 200×pip`
- `dist = min(dist_ema, dist_cap)`
- `StopRule.price = C[t] − dist`

**Short:**
- `dist_ema = (EMA60[t] − C[t]) + 5×pip`
- `dist = min(dist_ema, 200×pip)`
- `StopRule.price = C[t] + dist`

- **move_to_breakeven_on:** `"TP1"` (the ExitLeg label in §7). `breakeven_offset_pips = 0.0`. Per F8 the move happens at the **close of the H1-resolution bar on which TP1 fills**, not intrabar.
- **trail (StopRule.trail_atr_multiple):** **none** (`None`). The runner's 200-pip trailing stop is carried by the second ExitLeg (`kind="trailing", pips=200`), not by the StopRule, because the source trail is a **fixed pip distance, not an ATR multiple** — a fixed-pip trail is honestly expressible only as the pip-parameterised trailing leg (§10 #4).
- Stop interaction: stops never widen (contract test 12). After the TP1 fill moves the stop to breakeven, the trailing leg may only improve it further.

## 7. Exit legs

Anchor `C[t]` = decision-bar close; `pip` per §3 (0.0001 / 0.01 for JPY pairs).

| Label | Fraction | Kind | Level formula |
|---|---|---|---|
| TP1 | 0.5 | take_profit | price = `C[t] + 200×pip` (long) / `C[t] − 200×pip` (short) |
| RUNNER | 0.5 | trailing | pips = 200 — trailing stop 200 pips behind the most favourable **bar close** since entry, ratcheted at each H1-resolution bar close (F9 analogue: updates at bar close, never widens; close-based, not high/low-based — conservative, §10 #4) |

**Fractions sum to 1.0** (0.5 + 0.5). "TP1 at +200 pips = 1:1" holds only when `dist = 200×pip`; when the tighter EMA60 stop governs, TP1 is better than 1R by design. Realised R is computed by the engine against the **actual fill** and initial risk `|entry_fill − stop.price|`; when the fill gaps or slips, realised R ≠ declared R (F2, F3, F6 resolve the fill honestly) — see §10 #6.

## 8. Filters

None. The source defines **no** trend filter beyond the EMA60 condition itself (which is part of the entry signal, §4/§5), no session filter, no volatility filter, and no news/calendar filter. None are added: inventing gates would depart from the source, and no non-price data exists in the platform in any case (DATA_AVAILABILITY: no calendar, no spreads series, no session feed). The fixed 1.0-pip spread / 0.5-pip entry-slippage cost model (F10) is applied by the engine, not the strategy.

## 9. Causality audit

| Rule | Inputs | Fully known at | Lag |
|---|---|---|---|
| Long/short condition 1 (`Close` vs `EMA60[t]`) | Close and EMA60 computed from closes up to bar `t` | Close of decision bar `t` | 0 bars beyond decision bar; EMA60 is causal (recursive over past closes only) |
| Long/short condition 2 (`CCI14[t]` vs ±100) | H/L/C of bars `t-13 … t` | Close of decision bar `t` | 0 bars beyond decision bar |
| Fresh-signal gate (condition at `t-1`) | Same series at `t-1` | Close of bar `t` (trivially — `t-1` closed earlier) | 0 |
| Initial stop from `EMA60[t]` and `C[t]` | Values at `t` | Close of decision bar `t` | 0 |
| TP1 level from `C[t]` | Close of `t` | Close of decision bar `t` | 0 |
| Market fill | — | Open of bar `t+1` (F1, F2) | execution strictly after decision |
| Breakeven move on TP1 | TP1 fill event on H1-resolution bar `k` | **Close of bar `k`** (F8) | protection arrives 1 bar after the fill bar — documented pessimism, not look-ahead |
| 200-pip trailing leg | H1-resolution bar closes since entry | Each bar close at which it ratchets (F9) | 0; never widens |
| Swing/pivot/ZigZag/fractal rules | **None used** (swing-trail variant rejected, §10 #4) | — | **No confirmation lag applies to any rule in this spec** |
| Multi-timeframe | **None** — each (pair, granularity) instance decides on its own native frame only; no context bars | — | MTF rule (contract §4) is not triggered; no D1 bar ever informs an H4 decision or vice versa |
| Warmup | First 120 native bars | — | No intent can be emitted before bar 120 |

## 10. Ambiguities resolved

| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | Source page has a sign typo in the buy rule (noted in the CSV itself) | Buy rule is `CCI14 > +100`, symmetric with the sell rule `CCI14 < -100` | Literal typo reading (buy on `CCI < -100`), which would invert the system's logic and contradict the sell rule and the worked example |
| 2 | "Enter at market with 2 lots" | `size_fraction = 1.0` with two exit legs of 0.5/0.5 (r-multiple accounting; System 1 never sizes) | Emitting two separate OrderIntents of full size — doubles F12 concurrency and is position sizing, which is out of scope |
| 3 | "SL just beyond EMA60 or 200 pips, whichever is less risky" — "less risky" undefined; "just beyond" unquantified | "Less risky" = **smaller distance** from anchor: `dist = min(C−EMA60+buffer, 200 pips)`; "beyond" = far side of EMA60 from price with a fixed **5-pip buffer** | (a) "Less risky" = wider stop (less likely to be hit) — rejected: it maximises risk per trade and contradicts the two-lot de-risking intent; (b) stop exactly at EMA60 with no buffer — rejected: "beyond" explicitly places it past the line |
| 4 | "Trail the runner with a 200-pip trailing stop **(or move SL to each new swing low/high)**" — two trailing variants; fixed-pip trail not an ATR trail | Fixed 200-pip trail expressed as `ExitLeg(kind="trailing", pips=200)`, ratcheting on **bar closes** (slower ratchet → lower/worse stop → conservative); StopRule.trail_atr_multiple stays `None` because a fixed-pip distance cannot be honestly written as an ATR multiple | (a) Swing low/high trail via `causal_structure.confirmed_swing_points(period=5)` — rejected: source lists it as the alternative, it needs an invented period, and its 5-bar confirmation lag delays stop tightening; (b) trailing from bar highs/lows — rejected: ratchets faster, flattering results; (c) approximating 200 pips as `trail_atr_multiple` — rejected as dishonest (ATR varies; the source says fixed pips) |
| 5 | "Close above EMA60 AND CCI > +100" is a persistent state — re-emit every bar while true? | **Fresh-crossover gate**: emit only on the first bar the joint condition turns true; no re-entry after a stop-out while the state persists (fewer trades) | Re-emitting on every bar where the state holds — rejected: more trades, and repeated re-entry into a failing trend flatters win rate via churn |
| 6 | SL/TP measured "from entry" — entry price of a market order is unknowable at emission | All geometry anchored to **decision-bar close `C[t]`**; engine resolves the fill honestly (F2/F6) and realised R ≠ declared R under gap/slippage | Fill-anchored geometry — rejected as **inexpressible** in contract v2 (declarative OrderIntents cannot observe fills), not merely less conservative |
| 7 | Target pairs "Any" | Restricted to the 13-pair universe (5 live + 8 Wave-1 pending); XAU_USD treated as **not** covered by "Any" | Including XAU_USD — rejected: deliberately excluded from the platform (not FX; pip/margin conventions break); including only the 5 live pairs — rejected as an unnecessary restriction since pending pairs are skipped gracefully, and is the fewer-trades reading only incidentally |
| 8 | EMA60/CCI14 warmup unspecified | No intents before **120 completed native bars** (EMA recursion stabilised, CCI well-defined) | Minimum-only warmup (61 bars) — rejected: early EMA values are seed-sensitive and would produce non-reproducible borderline signals |
| 9 | H4\|D1 with no ranking | Both kept as **separate (strategy, pair, granularity) cells** (contract metadata emits per granularity); H4 designated primary for trade-count reasons (§2); no MTF mixing | Picking D1 only (fewer trades but discards the more testable cell) or merging frames into one signal stream (would trigger MTF causality rules the source never intended) |

## 11. Expected behaviour

- **Trade frequency:** low-to-moderate. H4: roughly 3–8 trades per pair-year (fresh EMA60 crosses with CCI beyond ±100 are not rare, but the joint fresh-condition gate suppresses churn); D1: roughly 1–3 per pair-year. Across 13 pairs × 2 granularities this should still clear minimum-trade gates on the pooled H4 cells, but individual D1 cells and low-volatility pairs (EUR_GBP, AUD_NZD) may return `low_confidence`.
- **What would make it fail the gates:** (a) the EMA60-side stop is often razor-thin immediately after a cross, so whipsaw clusters can produce long strings of small losses before any runner pays; (b) fixed 200-pip geometry is not volatility-adjusted — on low-ADR pairs TP1 is rarely reached and the breakeven runner gives back open profit, while on JPY crosses 200 pips is a much smaller move; (c) F5 (stop-before-target) punishes the tight-stop cases hardest; (d) the +1.5-pip round-trip cost (F10) is material against a sometimes-tiny initial risk denominator.
- **Is the author's MODERATE conviction justified by the rules as written?** Barely. The page offers one worked pip-by-pip example and no statistical evidence; the two-rule entry is plausible trend-following logic but the fixed-pip exits across heterogeneous pairs are the weak point, and the sign typo suggests the source was never machine-verified. MODERATE is fair as a prior; the backtest verdict should hinge on whether the runner leg's tail gains actually cover the tight-stop whipsaw losses out of sample.
