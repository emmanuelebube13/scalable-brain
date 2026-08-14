# SPEC-xard_ma_cross_daily_open

**Source:** row 26 of forex_swing_strategies.csv · https://forex-station.com/xard-simple-trend-following-trading-system-t8416709-15170.html
**Conviction (author's):** MODERATE

## 1. Hypothesis

A fresh fast/slow moving-average cross on H1, taken only when price has already established a same-direction displacement of at least 15% of the average daily range away from the daily open, captures intraday trend-continuation flow: once the market has committed to one side of the day's opening reference (the level at which overnight positioning is marked) with meaningful range behind it, stop-running and session momentum tend to extend the move further in that direction, so a 2:1 reward:risk target is reached more often than chance. The edge should persist because daily opens and MA crosses are universally watched, self-reinforcing reference points for intraday FX participants, and the 15%-ADR displacement gate filters the flat-open chop in which MA crosses whipsaw.

## 2. Scope

- **primary_granularity:** H1
- **context_granularities:** none (single-timeframe). The daily open and ADR are derived by aggregating H1 bars at the 21:00 UTC day boundary — no separate D1 frame is consumed, so no MTF alignment is required. (Numerically identical to reading the D1 frame shifted by one bar; see §10 row 9. The optional H4 bias mentioned in the CSV is dropped — see §10 row 8.)
- **simulate_on:** H1
- **pairs_requested (verbatim):** `Majors and minors|Gold`
- **pairs_available:**
  - Live: EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD
  - Pending (Wave-1 additions, not gaps): GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD
  - Reading taken: "Majors" = the 5 live pairs; "minors" = the 8 Wave-1 crosses. The harness skips pairs with insufficient history, so pending pairs are declared and simply no-trade until backfilled.
- **pairs_missing:** XAU_USD ("Gold") — deliberately excluded from the platform (not Forex; `calculate_pips()`/margin conventions assume FX). → **DATA-GAP-xard_ma_cross_daily_open.md**

## 3. Indicators

All computed on the H1 frame only, from bars with timestamp ≤ decision bar *t* (bars stamped at their OPEN; the decision is made at the CLOSE of bar *t*).

| Indicator | Params | Source |
|---|---|---|
| SMA of H1 Close | period 13 | `indicators.sma(close, 13)` |
| SMA of H1 Close | period 55 | `indicators.sma(close, 55)` |
| SMA of H1 Close | period 89 | `indicators.sma(close, 89)` |
| Daily open (DO) | day boundary 21:00 UTC | Private, exact: for any H1 bar *t*, `day_id(t)` = the 21:00-UTC-stamped bar that opens the 24h window containing *t* (a window runs 21:00 UTC → 21:00 UTC, matching the DB's D1 stamping). `DO(t) = Open` of the first H1 bar of `day_id(t)`'s window. Constant within the day. |
| Daily range DR(d) | per completed day | Private, exact: `DR(d) = max(High) − min(Low)` over all H1 bars belonging to day *d*'s 21:00→21:00 UTC window. Only days with ≥ 1 H1 bar count (Saturday windows have none and are skipped). |
| ADR(5) | 5 completed days | Private, exact: at decision bar *t*, `ADR(t) = mean(DR(d))` over the **5 most recent days completed strictly before** `day_id(t)` — i.e. days whose windows have fully closed before the current day's opening bar. Constant within the day. Contains no part of the current day. |
| Pip size | per pair | `indicators.get_pip_value(asset)` / `calculate_pips` conventions (0.0001 for 4-decimal pairs, 0.01 for JPY pairs). Used for the 5-pip stop buffer. |

**Deliberately absent:** EMA200 (only used by the dropped add-on rule — §10 row 4), semafor dots / arrows / channel lines (repainting ZigZag-family indicators — §10 rows 4 and 6). No `causal_structure` function is needed because no swing/pivot rule survives into this spec (see §9).

## 4. Entry — long

Decision made at the close of H1 bar *t*, using only data with timestamp ≤ *t*:

1. **Fresh cross:** `SMA13[t] > SMA55[t]` **and** `SMA13[t−1] ≤ SMA55[t−1]`, **OR** the identical two-bar condition against SMA89. Either cross event qualifies (union — §10 row 2).
2. **Daily-open filter:** `Close[t] > DO(t)`.
3. **ADR displacement gate:** `(Close[t] − DO(t)) / ADR(t) ≥ 0.15`, where ADR(t) is the §3 definition (5 completed days, fixed for the day). Requires ADR(t) > 0 and ≥ 5 completed days of history, else no signal.
4. **Stop-side sanity:** the computed stop (§6) must be strictly below the decision anchor `Close[t]`; if not, emit no order (degenerate flat day).

- **Entry type:** `market` (entry_price = None). Per F1/F2 the order is emitted at the close of *t* and fills at the open of bar *t+1* plus adverse slippage.
- **Entry level (anchor):** `market`; all stop/TP geometry is anchored to the decision-bar-knowable price `A = Close[t]` (fleet rule: the fill price is unknowable at emission).
- **expires_after_bars:** null (not applicable to market entries; the order fills or dies at bar *t+1* by engine convention).
- **Concurrency:** `max_concurrent_positions = 1` (F12 default). No add-ons, no pyramiding (§10 row 4). Because entries are market-only and one position max, there is at most one order in flight at any time; no OCO/cancel-on-fill semantics are needed or assumed. If a fresh same-direction cross occurs while a position is open, the new OrderIntent is simply not admitted by F12 — no "supersede" behaviour is implied.

## 5. Entry — short

Mirror of §4:

1. **Fresh cross:** `SMA13[t] < SMA55[t]` **and** `SMA13[t−1] ≥ SMA55[t−1]`, **OR** the identical condition against SMA89.
2. **Daily-open filter:** `Close[t] < DO(t)`.
3. **ADR displacement gate:** `(Close[t] − DO(t)) / ADR(t) ≤ −0.15` (the CSV's "contraction ≥ −15%" — §10 row 3).
4. **Stop-side sanity:** computed stop (§6) strictly above `Close[t]`, else no order.

Entry type `market`, anchor `A = Close[t]`, expires_after_bars null, concurrency 1. Identical lifecycle guarantees as §4.

## 6. Stop

- **Initial stop (exact formula):**
  - Long: `S = DO(t) − 5 × pip_size`
  - Short: `S = DO(t) + 5 × pip_size`
  where `DO(t)` is the daily open of the decision bar's day and `pip_size` is the pair's pip size. "A few ticks beyond the daily open" → 5 pips (§10 row 5). The alternative stop (last swing high/low per the semafor dot) is **rejected** — §10 row 6.
- **move_to_breakeven_on:** none.
- **trail:** none. The CSV's "trailing stops in trends" has no documented parameterisation; conservative reading = no trailing (§10 row 7).
- Declared risk per trade: `R = |A − S|` with `A = Close[t]`. Realised R differs from declared R when the *t+1* open gaps (F2/F3/F6 resolve the fill honestly); this is inherent to market entries and is recorded here, not worked around.

## 7. Exit legs

| Label | Fraction | Kind | Level formula |
|---|---|---|---|
| TP1 | 1.0 | take_profit | Long: `A + 2 × (A − S)` · Short: `A − 2 × (S − A)` — fixed 2:1 reward:risk on the declared risk, anchored to the decision close `A` |

Fractions sum to 1.0. Single full-size leg. Rejected exit options from the CSV (opposite arrow/dot, candle-colour flip, ADR high/low lines, channel line) are recorded in §10 rows 6 and 7 — the fixed 2:1 RR is the only fully mechanical option the CSV documents.

## 8. Filters

| Filter | Rule | Timeframe | Knowable from |
|---|---|---|---|
| Daily-open bias | Long only if `Close[t] > DO(t)`; short only if `<` | H1, day-boundary series (21:00 UTC) | The 21:00 UTC opening bar of the current day; valid for every decision bar of that day |
| ADR displacement | `|(Close[t] − DO(t)) / ADR(t)| ≥ 0.15`, sign-matched | H1 decision close against day-fixed ADR(5) | ADR(5) is knowable from the 21:00 UTC opening bar of the current day (uses only days closed before it); `Close[t]` at the close of *t* |
| Cross/filter agreement | Trade only when the fresh MA cross and the daily-open filter agree in direction | H1 | Close of bar *t* |

No session, news, calendar, volatility-regime, or higher-timeframe filter survives into this spec. The CSV mentions none beyond the above. Note: spread is **not** an input — the F10 cost model applies a flat 1.0-pip spread; no live spread series exists in the data and none is proxied.

## 9. Causality audit

Bars are stamped at their OPEN. "Knowable at close of *t*" means computable from bars stamped ≤ *t* (whose OHLC are complete at *t*'s close).

| Rule | Inputs | Fully knowable at |
|---|---|---|
| SMA13/55/89 | H1 closes of bars ≤ *t* | Close of decision bar *t* |
| Fresh-cross test | SMA values at *t* and *t−1* | Close of *t* |
| Daily open DO(t) | `Open` of the H1 bar stamped 21:00 UTC opening the current day | **From the open of the 21:00 UTC bar onward** — i.e. before the first decision bar of the day. Lag within the day: zero bars; it never uses any part of the current day beyond its opening print. The DB day boundary is 21:00 UTC fixed (no DST shift in UTC data) — see §10 row 10 for the broker-chart discrepancy. |
| ADR(5) | Full-day High/Low extremes of the 5 completed days strictly before the current day | **From the open of the 21:00 UTC bar of the current day.** Confirmation lag: the most recent day in the mean closed at 21:00 UTC today; ADR is therefore 1 full day stale by construction and reflects no intraday information. |
| Daily-open filter, ADR gate | `Close[t]`, DO(t), ADR(t) | Close of *t* |
| Stop/TP levels | `Close[t]`, DO(t), pip_size | Close of *t* — absolute values declared at OrderIntent creation |
| Fill timing | — | Order emitted at close of *t* is eligible for fill from bar *t+1* (F1); market fill at open of *t+1* (F2) |
| Swing/pivot/ZigZag rules | — | **None retained.** The semafor-dot stop anchor and the "2nd-dot / EMA200-cross" add-on were dropped (§10 rows 4, 6). Had a swing anchor been kept, it would have required `causal_structure.confirmed_swing_points` with a period-bar confirmation lag (a swing at bar *k* knowable only at *k+period*); since none is kept, no swing confirmation lag applies anywhere in this spec, and no centred-window indicator is used. |

Multi-timeframe causality: not applicable — single frame (H1). Day-boundary series (DO, ADR) are H1-aggregates with the lag stated above, numerically identical to reading a D1 frame after its close per the §4 contract rule.

## 10. Ambiguities resolved

| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | "EMA/SMA 13, 55, 89" — the CSV names both MA families | **SMA** for all three — the author's own pandas pseudocode uses `rolling().mean()` | EMA (the XARD charts' convention) — deviating from the author's documented formula would be invention, not interpretation |
| 2 | "13-period MA crosses above 55 or 89 MA" | **Union:** a fresh cross of SMA13 over either SMA55 or SMA89 triggers | Requiring both crosses simultaneously — near-impossible event, degenerate (zero trades), not what "or" means |
| 3 | "ADR expansion >= +15% from daily open" / "contraction >= -15%" | The author's pseudocode reading: signed displacement `(Close − DO)/ADR ≥ +0.15` (long) / `≤ −0.15` (short), ADR = mean of the last 5 **completed** daily ranges | "Today's range has expanded to ≥ 115% of ADR" — arguably fewer trades, but no formula for it exists in the prose and it directly contradicts the author's own pseudocode; taking it would invent a different strategy |
| 4 | "Add on subsequent blue/pink dots while price crosses above/below EMA200" (pyramiding on semafor dots) | **Dropped entirely.** `max_concurrent_positions = 1`; EMA200 removed from the indicator set. The dots are semafor (ZigZag-family, repainting) signals | Rebuilding adds via `causal_structure.zigzag_swings` + raised F12 concurrency — rejected: it changes the strategy's identity, the semafor parameters (depth/deviation/backstep) are nowhere documented, and a causal ZigZag is not the repainting indicator the author traded from |
| 5 | "a few ticks beyond the daily open" | **5 pips** beyond the daily open (a "few" pips reading; ticks are pair-dependent and sub-pip) | 1 pip ("few ticks" literally) — absurdly tight for an H1 swing stop; 10 pips — arbitrary widening beyond any documented hint |
| 6 | "or the last swing high/low (semafor dot)" as the stop anchor | **Daily-open stop chosen** (row 5); the swing alternative is dropped | Confirmed-swing stop via `causal_structure` — rejected: the semafor dot is a repainting ZigZag pivot; its period is undocumented; a causal substitute is a different stop than the author used, and the daily-open stop is fully mechanical with zero parameters beyond row 5 |
| 7 | Exit "at opposite arrow/dot signal or when candle colour flips"; "TP at ADR high/low lines, channel line, or 2:1 RR"; "trailing stops in trends" | **Fixed 2:1 RR, single leg, no trailing** — the only fully mechanical option documented | Arrow/dot exits (repainting, inexpressible causally); "candle colour flip" (timeframe and exact rule undefined — flip of which bar, exit where?); ADR high/low lines and channel line (no formula anywhere in the CSV for either); trailing stop (no trail distance, trigger, or ATR multiple documented) |
| 8 | "H4 usable for bias" | **Dropped — single timeframe (H1).** The CSV never states what the H4 bias rule is | Adding an H4 filter of the implementer's design — inventing a rule *and* adding an MTF causality surface for an undocumented filter |
| 9 | Daily open / ADR source frame | **Derived by H1 aggregation at the 21:00 UTC boundary**; no D1 frame consumed | Reading the D1 frame — numerically identical (D1 bars are stamped at 21:00 UTC opens) but introduces an MTF join whose one-bar error mode is the FIX-S1-005 bug class; the H1 aggregate has no such surface |
| 10 | "Daily open" on the author's charts vs the DB | **21:00 UTC DB day boundary, fixed** — knowable from the first H1 bar of the day (§9) | Broker-time daily open (XARD charts typically run UTC+2/+3 with DST, i.e. a midnight-broker open). The author's DO therefore differs from ours by 2–3 hours seasonally; no DST-adjusted broker clock exists in the data, and simulating one would require assuming a specific broker's DST calendar — recorded, not fixed |
| 11 | "enter Long on cross candle" | Decision at the **close** of the cross bar; market fill at the **open of the next bar** (F1/F2) | Fill at the cross bar's close — impossible at decision time and forbidden by F1 |

## 11. Expected behaviour

- **Trade frequency:** SMA13/55 and 13/89 crosses on H1 occur several times per month per pair; after the daily-open and 15%-ADR-displacement gates, expect roughly **2–6 trades per pair per month** (≈25–70 per pair per year; ≈150–350 per year across the 5 live pairs). Walk-forward folds will carry ample trade counts on H1.
- **Risk geometry:** declared risk ≈ 0.15×ADR + 5 pips (the distance from anchor to the daily-open stop), so TP sits ≈ 0.3×ADR + 10 pips beyond the anchor — reachable within a trending day or two, but the stop sits at the day's reference level where mean-reversion flow clusters; expect a hit rate well below 50% carried by the 2:1 payoff.
- **What would make it fail the gates:** H1 MA crosses whipsaw in multi-day ranges, and the 15%-ADR gate does not prevent late entries on exhausted days (a cross firing at 21:00 with price already 0.15×ADR from the open has often spent the day's move). Gap-through-stop losses >1R (F6) will occur at Monday opens. If the true edge lived in the dropped semafor/channel machinery rather than the MA-cross core, this implementation measures a generic trend-follower and the MODERATE conviction does not transfer.
- **Is the author's conviction justified by the rules as written?** MODERATE is fair, arguably generous. The rules are objective and codeable (the author's own pseudocode proves it), but there is no documented rigorous backtest, the original system's visual edge (semafor/channel) is deliberately absent here, and what remains is a plain dual-MA cross with a day-bias filter — a strategy class with well-documented fragility. The honest prior is "plausible, unproven."
