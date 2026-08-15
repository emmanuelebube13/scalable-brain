# SPEC-usd_carry_basket

**Source:** row 5 of forex_swing_strategies.csv (CSV line 6) · https://quantpedia.com/strategies/dollar-carry-trade
**Conviction (author's):** HIGHLY_RECOMMENDED

**BLOCKING DEPENDENCY:** This strategy's signal is an interest-rate differential. No rate
data exists in the DB (`DATA_AVAILABILITY.md`: "Non-price data — none of it exists").
The full mechanics are specified below so implementation is mechanical once the data lands;
until then this strategy can emit **zero orders**. See `DATA-GAP-usd_carry_basket.md`.

## 1. Hypothesis

The US dollar earns a countercyclical currency risk premium: when the US 3-month interest
rate exceeds the average 3-month rate of a developed-currency basket, holding USD (short
the basket) harvests positive carry plus the tendency of high-rate USD states to coincide
with dollar appreciation; symmetrically, when foreign rates are higher on average, being
short USD and long the basket collects the foreign premium. The edge should persist because
it is compensation for bearing countercyclical risk — currencies with high interest rates
tend to depreciate in bad times, so investors demand a premium for holding them — as
established academically by Lustig, Roussanov & Verdelhan, "Countercyclical Currency Risk
Premia". Quantpedia rates confidence "Strong"; the documented 1983–2009 backtest reports
5.6% p.a., volatility 8.53%, Sharpe 0.66, max drawdown −31.72%, and the strategy is only
loosely correlated with conventional cross-currency carry, making it additive to an FX book.

## 2. Scope

- primary_granularity: **D1** — the signal cadence is monthly (one rebalance decision per
  calendar month). D1 is chosen as the order-emission frame because (a) a month is 19–23
  trading days, cleanly expressible as a D1 time-exit (~21 bars), whereas W1 (4–5 bars/month)
  cannot represent "hold one month" without 20–25% timing error, and (b) the W1 series in the
  DB is stale by ~8 weeks (DATA_AVAILABILITY.md), so W1 decisions would be unverifiable.
  D1 decisions are resolved on H1 bars per Contract Part D.
- context_granularities: [] — none. The signal is an external rate differential, not a
  higher-timeframe price pattern. No price context frame is needed.
- simulate_on: H1
- pairs_requested (verbatim from CSV): USD vs EUR | AUD | CAD | DKK | JPY | NZD | NOK | SEK | CHF | GBP (equal-weighted basket)
- pairs_available: EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD (5 of 10)
- pairs_pending (Wave 1 additions, may be incomplete when Wave 2 runs — harness skips
  insufficient history): NZD_USD, USD_CHF
- pairs_missing (no Wave-1 plan exists): USD_DKK, USD_NOK, USD_SEK → **DATA-GAP note**
  (combined with the rates gap in `DATA-GAP-usd_carry_basket.md`)

The basket is traded as USD-pair instruments: long-USD signals are expressed as SELL
EUR_USD / GBP_USD / AUD_USD (/NZD_USD) and BUY USD_JPY / USD_CAD (/USD_CHF).

## 3. Indicators

The signal is a **rate differential, not a price indicator**. Required series:

| Indicator | Params | Source |
|---|---|---|
| US 3-month Treasury rate | daily, annualised %, secondary-market or constant-maturity | **NOT IN DB** — external (e.g. FRED `DGS3MO` / `DTB3`) |
| 3-month interbank/T-bill rate per basket currency | EUR, GBP, JPY, AUD, CAD (+ NZD, CHF pending; DKK, NOK, SEK for the full basket) | **NOT IN DB** — external (e.g. OECD, ECB/BoE/BoJ/RBA/BoC national sources, or 3-month FX forward points converted to implied yield) |
| Average Forward Discount (AFD) | `mean over available basket currencies of foreign 3-month rate` (source: "average 3-month foreign rate can substitute" for the forward discount) | derived from the two series above |
| ATR | period 14, on D1, per traded pair | `indicators.atr(high, low, close, 14)` — exists; used ONLY for the contract-required catastrophic stop, never for the signal |

**No rate series exists in the DB.** No price-only proxy is substituted for the signal;
candidate proxies are discussed and rejected in §10 and in the DATA-GAP document.
ATR is the only indicator computed from DB data.

## 4. Entry — long

"Long" here means **long USD / short the basket** (the CSV's `entry_logic_long`).

At the monthly decision bar (§8):

1. Let `r_US` = most recent US 3-month rate observation whose publication date is at least
   **2 business days before** the decision bar's close (publication-lag rule, §9).
2. For each basket currency `c` with a tradable, data-sufficient USD pair, let `r_c` = the
   most recent foreign 3-month rate observation under the same lag rule.
3. Compute `AFD = mean(r_c)` over exactly the currencies that will be traded this month,
   `N(t)` of them (renormalised universe, §10 row 3).
4. Condition: `r_US > AFD`. If false, emit nothing on this leg.
5. If true, emit one `OrderIntent` per available pair `p`:
   - `direction = +1` for USD-base pairs (USD_JPY, USD_CAD, USD_CHF) — buying the pair = long USD
   - `direction = -1` for USD-quote pairs (EUR_USD, GBP_USD, AUD_USD, NZD_USD) — selling the pair = long USD
6. Every leg carries the same `decision_bar`, stop, exit, and `size_fraction = 1 / N(t)`.

- entry type: `market` (fills at open of bar t+1 per F1/F2 — conservative, one bar of drift)
- entry level: n/a (market)
- expires_after_bars: n/a for market entries (not GTC-relevant; market orders fill at t+1 open or not at all)
- size_fraction formula: `1 / N(t)`, where `N(t)` = number of basket pairs passing the
  data-sufficiency gate at decision bar t (5 initially, 7 after Wave 1 backfills complete).
  `size_fraction` expresses the equal-weight basket allocation in units of R, per the
  contract ("relative allocation across legs of one idea"); it is not position sizing.

## 5. Entry — short

Mirror of §4 ("short USD / long the basket"):

1.–3. Identical rate observations and AFD computation as §4 steps 1–3.
4. Condition: `r_US < AFD`. If `r_US == AFD`, emit nothing (no trade this month; the source
   treats the differential as strictly signed and equality is measure-zero, but the flat
   case is specified here so the implementer never has to decide).
5. If true, emit one `OrderIntent` per available pair with **reversed** direction:
   - `direction = -1` for USD-base pairs (short the pair = short USD)
   - `direction = +1` for USD-quote pairs (long the pair = short USD)
6. Same decision bar, stop, exit, and `size_fraction = 1 / N(t)` as §4.

- entry type: `market`
- entry level: n/a
- expires_after_bars: n/a
- size_fraction: `1 / N(t)`

## 6. Stop

The source specifies **no stop-loss** — it holds one month and rebalances, with risk managed
by equal weights and monthly re-evaluation (documented max DD −31.72% over 1983–2009 arose
under that regime). The contract REQUIRES a `StopRule` on every `OrderIntent`.

- initial stop (conservative catastrophic stop), **anchored to a decision-bar-knowable
  price** (fleet rule: with market entries the fill is unknowable at emission, so
  `StopRule.price` must be declarable from the decision bar alone):
  `stop.price = close(decision_bar) − 3.0 × ATR(D1, 14)` for `direction=+1`;
  `stop.price = close(decision_bar) + 3.0 × ATR(D1, 14)` for `direction=−1`;
  where `close(decision_bar)` is the close of the month-end D1 decision bar and ATR(14) is
  computed on the D1 frame from bars closed at or before the decision bar. Both inputs are
  fully known at the decision bar's close, so `StopRule.price` is an absolute float at
  `OrderIntent` creation, as the contract requires. The actual fill (next bar's open per
  F1/F2) will differ from the anchor; realised R therefore differs from declared R whenever
  the market moves between decision close and fill — F3/F6 handle the fill mechanics, the
  anchor stays declarable (§10 row 7). At 3× daily ATR, ≈ 3 typical days of range must be
  traversed adversely before the stop engages; it should bind only in gap/crisis scenarios,
  approximating the source's stop-free monthly hold while satisfying the contract. (F6
  gap-through-stop fills at the open and can exceed 1R — accepted and reported, matching
  the engine's pessimistic convention.) The tension between the stop-free source and the
  required StopRule is recorded in §10 row 1.
- move_to_breakeven_on: none
- trail: none

## 7. Exit legs

The exit is **time-based** (monthly hold + rebalance). One leg per order, fraction 1.0:

| Label | Fraction | Kind | Level formula |
|---|---|---|---|
| MONTH_END | 1.0 | `time` | `bars = 21` (≈ one calendar month of D1 trading days, measured on the primary D1 frame; engine resolves on H1 within those bars) |

Fractions sum to 1.0 per pair-order. There is deliberately only one leg: the source holds
the full position for the whole month; scale-outs would deviate from the documented
strategy. Month-length drift (19–23 trading days) is handled conservatively in §10 row 5.

## 8. Filters

1. **Monthly cadence gate:** orders may be emitted only at the decision bar = the **last
   completed D1 bar of the calendar month**. A D1 bar is stamped at its open (21:00 UTC);
   the final D1 bar of month M is the bar whose open date is the last trading day of M.
   That bar is fully knowable at its close (21:00 UTC on the last trading day of M, or the
   first minutes of the next bar). All non-month-end D1 bars emit nothing.
2. **Rate-publication lag gate:** both `r_US` and every `r_c` must come from observations
   published at least **2 business days** before the decision bar's close (see §9). If the
   required rate history is unavailable at that lagged horizon for any traded currency,
   that currency's pair is dropped from the basket for that month (and `N(t)` shrinks);
   if `r_US` itself is unavailable, emit nothing that month.
3. **Pair-universe gate:** a pair enters the month's basket only if (a) it is in
   `pairs_available` or a completed Wave-1 addition with sufficient history per the harness
   rule (harness skips, never fails), and (b) its currency's 3-month rate series exists at
   the lagged horizon. DKK/NOK/SEK are excluded unconditionally (no pairs, no Wave-1 plan).
4. **No re-entry within the month:** at most one decision per month per pair. F12
   (max 1 concurrent position per strategy/pair/granularity) additionally prevents stacking;
   because the prior month's position exits on its 21-bar time leg at approximately the next
   decision bar, a sign flip becomes effective at the following rebalance (§10 row 4).

## 9. Causality audit

| Rule | Inputs | Fully known at |
|---|---|---|
| Monthly decision bar identification (§8.1) | Calendar of trading days; bar timestamps stamped at open | Close of the last D1 bar of month M (21:00 UTC). Whether a D1 bar is the month's last is knowable **at its open** from the calendar (weekend/holiday gaps handled by taking the last bar that actually exists in the data). |
| US 3-month rate `r_US` (§4.1) | Published daily rate series | Assumed publication lag: observations are used only if dated ≥ **2 business days** before the decision bar's close. Rationale: T-bill/constant-maturity series publish next business day; the extra day is a conservative buffer for foreign series with slower publication (some national series publish with 1–2 day lag or are revised). Using month-end rates observed *after* month-end would be look-ahead and is prohibited. |
| Foreign rates `r_c`, AFD (§4.2–4.3) | Published daily/monthly foreign series | Same ≥2-business-day lag rule, applied per series. The AFD is computable at the decision bar's close using only lagged observations. |
| Stop anchor and ATR(14) distance (§6) | Decision-bar D1 close; D1 OHLC for ATR | Close of the decision bar. `stop.price` is anchored to `close(decision_bar)` ± `3.0 × ATR(D1,14)`; both inputs use only bars ≤ the decision bar (standard trailing computation, no centred windows), so the stop is an absolute declarable float at `OrderIntent` emission — the unknowable next-bar fill is never referenced. |
| Market entry fill (§4/§5) | — | Order eligible from bar t+1 (F1); fills at t+1 open + adverse slippage (F2, F10). The strategy never sees t+1 data. |
| Catastrophic stop checks (§6) | H1 bars during holding period | Each H1 bar as it closes; the declared (decision-close-anchored) stop level is evaluated intrabar per F5/F6 using only bars ≥ t+1. |
| Time exit, 21 D1 bars (§7) | Bar count on the D1 frame | The exit bar is the 21st D1 bar after entry; knowable only as that bar closes. Resolved on H1 bars within the span per Contract Part D. |
| Rebalance / sign-flip (§6 exit logic, §8.4) | Next month's lagged rates | Close of the next month's decision bar. A flip cannot be acted on earlier because the strategy is declarative and cannot observe its own open position — conservative by construction (§10 row 4). |

No indicator in this strategy uses centred windows, future-shifted series, or swing points;
the banned `detect_swing_points` is not used.

## 10. Ambiguities resolved

| # | Ambiguity in the source | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | Source specifies **no stop-loss** (monthly hold, rebalance, risk managed by weights); contract REQUIRES a `StopRule` on every order | Catastrophic stop at `3.0 × ATR(D1,14)` — wide enough to bind only in gap/crisis scenarios, preserving the source's economic behaviour while bounding worst-case loss per leg. Documented −31.72% max DD in the source was achieved with no stop, so any stop is a deviation; the widest defensible one minimises it. | (a) No stop — violates the contract, impossible. (b) Tight stop (e.g. 1×ATR) — converts a monthly macro position into a multi-day trade, measures something that is not the strategy. |
| 2 | Signal is defined on **forward discounts** ("average 3-month foreign rate can substitute") — neither forwards nor rates exist in the DB | Use the source's own sanctioned substitute: average 3-month foreign rate vs US 3-month T-bill, from external series (per DATA-GAP). Under covered interest parity the 3-month forward discount ≈ the rate differential, so the substitute is economically faithful — but it still requires data we do not have. | Any price-derived proxy (momentum, trend, realised-return differential) as a silent stand-in — it measures a different factor (trend, not carry). Listed here only to be explicitly refused; see DATA-GAP §Impact. |
| 3 | Equal weights across a **10-currency basket**, but only 5 pairs exist (7 after Wave 1); contract forbids position sizing and defaults to 1 position per pair | Express the basket as one OrderIntent per pair with `size_fraction = 1/N(t)`, **renormalised over the available, data-sufficient universe**, and recompute AFD over that same universe each month so the signal matches the instruments actually traded. (Per-trade r-multiples are scale-invariant to `size_fraction`; the choice affects only pooled-equity reporting.) | (a) Fixed 1/10 weights with the missing 5 treated as uninvested cash — misstates capital deployment in pooled r-multiple reports and cannot be repaired until DKK/NOK/SEK exist. (b) Skip the strategy until all 10 pairs exist — DKK/NOK/SEK have no Wave-1 plan at all; indefinite deferral. (c) Trading the 5 pairs at full 1.0 size_fraction each — 5× the intended per-leg risk. |
| 4 | Exit logic says "reverse sign or flatten when differential flips" — but v2 strategies are declarative, cannot see their own open positions, and F12 allows only 1 concurrent position per pair | A flip is acted on only at the **next monthly decision bar**; the current month's position runs to its 21-bar time exit (or catastrophic stop). Since the time exit (21 D1 bars) approximately coincides with the next decision bar, the practical lag is ≤ a few days; the engine's F12 rule resolves any residual overlap by refusing the new order, which is the conservative outcome (fewer trades). | (a) Immediate reversal mid-month — not expressible in the contract (no close-existing-position intent) and would require position awareness, which the declarative interface deliberately forbids. (b) Shorter time exit so flips act sooner — deviates from the documented one-month hold. |
| 5 | "Hold one month" on a bar-count contract: calendar months have 19–23 D1 bars | Fixed `bars = 21` (long-run average trading days/month). In short months the position is held a few days past month-end; in long months it exits a few days early. Symmetric, mechanical, no discretion. | (a) Calendar-date exit ("close on last day of month") — not an ExitLeg kind; would require bespoke engine support. (b) W1 frame with bars=4–5 — 12–25% timing error per cycle and W1 data is stale (DATA_AVAILABILITY.md). |
| 6 | Rebalance timing vs data knowledge: when is "the month's last close" and month-end rate known? | Decision at the close of the last D1 bar of the month using rates published ≥2 business days earlier; fill at next bar's open (first H1 of the new month) plus costs. Every input is stale by construction. | Using month-end rates published after month-end (look-ahead — the naive pandas `resample('ME').last().ffill()` pattern in the CSV's pseudocode does exactly this if read literally); zero-lag rate observations. |
| 7 | Stop geometry needs an anchor price, but with `market` entries the fill (bar t+1 open) is unknowable when the `OrderIntent` is emitted and `StopRule.price` must be an absolute float | Anchor the 3×ATR stop to the **decision bar's close** — fully knowable at emission (fleet rule). Consequence: the engine's declared R unit (`|entry_fill − stop.price|`) differs from the intended `3.0 × ATR` distance whenever the fill moves from the decision close; over a month-end weekend/holiday gap this can be material, so **realised R ≠ declared R** is expected and must be stated in reports rather than smoothed over. F3/F6 resolve the fill pessimistically (gap-through → open); the anchor itself never depends on the unknowable fill. | (a) Anchoring to `entry_fill` — undeclarable at emission, contract-impossible. (b) Using a pending limit at the decision close to make anchor = fill — replaces a guaranteed month-start entry with a conditional one (fewer trades but a different strategy: it silently skips months where price never retraces), and the source's rebalance is unconditional. |

## 11. Expected behaviour

- **Trade frequency:** one basket rebalance per month → up to 12 decision events/year.
  On the 5 available pairs: ≈ **60 trades/year** (5 pairs × 12 months, one OrderIntent per
  pair per month; fewer only in months where `r_US == AFD` or rate data is missing, both
  rare). ≈ 84/year once NZD_USD and USD_CHF backfills complete. Per (strategy, pair,
  granularity) cell: ~12 trades/year.
- **What would make this strategy fail the gates:**
  1. **Thin per-cell counts under walk-forward.** A 6-month OOS fold contains ~6 trades per
     pair. Expect `low_confidence` flags and possible failure of minimum-trade/OOS-duration
     gates on per-cell verdicts even if the pooled result is sound — this is arithmetic, not
     a verdict on the edge (cf. the W1 statistical warning in the contract, which applies
     here in milder form).
  2. **Cost drag relative to holding-period edge.** 1.5 pips entry cost × ~60 entries/year;
     with a 3×ATR risk unit, a month's carry differential (tens of bps annualised ÷ 12)
     produces small r-multiples whose mean must clear costs — Sharpe 0.66 strategies can
     fail gates after realistic costs.
  3. **Concentration:** all 5 legs are the same USD-directional bet; a pooled verdict rests
     on one macro factor, and 1983–2009 regime dependence (Volcker-era rate levels,
     pre-2008 carry regimes) may not survive post-2009 folds. Reduced basket (5 vs 10
     currencies) weakens the diversification that produced the published Sharpe.
  4. **Blocking:** with no rate data, the strategy emits zero orders and cannot be gated at
     all — the DATA-GAP is the primary obstacle.
- **Is HIGHLY_RECOMMENDED justified?** The academic backing (Lustig–Roussanov–Verdelhan),
  Quantpedia "Strong" confidence, and the documented 1983–2009 result (5.6% p.a., Sharpe
  0.66) support the author's conviction **as a literature claim**. But the conviction is
  conditional on data this system does not have: every number cited was produced with actual
  forward discounts/rates and a full 10-currency basket. Until rate series land, the
  implementable artefact is a specification, not a strategy; the rating should be read as
  "high-conviction candidate, blocked on DATA-GAP-usd_carry_basket". A backtest run on a
  price-momentum stand-in would measure a different factor and must not inherit this rating.
