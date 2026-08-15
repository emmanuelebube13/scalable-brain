# SPEC-financial_regime_index

**Source:** row 49 of forex_swing_strategies.csv · https://www.tradingview.com/script/BZdZNCcS-US-SPY-Financial-Regime-Index-Swing-Strategy/
**Conviction (author's):** EXPERIMENTAL

> **IMPLEMENTATION BLOCKER (see DATA-GAP-financial_regime_index.md):** this strategy requires nine external daily series (SPY, ACWI, HYG, LQD, VIX, DXY, US02Y, US10Y, BIL), none of which exist in the database and none of which are FX pairs obtainable via the existing OANDA ingest. The spec below is complete and mechanical, but Wave-2 implementation cannot begin until the macro ingest described in the DATA-GAP note lands. Recommendation in that note: **DEFER**.

## 1. Hypothesis

Financial-conditions regimes are persistent and cross-asset: when equities (US and world), credit, the dollar, volatility, short rates, the yield-curve slope and cash-vs-equity liquidity preference point the same way at once, that alignment identifies a durable risk-on/risk-off state that liquid FX majors trend with, because global capital reallocates between funding, reserve and risk currencies on the same macro impulse. The composite persists because the underlying flows (hedge-fund deleveraging, central-bank cycles, collateral demand) move over weeks, not hours; a daily z-scored composite with slope and price-trend gates should enter after confirmation and stay out of chop. The author makes no performance claims and labels the idea experimental; the edge is plausible but unverified.

## 2. Scope

- **primary_granularity:** D1 (composite calculation AND FX decision frame)
- **context_granularities:** () — none; the "context" is the external macro composite, not an FX timeframe
- **simulate_on:** H1 (fills/stops/legs resolved on H1 bars within each D1 span, per contract §5)
- **pairs_requested (verbatim):** `EURUSD|GBPUSD|USDJPY (liquid FX majors in stated scope)|SPY|ES futures|gold`
- **pairs_available:** EUR_USD (live), GBP_USD (live), USD_JPY (live)
- **pairs_missing:** SPY (equity ETF — not an FX instrument, not in `dim_asset`), ES futures (not in DB), gold/XAU_USD (deliberately excluded by policy per DATA_AVAILABILITY.md). → DATA-GAP-financial_regime_index.md. These are *execution targets*; the three FX majors cover the CSV's "stated scope", so the strategy remains implementable on FX alone once the macro series land.
- **External series required (all missing):** SPY, ACWI, HYG, LQD, VIX, DXY, US02Y, US10Y, BIL daily closes → DATA-GAP note (required, blocking).

## 3. Indicators

All macro-composite math is **private** (not in the shared inventory; computed on external series, not on FX OHLCV). FX-side indicators map to the inventory.

| Indicator | Params | Source |
|---|---|---|
| Log return `r_i(t) = ln(P_i(t)/P_i(t−1))` | per macro series i, daily | private — formula given here |
| Rolling z-score `z_i(t) = (r_i(t) − mean_W(r_i)) / std_W(r_i)` | W = 252 trading days, min_periods = 126, sample std (ddof=1) | private — same form as inventory `zscore` but W=252, on external series |
| Winsorization | clip each z_i to [−3, +3] before weighting | private — declared choice (§10 #2) |
| Component σ for weights `σ_i = std_W(r_i)` | W = 252, ddof=1, on RAW log returns (not z-scores) | private — declared choice (§10 #4) |
| Inverse-vol weight `w_i(t) = (1/σ_i(t)) / Σ_j (1/σ_j(t))` | recomputed each day t | private |
| Composite `BFCI_raw(t) = Σ_i w_i(t) · c_i(t)` | 8 signed components c_i, table below | private |
| EMA smoothing `BFCI(t) = EMA(BFCI_raw, span=10)` | span=10, adjust=False | inventory `ema(series, 10)` equivalent, applied to BFCI_raw |
| SMA trend filter on FX pair | SMA(close, 200) on D1 | inventory `sma` |
| ATR (stop/trail geometry) | ATR(14) on FX D1 | inventory `atr` |

**Component definitions (8 components from 9 series; all "logret" = daily log return of the stated constructed series):**

| # | Component | Construction | Sign applied |
|---|---|---|---|
| 1 | EQ_US | z(logret(SPY close)) | + |
| 2 | EQ_WORLD | z(logret(ACWI close)) | + |
| 3 | CREDIT | z(logret(HYG close / LQD close)) | **−1** (falling HYG/LQD = credit stress hurts) |
| 4 | VIX | z(logret(VIX close)) | **−1** |
| 5 | USD | z(logret(DXY close)) | **−1** |
| 6 | Y2 | z(logret(US02Y yield level)) | **−1** (rising 2Y = tightening hurts) |
| 7 | SLOPE | z(Δ(US10Y − US02Y)) — first difference of the spread in percentage points, NOT logret (the spread can be ≤ 0) | + |
| 8 | LIQ | z(logret(BIL close / SPY close)) | **−1** (rising cash-vs-equity preference = risk-off) |

Sign flips implement the CSV's `comps[CREDIT]*=-1; comps[Y2]*=-1; comps[USD]*=-1; comps[VIX]*=-1; comps[LIQ]*=-1`. Constructions for CREDIT, SLOPE and LIQ are reconstructed (the pseudocode names symbols without defining them) — §10 #3.

## 4. Entry — long

Decision frame: FX pair D1 bar *t* (all conditions evaluated at the close of *t*; macro inputs subject to the +1-day availability lag of §9).

1. **Trigger (either):**
   a. threshold cross — BFCI(t) > +0.50 AND BFCI(t−1) ≤ +0.50; **or**
   b. floor cross — BFCI(t) > +1.00 AND BFCI(t−1) ≤ +1.00 (the CSV's "composite already above always-long floor", read as a cross event — §10 #5).
2. **Slope gate:** BFCI(t) > BFCI(t−1) (positive composite slope; vacuously true for the crosses above but retained as declared — matches the pseudocode `(bfci>bfci.shift(1))`).
3. **Price gate:** Close(t) > SMA200_close(t) on the FX D1 frame.
4. **Data-staleness gate:** the most recent macro observation feeding BFCI(t) is ≤ 10 calendar days old (§8).

- **Entry type:** `market` (fill at open of bar t+1, F1/F2).
- **Entry level:** n/a (market).
- **expires_after_bars:** null (market orders do not pend).

## 5. Entry — short

Mirror of long, with the asymmetry the source defines (the "always-long floor" has no short twin; shorts have only the threshold trigger — §10 #6):

1. **Trigger:** BFCI(t) < −0.50 AND BFCI(t−1) ≥ −0.50 (cross down through short threshold).
2. **Slope gate:** BFCI(t) < BFCI(t−1).
3. **Price gate:** Close(t) < SMA200_close(t) on the FX D1 frame.
4. **Data-staleness gate:** as in §4.

- **Entry type:** `market`. **Entry level:** n/a. **expires_after_bars:** null.

## 6. Stop

- **Initial stop (exact formula):**
  - Long: `StopRule.price = Close_D1(t) − 2.0 × ATR14_D1(t)`
  - Short: `StopRule.price = Close_D1(t) + 2.0 × ATR14_D1(t)`
  - Anchored to the **decision-bar close** (knowable at OrderIntent creation), NOT the fill — the source measures risk from entry; fill-anchored risk is inexpressible for market orders under contract v2 and is recorded as rejected in §10 #7. Realised R ≠ declared R when the t+1 open gaps (F2/F6 resolve honestly).
- **move_to_breakeven_on:** none.
- **trail (StopRule.trail_atr_multiple):** none — trailing is expressed as the single exit leg below, not duplicated on the stop.

## 7. Exit legs

The source's exits are *signal-based* (cross below long-exit line / cross above short-exit line / fresh opposite signal / stress guard at the floor). Contract v2 has no close-position intent and ExitLeg levels must be declarable absolute values at OrderIntent creation, so a moving-composite cross is **inexpressible**. Conservative mapping (§10 #8): one ATR-trailing leg stands in for the regime exit — it keeps the trade while the regime runs and exits on a material adverse excursion.

| Label | Fraction | Kind | Level formula |
|---|---|---|---|
| REGIME_TRAIL | 1.0 | trailing | atr_multiple = 3.0 (ATR(14) on the FX D1 frame; trail updates at each D1 bar close per F9, using that bar's completed ATR; fills resolved on H1) |

Fractions sum to 1.0. The static 2.0×ATR initial stop remains in force as the catastrophe stop; in practice the 3.0×ATR trail from the running extreme will usually be hit first in a regime reversal, which is the intended stand-in for the composite-cross exit.

## 8. Filters

| Filter | Timeframe / series | When knowable |
|---|---|---|
| SMA200 price-trend gate (long above / short below) | FX pair D1 close | at the close of decision D1 bar *t* |
| Composite slope gate (sign of BFCI(t) − BFCI(t−1)) | external macro daily | with the +1-FX-D1-bar macro lag of §9 — i.e. BFCI values dated through US trading day *d* are first usable on the FX D1 bar opening at/after 21:00 UTC on day *d+1* |
| Macro data-staleness guard: no new entries if the newest macro observation behind BFCI is > 10 calendar days old (covers US holiday stretches and feed outages; 10 days tolerates the longest normal holiday clusters) | ingest metadata | at decision time |
| Session/news filters | none | N/A — no calendar data exists and none is claimed |

The CSV's "regime gating suppresses trades in chop via slope and price filters" is exactly the slope + SMA gates above; no additional chop filter is specified or added.

## 9. Causality audit

| Rule | Inputs fully known at | Confirmation lag |
|---|---|---|
| Log returns, z-scores (W=252), weights, BFCI_raw, EMA10 of BFCI | US trading day *d*'s close (≈20:00–21:00 UTC, DST-dependent) | **Macro availability lag: declared conservatively as one full FX D1 bar** — macro data through US day *d* may only inform FX D1 decisions on bars opening at/after 21:00 UTC on day *d+1* (mechanically: shift the macro frame forward one extra day before `merge_asof(..., direction="backward")` onto the FX D1 index). This absorbs the DST ambiguity around whether the US close coincides with the FX 21:00 UTC bar open. |
| Cross triggers (§4.1, §5.1) and slope gate | close of FX D1 bar *t*, using lagged BFCI | one D1 bar vs the macro observation, as above; cross detection itself uses only t and t−1 — no lag beyond that |
| SMA200 price gate | close of FX D1 bar *t* | none (rolling, backward-looking) |
| ATR14 stop/trail geometry | close of FX D1 bar *t* | none |
| Entry fill | open of bar t+1 (F1/F2) | engine convention |
| Trailing exit | updates at each D1 close using completed ATR (F9); H1 resolution checks | engine convention |
| Swing / ZigZag / pivot / fractal rules | **none used anywhere in this strategy** | N/A — no confirmation-lag exposure of that class |

Non-trading-day alignment: FX trades 24/5, US markets ~252 days/yr with holidays. Mechanical rule: forward-fill each macro series onto the FX D1 calendar (last available observation), subject to the +1-day availability shift and the 10-day staleness guard. No macro value is ever interpolated or back-filled.

## 10. Ambiguities resolved

| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | All five thresholds ("long threshold / always-long floor / exit lines") are Pine script inputs with no values in the CSV | **Declared: long threshold +0.50; always-long floor +1.00; long-exit = short-exit line 0.00; short threshold −0.50** (BFCI is a weighted mean of ±3-clipped z-scores, so these sit in the plausible mid-range). Reconstructed-from-script conventions; flagged in DATA-GAP as values to validate against the published script's defaults | Leaving them to the implementer (auto-fail review); treating the strategy as unimplementable (spec still has value once defaults are extracted — the DATA-GAP records both) |
| 2 | "Optionally winsorized" z-scores | Winsorize ON: clip z_i to [−3, +3] — dampens single-series spikes (VIX 2020-style prints), fewer whipsaw signals | No winsorization (more extreme composites, more crosses, more trades) |
| 3 | CREDIT / SLOPE / LIQ symbols undefined in pseudocode | CREDIT = HYG/LQD ratio; SLOPE = first difference of (US10Y−US02Y); LIQ = BIL/SPY ratio — the economically standard constructions matching the stated sign flips | SLOPE as logret of the spread (undefined when spread ≤ 0 — arithmetically inadmissible); LIQ as raw BIL return (ignores the "/SPY liquidity" phrase) |
| 4 | Inverse-vol weights: vol of what? | σ_i computed on **raw log returns** (W=252) — this differentiates components (VIX far more volatile than BIL), which is the point of inverse-vol weighting | σ on the z-scores (all ≈ 1 by construction → weights ≈ uniform → the "inverse-vol" feature silently deleted) |
| 5 | "Composite already above always-long floor" reads as a continuous state | Read as a **cross event** (BFCI(t−1) ≤ +1.00 < BFCI(t)): a continuous reading re-emits a market intent on every bar while flat above the floor, re-entering immediately after every stop-out — more trades, worse churn | Continuous re-emission (contract has no supersede/cancel; F12 would silently drop most duplicates while a position is open, making behaviour engine-artefact-dependent) |
| 6 | Source defines a long-side floor but no short-side floor | Shorts get only the ±0.50 threshold cross (source asymmetry preserved: the strategy is risk-on-biased; the floor is a long re-entry concession and a short stress-guard only) | Inventing a symmetric always-short floor (adds trades the author never specified) |
| 7 | Source risk sizing measured from entry; script uses %-of-equity and its own commission/slippage | Stop/TP geometry anchored to **decision-bar close** (knowable at emission); sizing out of scope (System 1 never sizes); **F10 cost model applies** (1.0-pip spread + 0.5-pip entry slippage, commission 0) in place of the script's 0.05% commission + 5-tick slippage | Fill-anchored risk (inexpressible for market orders under contract v2, not merely less conservative); importing the script's cost model (F10 is inviolable) |
| 8 | Signal-based exits inexpressible (no close intent; ExitLeg needs declarable absolute levels) | Map the regime exit to a single 3.0×ATR(14, D1) trailing leg; keep 2.0×ATR static initial stop | Fixed-pip or time exits (not the strategy); emitting opposite orders to "close" (no such mechanism; would open a second position if F12 were ever raised) |
| 9 | "H4 or D1 execution" | **D1 execution** — matches daily macro data, avoids pretending intraday precision exists in a daily composite, fewer trades | H4 execution (4× more decisions off the same daily information; invites over-trading a daily signal) |
| 10 | Z-score window "win" unspecified | W = 252 trading days (≈1y), min_periods 126 — slow regime measure, fewest regime flips | W = 20 (inventory default; far too reactive for a "regime" claim, many more crosses/trades); W = 63 |

## 11. Expected behaviour

- **Trade frequency:** very low. BFCI is EMA-10-smoothed on daily data; crosses of ±0.50 (let alone ±1.00) are episodic — roughly **1–4 entries per pair per year**, fewer once the SMA200 and slope gates bite. Over a 10-year H1-resolved backtest expect ~15–40 trades per pair, with long flat stretches when the composite hugs zero.
- **Gate risk:** trade count is the dominant failure mode — per-cell counts will flirt with `low_confidence` in every fold, and a pooled OOS window can plausibly contain single-digit trades. Second failure mode: whipsaw in 2011/2015-style choppy macro tapes where the composite oscillates around ±0.5 and the 3×ATR trail donates back open profit. Third: the strategy's real edge claim is cross-asset confirmation; if that adds nothing over the SMA200 gate alone, it is a slow trend-follower with extra data dependencies.
- **Conviction check:** EXPERIMENTAL is justified — the author makes no performance claims, the thresholds are unvalidated reconstructions, and the signal-exit semantics are approximated. Even with perfect data this strategy should be treated as a hypothesis about regime persistence, not a demonstrated edge. The nine-feed data cost (DATA-GAP) is disproportionate to the evidence unless the initiative wants the macro infrastructure for its own sake.
