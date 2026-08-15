# SPEC-psar_gbpjpy_daily
**Source:** row 21 of forex_swing_strategies.csv · https://www.tradingview.com/script/Ky2dfFEn-Parabolic-SAR-Swing-strategy-GBP-JPY-Daily-timeframe/
**Conviction (author's):** MODERATE

## 1. Hypothesis
GBP/JPY daily trends persist for weeks at a time because they are driven by slow-moving macro forces — BoJ vs. BoE policy differentials and broad risk-on/risk-off flows — which do not reverse day-to-day; an accelerating trailing stop (Wilder's Parabolic SAR with a fast AF cap of 1.0) keeps the position alive through ordinary daily noise yet locks in profit progressively as the trend matures, harvesting the fat middle of sustained JPY-cross trends while self-limiting the damage from the whipsaw that ranging regimes inflict on any trend-follower.

## 2. Scope
- **primary_granularity:** D1
- **context_granularities:** none (single-timeframe strategy)
- **simulate_on:** H1 (decisions on D1 close; fills/stops resolved on H1 bars within each D1 span, per contract §5)
- **pairs_requested (verbatim):** `GBPJPY (optimized parameters)|other JPY crosses|FX majors`
- **pairs_available:**
  - GBP_JPY — **pending** (Wave-1 addition; the primary cell, the pair the AF parameters were optimized for)
  - EUR_JPY — **pending** (Wave-1 addition; secondary cell, run with the GBPJPY-optimized parameters verbatim — flagged in §11 as a parameter-mismatch cell, reported per-cell only)
- **pairs_missing:** AUD_JPY, CAD_JPY, CHF_JPY (the remainder of "other JPY crosses") are **not** in the Wave-1 pair list; "FX majors" beyond GBP_JPY are excluded by choice, not availability. **No DATA-GAP file is written**: the conservative coverage reading (§10 row 3) restricts the strategy to the two pending JPY crosses above, so nothing outside the Wave-1 data plan is required.

## 3. Indicators

| Indicator | Params | Source |
|---|---|---|
| Custom Parabolic SAR (private function `psar_custom`) | start AF α0 = 0.05, increment αΔ = 0.075, max AF αmax = 1.0 | Private to this strategy — NOT in `indicators.py` and must NOT be added there; exact recursion specified below |
| ATR | period = 14, computed on D1 (High, Low, Close) | Inventory `atr(high, low, close, period=14)` — used only for the trailing-stop proxy multiple |

### Custom PSAR — exact specification (Wilder's recursion, non-standard parameters)

State carried between bars: direction `dir_t ∈ {+1 (long), −1 (short)}`, stop value `SAR_t`, extreme point `EP_t`, acceleration factor `AF_t`. `SAR_t` is the stop level that is **active during bar t**, computed at the close of bar t−1.

**Initialization** (bar index 1, the second bar of any series):
- `dir_1 = +1` if `Close_1 ≥ Close_0`, else `−1`
- `SAR_1 = Low_0` if `dir_1 = +1`, else `High_0`
- `EP_1 = High_1` if `dir_1 = +1`, else `Low_1`
- `AF_1 = 0.05`

**Update at the close of bar t**, given state from t−1:

1. **Extreme-point / AF update** (only if no reversal on this bar — see step 3; evaluated against the state entering bar t):
   - If `dir = +1` and `High_t > EP`: `EP ← High_t`; `AF ← min(AF + 0.075, 1.0)`
   - If `dir = −1` and `Low_t < EP`: `EP ← Low_t`; `AF ← min(AF + 0.075, 1.0)`
2. **Next-bar SAR:**
   - `SAR* = SAR_t + AF × (EP − SAR_t)` (using the updated `EP`, `AF`)
   - Wilder clamp: if `dir = +1`: `SAR_{t+1} = min(SAR*, Low_t, Low_{t−1})`; if `dir = −1`: `SAR_{t+1} = max(SAR*, High_t, High_{t−1})`
3. **Reversal check** (uses the SAR active *during* bar t, i.e. `SAR_t`, knowable since the close of t−1):
   - Long trend (`dir = +1` entering bar t): reversal to short iff `Low_t < SAR_t` (strict inequality — see §10 row 4). Then: `dir_{t+1} = −1`; `SAR_{t+1} = EP` (the extreme point of the just-finished long trend); `EP ← Low_t`; `AF ← 0.05`. Step 1's update is discarded on a reversal bar.
   - Short trend: mirror — reversal to long iff `High_t > SAR_t`; then `SAR_{t+1} = EP`; `EP ← High_t`; `AF ← 0.05`.

**Warm-up:** no OrderIntent may be emitted from the first 20 D1 bars of any loaded series (ATR(14) stabilisation plus PSAR initialisation arbitrariness). The signal requires a completed reversal, which cannot occur before bar 2 in any case.

## 4. Entry — long

At the close of D1 decision bar t:

1. Compute the custom PSAR state (§3) using only bars 0…t.
2. The trend state **entering** bar t was short (`dir_t = −1`), **and** during bar t a reversal to long occurred: `High_t > SAR_t` (the stop active during bar t, fixed at the close of t−1). Equivalently: `dir_{t+1} = +1` while `dir_t = −1` — a state change between two consecutive closed bars.
3. No further conditions (no trend, momentum, session, or volatility gates exist in the source).

- **Entry type:** `market`
- **Entry level:** none declared (`entry_price = None`); fill at the open of bar t+1 (first H1 bar of the next D1 bar under H1 fill resolution), per F1/F2
- **expires_after_bars:** null (market entry fills at the next bar's open or not at all; the field is inapplicable, declared null, not left to default)

## 5. Entry — short

Mirror of §4:

1. Custom PSAR state computed on bars 0…t.
2. Trend state entering bar t was long (`dir_t = +1`), **and** `Low_t < SAR_t` during bar t → reversal to short (`dir_{t+1} = −1`).
3. No further conditions.

- **Entry type:** `market`; `entry_price = None`; fill at open of t+1 per F1/F2
- **expires_after_bars:** null

## 6. Stop

- **Initial stop (exact formula):** `stop.price = SAR_{t+1}` — the SAR value computed at the close of decision bar t per §3 step 2/3, i.e. the stop level the live strategy would carry into bar t+1. For a long flip this is the extreme point (lowest low) of the just-completed short trend — below the entry, so the side check passes; mirror for shorts. This is an absolute number fully declarable at OrderIntent creation (fleet rule 8 satisfied; the fill price is never referenced).
- **move_to_breakeven_on:** none
- **trail:** `trail_atr_multiple = 2.0` on ATR(14, D1), updated at bar close per F9 — this is the **SAR-trail proxy**, the conservative expressible stand-in for the per-bar SAR re-computation that contract v2 cannot express (§10 rows 1–2). The stop starts at the true SAR level and thereafter only tightens, at 2.0×ATR from the most favourable close; it never widens (contract invariant).

## 7. Exit legs

| Label | Fraction | Kind | Level formula |
|---|---|--:|---|---|
| time-backstop | 1.0 | time | bars = 126 D1 bars (≈ 6 calendar months) from entry fill |

Fractions sum to 1.0. The **primary exit is the trailing stop of §6**; the time leg exists only because an OrderIntent must carry at least one exit leg and as a backstop against positions stranded to end-of-data (F11). It binds rarely (typical SAR trade lasts days to a few months); when it binds it cuts a still-open trade at market, which can only hurt a still-running trend trade — the conservative direction.

## 8. Filters

**None.** The source defines no trend filter, session gate, volatility gate, or news gate, and none is invented here. Two source artefacts are disposed of explicitly:

- The source's **"date-window input limits backtest period"** is a TradingView backtest-harness feature, not a trading rule. It is realised by the walk-forward fold boundaries (`walk_forward.py`), not by any strategy-level gate (§10 row 6).
- **Costs** are engine-applied per F10 (1.0-pip spread + 0.5-pip slippage on entry, commission 0). FLAGGED PROXY: GBP/JPY retail spreads typically run 1.5–3 pips, so the mandated cost model *understates* GBPJPY transaction costs — every GBP_JPY and EUR_JPY result in the report carries this caveat. The value may not be changed (F10 imports the constant block); it is disclosed, not substituted.

## 9. Causality audit

| Rule | Inputs | Bar at which fully known | Lag statement |
|---|---|---|---|
| PSAR state & SAR_{t+1} (§3) | OHLC of bars 0…t only; recursion carries state forward, never reads t+k | Close of decision bar t | Zero lag — the recursion is strictly causal by construction; `SAR_t` (the stop active during bar t) was fixed at close of t−1 |
| Flip detection (§4/§5) | `dir_t`, `SAR_t` (both known since close of t−1) and bar t's High/Low | Close of bar t | The signal is a state change between two **consecutive closed bars**; fill occurs at open of t+1 (F1/F2), never on bar t |
| Initial stop price (§6) | `SAR_{t+1}` computed from bars 0…t | Close of bar t | Declarable absolute at intent creation; no fill-price dependence |
| Trailing stop (§6) | ATR(14) of completed D1 bars | Updated at each bar's close using that bar's completed ATR (F9) | Uses only closed bars; never widens |
| Time backstop (§7) | Count of elapsed bars since fill | Every bar | Counts only elapsed time |
| ATR(14) indicator | High/Low/Close of bars t−13…t | Close of bar t | Standard trailing window, causal |
| Swing/pivot/ZigZag/fractal rules | — none in this strategy — | — | **No confirmation-lag exposure**; nothing in this spec uses `detect_swing_points` or any centred window |
| Multi-timeframe context | — none — | — | §4 of the contract is vacuous: single timeframe. H1 is used **engine-side only** for fill resolution (contract §5); the strategy never sees H1 data, so no H1/D1 alignment causality question arises |

## 10. Ambiguities resolved

| # | Ambiguity | Conservative reading taken | Alternative rejected |
|--:|---|---|---|
| 1 | "Pure stop-and-reverse" is one atomic action: exit long *and* enter short on the same SAR cross. Contract v2 has no signal exits, no OCO, no supersede; the strategy never observes its position | Each SAR flip is emitted as a **fresh market entry** in the new direction; the open trade is closed only by its own trailing stop / time backstop. Because F12 admits at most 1 concurrent position, an opposite-direction intent emitted while the prior trade is still open **cannot be admitted and is treated as dropped** (stated engine assumption). The "always in the market" property is lost; realized entries are a subset of true SAR flips → fewer trades, the conservative direction | Rejected: emitting the reversal as an exit instruction on the open position (no such mechanism exists — inexpressible, not merely less conservative). Rejected: raising `max_concurrent_positions` to 2 so the reversal "always fills" (creates simultaneous long+short exposure the source never intends, and double-counts margin/risk) |
| 2 | The SAR trail is recomputed every bar by the AF recursion; a StopRule is declared once per intent and cannot be re-emitted per bar (option (a) is impossible) | Expressible proxy: initial stop at the true SAR level `SAR_{t+1}` (faithful initial risk) + trail at **2.0×ATR(14, D1)**. 2.0×ATR approximates the SAR's *average* mid-trend distance on GBPJPY D1 (daily ATR ≈ 100–150 pips; SAR typically sits 1.5–2.5×ATR away mid-trend). In extended trends the real SAR (AF → 1.0) tightens far below 2×ATR and locks profit; the proxy gives back more → **worse exits, conservative**. **The backtest therefore measures a degraded variant: the adaptive accelerating trail IS this strategy's documented edge, and it is only approximated** | Rejected: per-bar SAR re-emission (inexpressible). Rejected: 1.5×ATR (closer to late-trend SAR, but tighter than the typical mid-trend SAR → *better* exits than the source on average — non-conservative). Rejected: static stop + time exit only (measures "price above entry after N bars", a momentum test that is not this strategy at all) |
| 3 | `target_pairs` lists "other JPY crosses" and "FX majors" alongside GBPJPY | Coverage restricted to **GBP_JPY (primary) + EUR_JPY (secondary)**, both Wave-1 pending. Rationale: the AF parameters (0.05/0.075/1.0) are explicitly "optimized for GBPJPY Daily"; porting them unchanged to AUD_JPY/CAD_JPY/CHF_JPY (not even in the Wave-1 plan) or to USD-majors with different volatility scale would be a different, untested strategy. Restricting coverage = fewer cells, the conservative direction. No DATA-GAP is raised because the restriction makes the strategy fully expressible within the Wave-1 data plan | Rejected: including AUD_JPY/CAD_JPY/CHF_JPY (would require a DATA-GAP for pairs no wave plans to ingest, and applies pair-optimised parameters off-label). Rejected: "FX majors" (all five live pairs) — same parameter-mismatch objection, and it would dilute the GBPJPY cell the author actually staked the claim on |
| 4 | Reversal trigger: does the SAR need to be *crossed* or merely *touched*? Source pseudocode compares SAR to Close; TradingView `ta.sar` reverses on penetration | Strict inequality: long→short reversal iff `Low_t < SAR_t` (mirror for shorts). Strict inequality produces **fewer** flips than touch-reversal (`≤`) → fewer trades, later entries — conservative | Rejected: `Low_t ≤ SAR_t` touch-reversal (more whipsaw flips → more trades). Rejected: close-based flip (`Close_t < SAR_t` per the pseudocode's `exit_long = close < sar`) — ignores intrabar penetration, exits *later* and at worse prices than the live SAR; kept as noted divergence, not adopted |
| 5 | Entry mechanics on the flip: the source's stop-and-reverse fills at the moment of the SAR cross intrabar | `market` entry at the **open of bar t+1** (F2) — one full bar later than the live intrabar cross. Later entry, adverse-selection exposed (the flip bar's momentum often continues into t+1's open, but gaps against are taken honestly per F2/F3-class fill rules) — conservative on entry timing | Rejected: `buy_stop` at flip-bar high (an invented filter that skips weak flips → *fewer* trades but *better-selected* ones; it is not in the source and flatters the strategy). Rejected: modelling an intrabar fill at `SAR_t` on bar t (violates F1 — the intent cannot fill on its decision bar) |
| 6 | "date-window input limits backtest period" | Harness-level artefact realised by walk-forward folds; **no** date condition appears in strategy logic | Rejected: encoding a date gate in the strategy (meaningless for out-of-sample evaluation and not a trading rule) |
| 7 | Cost model vs GBPJPY reality | F10 constants (1.0-pip spread, 0.5-pip entry slippage, 0 commission) applied unchanged, as mandated; the understatement of real GBPJPY spread (typically 1.5–3 pips retail) is **flagged here and must be flagged in the report** | Rejected: substituting a higher bespoke spread for GBPJPY (F10 forbids changing the imported constants; a silent proxy change would break comparability with the 134,520 live rows) |
| 8 | Trend-state definition | The recursion's internal `dir` state (§3), flipped only on SAR penetration | Rejected: the CSV pseudocode's `uptrend = sar < close` (close-relative state flickers near the SAR and disagrees with the recursion at touch bars; the recursion is the faithful Wilder object the author describes) |

## 11. Expected behaviour

- **Trade frequency:** with AF start 0.05 / step 0.075 (much faster than Wilder's 0.02/0.02 default), GBPJPY D1 produces roughly **10–25 flips per year**; over the ~20-year backfill expect ~200–400 admissible trades in the GBP_JPY cell — fewer after F12 drops intents emitted while a prior trade is still open (§10 row 1). EUR_JPY, run with un-re-optimized parameters, is a secondary per-cell datapoint, expected to degrade; it must never be pooled away from the GBP_JPY verdict (contract §8 per-cell reporting).
- **What the backtest does NOT capture:** the documented edge is the **adaptive accelerating trail** — the SAR ratcheting toward price as AF climbs to 1.0. The expressible variant replaces it with a fixed 2.0×ATR trail plus a one-time SAR-level initial stop, and replaces atomic reversal with stop-out-then-maybe-re-enter. Both substitutions point the same way: **worse exits in mature trends, missed reversals while the stale leg is open, fewer trades**. A pass here understates the documented system; a fail does not refute it. The report must say this verbatim.
- **What would make it fail the gates:** extended D1 ranging regimes (JPY crosses spent much of 2016–2019 range-bound) produce SAR whipsaw bleed; the fast AF cap makes flips *more* frequent in chop, not less. F5 (stop-before-target at H1 resolution) punishes the tight SAR levels immediately after a flip, where the new trend's SAR sits at the old trend's extreme and early pullbacks are common. The understated GBPJPY spread (§8) flatters results slightly; per-cell reports must carry the caveat.
- **Author conviction (MODERATE) — justified?** For the *documented* system, yes: it is objective, fully codable, parameter-tuned to the pair, and the author is honest about whipsaw-proneness and the absence of performance figures. For the **expressible degraded variant**, MODERATE is the ceiling and arguably generous: the mechanism the author optimised (the accelerating trail) is exactly the mechanism the contract approximates. Expect the degraded variant to pass gates only if GBPJPY D1 trends are strong enough to carry a 2×ATR trail — i.e. the result tests JPY-cross trend persistence more than it tests PSAR.
