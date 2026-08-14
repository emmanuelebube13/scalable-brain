# SPEC-reps_donchian_pyramiding

**Source:** row 14 of forex_swing_strategies.csv · https://www.forexfactory.com/thread/552483-reverse-engineering-a-profitable-system-reps
**Conviction (author's):** MODERATE

## 1. Hypothesis

Turtle-style Donchian breakouts on the weekly chart capture the birth of large multi-month FX trends, which persist because macro divergences (rates, growth, capital flows) reprice currencies slowly and herding/underreaction extends the move; pyramiding into confirmed strength then concentrates exposure in the small number of trends that pay for the many false breakouts, so expectancy is carried by a fat right tail rather than by win rate.

## 2. Scope

- **primary_granularity:** D1 (all OrderIntents are decided at D1 closes; see §4/§5 and §10 #9 for why the H4 pattern is evaluated at D1 cadence)
- **context_granularities:** W1 (DERIVED from D1 bars by weekly resample — see §3 and §10 #3; the native W1 frame is NOT used), H4
- **simulate_on:** H1
- **pairs_requested (verbatim):** "Any trending FX pairs; prefer habitual trenders e.g. EURAUD over EURGBP|majors|minors"
- **pairs_available:** EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD (live); EUR_AUD (Wave-1 pending — the one pair the author explicitly prefers); GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, AUD_NZD, EUR_CAD (Wave-1 pending, covered by "minors")
- **pairs_missing:** none. "Any trending FX pairs / majors / minors" is fully covered by the 5 live + 8 pending pairs. **No DATA-GAP file is required** — all data (D1, H4, H1 OHLCV) exists and the W1 frame is derived, not loaded (see §10 #3).
- **Metadata:** `max_concurrent_positions = 4` (MUST be declared and MUST appear in the report per F12; see §10 #2). `primary_granularity="D1"`, `context_granularities=("W1_derived","H4")`, `simulate_on="H1"`, `source_row=14`.

## 3. Indicators

| Indicator | Params | Source |
|---|---|---|
| Donchian channel, D1 | `donchian_channel(high_D1, low_D1, period=20)`, then `.shift(1)` | INDICATOR_INVENTORY (`donchian_channel`) |
| Donchian channel, W1 (derived) | Resample D1→W1 (weeks = Sunday 21:00Z → Friday 21:00Z, matching broker week and bar-open stamping; High=max, Low=min, Close=last), then `donchian_channel(high_W1, low_W1, period=20)`, then `.shift(1)` | Inventory `donchian_channel` applied to a derived frame; the resample itself is a frame transformation, specified here, not added to the shared inventory |
| Donchian channel, H4 | `donchian_channel(high_H4, low_H4, period=20)`, then `.shift(1)` | Inventory (`donchian_channel`) |
| ATR (trailing exit leg) | `atr(high, low, close, period=14)` on the simulation frame (H1), engine-side per F9 | Inventory (`atr`); applied by the position engine, not the strategy |

Notes:
- The `.shift(1)` on every Donchian channel is mandatory and matches the author's own pseudocode (`rolling(20).max().shift()`): the channel at decision bar *t* is computed from bars up to *t-1* only, so a breakout of the channel is never measured against a channel that contains the current bar. This shift is the confirmation-lag mechanism for this strategy (see §9).
- The derived weekly frame must be causally merged into the D1 decision frame: a weekly bar covering Sunday 21:00Z → Friday 21:00Z is knowable only from the first D1 bar stamped after Friday 21:00Z (i.e. the Sunday 21:00Z D1 bar). Mechanically: shift the derived W1 frame's index forward by one full weekly interval, then `merge_asof(..., direction="backward", allow_exact_matches=False)` per CONTRACT §4.
- No swing/ZigZag/pivot/fractal constructs are used anywhere in this strategy. `detect_swing_points` is not needed and remains banned.

## 4. Entry — long

All conditions are evaluated at the close of the D1 decision bar *t*. `dcW_hi(t)`, `dcW_lo(t)` denote the shifted derived-W1 channel knowable at *t*; `dcD_hi(t)`, `dcD_lo(t)` the shifted D1 channel at *t*; `dcH_hi(u)`, `dcH_lo(u)` the shifted H4 channel at H4 bar *u*.

**Series state machine (declarative, causal — the strategy tracks only its own emissions and bar data):**
- State `LONG_SERIES` becomes ACTIVE at the first INITIAL_LONG emission and stays ACTIVE until the close of a D1 bar where `close(t) <= dcD_lo(t)` (SERIES_RESET_LONG event), after which it becomes INACTIVE. While ACTIVE, no further INITIAL_LONG may be emitted (see §10 #11 for why the trailing-leg exit does NOT reset the state).

**INITIAL_LONG (state = INACTIVE):**
1. The most recently closed derived-W1 bar *w* satisfies `close_W1(w) > dcW_hi(w)` — i.e. the weekly bar that closed most recently before decision bar *t* closed above its shifted 20-week upper channel.
2. *t* is the first D1 decision bar after *w* closed (the signal fires exactly once per weekly breakout event, at the first D1 close knowable after the W1 close).
3. Guard: proposed stop (below) is strictly below `close(t)`; otherwise skip emission.
- **Entry type:** market. **Entry level:** none (F2: fills at open of D1 bar *t+1*, H1-resolved, plus adverse slippage).
- **expires_after_bars:** 1 (hygiene: a market intent fills at the next bar's open or not at all; expiry 1 guarantees zero lingering pendings, so pending-order overlap arithmetic is trivially satisfied — at most one unfilled market intent per side exists for exactly one bar).

**ADDON_LONG_D1 (state = LONG_SERIES ACTIVE):**
1. Fresh D1 breakout crossover: `close(t) > dcD_hi(t)` AND `close(t-1) <= dcD_hi(t-1)` (one emission per crossover event — see §10 #10).
2. Pyramid-into-strength proxy: `close(t) > close(t_prev)` where `t_prev` is the decision bar of the most recent emitted long intent of any kind (see §10 #8 — the source's "risk-free first" gate is unobservable; this is the conservative expressible proxy).
3. Same stop guard as INITIAL_LONG.
- **Entry type:** market. **expires_after_bars:** 1.

**ADDON_LONG_H4 aggressive (state = LONG_SERIES ACTIVE), evaluated at D1 close *t* using only H4 bars closed at/before *t*:**
1. Counter-move exists: within the H4 bars comprising D1 bar *t* and the preceding D1 bar (up to 12 H4 bars), at least one H4 bar *u1* has `close_H4(u1) < dcH_lo(u1)` (H4 pushed opposite to the D1/W1 trend).
2. Reversal back with trend: a later H4 bar *u2 > u1* within the same window has `close_H4(u2) > dcH_hi(u2)`.
3. Pyramid-into-strength proxy as in ADDON_LONG_D1 condition 2; same stop guard.
4. At most one ADDON_LONG_H4 emission per D1 decision bar.
- **Entry type:** market. **expires_after_bars:** 1.

F12 note: with `max_concurrent_positions = 4`, admission of a 5th concurrent position is refused by the engine; emission continues declaratively. Net effect: initial + up to 3 concurrent add-ons, excess add-on signals silently unfilled — conservative (under-pyramids vs the source).

## 5. Entry — short

Full mirror (no asymmetry in the source):
- State `SHORT_SERIES` ACTIVE from INITIAL_SHORT until a D1 close with `close(t) >= dcD_hi(t)` (SERIES_RESET_SHORT).
- INITIAL_SHORT: most recently closed derived-W1 bar *w* has `close_W1(w) < dcW_lo(w)`; fires once, at the first D1 close after *w*; stop guard: stop strictly above `close(t)`.
- ADDON_SHORT_D1: `close(t) < dcD_lo(t)` AND `close(t-1) >= dcD_lo(t-1)`; pyramid proxy `close(t) < close(t_prev)`.
- ADDON_SHORT_H4: H4 bar *u1* with `close_H4(u1) > dcH_hi(u1)` followed by later *u2* with `close_H4(u2) < dcH_lo(u2)` within the same 2-D1-bar window; pyramid proxy and guard mirrored.
- Entry type market, expires_after_bars = 1 throughout.
- LONG_SERIES and SHORT_SERIES are independent state machines; a pair can in principle carry both (W1 whipsaw). This is faithful to the source (independent trend-birth detectors per direction) and bounded by F12=4 per (strategy, pair, granularity) — recorded in §10 #12.

## 6. Stop

Identical structure for every intent (initial and all add-ons):

- **Initial stop price (long):** `dcH_lo(u*)` — the shifted 20-period H4 Donchian lower band evaluated at the last H4 bar *u** closed at/before the D1 decision bar *t*. This is an absolute price fully knowable at decision-bar close (FLEET decision-bar anchoring rule). Short: `dcH_hi(u*)`.
- **move_to_breakeven_on:** none. The source's "move to breakeven as soon as practicable" trails the H4 channel until breakeven, which is not expressible (StopRule supports only ATR trails and leg-triggered breakeven; there is no TP leg to trigger it). Conservative reading: no breakeven move — positions carry initial risk until exit. Rejected alternatives in §10 #5/#6.
- **trail:** none on the StopRule (static stop). The source's "trail SL along the H4 DC" is a channel trail — inexpressible; an ATR-trail proxy on the StopRule is rejected (§10 #5) because it would double-trail against the trailing exit leg with the tighter one dominating unpredictably.
- **R anchoring:** initial risk = |decision close − stop price| is declarable at intent creation. The engine's r_multiple uses |fill − stop| per §3.3; when the market fill gaps (F3/F6), realized R ≠ declared R — accepted, recorded per FLEET rule 8 (fill-anchored variant rejected as inexpressible).

## 7. Exit legs

Every intent (initial and add-ons, both directions) carries exactly one leg:

| Label | Fraction | Kind | Level formula |
|---|---|---|---|
| SERIES_EXIT | 1.0 | trailing | `atr_multiple = 6.0`, ATR(14) on the simulation frame (H1), trailed per F9 |

Fractions sum to 1.0. ✔

**What this approximates:** the source's exit is "close ALL positions when price hits the opposing 20-period Donchian channel on the D1 chart" — a moving price level, not expressible as any ExitLeg kind (take_profit needs a fixed absolute price at creation; time is a bar count). The conservative expressible approximation is a chandelier-style ATR trail standing in for the D1-DC(20) opposing band. Calibration arithmetic (declared, not tuned): H1 ATR(14) on the 5 majors ≈ 12–20 pips, so 6.0×H1-ATR ≈ 70–120 pips ≈ 1.0–1.5× typical D1 ATR; the opposing D1-DC(20) band in an established trend typically sits 1.5–3× D1 ATR away from price. The trail is therefore **tighter than the true channel exit in most conditions → earlier exits → truncated winners → pessimistic bias**, which is the required conservative direction. The fidelity loss is severe for a trend-following system and is flagged in §10 #4 and §11. The static H4-DC stop (§6) remains as the deeper protective layer; in practice the trailing leg will usually bind first.

## 8. Filters

The source defines **no** trend/session/volatility/news filters beyond the breakout structure itself.

- **Pair-quality preference** ("prefer habitual trenders e.g. EURAUD over EURGBP"): non-mechanical; NOT implemented as a gate. The strategy runs on all available pairs; per-cell verdicts (CONTRACT §8) will reveal any trendiness dependence. Recorded in §10 #13.
- **Structural state gates** (already in §4/§5, restated as filters for completeness): INITIAL only when series INACTIVE (evaluated on D1, knowable at D1 close); add-ons only when series ACTIVE (D1 close); pyramid-into-strength proxy (D1 close, uses only the strategy's own prior emissions). All are knowable at the decision bar.
- No session, spread, news, calendar, COT, or volatility gates exist in the source; none are invented. No non-price data is required anywhere in this spec, so no proxy (including the 1.0-pip cost-model spread) is substituted for any filter.

## 9. Causality audit

Bars are stamped at their open (DATA_AVAILABILITY). "Knowable at X" means all inputs are from bars closed at/before X.

| Rule | Inputs | Fully knowable at | Confirmation lag |
|---|---|---|---|
| Derived-W1 Donchian (20, shifted) | D1 bars resampled to W1; channel shifted 1 weekly bar | A weekly bar *w* (Sun 21:00Z→Fri 21:00Z) is knowable at the first D1 bar stamped after Fri 21:00Z; the shifted channel at *w* uses weekly bars up to *w−1* | **1 weekly bar (shift)** + up to 2 days of transport lag (W1 close Friday → first D1 decision bar Sunday 21:00Z). INITIAL entries therefore fire 2–3 calendar days after the weekly breakout close — deliberately conservative |
| D1 Donchian (20, shifted) | D1 bars up to *t−1* | D1 close *t* | 1 D1 bar (shift) |
| H4 Donchian (20, shifted) for stops | H4 bars up to *u* | D1 close *t* ⊇ close of last H4 bar *u** | 1 H4 bar (shift) |
| H4 aggressive add-on pattern | H4 closes within D1 bars *t−1* and *t* | D1 close *t* (all constituent H4 bars have closed) | Up to 2 D1 bars vs an H4-native decision — later entries, conservative (§10 #9) |
| Series state machine | D1 closes vs shifted D1 channel; own prior emissions | D1 close *t* | Reset requires a full D1 close through the opposing shifted channel; strategy cannot observe its own fills/exits, so state never depends on fill information |
| INITIAL entry fill | — | Open of D1 bar *t+1* (F1/F2) | 1 D1 bar execution lag |
| Stop level | Shifted H4 channel at decision bar | D1 close *t* (absolute price at intent creation) | None beyond the shift |
| Trailing exit leg | H1 ATR(14), completed bars only | Updated at each H1 bar close per F9 | 1 H1 bar on each trail update |

**Swing/pivot/ZigZag/fractal audit:** this strategy uses none. The Donchian `.shift(1)` plays the equivalent causal role: no channel value ever incorporates the bar being tested against it. MTF causality follows CONTRACT §4 exactly (context frames shifted one full interval before asof-merge; no exact matches).

## 10. Ambiguities resolved

| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | "Break of the channel" — intrabar touch or close-through? | Close-through on the signal timeframe (W1 close, D1 close, H4 close), then market entry next decision bar | `buy_stop`/`sell_stop` pending at the channel level (intrabar touch, earlier fill, more trades — the author's pseudocode uses `close > channel`, so the pending reading is also less faithful) |
| 2 | Pyramiding depth — source caps add-ons only via money management ("zero added risk"), which is unbounded in position count | `max_concurrent_positions = 4` declared in metadata (1 initial + ≤3 add-ons), MUST be stated in the report per F12; classic Turtle 4-unit pyramid makes 4 defensible rather than arbitrary | (a) Unlimited concurrency — undeclarable, risk-unbounded; (b) collapse to initial-entry-only — deletes the strategy's core mechanism, so punishing that the backtest would no longer measure REPS |
| 3 | Native W1 frame is stale ~8 weeks (last bar 2026-06-12): W1 entries undecidable after that date | Derive the weekly frame from current D1 bars (Sun 21:00Z→Fri 21:00Z resample); W1 channel computed on the derived frame. No missing data → no DATA-GAP | Using the native stale W1 frame (signals silently frozen for the last ~8 weeks of every OOS window — worse than a derivation whose only cost is potential minor divergence from OANDA's native weekly aggregation) |
| 4 | "Series exit: close ALL when price hits the opposing D1 20-DC" — a moving price level, not expressible in ExitLeg kinds | Single trailing leg, `atr_multiple=6.0` on the simulation-frame ATR(14) (calibration in §7); per-position trailing approximation instead of a synchronized close-all. Fidelity loss: the trail is tighter than the channel, truncating the right-tail winners that carry this strategy's edge | (a) Direct channel exit — inexpressible (no ExitLeg kind accepts a moving series); (b) per-bar re-emission of updated take_profit legs — impossible, exits are frozen at intent creation; (c) `time`-based exit — unrelated to the source logic |
| 5 | "Trail SL along the H4 DC until breakeven reached" — channel trailing stop | Static initial stop at the shifted H4-DC(20) opposing band; no StopRule trail. Stop never improves except via the engine's trailing exit leg | (a) `trail_atr_multiple` on the StopRule as an H4-DC proxy — rejected: double-trailing against the SERIES_EXIT leg makes the effective exit the tighter of two interacting trails, an uncontrolled distortion; (b) true channel trail — inexpressible |
| 6 | "Move to breakeven as soon as practicable" — no trigger defined | `move_to_breakeven_on = none`; positions carry initial risk until exit (conservative: the source's risk-free claim is forfeited) | Fabricating a take_profit leg solely to trigger breakeven — invents an exit the source does not have and would scale out of a system whose edge is holding winners |
| 7 | Money management: "initial risk 0.25–2% of balance", "lock 50% of floating profit via SL and use the other 50% to fund the next add-on", "after a stopped-out loss, next stake = lesser of recalculated stake minus prior loss or initial risk %" | **Out of scope — all are position sizing / equity-curve rules.** System 1 never sizes; results are r-multiples only. Every intent uses default `size_fraction = 1.0`. The "zero added risk" pyramid property is NOT reproduced | Modelling locked-profit compounding or loss-recovery staking — inexpressible in OrderIntent terms and prohibited by contract ("No position sizing") |
| 8 | "Add-on longs at locations allowed by MM" — i.e. only after the initial entry is risk-free. Fill/P&L state is unobservable to a v2 strategy | Pyramid-into-strength price proxy: an add-on requires `close(t)` beyond the decision close of the most recent emitted same-direction intent | (a) Ungated add-ons — more concurrent risk than the source intends; (b) conditioning on fill state — inexpressible (strategy never observes fills) |
| 9 | H4 aggressive add-on decision cadence — H4-native or D1-native? | D1-native: the H4 pattern (counter-move then reversal) is evaluated at the D1 close over the ≤12 most recent closed H4 bars; entry is a D1 market order | Emitting on the H4 frame — mixes decision granularities against a single `primary_granularity` declaration and creates earlier, more frequent entries (non-conservative) |
| 10 | D1 add-on re-emission: close can stay above the shifted channel for many bars | Only the fresh crossover (`close` crosses from ≤ to > the shifted channel) emits; one intent per breakout event | Any-bar-above re-emission — floods market intents every D1 bar; F12 caps positions but NOT pendings, and the resulting emission storm is neither faithful nor bounded |
| 11 | Series reset after an early trailing-leg exit: the strategy cannot observe that the SERIES_EXIT leg closed its position | State resets ONLY on the D1-close-through-opposing-channel event; a new INITIAL may not fire before then even if flat | Resetting state on assumed exit — inexpressible (no fill observation) and would permit faster re-entry (non-conservative) |
| 12 | Long and short series concurrently on one pair (independent W1 detectors) | Allowed; bounded by F12=4 per (strategy, pair, granularity) | Mutual exclusion — invents a rule the source does not state |
| 13 | "Prefer habitual trenders e.g. EURAUD over EURGBP" | Not implemented as a filter; all available pairs traded, per-cell verdicts expose pair dependence | A trendiness pre-screen (e.g. ADX gate) — invents a filter with a threshold the source never declares |
| 14 | R anchored to fill vs decision bar | All stop/exit geometry anchored to decision-bar-knowable prices (shifted H4-DC level at decision close; trail multiple declared at creation). Realized R ≠ declared R when the fill gaps; F3/F6 resolve fills honestly | Fill-anchored geometry — inexpressible (fill price unknowable at emission), per FLEET decision-bar anchoring rule |

## 11. Expected behaviour

- **Trade frequency:** very low for INITIAL entries — a 20-week Donchian close-breakout fires roughly 0–2 times per pair per year (fewer in ranging pairs like EUR_GBP, more in habitual trenders). Add-ons (D1 and H4-aggressive) fire only inside active series, adding perhaps 1–4 positions per genuine trend. Expect on the order of 1–5 positions per pair per year fleet-wide, clustered in trending regimes; long flat stretches are normal.
- **Gate prognosis:** per-cell trade counts will frequently be single digits per 6-month OOS fold → `low_confidence` flags and failure of `OOS ≥ 60 months` arithmetic on many cells (CONTRACT §7 W1-statistics warning applies in spirit: the signal cadence is weekly even though decisions are D1). The pooled verdict across 13 pairs is the only numerically meaningful cell.
- **What would make it fail the gates:** (a) the SERIES_EXIT ATR-trail approximation (§10 #4) cuts winners short — it systematically removes the fat right tail that is this strategy's entire edge, so a fail is partly an artefact of expressibility, not necessarily of the idea; (b) no breakeven/locked-profit protection (§10 #6/#7) leaves full initial risk on every unit, so losing streaks in choppy regimes cost more than the live-traded version; (c) W1 breakout systems lose persistently in mean-reverting regimes.
- **Is the author's MODERATE conviction justified by the rules as written?** The written rules are a coherent, fully mechanical Turtle descendant with a genuinely clever zero-added-risk pyramid — but that property lives entirely in the money management (§10 #7), which this harness cannot express. As specified here, the backtest measures a *degraded* REPS: capped pyramiding, no breakeven, an over-tight trail standing in for the D1 channel exit. A fail should be read as "inexpressible fidelity loss + regime dependence", a pass as strong evidence for the underlying edge despite handicaps. MODERATE is fair; the spec's conservatism biases the verdict downward.
- **W1 staleness note:** no impact on signals as specified (weekly frame derived from current D1 data), but the derivation must be noted in the report so results are not attributed to the native W1 feed.
