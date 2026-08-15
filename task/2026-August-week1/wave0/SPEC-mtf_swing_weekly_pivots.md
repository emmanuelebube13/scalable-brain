# SPEC-mtf_swing_weekly_pivots

**Source:** row 19 of forex_swing_strategies.csv · https://www.tradingview.com/script/oXYuZB8v-Swing-Strategy-MTF-with-Auto-SL-TP-Weekly-Pivots/
**Conviction (author's):** MODERATE

## 1. Hypothesis

The edge is a trend-aligned pullback entry: when the daily chart is in an established regime (price above a rising-stacked EMA50/EMA200), intraday dips back toward the 21-period EMA are more likely to be profit-taking pauses than trend reversals, so buying a confirmed bullish rejection candle at that "value" line with a fixed 1:2 reward-to-risk harvests the behavioural tendency of trend-following flows to re-enter after shallow retracements. The daily regime gate exists to keep the strategy out of ranging markets where EMA pullbacks have no follow-through; persistence rests on the well-documented medium-term momentum/trend premium in FX majors rather than on any microstructural quirk that arbitrage would quickly erase.

## 2. Scope

| Field | Value |
|---|---|
| primary_granularity | **H4** (decision frame; see §10 #1 — "H1|H4 execution" resolved to H4, the fewer-trades reading) |
| context_granularities | **D1** (trend regime filter only) |
| simulate_on | **H1** (fill resolution per contract Part D) |
| pairs_requested (verbatim) | `EURUSD|GBPUSD|USDJPY|AUDUSD|FX majors and liquid indices` |
| pairs_available | EUR_USD, GBP_USD, USD_JPY, AUD_USD (live) · USD_CAD (live; covers the generic "FX majors" clause) |
| pairs_missing | "liquid indices" — no index instruments exist in `dim_asset` and none are planned → **DATA-GAP-mtf_swing_weekly_pivots.md** (recommendation: implement now, FX-only). No Wave-1 pending pair is required. |

W1 is **not** a declared granularity: the weekly pivot levels named in the source are dropped as non-load-bearing (§10 #3), so the stale W1 series is irrelevant to this strategy.

## 3. Indicators

| Indicator | Params | Source |
|---|---|---|
| EMA on H4 Close | period 21 | inventory `ema(close, 21)` on the H4 frame |
| RSI on H4 Close | period 14 | inventory `rsi(close, 14)` on the H4 frame |
| EMA on D1 Close | period 50 | inventory `ema(close, 50)` on the D1 frame |
| EMA on D1 Close | period 200 | inventory `ema(close, 200)` on the D1 frame |
| Trailing 5-bar lowest low (long stop) | window 5, inclusive of decision bar | private, specified: `S_long(t) = min(Low[t-4 … t])` on H4. This is a plain trailing rolling minimum, **not** a swing-point detection — no confirmation lag exists and `causal_structure` is not needed. |
| Trailing 5-bar highest high (short stop) | window 5, inclusive of decision bar | private, specified: `S_short(t) = max(High[t-4 … t])` on H4. Same causality note. |

Warm-up requirement: no OrderIntent may be emitted until at least 200 completed D1 bars exist (EMA200 defined) and at least 21 H4 bars + 14 H4 bars exist; the harness's history gate covers this.

No `detect_swing_points`, no ZigZag, no fractals, no weekly pivot series are used anywhere in the executable logic.

## 4. Entry — long

All conditions are evaluated on the H4 decision bar `t` at the **close** of `t`. Only data knowable at that instant may be used.

1. **D1 regime (context).** Let `d` be the most recent D1 bar that has **fully closed** at or before the open of `t` — mechanically: `d` is the last D1 bar whose timestamp ≤ `t.timestamp − 24h` (D1 bars are stamped at their open and close 24h later; implemented as `merge_asof(h4, d1, direction="backward", allow_exact_matches=False)` after shifting the D1 index forward one full D1 interval, per contract §4). Require:
   `d.Close > EMA50_D(d) > EMA200_D(d)`.
2. **Momentum:** `RSI14_H4(t) > 50`.
3. **Pullback to value (directional band, §10 #2):** price is at or below the EMA21 but by less than 1%:
   `0 ≤ EMA21_H4(t) − Close(t)` AND `(EMA21_H4(t) − Close(t)) / EMA21_H4(t) < 0.01`.
4. **Bullish reversal candle:** `Close(t) > Open(t)` AND `Close(t) > High(t−1)`.
5. **Stop sanity guard:** `Close(t) − S_long(t) > 0`. If this fails, no signal (degenerate zero-risk stop).

If 1–5 all hold, emit:

- **entry type:** `market`
- **entry level:** none at emission (`entry_price = None`); fills at the **open of H4 bar t+1** (F1/F2) plus the standard cost model (F10: 1.0 pip spread + 0.5 pip slippage, entry only)
- **expires_after_bars:** `null` — market orders fill at the next bar's open; no pending lifetime exists
- **tag:** `"long_pullback"`

Signal re-emission: if conditions hold on consecutive bars, one intent is emitted per bar. The strategy never observes positions; over-subscription is handled solely by F12 (`max_concurrent_positions = 1`, the default — this is the source's "single-position signal logic"). No pending-order overlap can occur because entries are market (§10 #6).

## 5. Entry — short

Mirror of §4, evaluated at the close of H4 bar `t`:

1. **D1 regime:** same context bar `d` as §4; require `d.Close < EMA50_D(d) < EMA200_D(d)`.
2. **Momentum:** `RSI14_H4(t) < 50`.
3. **Pullback to value:** `0 ≤ Close(t) − EMA21_H4(t)` AND `(Close(t) − EMA21_H4(t)) / EMA21_H4(t) < 0.01`.
4. **Bearish reversal candle:** `Close(t) < Open(t)` AND `Close(t) < Low(t−1)`.
5. **Stop sanity guard:** `S_short(t) − Close(t) > 0`.

Emit `market` sell, `entry_price = None`, fill at open of `t+1` (F1/F2), `expires_after_bars = null`, tag `"short_pullback"`. F12 = 1 as in §4.

## 6. Stop

- **Initial stop (long):** `StopRule.price = S_long(t) = min(Low[t-4 … t])` — absolute, declarable at OrderIntent creation.
- **Initial stop (short):** `StopRule.price = S_short(t) = max(High[t-4 … t])`.
- **move_to_breakeven_on:** `none` (source declares no breakeven rule).
- **trail:** `none` (source declares a fixed structural stop; `trail_atr_multiple = None`).

The stop is anchored to decision-bar-knowable prices (fleet rule 8): the fill price of a market order is unknowable at emission, so the declared stop is the 5-bar extreme at the decision bar. If bar `t+1` opens beyond the stop, F6 resolves the fill honestly at the open and realised loss may exceed the declared 1R — this is recorded, not hidden.

## 7. Exit legs

Fractions sum to 1.0. Single leg, matching the source's explicit 1:2 RR with no scale-outs.

| Label | Fraction | Kind | Level formula |
|---|---|--:|---|
| TP1 | 1.0 | take_profit | **Long:** `Close(t) + 2.0 × (Close(t) − S_long(t))` · **Short:** `Close(t) − 2.0 × (S_short(t) − Close(t))` |

The TP is anchored to the **decision-bar close**, not the fill (fleet rule 8 — the fill-anchored version is inexpressible in contract v2 and is rejected in §10 #4). Declared R is therefore `2.0` by construction; realised R differs whenever the `t+1` open differs from `Close(t)` (weekend gaps, news spikes) — F3/F6 resolve those honestly and the delta is visible in `r_multiple`.

Weekly pivot/R1/S1 levels, named in the source "as confluence zones for exits and context", do **not** modify this leg (§10 #3).

## 8. Filters

| Filter | Timeframe | Rule | Knowable at |
|---|---|---|---|
| D1 trend regime (long) | D1 | `d.Close > EMA50_D(d) > EMA200_D(d)` | Close of D1 bar `d`; first usable at H4 bars with `timestamp ≥ d.timestamp + 24h` (contract §4 shifted-merge) |
| D1 trend regime (short) | D1 | `d.Close < EMA50_D(d) < EMA200_D(d)` | same |
| RSI midline | H4 | `RSI14 > 50` (long) / `< 50` (short) | Close of decision bar `t` |
| Pullback band | H4 | within 1% of EMA21 on the trend side (§4.3 / §5.3) | Close of decision bar `t` |

There is **no** session, news, volatility, or spread filter in the source, and none is added. The 1.0-pip cost-model spread (F10) is a fixed engine constant, not a strategy filter — no proxy is introduced. The weekly-pivot "confluence" is dropped, not proxied (§10 #3), so the stale W1 series imposes no data dependency.

## 9. Causality audit

| Rule | Inputs | Fully knowable at | Confirmation lag |
|---|---|---|---|
| D1 regime filter | D1 bar `d` OHLC + EMA50_D/EMA200_D through `d` | Close of `d` = `d.timestamp + 24h`; decision bars strictly after that | **One full D1 interval** relative to the D1 bar's open stamp. Enforced by `allow_exact_matches=False` after a one-interval forward shift of the D1 index. An H4 bar at `d.timestamp + 24h` is the first that may use `d`; nothing earlier. |
| EMA21 (H4) | H4 closes through `t` | Close of `t` (decision instant) | None — trailing window. |
| RSI14 (H4) | H4 closes through `t` | Close of `t` | None — trailing window. |
| Pullback band | `Close(t)`, `EMA21(t)` | Close of `t` | None. |
| Reversal candle | `Open/High/Close(t)`, `High/Low(t−1)` | Close of `t` | None — `t−1` is fully closed by `t`. |
| 5-bar stop (long/short) | `Low/High[t-4 … t]` | Close of `t` | **Zero — this is a trailing rolling extreme, not a swing-point detection.** No `center=True`, no future bars. It is causal by construction and does not need `causal_structure.confirmed_swing_points`. (Note for reviewers: had this been "the swing low of the last swing", a `period`-bar confirmation lag would apply; the source is explicit that it is a plain 5-bar lowest low / highest high, and the pseudocode `low.rolling(5).min()` confirms the trailing reading.) |
| TP level | `Close(t)`, stop level | Close of `t` | None — declarable at emission. |
| Weekly pivots | — | — | **Dropped** (§10 #3); had they been kept, the previous week's H/L/C would be knowable only at the W1 close (one full week of lag), computable from closed D1 bars since W1 is stale ~8 weeks. |

No rule reads any bar after `t` (context) or after the close of `t` (execution frame). `assert_no_lookahead_v2` truncation should leave the order list unchanged.

## 10. Ambiguities resolved

| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | "H1\|H4 execution" — two decision frames named | **H4 as the sole primary frame.** Fewer bars → fewer signals, later entries, wider stops relative to the fixed 1.5-pip round-trip cost; cleaner one-step D1→H4 causality. | H1 as primary (4× the signal count, stop distances ~½ → costs consume far more of the 1R risk; the looser reading). Also rejected: running both frames simultaneously (source gives no rule for combining them; inventing one is out of scope). |
| 2 | "price within 1% of EMA21 (pullback to value)". The pseudocode's symmetric reading `\|close−e21\|/e21 < 0.01` is ~110 pips on EURUSD H4 — a band so wide it is almost never false and admits entries *above* value in a long, contradicting the words "pullback to value". | **Directional band:** long requires `Close(t) ≤ EMA21(t)` and the gap below EMA21 < 1% of EMA21 (short mirrored). This rejects every entry where price is above the value line → strictly fewer, better-located entries, faithful to "pullback". | Symmetric ±1% literal band (rejected: nearly vacuous on H4, more trades, admits momentum-chasing entries the label forbids). Also rejected: inventing a tighter numeric threshold (e.g. 0.1%) with no source support. |
| 3 | Weekly pivots "used as confluence zones for exits and context" — no mechanical rule states how they alter an entry, the stop, or the TP. | **Dropped from the executable logic.** Any conversion into a hard gate (e.g. "no longs below weekly PP") or a TP relocation would be an invented rule with an arbitrary parameter, and would also create a dependency on the stale W1 series. The trade plan is fully specified without them. | Keeping pivots as a mandatory filter/exit derived from the last fully-closed week of D1 bars (rejected: invents thresholds the source never quantifies; also rejected as unjustifiable given W1 is stale ~8 weeks and the source never defines the confluence distance). |
| 4 | "TP = entry + 2.0 × stop distance" — "entry" means the fill price in the source. | TP and risk anchored to the **decision-bar close**: `TP = Close(t) + 2×(Close(t) − S_long(t))`, declared as an absolute price at OrderIntent creation (fleet rule 8). Realised R ≠ 2.0 when the `t+1` open differs from `Close(t)`. | Fill-anchored TP (rejected as **inexpressible** in contract v2: the fill price is unknowable at emission for a market order — not merely a less conservative choice). |
| 5 | "enter on candle close" | Market OrderIntent at decision bar `t`; fill at **open of `t+1`** per F1/F2 — the only mechanism the engine offers. | Filling at the close of `t` itself (rejected: impossible under F1 decision/execution separation; would be look-ahead-flavoured). |
| 6 | "single-position signal logic" vs declarative intents that cannot observe open positions | Rely on **F12 default `max_concurrent_positions = 1`** per (strategy, pair, granularity); consecutive-bar signals simply emit intents that the engine declines while a position is open. No cancellation/supersede semantics are assumed anywhere. | Re-emission throttling inside the strategy (rejected: the strategy cannot know whether the prior intent filled — no such channel exists — and any look-back guess would corrupt the truncation probe). No pending orders exist, so no multi-fill overlap risk arises (§4). |
| 7 | "FX majors and liquid indices" | FX majors covered by the five live pairs (the four named + USD_CAD). "Liquid indices" → DATA-GAP; proceed FX-only. | Treating indices as optional flavour to silently ignore without a gap note (rejected: they are explicitly named in `target_pairs`, so the omission is documented, not silent). |

## 11. Expected behaviour

- **Trade frequency:** the D1 EMA50/200 stacked-regime gate is satisfied roughly 30–50% of the time per pair; layering RSI on the correct side of 50, the directional ≤1% pullback band, and the reversal candle leaves joint signal rates of roughly 1–4% of H4 bars — expect on the order of **2–8 trades per pair per year**, i.e. ~10–40 trades/year across the five FX pairs. OOS folds of 6 months will carry single-digit trade counts per pair; `low_confidence` flags are likely per-cell and the pooled verdict should be read with that caveat.
- **What makes it fail the gates:** (a) 1:2 RR systems need a sustained win rate above ~33% — prolonged D1 ranging regimes that still pass the EMA stack (slow, flat EMAs near the price) will generate repeated stopped-out pullbacks; (b) the 5-bar trailing stop is tight relative to H4 noise, so adverse excursion before trend resumption is common and F5 (stop-before-target) compounds it; (c) realised R erosion from F10 costs and gap fills (F6) matters more on H4-sized stops than on D1.
- **Is the author's MODERATE conviction justified by the rules as written?** Yes — arguably the honest grade. The system is fully mechanical, non-lookahead (the Pine source used non-lookahead `request.security`, and this spec preserves that via the shifted D1 merge), has an explicit structural stop and fixed RR, and rests on a plausible trend/pullback behavioural premium. Against it: no documented performance in the source, low community validation (3 likes), and the edge is a crowded, well-known pattern whose excess return is likely modest. MODERATE with an independent backtest requirement is the correct stance; nothing in the rules as written justifies HIGHLY_RECOMMENDED.
