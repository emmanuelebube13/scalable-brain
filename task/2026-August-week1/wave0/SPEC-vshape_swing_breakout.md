# SPEC-vshape_swing_breakout

**Source:** row 33 of forex_swing_strategies.csv · https://tradingstrategyguides.com/best-breakout-trading-strategy/
**Conviction (author's):** MODERATE

## 1. Hypothesis

A sharp, V-shaped reversal marks a point where one side of the market was forced to liquidate in a hurry and the other side absorbed that flow aggressively; the extreme of that flush and the origin of the selloff become reference levels that subsequent order flow respects. When price later breaks back through the origin of the flush on a candle that is both unusually large and unusually active, it signals that the absorbing side has taken control with conviction rather than drift, so continuation in the breakout direction is more likely than chance. The edge should persist because breakout confirmation (range expansion plus activity surge) systematically filters out the low-participation pokes that produce most false breakouts — a behavioural asymmetry (committed vs. uncommitted flows) rather than a data-mined pattern.

## 2. Scope

- **primary_granularity:** H4
- **context_granularities:** none (the source states no higher-timeframe trend filter; adding one would be an invented rule — see §10 #9)
- **simulate_on:** H1 (contract v2 §5: decisions on H4, fills resolved on H1 bars; run both ways and report the delta)
- **pairs_requested (verbatim):** "All forex majors and minors"
- **pairs_available:** EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD (live); GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD (**pending** — Wave-1 additions; harness skips pairs with insufficient history rather than failing)
- **pairs_missing:** none requiring action. "Majors and minors" is fully covered by the 13-pair universe above per CONTRACT Part F ("any pair / majors" language maps to these 13). No DATA-GAP file is written: the source itself declares "volume (tick volume acceptable)", so OANDA tick count is the author-sanctioned feed, not a gap (flagged as a proxy in §8 and §10 #8).

**H4 primary, justification:** the source lists "H4|D1" without ranking. H4 is chosen because (a) ~33,100 bars/pair vs ~5,900 on D1 gives an adequate per-cell trade count for the gates after the strategy's triple entry filter (V-shape + big candle + volume) is applied — on D1 the filtered count would risk `low_confidence` in every fold; (b) the strategy's entry quality rests on single-candle anatomy (body vs. 20-bar average body), which is statistically meaningful at H4 and noisier at D1 where weekend gaps distort bodies; (c) contract v2 §5 resolves fills on H1 regardless, so no fill-fidelity is lost by choosing the finer decision frame.

## 3. Indicators

All computed on the H4 decision frame. `t` = decision bar (a closed bar). `calculate_pips`/`get_pip_value` supply pip size per pair.

| Indicator | Params | Source |
|---|---|---|
| Confirmed swing highs/lows | `confirmed_swing_points(high, low, period=5)`; stamped at confirmation bar c = k+5 where k = occurrence bar | `causal_structure.confirmed_swing_points` (**substitute** for the CSV pseudocode's banned `rolling(11, center=True)` — see §10 #1) |
| ATR | `atr(High, Low, Close, period=14)` — Wilder | `indicators.atr` |
| Average absolute candle body | `sma(abs(Close - Open), period=20)`, window bars t-19..t inclusive | `indicators.sma` on a derived series |
| Average tick volume | `sma(Volume, period=20)`, window bars t-19..t inclusive | `indicators.sma` on `Volume` |
| V-shape legs (private, specified here — NOT added to shared inventory) | For a swing low occurring at bar k: `down_leg = max(High[k-5 .. k]) - Low[k]`; `up_leg = max(High[k+1 .. k+5]) - Low[k]`. Mirror for a swing high: `up_leg_in = High[k] - min(Low[k-5 .. k])`; `down_leg_out = High[k] - min(Low[k+1 .. k+5])`. All inputs knowable at confirmation bar c = k+5. | private, defined in this spec (§10 #2) |
| Breakout level L (private derivation) | Long setup: `L = max(High[k-5 .. k])` for the governing V-low (the left lip / origin of the flush). Short setup: `L = min(Low[k-5 .. k])`. Fixed for the life of the setup. | private, defined in this spec (§10 #3) |

No other indicators. No EMA/ADX/session/news filters — none are in the source and the data does not exist (DATA_AVAILABILITY: no calendar/news feeds).

## 4. Entry — long

Evaluated at the close of each H4 bar `t`. A **long setup** becomes active at bar c (the confirmation bar of a qualifying V-low) and remains active for bars c … c+19 inclusive (20-bar validity window, per the pseudocode's `rolling(20)` — see §10 #7). Only the **most recently confirmed** qualifying V-low governs.

Setup qualification at bar c, for a swing low occurring at bar k = c−5:

1. **S1 — sharp down-leg:** `down_leg = max(High[k-5..k]) − Low[k] ≥ 1.5 × ATR14[k]` (ATR evaluated at the occurrence bar k; knowable at c).
2. **S2 — sharp rally leg:** `up_leg = max(High[k+1..k+5]) − Low[k] ≥ 1.0 × ATR14[k]` (the confirmation window doubles as the rally window; knowable at c exactly).
3. Setup level fixed at c: `L = max(High[k-5..k])`.

Breakout trigger, evaluated at the close of any bar `t` in the active window (c ≤ t ≤ c+19), all conditions on bar `t`:

4. **T1 — level break:** `Close[t] > L` (strict).
5. **T2 — big bold candle:** `body[t] = Close[t] − Open[t] > 1.5 × SMA20(|Close−Open|)[t]`. (The 1.5 multiplier and 20-bar window are the author's own pseudocode constants; body > 1.5× average *signed positive* body also enforces a bull candle.)
6. **T3 — activity surge:** `Volume[t] > SMA20(Volume)[t]` (tick volume — proxy flagged §8 / §10 #8).
7. **T4 — first signal only:** bar `t` is the FIRST bar of this setup's window on which T1–T3 all hold. The setup is then consumed; no re-emission from the same setup (conservative: fewer entries; see §10 #6).

- **entry type:** `market` (the trigger is the *close* of the breakout candle; the order is emitted at decision_bar = t and fills at the open of t+1 per F1/F2).
- **entry level:** n/a for market entry; decision-bar anchor for all geometry is `Close[t]`, `Low[t]`, and the fixed level/stop inputs above. Fill gaps are resolved honestly by F2/F3/F6; realized R ≠ declared R when the fill gaps (fleet rule 8).
- **expires_after_bars:** null (market order — no pending lifetime exists).

## 5. Entry — short

Exact mirror. A **short setup** activates at the confirmation bar c of a qualifying V-high occurring at k = c−5:

1. **S1′ — sharp up-leg:** `High[k] − min(Low[k-5..k]) ≥ 1.5 × ATR14[k]`.
2. **S2′ — sharp selloff leg:** `High[k] − min(Low[k+1..k+5]) ≥ 1.0 × ATR14[k]`.
3. Setup level: `L = min(Low[k-5..k])`.

Trigger at any bar t in c … c+19, first occurrence only:

4. **T1′:** `Close[t] < L` (strict).
5. **T2′:** `Open[t] − Close[t] > 1.5 × SMA20(|Close−Open|)[t]` (bear candle, big body).
6. **T3′:** `Volume[t] > SMA20(Volume)[t]`.
7. **T4′:** first qualifying bar of the setup; setup then consumed.

Entry type `market`, expires_after_bars null, geometry anchored to decision-bar prices as in §4.

## 6. Stop

- **Initial stop (long):** `stop = Low[k] − 1.0 pip`, where `Low[k]` is the V-swing low (the occurrence-bar extreme of the governing setup) and 1.0 pip uses `get_pip_value(pair)` conventions. **(short):** `stop = High[k] + 1.0 pip`.
  This is the **wider** of the two readings in the source ("beyond … the breakout candle / the V-swing extreme"): the V extreme is always beyond the breakout-candle extreme because S1 forces the flush to be ≥ 1.5×ATR deep. Wider stop ⇒ same pip reward divided by larger risk ⇒ smaller reported r-multiples — the conservative direction for gate-reported performance. The author's own pseudocode (`stop = breakout candle low`, tighter, r-inflating) is the rejected alternative (§10 #4). The 1.0-pip buffer mechanizes "beyond"; it coincidentally equals the cost-model spread and is flagged (§10 #5).
  Stop is an absolute price declarable at OrderIntent creation (Low[k] fixed at c ≤ t). Validation: stop is strictly below entry for longs by construction (entry ≈ Close[t] > L ≥ High[k] > Low[k]).
- **move_to_breakeven_on:** none (there is no take-profit leg to trigger it; the single leg is a trail).
- **trail:** `trail_atr_multiple = 3.0` × ATR(14) computed on the H4 frame, updated at each H4 bar close per F9 (moves only favourably, never widens). The trail starts from the initial stop — i.e. the effective stop is `max(initial_stop, highest_close_since_fill − 3.0×ATR14)` for longs (mirror for shorts), evaluated per F9 on H4 closes while fills resolve on H1 (simulate_on).

## 7. Exit legs

| Label | Fraction | Kind | Level formula |
|---|---|---|---|
| TRAIL | 1.0 | trailing | `atr_multiple = 3.0` × ATR14(H4), anchored/updated at H4 bar closes per F9; fill resolved on H1 bars |

Fractions sum to 1.0. One leg, full position. Rationale for rejecting the source's other reading ("exit at … next major S/R"): an S/R target requires an unbounded level search the source never parameterizes (how far back, which swings count as "major"), i.e. invented parameters; a pure ATR trail is fully expressible in contract v2 and is conservative — trails on breakout entries systematically give back open profit versus a fixed target (§10 #10). F11 handles end-of-data.

## 8. Filters

| Filter | Timeframe | When knowable |
|---|---|---|
| T3/T3′ activity surge: `Volume[t] > SMA20(Volume)[t]` — **Volume is OANDA tick count, not traded volume.** The source explicitly accepts tick volume ("tick volume acceptable"), so this is the author-sanctioned proxy, not a data gap; still, the filter measures *activity*, not committed volume, and that limitation is stated here and in §10 #8. | H4 | close of bar t |
| T2/T2′ big-body gate (also acts as the "decisive close" and false-breakout quality filter the article stresses) | H4 | close of bar t |
| S1/S2, S1′/S2′ V-shape quality gates (the article's "filter out low-quality swings") | H4 | confirmation bar c = k+5 |
| Session/news/calendar filters | — | **None exist in the source and no such data exists** (DATA_AVAILABILITY: no calendar, no news). No proxy substituted. |

## 9. Causality audit

| Rule | Inputs fully known at | Confirmation lag |
|---|---|---|
| Swing detection (all setups) | Swing at occurrence bar k is knowable only at **k+5** (period=5 subsequent bars failing to exceed it). Setups activate at c = k+5, never at k. The banned `rolling(11, center=True)` reading (knowable at k) is replaced by `causal_structure.confirmed_swing_points(period=5)` — **lag = 5 H4 bars**. | 5 bars |
| S1/S1′ sharp inbound leg | Uses High/Low over [k−5, k] and ATR14[k] — knowable at k, hence at c where it is evaluated. | 5 bars (via k) |
| S2/S2′ sharp outbound leg | Uses High over [k+1, k+5] = the confirmation window — knowable **exactly at c**, no earlier. This is deliberate: the rally leg is measured only over bars that already exist at confirmation. | 0 beyond the 5-bar swing lag |
| Level L = max/min of [k−5, k] | Knowable at k; frozen at c. | 5 bars (via k) |
| ATR14 (stop trail, shape tests) | Wilder ATR over completed bars — close of the bar where evaluated. | 0 |
| T2/T2′ big body (incl. SMA20 of \|body\|, window t−19..t) | close of bar t. The 20-bar average INCLUDES bar t's own body; this matches the author's pseudocode and is causal (bar t is closed at decision time). | 0 |
| T3/T3′ volume vs SMA20 (t−19..t inclusive) | close of bar t. | 0 |
| Entry fill | OrderIntent emitted at decision_bar t; fill eligible from t+1 (F1), market fill at open of t+1 (F2). | 1 bar execution lag |
| Trail updates | H4 bar closes only (F9); H1 bars inside the current H4 bar never move the stop. | up to 1 H4 bar |
| MTF | None — single decision frame (H4); simulate_on H1 is fill *resolution* only, the strategy never sees H1 data (contract §5), so no MTF alignment rule is invoked. | n/a |

No rule reads bar t+1 or later at decision time; no centred windows anywhere; no fills, P&L, or pending state observed by the strategy.

## 10. Ambiguities resolved

| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | CSV pseudocode detects swings with `rolling(11, center=True)` — the BANNED look-ahead pattern (knows at k that k is a swing extreme) | `causal_structure.confirmed_swing_points(period=5)`; setups act from k+5 onward using the level set at k. **Mandatory substitution, explicitly recorded.** Fewer, later signals. | Literal pseudocode semantics — rejected: look-ahead, contaminated the production strategy (INDICATOR_INVENTORY). |
| 2 | "V-shaped … sharp selloff immediately followed by sharp rally" is qualitative | Mechanized: inbound leg ≥ **1.5×ATR14[k]** over the 6 bars ending at k AND rebound leg ≥ **1.0×ATR14[k]** within the 5-bar confirmation window. Justification: "sharp" must mean large relative to typical bar range; 1.5×ATR over ≤6 bars is a genuine flush, 1.0×ATR rebound within 5 bars excludes rounded/slow bottoms. Both thresholds are evaluated only at c, so the rebound window costs no look-ahead. | (a) Drop the shape filter to bare "confirmed swing + breakout" — rejected: admits rounded bottoms = MORE trades, less faithful to the source's core idea. (b) 2.0/1.5×ATR thresholds — rejected: arbitrary tightening beyond what "sharp" supports; 1.5/1.0 already errs strict. |
| 3 | "closes … above the V-swing high **(or defined resistance)**" — which level? | L = `max(High[k−5..k])`, the origin (left lip) of the flush that formed the V — the level the V-low's own structure defines; fixed at c for the setup's life. | "Nearest confirmed swing high above price" — rejected: which swing counts is under-specified, it can sit below the flush origin, and it changes as new swings confirm (moving level = ambiguity per bar). |
| 4 | "Stop loss beyond the opposite side of the breakout candle / the V-swing extreme" — two different widths | **V-swing extreme ∓ 1.0 pip** (the wider). R-multiple direction: wider stop ⇒ same pip P&L ÷ larger initial risk ⇒ smaller reported r-multiples on winners — conservative for gate-reported performance. | Author's own pseudocode `stop = breakout candle low` (tighter) — rejected for the spec's declared rule: inflates winner r-multiples. (Recorded, not forgotten: reviewers may rerun with it as a sensitivity.) |
| 5 | "Beyond" implies a buffer of unspecified size | 1.0 pip, matching the cost-model spread scale (F10); fixed, pair-adjusted via pip conventions. **Flag:** this is a convention proxy, not source data. | 0.1×ATR buffer — rejected: a second invented parameter where a fixed pip suffices. |
| 6 | Pseudocode's signal can fire on multiple bars of the 20-bar window (re-emission) | First qualifying bar consumes the setup (T4/T4′). Fewer entries; avoids stacked re-entries that F12 would silently block anyway, making behaviour deterministic rather than engine-dependent. | Re-emit on every qualifying bar — rejected: admission then depends on engine concurrency state, an implicit channel the declarative contract forbids relying on. |
| 7 | Pseudocode's `v_low.rolling(20)` window starts at the (look-ahead) occurrence bar | Validity window = bars **c … c+19** (20 bars from CONFIRMATION). Later entries, fewer signals — conservative — and fully causal. | Window from occurrence k … k+19 — rejected: would let the strategy act at k+1..k+4, before the swing is knowable. |
| 8 | "above-average volume" but only OANDA tick count exists | Use tick volume vs its 20-bar SMA — the proxy the **source itself sanctions** ("tick volume acceptable"). Prominently flagged here and §8. | Treating real volume as required (DATA-GAP) — rejected: the author waives it; dropping T3 entirely — rejected: removes the article's core false-breakout filter and increases trade count. |
| 9 | Source lists "H4|D1" with no higher-timeframe filter | H4 decision frame only; no D1 trend filter added (nothing in the source supports one; inventing one would flatter results untraceably). | Adding a D1 EMA/structure trend gate "because breakouts need trend context" — rejected: invented rule, plus MTF causality surface for zero source support. |
| 10 | Exit: "measured objective (next major S/R) **or** trail … no fixed TP rule" | Single 3.0×ATR14(H4) trailing leg on 100% of the position. Conservative: trails surrender open profit versus fixed targets; expressible exactly in contract v2 (ExitLeg kind="trailing" + StopRule.trail_atr_multiple). 3.0 aligns with the system's existing 3×ATR convention (T6 harness), not a tuned value. | TP at "next major S/R" — rejected: "major" S/R requires an unbounded, unparameterized level search (invented parameters). 2.0×/4.0×ATR trails — rejected: parameter tuning the source doesn't support. |
| 11 | "bigger breakout candle preferred" — a preference, not a rule | Not mechanized (deterministic specs cannot express preferences); T2's 1.5× threshold already encodes "big". | Scaling conviction/size with candle size — rejected: System 1 never sizes (contract §10); ranking signals is not expressible in OrderIntent. |

## 11. Expected behaviour

- **Trade frequency:** the triple filter (qualified V-shape within 20 bars + 1.5× body breakout close + volume surge + first-signal-only) is strict. Expect roughly **2–6 trades per pair per year** on H4 (≈1 V-flush per 2–4 months per pair, of which a minority produce a confirmed breakout close in-window). Across 13 pairs: ~30–70 trades/year system-wide; per-cell (pair × H4) 10-year counts of ~20–60 trades — some cells will carry `low_confidence` flags; the pooled verdict is the meaningful one. D1 would have failed trade-count gates in most cells, confirming the H4 choice.
- **Likely failure modes at the gates:** (a) the wide V-extreme stop compresses winner r-multiples while the 3×ATR trail gives back trend profit — many trades will close between 0R and +1R, so expectancy hinges on a minority of runners; (b) weekend/news gaps through the wide stop fill at open (F6) producing losses > 1R on a wide base; (c) H1-resolved trails (F5 at H1 granularity) clip trades the H4-native run would survive — the native-vs-H1 delta will be material and must be reported; (d) tick-volume surges around rollover/illiquid hours can pass T3 without genuine participation.
- **Is the author's MODERATE conviction justified by the rules as written?** Yes, and if anything slightly generous. The entry filters are objective and defensible (confirmed structure + range expansion + activity), but the V-shape thresholds are our mechanization rather than the author's, the exit is a generic trail rather than the article's S/R-target craft, and no performance evidence exists in the source. This is a plausible-but-unproven breakout-with-confirmation strategy: exactly what MODERATE denotes. It should be judged by the pooled OOS gates with per-cell dispersion reported; a pass would be meaningful because the conservative readings (5-bar confirmation lag, wide stop, first-signal-only, trailing exit) all push reported performance down, not up.
