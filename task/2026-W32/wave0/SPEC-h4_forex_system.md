# SPEC-h4_forex_system
**Source:** row 8 of forex_swing_strategies.csv · https://www.forexstrategiesresources.com/trend-following-forex-strategies/44-4h-system/
**Conviction (author's):** MODERATE

## 1. Hypothesis
A fast/slow moving-average crossover (6 EMA vs 13 SMA) on H4/D1 captures the early phase of short-term trend persistence in GBP pairs, and requiring simultaneous MACD-momentum agreement plus Parabolic SAR position filters out the whipsaw crosses that dominate in range-bound regimes. The claimed edge rests on the well-documented behavioural tendency of FX trends to persist over multi-bar horizons (herding, staggered information diffusion, and central-bank policy cycles that unfold over days), so that a confirmed momentum cross is more likely than chance to be followed by continuation far enough to reach a fixed pip target before a fixed stop.

## 2. Scope
- **primary_granularity:** H4
- **context_granularities:** none (single-timeframe decision logic; see §10 row 6)
- **simulate_on:** H1 (fills, stops, and TP legs resolved on H1 bars per contract §5 / Part D)
- **D1 variant:** the source defines the same system on D1 with its own SL/TP table. Contract v2 keys cells by (strategy, pair, granularity), so the H4 and D1 variants are run as **two separate cells** — separate `generate_orders` streams on the native frame, each resolved on H1. The D1 cell is declared with primary_granularity=D1 and the D1 rows of the tables in §6/§7. It is NOT a D1 filter on the H4 cell (see §10 row 6).
- **pairs_requested (verbatim):** `GBP/USD|GBP/JPY`
- **pairs_available:** GBP_USD (live); GBP_JPY (**pending** — Wave-1 addition per DATA_AVAILABILITY.md §"Pairs being added in Wave 1"; harness skips it if backfill incomplete — this is NOT a gap)
- **pairs_missing:** none → no DATA-GAP note required. All granularities (H4, D1, H1 simulation frame) are current.

## 3. Indicators

| Indicator | Params | Source |
|---|---|---|
| EMA | period=6, on Close | inventory `ema(close, 6)` |
| SMA | period=13, on Close | inventory `sma(close, 13)` |
| MACD | fast=12, slow=26, signal=9, on Close → macd line, signal line | inventory `macd(close, 12, 26, 9)` |
| Parabolic SAR | step=0.02, max=0.2 | **PRIVATE — not in inventory; specified below** |
| Pip size | per pair | inventory `get_pip_value(asset)` (GBP_USD 0.0001, GBP_JPY 0.01) |

**Private Parabolic SAR specification (Wilder, 1978) — to be implemented as a private module function, NOT added to `indicators.py`:**

State per series: `trend ∈ {+1 long, −1 short}`, `SAR`, `EP` (extreme point), `AF` (acceleration factor).

- Initialisation: first bar has no SAR. Seed at the second bar: if `Close[1] >= Close[0]` initialise long (trend=+1, `SAR = Low[0]`, `EP = High[1]`), else short (trend=−1, `SAR = High[0]`, `EP = Low[1]`). `AF = 0.02` in both cases.
- Recursion at each subsequent bar `t` (using only data at or before `t`):
  1. `SAR_raw = SAR[t−1] + AF × (EP − SAR[t−1])`.
  2. Clamp (Wilder's rule): if long, `SAR[t] = min(SAR_raw, Low[t−1], Low[t−2])`; if short, `SAR[t] = max(SAR_raw, High[t−1], High[t−2])`.
  3. Reversal check: if long and `Low[t] < SAR[t]`, flip to short: `SAR[t] = EP` (the highest high of the prior long leg), `EP = Low[t]`, `AF = 0.02`. Mirror for short: if `High[t] > SAR[t]`, flip to long: `SAR[t] = EP` (lowest low of the prior short leg), `EP = High[t]`, `AF = 0.02`.
  4. Otherwise update EP/AF: if long and `High[t] > EP`, set `EP = High[t]`, `AF = min(AF + 0.02, 0.20)`. Mirror for short with `Low[t] < EP`.
- Output series `psar[t]`, causal by construction (each value depends only on bars ≤ t).
- **"PSAR dot below the candle" at bar t is defined as `psar[t] < Low[t]`** (long mode). "Dot above" is `psar[t] > High[t]`. See §10 row 3.

Warm-up: the decision logic needs at least 27 completed bars (slow EMA 26 + signal seed); orders are emitted only where all of EMA6, SMA13, MACD line, signal line, and psar are defined.

## 4. Entry — long

Evaluated at the **close of decision bar t** on the native frame (H4 cell or D1 cell), using only bars ≤ t:

1. `EMA6[t] > SMA13[t]` **and** `EMA6[t−1] <= SMA13[t−1]` — the 6 EMA crosses above the 13 SMA **on bar t**.
2. `MACD_line[t] > Signal[t]` **and** `MACD_line[t−1] <= Signal[t−1]` — the MACD line crosses up through its signal line **on bar t**.
3. `psar[t] < Low[t]` — the Parabolic SAR dot is below bar t.

All three conditions must hold simultaneously on bar t (conjunctive reading; see §10 row 1).

- **Entry type:** `market`
- **Entry level:** none declared (`entry_price = None`); fills at the open of bar t+1 per F2, plus adverse slippage per F10.
- **expires_after_bars:** null (market entry — no pending order exists to expire).

## 5. Entry — short

Mirror image, evaluated at the close of decision bar t:

1. `EMA6[t] < SMA13[t]` **and** `EMA6[t−1] >= SMA13[t−1]` — 6 EMA crosses below 13 SMA on bar t.
2. `MACD_line[t] < Signal[t]` **and** `MACD_line[t−1] >= Signal[t−1]` — MACD line crosses down through signal on bar t.
3. `psar[t] > High[t]` — SAR dot above bar t.

All three simultaneously. Entry type `market`, `entry_price = None`, expires_after_bars null.

## 6. Stop

Initial stop, anchored to the **decision-bar close** `C = Close[t]` (fleet rule 8 — the fill is unknowable at emission), with pip size `P = get_pip_value(pair)`:

- Long: `StopRule.price = C − SL_pips × P`
- Short: `StopRule.price = C + SL_pips × P`

`SL_pips` per cell:

| Cell | SL_pips |
|---|---:|
| H4 GBP_USD | 70 |
| H4 GBP_JPY | 90 |
| D1 GBP_USD | 100 |
| D1 GBP_JPY | 150 |

- `move_to_breakeven_on`: none
- `trail_atr_multiple`: none (static stop; stops never widen, and this one never moves)

Note (fleet rule 8): the source measures SL/TP from the fill. Anchoring at the decision close means declared geometry ≠ fill-relative geometry when bar t+1 opens away from `C`; F2/F6 resolve the actual fill and stop honestly, so realised R ≠ declared R on gaps. The fill-anchored reading is recorded as rejected-inexpressible in §10 row 4.

## 7. Exit legs

| Label | Fraction | Kind | Level formula |
|---|---:|---|---|
| TP1 | 1.0 | take_profit | Long: `C + TP_pips × P` · Short: `C − TP_pips × P` (`C = Close[t]`, `P = get_pip_value(pair)`) |

`TP_pips` per cell:

| Cell | TP_pips |
|---|---:|
| H4 GBP_USD | 60 |
| H4 GBP_JPY | 80 |
| D1 GBP_USD | 280 |
| D1 GBP_JPY | 320 |

Fractions sum to 1.0 (single leg). Any position not stopped or taken out closes at the final bar's close with reason `END_OF_DATA` (F11). The source's signal-based exit ("exit when 6 EMA crosses back through 13 SMA") is **not expressible** in contract v2 and is rejected — see §10 row 2; its absence means positions otherwise run to SL, TP1, or END_OF_DATA.

## 8. Filters

The source defines **no** trend filter, session filter, volatility filter, or news filter beyond the entry conditions themselves. None are added.

- The MACD-cross and PSAR conditions in §4/§5 are entry conditions, not filters, and are evaluated on the decision timeframe (H4 or D1) at the close of bar t — fully knowable at that close.
- No external data of any kind is required. Costs (1.0 pip spread + 0.5 pip entry slippage, commission 0) are applied by the engine per F10 and are not strategy logic.

## 9. Causality audit

| Rule | Inputs | Bar at which fully known |
|---|---|---|
| EMA6/SMA13 cross (long & short) | Close[t−1], Close[t] plus history → EMA/SMA at t and t−1 | Close of decision bar t. No confirmation lag beyond the bar itself; EMA/SMA are causal. |
| MACD cross (long & short) | Close history through t → MACD line, signal at t and t−1 | Close of decision bar t. MACD is causal. |
| PSAR dot position | psar[t] per §3 recursion; Low[t]/High[t] | Close of decision bar t. The recursion in §3 reads only bars ≤ t; no repaint, no centred window, no swing-point confirmation lag. **This strategy uses no swing/pivot/ZigZag/fractal construct**, so the `causal_structure` confirmation-lag machinery is not needed; `detect_swing_points` is not used. |
| Entry fill | — | Order emitted at close of t, eligible from bar t+1 (F1), market fill at open of t+1 (F2). The decision never reads the fill bar. |
| Stop / TP levels | Close[t], fixed pip tables, `get_pip_value` | Close of decision bar t — both are absolute, declarable prices at OrderIntent creation (fleet rule 8 satisfied). |
| D1 cell vs H4 cell | Each cell decided on its own native frame | **No multi-timeframe interaction exists in either cell**, so the §4 MTF causality rule (context bar must have closed) has nothing to bite on. Each cell is single-timeframe by construction (§10 row 6). Fills are resolved on H1 within each native bar's span (Part D); the strategy never sees H1 data. |
| GBP_JPY warm-up | Wave-1 backfill history | If backfill is incomplete at Wave 2 runtime the harness skips the pair (DATA_AVAILABILITY); no decision is made on partial history. |

## 10. Ambiguities resolved

| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---:|---|---|---|
| 1 | "6 EMA crosses above 13 SMA with MACD lines crossing up **and/or** Parabolic SAR dot below" — the and/or is logically sloppy; the CSV pseudocode uses `cross & (macd_state OR psar)`. | **Full conjunction:** EMA cross AND MACD cross AND PSAR dot position, all on decision bar t. Fewest trades; a single bar must show all three events. | (a) Disjunctive "cross AND (MACD OR PSAR)" per pseudocode — admits ~2× more signals including momentum-less crosses. (b) MACD *state* (`macd > signal`) rather than MACD *cross* on bar t, per pseudocode `ml>sg` — admits entries long after momentum confirmed; rejected because the prose says "crossing". |
| 2 | Exit "when 6 EMA crosses back through 13 SMA" is a signal-based exit. Contract v2 has no declarative opposite-cross ExitLeg kind and the strategy never observes its position. | **Fixed per-cell TP/SL as the sole exits** (TP table §7, SL table §6). Positions run to SL, TP1, or END_OF_DATA (F11). | Opposite-cross exit — **inexpressible**, not merely less conservative. Consequence: trades that the author would have scratched on a fast re-cross instead ride to the full stop, degrading results vs the source's chart evidence; this bias is accepted and stated in §11. |
| 3 | "PSAR dot below the candle" — relative to Low, Close, or just SAR mode? | `psar[t] < Low[t]` (dot strictly below the bar's low; standard long-mode test). | `psar[t] < Close[t]` — weaker, admits dots inside the bar's range after a shallow reversal; produces more, lower-quality entries. |
| 4 | Are the pip SL/TP measured from the fill or from a decision-time price? The source assumes fill-relative. | Anchored at the **decision-bar close** `Close[t]` as absolute prices (fleet rule 8; declarable at OrderIntent creation). Realised R ≠ declared R when bar t+1 gaps (F2/F6 resolve honestly). | Fill-relative measurement — **inexpressible** under contract v2 (fill price unknowable at emission). |
| 5 | "MACD lines crossing up" — must the MACD cross occur on the same bar as the EMA cross, or within some window? | **Same decision bar t** (strictest; no lookback window parameter invented). | "MACD cross within the last N bars" — requires inventing an undeclared N and admits stale momentum; rejected as less conservative. |
| 6 | `timeframes: H4|D1` — is D1 a higher-timeframe filter on H4, or a separate variant? | **Two separate cells** (pair × granularity), each with its own SL/TP row, no MTF combination. This matches the source's separate per-timeframe SL/TP tables. | D1-as-filter-on-H4 — the source states no filter direction or alignment rule; inventing one adds an MTF causality surface (§4 contract) with no textual basis. |
| 7 | EMA/SMA/MACD price input (close vs typical price)? | **Close**, per the CSV pseudocode (`ewm(span=6)` and `rolling(13)` on `d['close']`) and inventory defaults. | Typical price `(H+L+C)/3` — no textual support. |

## 11. Expected behaviour

- **Trade frequency:** the conjunctive triple-condition entry is restrictive. EMA6/SMA13 crosses occur on H4 GBP pairs roughly every 1–3 weeks; requiring a same-bar MACD cross plus PSAR alignment cuts that substantially. Expect roughly **1–5 trades per month per H4 cell** (often fewer), and **a few trades per year per D1 cell**. Two pairs × two granularities = 4 cells (GBP_JPY pending Wave-1 backfill). Per-cell trade counts will be modest; D1 cells may approach `low_confidence` territory in 6-month OOS windows.
- **Risk/reward as written:** H4 GBP_USD risks 70 pips to make 60 (R:R 0.86) and H4 GBP_JPY risks 90 to make 80 (0.89) — the H4 cells need a win rate above ~54% **before** the 1.5-pip round-trip cost (F10) just to break even. The D1 cells are healthier (280/100 = 2.8R; 320/150 ≈ 2.1R). The fixed-TP-only exit (§10 row 2) removes the author's re-cross scratch, so realised H4 win rates will sit below the source's "6 wins / 2 losses" chart markup.
- **What would fail the gates:** (a) H4 cells — negative R:R plus costs means any win-rate slippage produces negative expectancy; whipsaw regimes (PSAR flips that arrive one bar after the cross) should generate clusters of full-stop losses. (b) D1 cells — too few trades per fold for statistical confidence. (c) GBP_JPY cells skipped entirely if Wave-1 backfill is incomplete.
- **Is MODERATE justified by the rules as written?** Barely. The only on-page evidence is a marked-up chart (6/2), and the two rules the backtest cannot honour (and/or looseness, re-cross exit) both flattered the original. Under the conservative conjunctive + fixed-exit reading, the H4 variant is structurally handicapped (sub-1R target with 1.5-pip costs on GBP spreads) and the D1 variant is the more plausible carrier of any edge. A pooled pass would be meaningful precisely because the deck is stacked against it; a per-cell read (H4 vs D1 separately) is essential and is provided for by the cell structure in §2.
