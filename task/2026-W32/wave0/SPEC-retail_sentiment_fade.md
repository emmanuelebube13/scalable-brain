# SPEC-retail_sentiment_fade

**Source:** row 51 of forex_swing_strategies.csv · https://www.mql5.com/en/code/62627
**Conviction (author's):** EXPERIMENTAL

## 1. Hypothesis

Retail traders as a crowd are systematically wrong at positioning extremes: when ≥60% of retail accounts are short a pair, their aggregate future buy-to-cover flow plus the tendency of inexperienced traders to fight trends and average losers creates persistent pressure in the direction *against* the crowd. Fading an extreme retail skew — but only when the technical trend (fast SMA vs slow SMA) confirms the crowd is fighting the tape — should capture a behavioural edge that persists because it is rooted in retail loss asymmetry, not in an arbitrage that sophisticated flow can close. The MA alignment condition exists to avoid fading a sentiment extreme that arises during a genuine crowd-aligned trend. The author himself labels this EXPERIMENTAL: no backtest evidence is published; it is a research seed.

## 2. Scope

- **primary_granularity:** D1
- **context_granularities:** none (all indicators computed on D1)
- **simulate_on:** H1 (fills/stops/legs resolved on H1 bars within each D1 span, per contract §5)
- **pairs_requested (verbatim):** `EURUSD|GBPUSD|USDJPY|pairs covered by Ziwox sentiment API`
- **pairs_available:** EUR_USD ✅ · GBP_USD ✅ · USD_JPY ✅ (all three are live in `dim_asset`; the trailing "pairs covered by Ziwox sentiment API" clause is unbounded and adds nothing actionable — the three named pairs are the implementable set)
- **pairs_missing:** none among named pairs. **However the retail-sentiment feed itself is missing for ALL pairs** — no sentiment data exists anywhere in the DB. See `DATA-GAP-retail_sentiment_fade.md`. This is a feed gap, not a pair gap.

## 3. Indicators

| Indicator | Params | Source |
|---|---|---|
| SMA fast | period=20, on D1 `Close` | inventory `sma(series, 20)` |
| SMA slow | period=50, on D1 `Close` | inventory `sma(series, 50)` |
| ATR | period=14, on D1 High/Low/Close | inventory `atr(high, low, close, 14)` |
| Retail short ratio (short_ratio_pct) | % of open retail positions held short, count-of-positions basis, per pair, one value per sentiment observation | **EXTERNAL — not in inventory, not in DB.** Specified fully in §9 and DATA-GAP note: a time series `fact_sentiment(asset_id, observed_at, published_at, long_ratio_pct, short_ratio_pct, basis, sample_size)`. |
| Retail long ratio (long_ratio_pct) | mirror of the above | same external series |

SMA periods 20/50 are **reconstructed** (source says only "fast and slow SMA" — see §10 row 1). No swing/ZigZag/fractal indicators are used; `detect_swing_points` is not involved.

## 4. Entry — long

At the **close of D1 decision bar t**, all of:

1. **Sentiment extreme:** the most recent sentiment observation *eligible at t* (see §9 rule S1) reports `short_ratio_pct >= 60.0`.
2. **Trend alignment:** `SMA20(Close)[t] < SMA50(Close)[t]` — both SMA values computed from closes up to and including bar t.
3. **Both conditions true simultaneously at the same decision bar** (sentiment may be days stale per §9; that is intended and conservative).

- **entry type:** `market`
- **entry level:** none declared (`entry_price = None`); fills at the **open of bar t+1** plus adverse slippage (F2). "New-candle execution" in the source maps exactly to this: decide on the close of t, execute on the open of t+1.
- **expires_after_bars:** null (market order — not applicable; no pending order exists)

## 5. Entry — short

Mirror of long. At the close of D1 decision bar t, all of:

1. **Sentiment extreme:** the most recent eligible sentiment observation (§9 rule S1) reports `long_ratio_pct >= 60.0`.
2. **Trend alignment:** `SMA20(Close)[t] > SMA50(Close)[t]`.
3. Simultaneity as above.

- **entry type:** `market`; fill at open of t+1 (F2); `expires_after_bars`: null.

Note: conditions 4.1 and 5.1 are mutually exclusive on any single pair (short_ratio ≥ 60 implies long_ratio ≤ 40 under count basis), so the strategy can never emit both directions on the same pair/bar.

## 6. Stop

The source documents **no stop at all**; the CSV's own commentary recommends adding 1.5×ATR SL. Adopted overlay, anchored to decision-bar-knowable prices:

- **Initial stop (long):** `StopRule.price = Close[t] − 1.5 × ATR14[t]`
- **Initial stop (short):** `StopRule.price = Close[t] + 1.5 × ATR14[t]`
- where `ATR14[t]` is the completed ATR(14) on D1 at decision bar t.
- **move_to_breakeven_on:** none
- **trail:** none (static stop)

The fill occurs at the open of t+1 (F2), so realised risk = |fill − stop| which differs from the declared 1.5×ATR anchor whenever the market gaps between close(t) and open(t+1). Declared geometry is anchored at decision close as required; F3/F6 resolve the fill honestly. See §10 row 4.

## 7. Exit legs

The source has no TP; the CSV recommends 1:2 RR against the 1.5×ATR stop. Adopted:

| Label | Fraction | Kind | Level formula |
|---|---|--:|---|---|
| TP1 | 1.0 | take_profit | long: `Close[t] + 3.0 × ATR14[t]` · short: `Close[t] − 3.0 × ATR14[t]` |

Fractions sum to 1.0. (3.0 = 2 × 1.5, i.e. reward:risk 1:2 measured from the decision-close anchor.) Single leg; no scale-outs, no time exit. Any residual open position closes END_OF_DATA per F11 and is flagged.

## 8. Filters

- **MA trend filter (part of entry logic):** fast-vs-slow SMA alignment, evaluated on **D1**, knowable at the **close of decision bar t** (both SMAs use only closes ≤ t). It forbids fading the crowd when the crowd is aligned with the prevailing MA trend.
- **Sentiment-extreme gate (part of entry logic):** ratio ≥ 60%, evaluated on the **external sentiment series**, knowable only per the conservative lag rule S1 (§9): an observation is eligible at decision bar t only if its `published_at ≤ close(t) − 24h`. This 24h buffer is itself the causality filter.
- **Duplicate-trade guard:** the source's "one order per symbol via OrdersTotal check" maps to engine convention **F12: max_concurrent_positions = 1 per (strategy, pair, granularity)**. The strategy declares this via metadata default; it does not and cannot observe open positions itself. While a position is open, re-emitted intents on subsequent qualifying bars are not admitted (§3.2 step 6). After a stop/TP close, the next qualifying bar re-enters — intended behaviour; residual churn risk noted in §10 row 7.
- **Session/news/volatility filters:** none documented; none added. No economic calendar or news feed exists in the DB (DATA_AVAILABILITY: no non-price data) — no such filter can be expressed.
- **No proxy substitution:** the missing sentiment series is NOT proxied by tick volume, price momentum, or anything else in the DB. Any such substitution would measure a different strategy. Flagged here and in the DATA-GAP note.

## 9. Causality audit

| Rule | Inputs | Fully knowable at |
|---|---|---|
| S1 (sentiment eligibility) | sentiment observation with vendor fields `observed_at`, `published_at` | An observation is eligible at D1 decision bar t iff `published_at ≤ close(t) − 24 hours`. **Assumed observation lag: 24 h minimum between publication and use.** Ziwox's publication cadence and revision policy are undocumented; publication lag plus possible silent restatement make same-day use unsafe. With daily snapshots published ~00:00Z, effective staleness at the 21:00Z D1 close is 21–45 h. Stale sentiment is the conservative reading — fewer, later entries. |
| S2 (sentiment threshold) | `short_ratio_pct` / `long_ratio_pct` of the S1-eligible observation | Same bar as S1 (inherits the 24 h lag). |
| P1 (SMA fast) | D1 closes ≤ t | Close of bar t. `sma` is causal (trailing window). |
| P2 (SMA slow) | D1 closes ≤ t | Close of bar t. |
| P3 (ATR14) | D1 H/L/C ≤ t | Close of bar t. |
| E1 (long entry) | S2 ∧ P1<P2 | Close of bar t → intent emitted with `decision_bar = t`; eligible for fill from t+1 (F1), fills at open(t+1) (F2). Never on bar t. |
| E2 (short entry) | mirror | Same. |
| ST (stop level) | Close[t], ATR14[t] | Declared at OrderIntent creation (close of t); both inputs knowable at close of t. |
| X1 (TP leg) | Close[t], ATR14[t] | Same. |
| F12 guard | engine state | Engine-side; strategy emits unconditionally, engine admits ≤1 position. |

No swing/pivot/ZigZag/fractal rules exist in this strategy, so no confirmation-lag construct applies; the only non-trivial lag is the sentiment publication lag S1, stated above. There is no multi-timeframe context, so the §4 MTF rule is not engaged — but the same closed-bar discipline applies trivially: every D1 input is a *closed* D1 bar.

## 10. Ambiguities resolved

| # | Ambiguity | Conservative reading taken | Alternative rejected |
|--:|---|---|---|
| 1 | "Fast and slow SMA" — periods never named | SMA 20/50 on D1 close, a standard swing default; **reconstructed** | 9/21 or other faster pairs — more regime flips → more trades; rejected as less conservative and equally undocumented |
| 2 | Timeframes "H1|H4|D1 (runs on chart TF)" | **D1 chosen**: retail sentiment is a daily-cadence dataset; D1 produces the fewest trades and matches the data's natural frequency | H1 or H4 — more trades on a feed that updates ~daily, so intraday signals would re-read stale sentiment and inflate trade count with duplicated information; rejected |
| 3 | Ratio basis: Ziwox/Myfxbook publish both %-of-positions (headcount) and %-of-volume | **%-of-positions (headcount)**: the behavioural hypothesis is about how many retail traders are wrong, not how much they bet | %-of-volume — a few large retail tickets skew it; also evaluates the fields directly rather than deriving short = 100 − long (rounding/neutral accounts may break the identity) |
| 4 | Source has **no SL/TP at all** | Adopted the CSV's own recommended overlay: SL = 1.5×ATR14, TP = 2×SL distance, **anchored to decision-bar close** | (a) The no-exit original — **inexpressible/incomplete**: a position with no exits only closes END_OF_DATA (F11), measuring nothing; (b) anchoring R at the fill price — **inexpressible** under decision-bar anchoring (fill price unknowable at emission); realised R ≠ declared R when t+1 opens away from close(t), resolved honestly by F2/F6 |
| 5 | Sentiment publication timing/cadence undocumented | Assume **24 h minimum lag** between publication and eligibility (rule S1); treat values as as-published, never restated | "Use the latest snapshot available at decision time" — risks acting on data published hours later or silently revised; rejected as potential look-ahead via an external feed |
| 6 | "Duplicate-trade guard (one order per symbol)" mechanics | Maps to **F12 max_concurrent_positions = 1**; strategy emits intents regardless, engine caps admission | "A new signal supersedes/closes the open position" — **that mechanism does not exist in contract v2** (no OCO, no supersede, strategy never observes positions); rejected as inexpressible |
| 7 | Extremes can persist for many days → signal re-fires daily | While a position is open, re-emissions are blocked by F12; after a stop-out with the extreme still in force, the next qualifying bar re-enters. Residual risk: repeated re-entry into a persistent extreme (churn/whipsaw), direction = **more** trades/losses than a fire-once reading — recorded, not suppressed | "Fire once per extreme episode" — requires the strategy to remember episode state across bars; while expressible, it suppresses trades and is a larger departure from the source; rejected in favour of the documented MT4 behaviour (OrdersTotal guard only) |
| 8 | Threshold inclusivity | `>= 60.0` inclusive, exactly as documented ("Retail Short Ratio >= 60%") | Strict `>` — contradicts the documented operator |

## 11. Expected behaviour

- **Frequency:** sentiment extremes (≥60%) occur perhaps 5–15% of days per major pair; intersected with the MA-alignment condition and one-position-at-a-time, expect roughly **1–4 trades per pair per month**, i.e. ~150–900 trades over 10 years × 3 pairs *if* sentiment history existed. Trade duration: with 1.5×ATR(D1) stop and 3×ATR target, typical holds of 2–15 days.
- **Gate risks:** (a) **trade count / low_confidence** is the dominant risk — sentiment history will be short (see DATA-GAP), and walk-forward folds (36-month train) will contain very few trades; expect `low_confidence` verdicts by arithmetic, not by strategy defect; (b) pooled OOS could fail simply because D1 ATR-scale moves make costs (1.0 pip spread + 0.5 pip slippage) negligible, so any failure is genuine lack of edge, not cost drag; (c) the edge may be regime-dependent — retail-fade works in mean-reverting regimes and bleeds in sustained trends (crowd extremes can persist for weeks while price keeps trending; the MA gate only partially protects).
- **Author's conviction justified?** Yes — EXPERIMENTAL is exactly right. The behavioural mechanism (retail crowds systematically wrong at extremes; their closing flow fuels the reversal) is plausible and documented in the SSI literature, but the published logic has no backtest evidence, incomplete exits (no SL/TP at all in the original), an unnamed-parameter trend filter, and a hard external data dependency with unknown history depth. The rules as written here are implementable, but they remain a **research seed**: the verdict will rest on data that does not yet exist in the system, and even once ingestion starts, a statistically meaningful sample is 12–24 months of forward accumulation away.
