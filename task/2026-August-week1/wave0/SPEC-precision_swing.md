# SPEC-precision_swing

**Source:** row 10 of forex_swing_strategies.csv · https://www.forexstrategiesresources.com/trend-following-forex-strategies-ii/214-precision-swing-strategy/
**Conviction (author's):** MODERATE

## 1. Hypothesis

When four independent trend/momentum lenses — price vs. a fast/slow EMA pair, the EMA pair's own ordering, the Parabolic SAR's trailing point, and a detrended oscillator — all agree on direction on the H4 frame, the market is in a persistent institutional-order-flow regime rather than noise, and continuation is more likely than reversal. The edge should persist because trend-following harvests the behavioural premium created by herding, anchoring, and slow information diffusion in FX; the DPO-near-zero veto exists to stand aside during the mean-reverting flat regimes where trend systems bleed. A swing-anchored stop with a fixed 1:1.25 reward converts that agreement into a positive-skew bet.

## 2. Scope

- **primary_granularity:** H4 (first granularity listed in the CSV; pseudocode is frame-agnostic — see §10 #1)
- **context_granularities:** none (no higher-timeframe filter exists in the source; D1/W1 are alternative *run* frames, not context)
- **simulate_on:** H1 (fills resolved on H1 bars per contract §5)
- **Additional cells:** the strategy is also runnable standalone on D1 and W1 (the CSV lists H4|D1|W1). Per-cell reporting (contract §8) applies. W1 carries the standing statistical warning (contract §7: ~156 W1 train bars, single-digit trade counts per fold) and W1 data is stale ~8 weeks pending the Wave-1 refresh — a known staleness note, not a gap.
- **pairs_requested (verbatim):** "Any"
- **pairs_available:** EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD (live); GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD (**pending** — Wave-1 additions, harness skips if history insufficient)
- **pairs_missing:** none ("Any" is fully covered by the 13-pair FX universe; XAU_USD is not named)

No DATA-GAP file is required: every input is OHLCV-derived and all pairs are live or Wave-1 pending.

## 3. Indicators

All computed on the primary frame (H4) from `Close/High/Low`. Decision bar = bar *t*; all indicator values below are evaluated at the **close of bar *t***.

| Indicator | Params | Source |
|---|---|---|
| EMA fast | `ema(close, 14)` | inventory `ema` |
| EMA slow | `ema(close, 34)` | inventory `ema` |
| ATR | `atr(high, low, close, 14)` — used **only** to define the DPO-near-zero band (§8), not for stops | inventory `atr` |
| Confirmed swing low / swing high | `confirmed_swing_points(high, low, period=5)` → level of the **most recent confirmed** swing low (long) / swing high (short) at bar *t* | `causal_structure.confirmed_swing_points` (confirmation lag = 5 H4 bars, §9) |
| Parabolic SAR | Wilder recursive, AF start = 0.02, AF step = 0.02, AF **max = 0.02** (see formula below and §10 #2) | **private function — not in inventory** |
| Detrended Price Oscillator (causal form) | `DPO[t] = Close[t-11] − SMA(Close, 21)[t]`, i.e. `close.shift(11) - close.rolling(21).mean()` — verified to touch only bars ≤ *t* | **private function — not in inventory** (formula verbatim from CSV pseudocode) |

**Private PSAR specification (Wilder, exact):**

- State per bar: trend dir ∈ {+1, −1}, SAR, EP (extreme point), AF.
- Seed at the second bar of the series (bar index 1): if `Close[1] ≥ Close[0]` → dir = +1, SAR = `Low[0]`, EP = `High[1]`; else dir = −1, SAR = `High[0]`, EP = `Low[1]`. AF = 0.02.
- For each subsequent bar *t*, in order:
  1. `SAR[t] = SAR[t-1] + AF × (EP − SAR[t-1])`.
  2. Clamp (long): `SAR[t] = min(SAR[t], Low[t-1], Low[t-2])` (using only prior bars); (short): `SAR[t] = max(SAR[t], High[t-1], High[t-2])`.
  3. Reversal test using bar *t*'s own range: long reverses if `Low[t] < SAR[t]` → dir = −1, `SAR[t] = EP`, EP = `Low[t]`, AF = 0.02; short reverses if `High[t] > SAR[t]` → dir = +1, `SAR[t] = EP`, EP = `High[t]`, AF = 0.02.
  4. If no reversal: long → if `High[t] > EP`: EP = `High[t]`, AF = min(AF + 0.02, **0.02**); short → if `Low[t] < EP`: EP = `Low[t]`, AF = min(AF + 0.02, **0.02**). (With max = 0.02, AF is constant 0.02 after seeding — this is the literal reading of "(0.02|0.02)".)
- Condition uses the post-reversal `SAR[t]` against bar *t*'s range; all inputs are bars ≤ *t*, so the value is knowable at the close of bar *t*.

**Private DPO specification (exact):** `DPO[t] = Close[t−11] − mean(Close[t−20 … t])`. First valid value at bar index 20. This is the CSV's causal form; the classic charting DPO (`Close[t] − SMA(21)[t−10]`, centred) is look-ahead and is **rejected** (§10 #4).

## 4. Entry — long

Decision at the close of H4 bar *t*. All of the following must hold (values at bar *t*):

1. `Close[t] > EMA14[t]` **and** `Close[t] > EMA34[t]` ("close above EMAs" = above both; §10 #5).
2. `EMA14[t] > EMA34[t]`.
3. `PSAR[t] < Low[t]` (dot strictly below the bar — the CSV pseudocode's `psar < d['low']`, stricter than `psar < close`; §10 #3).
4. `DPO[t] > 0` **and** `DPO[t] ≥ 0.25 × ATR14[t]` (flat-market veto, §8).
5. A confirmed swing low exists: `SL_level = ` level of the most recent swing low confirmed at or before bar *t* (occurred at some bar *k*, confirmed at *k+5 ≤ t*), **and** `SL_level < Close[t]` (stop must sit below the decision close; otherwise no trade).
6. **Onset only:** emit an intent only on the first bar *t* for which conditions 1–5 all hold, i.e. they did **not** all hold at bar *t−1*. No re-emission while conditions persist (§10 #8).

Then:

- **entry type:** `market`
- **entry level:** none declared (fill = open of bar *t+1*, F2)
- **expires_after_bars:** null (market order; not applicable)
- **size_fraction:** 1.0 (fixed single unit; the page's 1-2-3-5-8-13 martingale lot sequence is explicitly ignored per the CSV risk_note, §7/§10 #7)

## 5. Entry — short

Mirror of §4 at the close of H4 bar *t*:

1. `Close[t] < EMA14[t]` **and** `Close[t] < EMA34[t]`.
2. `EMA14[t] < EMA34[t]`.
3. `PSAR[t] > High[t]`.
4. `DPO[t] < 0` **and** `DPO[t] ≤ −0.25 × ATR14[t]`.
5. `SL_level = ` level of the most recent confirmed swing high (confirmed at *k+5 ≤ t*), **and** `SL_level > Close[t]`.
6. Onset only, same rule as §4.6.

Entry type `market`, fill at open of *t+1* (F2), `expires_after_bars` null, `size_fraction` 1.0.

## 6. Stop

- **Initial stop (long):** `StopRule.price = SL_level` — the most recent confirmed swing-low level from §4.5, taken **exactly** (no buffer; §10 #6). For shorts, the most recent confirmed swing-high level.
- **Anchoring (fleet rule):** because the entry is `market`, the fill price is unknowable at emission. All geometry is anchored to the **decision-bar close** `D = Close[t]`, not the eventual fill. Declared risk is `R = |D − SL_level|`; realized R will differ when the *t+1* open gaps (F3/F6 resolve the fill honestly). The source's implicit fill-anchored reading is recorded as rejected (inexpressible) in §10 #9.
- **move_to_breakeven_on:** none (single exit leg; no leg exists to trigger it).
- **trail:** none (static stop; the source specifies no trailing rule).

## 7. Exit legs

| Label | Fraction | Kind | Level formula |
|---|---|---:|---|---|
| TP1 | 1.0 | take_profit | long: `D + 1.25 × (D − SL_level)`; short: `D − 1.25 × (SL_level − D)`, where `D = Close[t]` of the decision bar |

Fractions sum to 1.0. The source's alternative exit — "exit when EMA or PSAR flips position" — is a signal exit and is **inexpressible** declaratively in contract v2 (an OrderIntent cannot carry a future-condition exit); the expressible fixed 1:1.25 RR target is taken instead (§10 #10). **Lot sizing is a fixed single unit, `size_fraction = 1.0` — the page's optional 1-2-3-5-8-13 martingale sequence is explicitly ignored**, as instructed by the CSV's own risk_note.

## 8. Filters

| Filter | Rule | Timeframe | Knowable at |
|---|---|---|---|
| Flat-market veto (the only filter) | Trade only if `|DPO[t]| ≥ 0.25 × ATR14[t]`; skip when `|DPO[t]| < 0.25 × ATR14[t]` ("DPO near zero") | Primary frame (H4), bar *t* close | Close of decision bar *t* (both DPO and ATR14 use only bars ≤ *t*) |

The "near zero" prose is made mechanical as a 0.25×ATR(14) band because DPO is in price units and needs a volatility-relative threshold; the rejected alternatives (no filter, absolute pip band, other fractions) are in §10 #11. No session, news, calendar, or higher-timeframe trend gate exists in the source, and none is added. No non-price data is used anywhere in this strategy.

## 9. Causality audit

Decision bar = H4 bar *t*; OrderIntent emitted with `decision_bar = t`; fill eligible from bar *t+1* (F1), market fill at open of *t+1* (F2).

| Rule | Inputs | Fully known at | Confirmation lag |
|---|---|---|---|
| §4.1/§5.1 Close vs EMAs | `Close[t]`, `EMA14[t]`, `EMA34[t]` (recursive EMA over closes ≤ *t*) | Close of bar *t* | 0 |
| §4.2/§5.2 EMA14 vs EMA34 | EMAs at *t* | Close of bar *t* | 0 |
| §4.3/§5.3 PSAR position | PSAR recursion over bars ≤ *t* (§3 formula; reversal test uses bar *t*'s own High/Low, completed at its close) | Close of bar *t* | 0 |
| §4.4/§5.4 DPO sign + band | `Close[t−11]` and `Close[t−20 … t]`; ATR14 over bars ≤ *t* | Close of bar *t* | 0 — **verified**: max index touched is *t*; this is the CSV's causal form, not the centred charting DPO |
| §4.5/§5.5 Stop level | Most recent confirmed swing low/high via `causal_structure.confirmed_swing_points(period=5)` | A swing at bar *k* is knowable only at bar **k+5**; the strategy at bar *t* uses only swings with *k+5 ≤ t*, acting on the **level** set at *k* | **5 H4 bars** (≈20 hours) |
| §4.6/§5.6 Onset | Conditions at *t* and *t−1* | Close of bar *t* | 0 |
| §7 TP1 level | `D = Close[t]`, `SL_level` (already confirmed) | Close of bar *t* — declarable absolute at OrderIntent creation | 0 |
| MTF | None — no context timeframe is used, so the §4 context-bar causality rule is vacuous here. If the strategy is also run on D1/W1 cells, each cell is decided and resolved on its own native frame (+H1 fill resolution), with no cross-frame reads | — | — |

No rule in this spec reads bar *t+1* or later. `detect_swing_points` is not used.

## 10. Ambiguities resolved

| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | CSV lists three frames "H4\|D1\|W1" with no primary | H4 is primary (first listed, largest trade sample of the three that retains acceptable statistics); D1/W1 run only as additional standalone cells | Treating all three as simultaneous context filters (invents an MTF gate the source does not have); W1 as primary (single-digit trades per fold = uninformative) |
| 2 | PSAR "(0.02\|0.02)": which parameters? | Wilder AF start = 0.02, step = 0.02, **max = 0.02** (literal reading; AF never accelerates) | Standard max 0.20 (invents an unstated parameter; accelerates the SAR, more reversals, more trades) |
| 3 | "PSAR dot below price" — below what? | `PSAR < Low[t]` (CSV pseudocode; stricter — dot must clear the whole bar) | `PSAR < Close[t]` (looser, more trades) |
| 4 | DPO variant | CSV causal form `Close[t−11] − SMA21[t]` (verified touches only bars ≤ *t*) | Classic centred DPO `Close[t] − SMA21[t−10]` — **look-ahead, banned-class** |
| 5 | "Close above EMAs" | Above **both** EMA14 and EMA34 (stricter) | Above EMA14 only (implied by condition 2 anyway; looser) |
| 6 | "SL below previous swing low" — how far below? | Stop placed **exactly at** the confirmed swing level (no buffer; level itself is the conservative stop — a buffer would only tighten it) | Subtracting a buffer (invents an unstated parameter; wider risk changes declared R) |
| 7 | Page's 1-2-3-5-8-13 lot sequence | Ignored — fixed single unit, `size_fraction = 1.0`, as the CSV risk_note itself instructs | Implementing the soft martingale (cannot: the strategy never observes fills/P&L in contract v2, and it is a red-flag sizing scheme) |
| 8 | Condition set holds for many consecutive bars | Emit on **onset only** (first bar all conditions true); one position per (strategy, pair, granularity) via F12 default | Re-emitting every bar (F12 blocks fills while a position is open, but redundant intents add noise and ambiguity) |
| 9 | R measured from fill (source implies) | Anchor stop/TP geometry to decision-bar close `D` (fleet rule — fill unknowable at emission); realized R ≠ declared R under gaps, resolved honestly by F3/F6 | Fill-anchored geometry — **inexpressible** in contract v2, not merely less conservative |
| 10 | "Exit when EMA or PSAR flips position" | Rejected as **inexpressible** (declarative contract has no future-condition exit); the source's own alternative — fixed TP at 1.25× stop distance — is the exit | Attempting to proxy the flip exit (e.g. trailing PSAR stop) — invents an unstated mechanism and is not the documented rule |
| 11 | "Skip when DPO near zero" — undefined band | `|DPO| < 0.25 × ATR14` → skip (volatility-relative since DPO is in price units; a wider band skips more trades = conservative) | Dropping the filter entirely (more trades, contradicts source intent); absolute pip band (not pair-scale-invariant); 0.10/0.50 × ATR (unstated constants — 0.25 chosen once, no optimisation per contract §10) |
| 12 | Direction flip while a position is open | The open position is **not** closed or reversed by the opposite signal (no such mechanism exists — no OCO/supersede); F12 (max 1 concurrent position) blocks the new market intent while the old position is open. Residual risk: an opposite onset intent emitted the bar after the old position closes can enter the reversal late — direction of bias: slightly fewer reversal trades than the author's live experience | "Signal closes/reverses the position" — mechanism does not exist in contract v2 |
| 13 | No confirmed swing exists in history, or stop on wrong side of close | **No trade** (condition §4.5/§5.5 fails) | Falling back to an ATR stop (invents an unstated rule) |

## 11. Expected behaviour

- **Trade frequency:** low-to-moderate. Four simultaneous conditions plus onset-only emission on H4: roughly **1–4 trades per pair per month** in trending years, near zero in flat regimes (the DPO band enforces this). Per walk-forward fold (6-month OOS ≈ 780 H4 bars) expect on the order of 5–20 trades per pair-cell; pooled across the 5 live pairs, folds should clear minimum-count gates, but individual D1 cells will be thinner and W1 cells will be single-digit (standing W1 warning).
- **Likely gate failure modes:** (a) the 1:1.25 RR with a swing stop gives a modest payoff ratio; if the four-filter agreement has no real edge, win rate lands near 1/(1+1.25) ≈ 44% and expectancy ≈ 0; (b) PSAR with AF pinned at 0.02 flips slowly, so condition 3 is the loosest filter — in choppy markets the EMA conditions may agree while PSAR whipsaws, and the DPO band (0.25×ATR) may be too narrow to veto all chop; (c) entries are late by construction (EMA cross + confirmed-swing stop + onset bar + next-open fill), so the strategy systematically buys strength part-way into a move and is hurt when H4 trends are short-lived; (d) F5 (stop-before-target on the same H1 bar) penalises trades whose 1.25R target sits within typical H1 ranges of the swing stop.
- **Author's conviction:** MODERATE is fair, arguably generous. The confluence logic is coherent and the CSV's own reviewer note flags the "high profitability" claim as unverified and the martingale sizing as a red flag; stripped to fixed sizing and honest causal swings, this is a vanilla four-filter trend follower whose survival depends entirely on whether H4 FX trends in 2006–2026 paid more than 1:1.25 after costs (1.0 pip spread + 0.5 pip slippage on entry, F10). Nothing in the rules as written distinguishes it from the large class of published EMA/PSAR systems that fail OOS.
