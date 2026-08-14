# SPEC-pinbar_key_level_50pct

**Source:** row 30 of forex_swing_strategies.csv · https://dailypriceaction.com/blog/forex-pin-bar-trading-strategy/
**Conviction (author's):** MODERATE

## 1. Hypothesis

A long-tailed rejection candle ("pin bar") printing at a well-tested horizontal support or resistance level signals that larger participants aggressively absorbed one side of the market within a single day, leaving the losing side trapped; the edge persists because trapped traders must exit (fueling the reversal) and because the 50%-retracement limit entry buys into the residual stop-run at a discount, converting a visually obvious pattern into a structurally favourable reward-to-risk profile (minimum 2R) where even a modest win rate is profitable.

## 2. Scope

- **primary_granularity:** D1 (author: "setups below the daily timeframe are ignored")
- **context_granularities:** none (H4 "optional entry refinement" dropped — see §10 #8)
- **simulate_on:** H1 (decision on D1; fills, stops, TP resolved against H1 bars per contract §5)
- **pairs_requested (verbatim):** "Forex majors and minors (examples: AUDNZD, USDCAD)"
- **pairs_available:**
  - Live: EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD
  - Wave-1 pending (declared; harness skips until backfill lands): GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD
- **pairs_missing:** none. "Majors and minors" is mapped to the full 13-pair research universe (the DATA_AVAILABILITY table states these 13 cover all rows saying "majors"/"any pair"). AUD_NZD, the author's documented 3.5R example, is Wave-1 pending, not a gap. **No DATA-GAP file is required**: S/R levels are derivable from OHLCV via causal swings; trend lines are dropped as discretionary (§10 #1), not a data gap.

## 3. Indicators

| Indicator | Params | Source |
|---|---|---|
| Confirmed swing lows (support levels) | `confirmed_swing_points(high, low, period=5)` on D1; keep the last 6 confirmed swing-low levels | `causal_structure` |
| Confirmed swing highs (resistance levels / TP candidates) | `confirmed_swing_points(high, low, period=5)` on D1; keep the last 6 confirmed swing-high levels | `causal_structure` |
| ATR | `atr(high, low, close, period=14)` on D1 | inventory `indicators.atr` |
| Pin-bar geometry (private) | exact formulas in §4/§5 | private, fully specified below (no inventory equivalent; do NOT add to `indicators.py`) |

Private pin-bar geometry, evaluated on a completed D1 bar `t` with `O,H,L,C` and `rng = H - L` (bar skipped if `rng == 0`):

- `body = |C - O|`
- `tail_dn = min(O, C) - L`  (lower wick)
- `tail_up = H - max(O, C)`  (upper wick)

These are exactly the formulas in the CSV's pseudocode column; the 0.67 / 0.33 thresholds are kept verbatim.

## 4. Entry — long

At the **close** of D1 bar `t` (the decision bar), all of the following must hold:

1. `rng_t > 0`.
2. `tail_dn_t >= 0.67 * rng_t`  (lower tail at least 2/3 of range — exact CSV threshold).
3. `body_t <= 0.33 * rng_t`  (small body — exact CSV threshold).
4. `C_t >= O_t`  (bullish close; conservative reading of "bullish pin bar" — see §10 #3).
5. **Level confluence (mandatory):** among the last 6 confirmed D1 swing-low levels knowable at bar `t` (confirmation bar <= `t`; lag = 5 D1 bars, see §9), at least one level `L_s` satisfies `|L_t - L_s| <= 0.25 * ATR14_t`. The pin bar's tail must print at a confirmed support level.
6. **TP target exists:** define `entry = (H_t + L_t) / 2`. Among confirmed D1 swing-high levels knowable at bar `t` with `level > entry`, select the minimum (`TP`). If no such level exists, **no order**.
7. **Minimum 2R gate:** define `stop = L_t - 0.10 * ATR14_t`. If `(TP - entry) < 2 * (entry - stop)`, **no order**.

**Order:** `buy_limit`, `entry_price = (H_t + L_t) / 2` (the 50% retracement of the pin-bar range — exact CSV formula `df['high'] - 0.5*rng`). Emitted at decision_bar `t`; eligible to fill from bar `t+1` (F1). Note `entry < C_t` always holds under conditions 2–4 (`C_t >= L_t + 0.67*rng_t > L_t + 0.5*rng_t`), so the contract's "pending not already through the market" validation always passes.

**expires_after_bars:** 24 (H1 bars = 1 D1 bar). Source is silent; conservative short — see §10 #5 and the overlap arithmetic in §10 #11.

**size_fraction:** 1.0. The author's "risk 1-2% per trade" is position sizing, which this system never performs (contract §2.2); results are in r-multiples.

## 5. Entry — short

Mirror of §4 on D1 bar `t`:

1. `rng_t > 0`.
2. `tail_up_t >= 0.67 * rng_t`  (upper tail at least 2/3 of range).
3. `body_t <= 0.33 * rng_t`.
4. `C_t <= O_t`  (bearish close).
5. **Level confluence (mandatory):** among the last 6 confirmed D1 swing-high levels knowable at bar `t`, at least one `L_r` satisfies `|H_t - L_r| <= 0.25 * ATR14_t`.
6. **TP target exists:** `entry = (H_t + L_t) / 2`; among confirmed D1 swing-low levels knowable at `t` with `level < entry`, select the maximum (`TP`). If none, **no order**.
7. **Minimum 2R gate:** `stop = H_t + 0.10 * ATR14_t`; if `(entry - TP) < 2 * (stop - entry)`, **no order**.

**Order:** `sell_limit`, `entry_price = (H_t + L_t) / 2`, expires_after_bars = 24, size_fraction = 1.0. Validation: `entry > C_t` always holds, mirroring §4.

The author's "broken support turned resistance" short variant is **dropped** (discretionary flip detection; §10 #7) — shorts require a confirmed swing-high level, the stricter reading.

## 6. Stop

- **Initial stop (long):** `stop = L_t - 0.10 * ATR14_t` ("just beyond the end of the pin bar tail", with a declared ATR buffer; buffer choice in §10 #4).
- **Initial stop (short):** `stop = H_t + 0.10 * ATR14_t`.
- Both are anchored to decision-bar-knowable prices (the pin bar's own low/high and completed ATR), satisfying fleet rule 8. The entry is a limit, which fills at exactly `entry_price` (F3), so declared R equals realised entry risk absent exit gaps; F6 gap-through-stop resolves exits honestly and can produce losses > 1R.
- **move_to_breakeven_on:** none (author specifies no breakeven rule).
- **trail:** none (author specifies no trailing rule).

## 7. Exit legs

| Label | Fraction | Kind | Level formula |
|---|---|---|---|
| TP1 | 1.0 | take_profit | Long: min confirmed swing-high level > entry, knowable at decision bar `t`. Short: max confirmed swing-low level < entry, knowable at `t`. (Absolute price, declarable at OrderIntent creation.) |

Fractions sum to 1.0. Single leg: the author takes profit once, at "the first/next key level". The 2R gate in §4/§5 guarantees `TP1` is at least 2R beyond entry at declaration time.

## 8. Filters

| Filter | Timeframe | When knowable |
|---|---|---|
| Level confluence (mandatory, §4.5/§5.5) | D1 | Close of decision bar `t` (uses swing levels confirmed at or before `t`, confirmation lag 5 D1 bars) |
| Minimum 2R reward-to-risk gate (§4.7/§5.7) — setups failing it produce NO order | D1 | Close of `t` (all inputs: pin OHLC, ATR14, confirmed levels) |
| Timeframe gate: signals on D1 only; sub-daily setups ignored (author explicit) | — | Structural |
| Trend lines as confluence | — | **Not a filter — dropped as discretionary** (§10 #1) |

No session, volatility, news, or calendar filters are specified by the author, and none exist in the data (DATA_AVAILABILITY: no non-price feeds). The 1.0-pip spread in the F10 cost model is the only spread representation; this is standard for the whole fleet and is not a proxy invented for this strategy.

## 9. Causality audit

| Rule | Inputs fully known at | Confirmation lag |
|---|---|---|
| Pin-bar geometry (§4.1–4.4, §5.1–5.4) | Close of D1 bar `t` — the bar must be complete; the decision is stamped at its close | None beyond bar completion; order eligible from `t+1` (F1) |
| Support/resistance confluence (§4.5, §5.5) | Close of `t`, using only swing levels whose **confirmation bar** is `<= t` | **5 D1 bars** (`period=5`): a swing low occurring at bar `k` is knowable only at `k+5`; the level recorded at `k` may be used from `k+5` onward (contract §6 semantics) |
| TP level selection (§4.6, §5.6, §7) | Close of `t`; candidate levels restricted to confirmation bar `<= t` | **5 D1 bars**, same mechanism |
| ATR14 buffer / proximity tolerance | Close of `t`; computed over completed bars `t-13 … t` | None (trailing window) |
| 2R gate (§4.7, §5.7) | Close of `t` — all three terms (entry midpoint, stop, TP) are decision-bar knowable | None |
| Order lifecycle | Limit eligible from first H1 bar of D1 bar `t+1` (F1); expires after 24 H1 bars (F4) | — |
| MTF | None. `simulate_on: H1` is used by the engine only to resolve fills/stops/TP inside each D1 bar's span (contract §5); the strategy never reads H1 data, so no MTF causality exposure exists | — |

No centred windows, no `detect_swing_points`, no future references anywhere in the decision path.

## 10. Ambiguities resolved

| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | "Key support/resistance level **or trend line**" — trend lines are hand-drawn | Trend lines dropped entirely; confluence only via confirmed swing levels (mandatory gate) | Mechanising trend lines (e.g. two-pivot regression lines) — discretionary in the source, unstable, and any mechanisation would be an invention, not a reading |
| 2 | "At a key level" — how close is "at"? | Pin extreme within `0.25 * ATR14(D1)` of one of the last 6 confirmed swing levels; confluence is **mandatory** (no level → no trade) | (a) "Any touch within the bar's range counts" (looser, more trades); (b) fixed-pip tolerance (not volatility-scaled across 13 pairs); (c) unbounded level history (stale levels inflate confluence) |
| 3 | "Bullish pin bar" — must it close up? | `C_t >= O_t` required (long; mirror short) | Pseudocode's direction-agnostic `body = abs(C-O)` (admits bearish-close pins; more trades, weaker pattern) |
| 4 | "Stop **just beyond** the tail" — buffer unspecified | `0.10 * ATR14(D1)` beyond the pin extreme (wider stop → worse R → conservative) | (a) 1-pip buffer (tighter, flatters R); (b) fixed 5-pip buffer (not volatility-scaled) |
| 5 | Pending-order lifetime — source silent | `expires_after_bars = 24` H1 bars (1 D1 bar). A 50% retrace that has not occurred within one full day rarely occurs at all; short expiry = fewer fills | (a) Contract default 5; (b) GTC — both hold stale levels open for days as price drifts from the level |
| 6 | "Enter on 50% retracement (preferred) **or on break of the pin bar nose**" | Only the 50% limit entry (author's stated preference; better price, fewer, higher-quality fills) | Nose-break entry (`buy_stop` at `H_t`, `sell_stop` at `L_t`) — worse entry price, more trades, and a second concurrent pending order the contract cannot OCO-cancel |
| 7 | Short variant "broken support turned resistance" | Dropped; shorts require confirmed swing-high resistance only | Mechanising S/R flips (level closed through, then retested) — multi-bar state machine not described by the author; invention risk |
| 8 | "H4 optional entry refinement" | D1 only (author calls H4 optional and ignores sub-daily setups; fewer trades) | Two-timeframe variant — adds an MTF causality surface and more signals for zero stated benefit |
| 9 | TP = "the first/next key level" — which level, and what if none? | Nearest confirmed swing level strictly beyond `entry` in the trade direction; if none exists, NO order | (a) Substitute `entry + 2R` synthetic TP when no level exists — invents exits the author forbids ("otherwise skip"); (b) farthest/most-tested level — later exit, not "first/next" |
| 10 | "Risk 1-2% per trade" | Not position sizing: `size_fraction = 1.0`, r-multiples only (contract §2.2: System 1 never sizes) | Encoding a percent-risk sizer — out of scope and forbidden by the contract |
| 11 | Order-lifecycle overlap (fleet rule 7) | With `expires_after_bars = 24`, two pending orders from consecutive D1 signals **cannot overlap**: pending A (signal at close of day `t`) is live only during day `t+1`; pending B (signal at close of `t+1`) is eligible only from `t+2` (F1). **Residual risk that remains:** pending A fills during day `t+1`, a new pin completes at close of `t+1`, and pending B fills on `t+2` while position A is still open → up to 2 concurrent positions, because F12 gates position admission (§3.2 step 6) but not pending fills (step 5), and the strategy cannot observe its own positions. Direction of bias: same-direction doubling of exposure after fresh signals; inflates trade count and correlated risk. Accepted and recorded — `max_concurrent_positions = 1` (default) still caps the counted positions at admission. | Claiming "the position blocks new orders" or "first fill cancels the other order" — those mechanisms do not exist in contract v2 |
| 12 | TP measured "from the fill" in the author's 2R language | All geometry anchored to the decision bar: entry = declared limit price (limits fill at exactly `entry_price`, F3, so declared = realised entry barring non-fills); stop/TP absolute at OrderIntent creation | Fill-anchored R (inexpressible under fleet rule 8 — the fill price is unknowable at emission) |

## 11. Expected behaviour

- **Trade frequency:** low. D1 pin bars with the exact 0.67/0.33 geometry occur perhaps 5–15 times per pair-year; requiring mandatory confirmed-level confluence, a same-direction close, an existing next-level target, and the 2R gate cuts this to roughly **1–5 signals per pair-year**, and the 1-day expiry means only a fraction (roughly 40–60%) of those limits actually fill. Across 13 pairs over ~10 years expect a few hundred fills total, but **per-cell (pair) counts may fall into `low_confidence`** territory — the report should say so rather than blending.
- **What would make it fail the gates:** (a) the mechanised swing levels are not the author's hand-drawn levels, so the documented 3.5R/4R anecdotes may not reproduce; (b) the 50%-retrace entry's fill rate collapses in trending markets (price never comes back), leaving a sample dominated by reversals that did retrace — a selection bias the backtest will measure honestly; (c) classic price-action folklore may simply carry no edge once level subjectivity is removed.
- **Is the author's MODERATE conviction justified by the rules as written?** Yes, and MODERATE (not higher) is appropriate: the geometry and the 2R minimum are fully objective, which is rare in this row set; but the evidence base is anecdotal community examples, the level definition had to be mechanised away from the author's discretionary practice, and the strategy as specified is materially stricter than what the author trades (no trend lines, no nose-break entries, no sub-daily setups, 1-day expiry). The honest prior is a low-frequency, possibly thin but cleanly measurable strategy.
