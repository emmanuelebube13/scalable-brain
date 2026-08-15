# SPEC-amazing_crossover

**Source:** row 34 of forex_swing_strategies.csv · https://forums.babypips.com/t/amazing-crossover-system-100-pips-per-day/19403
**Conviction (author's):** MODERATE

## 1. Hypothesis

The claimed edge is dual-confirmed short-term momentum ignition on H1: a fast/slow EMA cross marks a shift in the intraday order-flow balance, and requiring RSI(10) on the median price to cross 50 on the same bar demands that the shift is visible in the bar's central tendency (not merely a close-price artifact) at the same moment. The behavioural reason it could persist is herding: intraday breakout/momentum followers on the most liquid retail timeframe pile in once a fast trend signal and a momentum midline agree, extending the move for a few bars to a few hours; the strict same-bar conjunction exists to filter the chop that kills naked EMA crosses in ranging sessions.

## 2. Scope

- **primary_granularity:** H1
- **context_granularities:** none (author: "H1 only, never lower" — no higher-timeframe filter is defined either; single-frame strategy)
- **simulate_on:** H1
- **pairs_requested (verbatim):** "Majors (EUR/USD | GBP/USD | USD/JPY etc.; OP avoids crosses)"
- **pairs_available:** EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD (live); USD_CHF, NZD_USD (**pending** — Wave-1 additions; both are USD majors consistent with the author's "majors" scope)
- **pairs_missing:** none. Crosses (EUR_JPY, GBP_JPY, EUR_GBP, …) are **excluded by the author**, not missing — no DATA-GAP note is required. "Etc." is read as the seven USD majors only (EUR_USD, GBP_USD, USD_JPY, USD_CHF, AUD_USD, NZD_USD, USD_CAD); see §10 #6.

## 3. Indicators

| Indicator | Params | Source |
|---|---|---|
| EMA on Close | period 5 | inventory `ema(close, 5)` |
| EMA on Close | period 10 | inventory `ema(close, 10)` |
| Median price series | `med = (High + Low) / 2` per bar | trivial private derivation from OHLC; not a standalone indicator |
| RSI on median price | period 10, level 50 | inventory `rsi(series, 10)` **applied to the derived `med` series instead of Close** — same implementation, different input series; no new indicator code needed beyond passing `med` |

No swing points, ZigZag, pivots, or fractals are used anywhere in this strategy. `detect_swing_points` is not referenced. Minimum warmup: RSI(10) needs ≥ 11 bars and EMA(10) needs ~10 bars to stabilise; declare a 50-bar warmup so all indicators are fully formed before the first decision bar.

## 4. Entry — long

Evaluated at the **close of decision bar t** (H1). All conditions must hold on the **same bar t** (strict same-bar conjunction, matching the CSV pseudocode `long_sig = cross_up & rsi_up`):

1. `ema5[t] > ema10[t]` AND `ema5[t-1] <= ema10[t-1]` — EMA5 crosses above EMA10 from underneath exactly at bar t.
2. `rsi10_med[t] > 50` AND `rsi10_med[t-1] <= 50` — RSI(10, median) crosses up through 50 exactly at bar t.

If both hold:

- **Entry type:** `market`
- **Entry level:** `entry_price = None` (market). Fill per F1/F2 at the **open of bar t+1**, plus F10 costs (1.0 pip spread + 0.5 pip slippage, entry side only). The fill price is unknowable at emission; all geometry below is anchored to `C_t` = Close of decision bar t (fleet decision-bar anchoring rule).
- **expires_after_bars:** `null` (not applicable — market orders are not pending; they fill at t+1 open or not at all)
- **Concurrency:** `max_concurrent_positions = 1` (F12 default) implements the author's "one position per signal"; a signal emitted while a position is open is simply not admitted (§3.2 step 6). No pending orders exist, so there is no pending-overlap / multi-fill risk.

## 5. Entry — short

Exact mirror, evaluated at the close of decision bar t, both conditions on the same bar:

1. `ema5[t] < ema10[t]` AND `ema5[t-1] >= ema10[t-1]` — EMA5 crosses below EMA10 from above exactly at bar t.
2. `rsi10_med[t] < 50` AND `rsi10_med[t-1] >= 50` — RSI(10, median) crosses down through 50 exactly at bar t.

Same mechanics: `market` entry, fill at open of t+1 (F1/F2), `expires_after_bars = null`, geometry anchored to `C_t`.

## 6. Stop

Let `pip = get_pip_value(pair)` (inventory; 0.0001 for the five live majors, 0.01 for USD_JPY) and `C_t` = decision-bar close.

- **Initial stop (long):** `stop.price = C_t − 100 × pip`
- **Initial stop (short):** `stop.price = C_t + 100 × pip`
- **move_to_breakeven_on:** `"BE_TRIGGER"` (the ExitLeg label defined in §7). When that leg fills on bar k, the stop moves to breakeven at the **close of bar k** (F8), with `breakeven_offset_pips = 0.0`.
- **trail:** `none` (`trail_atr_multiple = None`). The author's open-ended P&L ladder ("at +40 lock +20, etc.") beyond the first rung is **inexpressible** in contract v2 (no P&L-ladder trail primitive, and the strategy never observes P&L); the conservative reading is that after the breakeven move the stop stays at breakeven with no further locking. Fidelity loss recorded in §10 #4.
- Stops only ever improve (initial → breakeven); contract test 12 (`test_stop_never_widens`) applies.

## 7. Exit legs

Long example (short mirrors with `C_t − …`):

| Label | Fraction | Kind | Level formula |
|---|---:|---|---|
| `BE_TRIGGER` | 0.10 | take_profit | `C_t + 20 × pip` |
| `TP1` | 0.90 | take_profit | `C_t + 50 × pip` |

Fractions sum to 1.0 (0.10 + 0.90). Design rationale:

- The author's TP is a **band "50–100 pips"**; the conservative reading takes the **lower bound 50 pips** (smaller winners). The pseudocode's `tp = entry + 75*pip` is rejected as non-conservative; see §10 #2.
- `BE_TRIGGER` is the expressible approximation of the first trailing rung ("at +20 pips move SL to breakeven"): a small 0.10-fraction TP leg at +20 pips whose fill triggers `move_to_breakeven_on` (§6). The 0.10 fraction is a declared interpretive decision (§10 #5).
- Absolute `price` levels anchored to `C_t` are used (not `pips`, which would be fill-anchored) per the decision-bar anchoring rule. Realised R ≠ declared R when the t+1 open gaps away from `C_t`; F3/F6 resolve fills honestly.

## 8. Filters

The source defines **no trend, session, volatility, or news filters**. The only discipline statements are:

| Rule | Reading | Timeframe / when knowable |
|---|---|---|
| "H1 only, never lower" | Granularity discipline: signals on H1, fills resolved on H1. Not a data filter. | n/a |
| "One position per signal" | `max_concurrent_positions = 1` (F12 default). | n/a |
| "OP avoids crosses" | Pair-scope restriction (§2), not a runtime filter. | n/a |

There is no news/calendar gate and none can be added — no calendar feed exists (DATA_AVAILABILITY §Non-price data). This is stated, not substituted.

## 9. Causality audit

Decision bar = H1 bar **t**; all inputs below are fully known at the **close of bar t**. No multi-timeframe context exists, so the §4 MTF rule is vacuously satisfied (no context bars to misalign).

| Rule | Inputs | Fully known at | Confirmation lag |
|---|---|---|---|
| EMA5×EMA10 cross up/down | `ema5[t], ema10[t], ema5[t-1], ema10[t-1]` on Close | close of bar t | none — trailing EMA of closes, no future data |
| RSI(10, median) cross of 50 | `med[t-10 … t]` where `med = (H+L)/2` | close of bar t | none — Wilder/RSI recursion over completed bars only |
| Same-bar conjunction | both conditions above at bar t | close of bar t | none |
| Market entry fill | — | open of bar t+1 (F1/F2) | 1 bar decision→execution separation, enforced by engine |
| Initial stop / TP levels | `C_t`, `pip` | close of bar t (declared at emission) | none |
| Breakeven move | `BE_TRIGGER` leg fill on bar k | **close of bar k** (F8 — protection arrives one intrabar step late, pessimistic) | enforced by engine |
| Stop/TP intrabar resolution | H1 bar range | F5: stop deemed hit before target on any bar touching both | pessimistic by convention |
| Swing/pivot/ZigZag/fractal rules | **none exist in this strategy** | n/a | n/a — stated explicitly per protocol |

No rule reads bar t+1 or later. EMA and RSI use only trailing windows; the median series uses each bar's own H/L, which is complete at that bar's close.

## 10. Ambiguities resolved

| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | Must the EMA cross and RSI-50 cross occur on the **same bar**, or may one follow the other within a few bars? | **Same-bar strict** conjunction (matches the CSV pseudocode `cross_up & rsi_up`). Produces the fewest, latest signals. | "Within a 3–5 bar window" reading — materially more trades, earlier entries; looser than anything the OP wrote. |
| 2 | TP band "50–100 pips" — which value? | **50 pips** (lower bound; smallest winners). Pseudocode's 75 pips also rejected. | 75 pips (pseudocode default) or 100 pips — both inflate per-trade winners; the pseudocode is illustrative, the prose band is the contract. |
| 3 | Are stop/TP measured from the **fill price** or from the decision bar? | Anchored to **decision-bar close `C_t`** (fleet anchoring rule; fill price is unknowable at emission for a market order). | Fill-anchored geometry — **inexpressible** in contract v2, not merely less conservative; realised R ≠ declared R under gaps (F3/F6). |
| 4 | Trailing ladder: "+20 → breakeven, +40 → lock +20, **etc.**" — the schedule is open-ended and P&L-driven. | Only the **first rung** is expressed (0.10-fraction `BE_TRIGGER` leg → `move_to_breakeven_on`); thereafter the stop stays at breakeven, never tightening further. Fewer profits locked than the author intends = conservative; fidelity loss explicitly accepted. | (a) ATR-trail approximation — invents a parameter the author never gave and changes the strategy's character; (b) pretending the ladder exists — inexpressible: contract v2 has no P&L-ladder trail and the strategy cannot observe P&L. |
| 5 | `BE_TRIGGER` leg fraction — the author describes a stop move, not a partial exit; any fraction > 0 is a construction. | **0.10** — smallest round material fraction; 90% of the position still rides to TP1 as the author intends. | 0.05 (needlessly micro; distorting reports) or ⅓-style splits (would gut the main TP leg the author describes). |
| 6 | "Majors (… etc.)" — which pairs? | The seven **USD majors**: EUR_USD, GBP_USD, USD_JPY, USD_CHF, AUD_USD, NZD_USD, USD_CAD. Crosses excluded because the author says so. USD_CHF/NZD_USD declared but **pending** Wave-1 backfill; harness skips them if absent. | "All liquid pairs including JPY crosses" — contradicts "OP avoids crosses". |
| 7 | RSI cross definition: "crosses up through 50" — touch vs strict cross? | Strict two-sided cross: `rsi[t] > 50` and `rsi[t-1] <= 50` (equality on the prior bar counts as not-yet-crossed). | `rsi[t-1] < 50` strict-below requirement — would drop borderline signals; difference is negligible but the chosen form matches the pseudocode (`shift() <= 50`). |

## 11. Expected behaviour

- **Trade frequency:** low. H1 EMA5×EMA10 crosses occur perhaps every 2–5 sessions per pair, but demanding an RSI(10, median) 50-cross on the *identical* bar is a much rarer conjunction — expect roughly **1–4 trades per month per pair**, i.e. ~250–1,000 trades per pair over the ~20-year H1 history, and ~1,200–5,000 pooled across the five live pairs. Per-cell walk-forward counts (6-month OOS ≈ 6–24 trades) will frequently trip `low_confidence`; pooled counts should be adequate.
- **Breakeven win-rate arithmetic (the central economic fact):** declared risk is 100 pips; weighted target is `0.10 × 20 + 0.90 × 50 = 47` pips, plus ~1.5 pips of entry costs (F10). Ignoring breakeven scratches, the strategy needs a raw win rate above **~100 / (100 + 47) ≈ 68%** just to break even. The BE move converts some would-be losers into ~0R scratches, lowering the required win rate somewhat, but the declared RR is **≈ 1 : 0.47** — the strategy is structurally a high-win-rate, small-winner scalper's profile on a swing harness.
- **What would make it fail the gates:** (a) win rate below ~65–68% — dual same-bar confirmation may not deliver that in chop-heavy regimes; (b) F5 (stop-before-target) plus the 100-pip stop means any intrabar spike against the position costs a full 1R while winners are capped under 0.5R — a few adverse streaks sink expectancy; (c) thin per-cell trade counts → `low_confidence`; (d) weekend gaps through the stop (F6) producing losses > 1R that the tight +47-pip winners cannot repay.
- **Author's conviction vs rules as written:** MODERATE is, if anything, generous. The author's own reasoning column concedes "no documented backtest or forward-test performance and 1:1-ish RR suggests edge must be re-validated" — and the conservative 50-pip TP reading makes the RR worse than 1:1 (≈1:0.47), while the inexpressible ladder trail removes the profit-locking the author relied on to manage the trade after entry. The signal rules are honest and fully causal, so the backtest will measure a real (if demanding) claim; expect qualification only if the dual trigger genuinely delivers a very high win rate.
