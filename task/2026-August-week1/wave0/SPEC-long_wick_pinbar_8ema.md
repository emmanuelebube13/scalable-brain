# SPEC-long_wick_pinbar_8ema

**Source:** row 2 of forex_swing_strategies.csv · https://www.forexfactory.com/thread/175346-swing-trades-using-price-action
**Conviction (author's):** HIGHLY_RECOMMENDED

## 1. Hypothesis

In a persistent trend, a pullback to the fast EMA that is *rejected* — evidenced by a daily candle whose dominant feature is a long wick probing through value and being refused — marks the point where counter-trend liquidity has been absorbed and trend-following participants reassert control. The edge is behavioural: the long wick is the footprint of trapped counter-trend traders and defended resting orders at the EMA8 "dynamic support/resistance" zone, so price should resume in the trend direction with a favourable 2:1 payoff. It should persist as long as FX trends exhibit pullback-continuation structure and traders anchor on short EMAs as reference levels.

## 2. Scope

- primary_granularity: D1
- context_granularities: [] (none — the trend filter is evaluated on D1 itself; the CSV's "H4 optional" variant is dropped, see §10 #8)
- simulate_on: H1
- pairs_requested: [EURUSD, AUDUSD, GBPUSD, EURJPY, "and other FX majors/minors (watch ~12 pairs)"]  # verbatim from the CSV
- pairs_available: [EUR_USD, GBP_USD, AUD_USD, EUR_JPY (pending — Wave-1 backfill, may be skipped by the harness if history is insufficient)]
- pairs_missing: [] — no DATA-GAP note. The four explicitly named pairs are all either present or in the Wave-1 addition list. The vague "watch ~12 pairs" is not expanded beyond the named four (conservative; see §10 #7). No granularity or feed outside H1/H4/D1 is needed.

## 3. Indicators

| Indicator | Params | Source |
|---|---|---|
| EMA of close | period=8, on D1 closes | inventory `ema(series, 8)` |
| EMA of close | period=16, on D1 closes | inventory `ema(series, 16)` |
| Candle range / wick / body measurements | per D1 bar: `rng = High - Low`; `lower_wick = min(Open, Close) - Low`; `upper_wick = High - max(Open, Close)` | **not in inventory** — trivial OHLC arithmetic; define privately in the strategy module per INDICATOR_INVENTORY.md guidance. Fully specified by these formulas. |
| Pip size per pair | e.g. 0.0001 for EUR_USD/GBP_USD/AUD_USD, 0.01 for EUR_JPY | inventory `get_pip_value(asset)` / `calculate_pips(price_change, asset)` |

No swing-point, ZigZag, pivot, fractal, SAR, or Fibonacci indicator is used — all were optional in the source and are rejected (§10 #5, #6). `causal_structure` is therefore not required.

## 4. Entry — long

All conditions are evaluated on the **completed D1 bar t** (the decision bar). Bars are stamped at their open; bar t is knowable only at its close, i.e. at the open timestamp of D1 bar t+1.

1. **Trend filter (mandatory):** `EMA8[t] > EMA16[t]`, strictly, using D1 closes up to and including bar t. If false, no long trade regardless of candle shape. (The "established trend structure" alternative is rejected; see §10 #4.)
2. **Non-degenerate candle:** `rng[t] = High[t] - Low[t] > 0`.
3. **Long lower wick:** `lower_wick[t] = min(Open[t], Close[t]) - Low[t]` satisfies `lower_wick[t] >= (2/3) * rng[t]` — the exact fraction 2/3 (i.e. 0.66666…), **not** the 0.66 used in the CSV pseudocode (see §10 #1).
4. **Wick touches EMA8:** the EMA8 value at bar t lies within the lower-wick segment: `Low[t] <= EMA8[t] <= min(Open[t], Close[t])`. "Touch" means the wick's price interval contains the EMA; a wick that stops short of the EMA does not qualify (see §10 #2).
5. No requirement on the sign of the candle body (bullish or bearish close both qualify — the prose admits "hammer/pinbar/long-wick doji").

- **Entry type:** `market` (F1/F2). The OrderIntent's `decision_bar` is D1 bar t; the engine fills at the open of the next D1 bar, resolved on H1 as the first H1 bar of that D1 span, plus entry spread+slippage per F10. This *is* the CSV's "enter at open of the following daily candle" (see §10 #3).
- **Entry level:** `fill = Open(D1 bar t+1)` (+ 1.0 pip spread + 0.5 pip slippage, applied by the engine, not the strategy).
- **expires_after_bars:** not applicable — market entry; it fills at the first eligible bar or not at all. (`None`.)

## 5. Entry — short

Mirror of §4, all on completed D1 bar t:

1. **Trend filter:** `EMA8[t] < EMA16[t]`, strictly. (Equality → no trade, both sides.)
2. `rng[t] > 0`.
3. `upper_wick[t] = High[t] - max(Open[t], Close[t])` satisfies `upper_wick[t] >= (2/3) * rng[t]`.
4. **Wick touches EMA8:** `max(Open[t], Close[t]) <= EMA8[t] <= High[t]`.
5. No body-sign requirement ("shooting star/hanging man").

- **Entry type:** `market`, fill at `Open(D1 bar t+1)` minus F10 costs.
- **expires_after_bars:** `None` (market).

## 6. Stop

- **Initial stop (long):** `stop = Low[t] - 2 pips` (2 pips beyond the extreme of the qualifying candle's wick; the CSV's "2-5 pips" band is resolved to the tight end — more stop-outs, conservative; the pseudocode also uses 2 pips — see §10 #9).
- **Initial stop (short):** `stop = High[t] + 2 pips`. Pip size from `get_pip_value(pair)`.
- **move_to_breakeven_on:** `none`.
- **trail:** `none` — the stop is static for the life of the trade (trailing/SAR management was an optional extra, rejected; §10 #5). StopRule with `move_to_breakeven_on=None`, `trail_atr_multiple=None`.

## 7. Exit legs

| Label | Fraction | Kind | Level formula |
|---|---|---|---|
| TP1 | 1.0 | take_profit | long: `TP = Close[t] + 2 * (Close[t] - stop)` ; short: `TP = Close[t] - 2 * (stop - Close[t])` — exactly 2R measured from the **decision bar's close** `Close[t]` (the reference price knowable when the OrderIntent is emitted), not from the unknowable fill. `ExitLeg.price` is declared as this absolute level at decision time. |

Fractions sum to 1.0. Single full-size take-profit leg at exactly the minimum 2:1 reward:risk. **Geometry anchor (fleet rule):** entry is `market`, so the fill (bar t+1's open) is unknowable at emission; ALL stop/TP geometry is therefore anchored to decision-bar-knowable prices — the stop to `Low[t]`/`High[t]` (§6) and the TP to `Close[t]`. Consequence: the realised reward:risk on the actual fill deviates from exactly 2:1 by the gap between `Close[t]` and the fill (a weekend gap shifts it most); the engine's r-multiple is computed honestly from the realised fill and the declared stop (contract §3.3), so this shows up as dispersion around 2R, not as hidden error. See §10 #10. The CSV's "unless S/R says otherwise" override and all optional exits (partials, EMA-crossback close, pivots/fibs/Parabolic SAR) are rejected — see §10 #5 and #6. If neither stop nor TP is hit, the position runs to end of data and is closed at the final bar's close with reason `END_OF_DATA` (F11). **Concurrency:** F12 (`max_concurrent_positions = 1` per (strategy, pair, granularity)) only blocks *admission* of new OrderIntents while a position is open — it never closes or modifies an open position. An opposite (or same-direction) signal forming while a position is open is simply not acted on; the open position runs to its stop, TP, or `END_OF_DATA` (see §10 #11).

## 8. Filters

- **Trend filter (the only filter):** `EMA8 vs EMA16` on **D1 closes**. It is knowable at the close of D1 bar t — i.e. a D1 bar stamped `2026-08-05T21:00Z` (its open) may first drive a decision at `2026-08-06T21:00Z`. Because signals are emitted on the native D1 frame and this filter uses only the decision bar's own close, no cross-timeframe alignment is needed; the standard merge_asof shift rule (contract Part C) is trivially satisfied.
- **No session filter** (D1 bars; the Friday 21:00 → Sunday 21:00 UTC weekend close is handled by the data, not by a filter).
- **No volatility filter** in the source; none added.
- **Position sizing note:** the CSV's "risk max 2% of account per trade" is **not implemented** — System 1 never sizes; results are in r-multiples (contract §2.2, §10 of the contract). The 2% figure is recorded here for provenance only.

## 9. Causality audit

Read first. Decision bar = D1 bar t; all inputs below are fully known at the **close of bar t** (timestamp: open of bar t+1). Nothing in this strategy looks past bar t. No rule uses a swing point, so **no confirmation lag applies anywhere** — this section exists to prove that.

| Rule | Inputs | Bar at which fully known | Confirmation lag |
|---|---|---|---|
| Long/short trend filter (§4.1, §5.1) | EMA8[t], EMA16[t] from D1 closes ≤ t | close of bar t | none (no swing points) |
| Non-degenerate candle (§4.2, §5.2) | High[t], Low[t] | close of bar t | none |
| Wick ≥ 2/3 range (§4.3, §5.3) | O/H/L/C[t] | close of bar t | none |
| Wick touches EMA8 (§4.4, §5.4) | O/H/L/C[t], EMA8[t] | close of bar t | none |
| Entry at next bar's open (§4, §5) | fill occurs at bar t+1 open; the *decision* used only bar t data | F1: eligible from t+1, never on t | n/a |
| Initial stop (§6) | Low[t] or High[t], pip size | close of bar t | none |
| TP leg (§7) | `Close[t]`, stop (from `Low[t]`/`High[t]`) — all decision-bar data; the absolute `ExitLeg.price` is fully determined at emission | close of bar t | none |
| D1 knowability (§8) | bars stamped at open; a D1 bar stamped 2026-08-05T21:00Z is not knowable until 2026-08-06T21:00Z | enforced by emitting on the D1 frame only | none |

`detect_swing_points` is **not used**. No `causal_structure` function is needed because every S/R-, pivot-, fib-, and SAR-based discretionary element of the source was rejected rather than re-implemented. EMA values are computed from closes with a causal (backward-only) recursion — the inventory `ema` is safe. The strategy must pass `assert_no_lookahead_v2` under truncation.

## 10. Ambiguities resolved

| # | Ambiguity in the source | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | "lower wick >= 2/3 of total candle range" vs pseudocode's `0.66 * rng` | Exact fraction: `lower_wick >= (2/3) * rng` (0.66666…) — stricter, fewer signals. Total range = `High - Low`; "wick" for longs = below `min(Open, Close)`; for shorts = above `max(Open, Close)`. | Pseudocode's 0.66 (≈1% looser, more trades, closer to author's reported results) |
| 2 | "long wick must at least touch or pierce EMA8" | Touch = EMA8[t] lies **within the wick segment**: longs `Low[t] <= EMA8[t] <= min(O,C)[t]`; shorts `max(O,C)[t] <= EMA8[t] <= High[t]`. Strictest literal reading. | Pseudocode's whole-range straddle `Low <= EMA8 <= High` (admits candles whose body, not wick, contains the EMA — more signals) |
| 3 | "enter at open of the following daily candle" — which open? | `market` OrderIntent at decision bar t; engine fills at the open of D1 bar t+1 (the bar stamped at that open), resolved on H1, with F10 costs (1.0 pip spread + 0.5 pip slippage). | Fill at bar t's close (would be look-ahead-adjacent and cost-free); fill at t+1 open without costs |
| 4 | Trend condition: "EMA8>EMA16 **or** established trend structure" | Only the deterministic half: strict `EMA8 > EMA16` on D1 closes (mirror for shorts). Equality = no trade. | "Established trend structure" — subjective, would require swing-point machinery (with its confirmation lag) and widen the signal set |
| 5 | "optional exits: partial profits then let rest run, exit if price closes back inside EMA8/EMA16, or use pivots/fibs/Parabolic SAR" | **None** of them. Single 100% leg at 2R, static stop. Rejecting management that the author credits for his live win-rate keeps the test honest. | Partial scale-outs (flatters win-rate, complicates r-math); close-inside-EMAs exit (extra exit paths raise measured edge); SAR trail (needs SAR state and intrabar decisions) |
| 6 | "Take Profit at minimum 2:1 … **unless S/R says otherwise**" | Fixed exactly-2R target, always. | S/R-adjusted targets — requires causal swing/S-R levels, discretionary placement, and can raise RR beyond 2:1 in the author's favour |
| 7 | "EURUSD\|AUDUSD\|GBPUSD\|EURJPY and other FX majors/minors (watch ~12 pairs)" | Trade only the four explicitly named pairs. | Expanding to an invented ~12-pair basket (unjustified pair selection; would also outrun data availability) |
| 8 | "D1 primary\|H4 optional" | D1 only. The H4 variant is an unspecified second strategy (no separate rules given) and 4× the signals. | Also running H4 (more trades, but doubles the spec's surface from one sentence of prose) |
| 9 | "Stop 2-5 pips beyond the extreme of the qualifying candle wick" | 2 pips (tight end; matches pseudocode's `2*pip`). Tighter stop = more stop-outs = pessimistic. | 5 pips (fewer stop-outs, kinder results); mid-band 3–4 pips (arbitrary) |
| 10 | What price should the 2:1 TP geometry be anchored to, given a market entry? | Anchored to the **decision bar**: `TP = Close[t] ± 2 * |Close[t] − stop|`, declared as an absolute `ExitLeg.price` at emission. This is the only expressible reading — entry is `market`, so the fill (t+1's open) is unknowable when the OrderIntent is emitted and cannot appear in any declared level (fleet rule). The engine still computes realised r-multiples from the actual fill and declared stop, so overnight/weekend gaps show up honestly as dispersion around 2R. | Anchoring TP to the actual fill (`fill ± 2 * |fill − stop|`) — **inexpressible under contract v2**: `ExitLeg.price`/`pips` must be fixed at decision time and the fill is not yet known; on Monday opens the anchor error would be 3× the weekend gap. Also rejected: anchoring risk to bar t's close for the *reported* r-multiple (the engine owns that computation from realised prices, contract §3.3). |
| 11 | What happens when an opposite signal forms while a position is open? | Nothing, by design. F12 caps admission at 1 open position per (strategy, pair, granularity): the new OrderIntent is not admitted while the old position runs, and no mechanism closes or reverses the open position — it exits only at its stop, TP, or `END_OF_DATA` (F11). Consequence: reversal signals during an open trade are silently dropped; this is the conservative reading (no discretionary early exits invented) and matches T6 semantics. | Closing/reversing the open position on an opposite signal — no such mechanism exists in contract v2 (F12 blocks admission only; there is no supersede), and inventing one would add an exit path the source does not specify |

## 11. Expected behaviour

- **Rough trade frequency:** the CSV states ~1 trade per 4–8 weeks per pair on D1 → ~6–13 trades/pair/year. On the 3 currently-available pairs plus EUR_JPY (pending), expect ~25–50 trades/year pooled, and roughly 120–260 trades per pair over the ~20-year D1 history. Per 6-month OOS fold this is ~3–7 trades/pair — thin; `low_confidence` flags are likely on single-pair cells and the pooled verdict carries the statistical weight (contract Part G).
- **What would make this strategy fail the gates:**
  1. Trade count too low per fold → `low_confidence` / insufficient OOS evidence.
  2. F5 (stop-before-target on any H1 bar touching both) plus the tight 2-pip buffer stop: the stop sits just under a wick that was, by construction, recently probed — re-tests of the wick extreme are common, so realised win-rate will land well below the author's variant-level claims.
  3. F6 weekend gaps through a 2-pip-buffer stop producing losses > 1R.
  4. The author's evidence is for the ADR and fib-continuation **variants** (71 trades/67 winners; 27/28), *not* this pinbar variant — the CSV itself says "the pinbar variant itself has forward examples but no standalone audited stats, so independent re-test still required." The edge as specified here is unproven.
- **Is the author's HIGHLY_RECOMMENDED conviction justified?** Not for this variant as specified. The recommendation leans on documented live results from *different* variants of the method and on forum forward examples for this one. The mechanical codification is genuine and the hypothesis is plausible, but our conservative subset (no optional exits, exact 2/3 wick, strict wick-touch, 2-pip stop) deliberately strips the discretionary management that produced the cited win-rates. Treat the strategy as EXPERIMENTAL in effect despite the author's label; the backtest verdict, not the forum record, decides.
