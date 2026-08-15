# SPEC-currency_momentum_factor

**Source:** row 43 of forex_swing_strategies.csv (CSV line 44) · https://quantpedia.com/strategies/currency-momentum-factor
**Conviction (author's):** MODERATE

This is a cross-sectional basket/factor strategy. Its core signal — trailing 12-month price
return per currency vs USD — is **computable from OHLCV alone**, so unlike
`usd_carry_basket` it is NOT data-blocked. The binding constraints are (a) a degenerate
universe on today's 5 live pairs and (b) the contract-required StopRule where the source
specifies none. Both are resolved below; see also `DATA-GAP-currency_momentum_factor.md`
for the universe-thinness note (non-blocking).

## 1. Hypothesis

Currencies that have appreciated against the US dollar over the trailing twelve months tend
to keep appreciating over the following month, and currencies that have depreciated tend to
keep falling, so a monthly-rebalanced long-short portfolio of the extreme terciles earns a
persistent cross-sectional spread. The edge should persist because FX trends are driven by
slow-moving macro forces — monetary-policy cycles, capital-flow reallocation, and
underreaction by investors who anchor on outdated fair-value estimates — and because central
banks smooth rather than jump policy, so rate-differential regimes (which pull exchange
rates) persist for quarters; trend-following is compensation for bearing crash risk in
sudden regime reversals. This is one of the best-documented anomalies in the currency
literature (Menkhoff, Sarno, Schmeling & Schrimpf: significant cross-sectional spread up to
~10% p.a., 1976–2010); Quantpedia documents 1989–2009 indicative 7.61% p.a., volatility
10.22%, Sharpe 0.30, max drawdown −45.87% — but Quantpedia's own out-of-sample check is
slightly negative, so the anomaly may be attenuating (crowding, lower macro volatility);
see §11.

## 2. Scope

- primary_granularity: **D1** — the signal is a 252-D1-bar return and the cadence is
  monthly (one rebalance per calendar month). D1 is the order-emission frame because a
  month is 19–23 trading days, cleanly expressible as a ~21-bar D1 time exit, whereas W1
  (4–5 bars/month) cannot represent a one-month hold without 20–25% timing error, and the
  W1 series in the DB is stale ~8 weeks (DATA_AVAILABILITY.md). D1 decisions are resolved
  on H1 bars per Contract Part D.
- context_granularities: [] — none. The signal is computed on the primary D1 frame itself;
  no higher-timeframe price context is needed.
- simulate_on: H1
- pairs_requested (verbatim from CSV): "Universe of 10-20 currencies vs USD (majors + liquid minors)"
- pairs_available (live today): EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD → currencies
  EUR, GBP, JPY, AUD, CAD (5 non-USD currencies)
- pairs_pending (Wave-1 additions; harness skips insufficient history rather than failing):
  NZD_USD, USD_CHF → adds NZD, CHF → 7 non-USD currencies. (The other Wave-1 pairs —
  GBP_JPY, EUR_JPY, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD — are crosses and add no new
  currency-vs-USD series; they are irrelevant to this strategy.)
- pairs_missing (no Wave-1 plan): USD_DKK, USD_NOK, USD_SEK and any other USD pairs needed
  to reach the documented 10–20 currency universe → **DATA-GAP note** (non-blocking; the
  strategy is implementable at reduced coverage, see `DATA-GAP-currency_momentum_factor.md`).

**Universe degeneracy warning.** The documented rule is "long top-3 / short bottom-3 of the
universe". With the 5 live pairs there are only **5** non-USD currencies, so top-3 (ranks
1–3) and bottom-3 (ranks 3–5) overlap at the median currency: the strategy degenerates to
long-2 / short-2 with the median currency flat, and ~83% of the universe is always
positioned. Only after the Wave-1 additions land (7 currencies) does top-3/bottom-3 become
non-degenerate (ranks 1–3 long, 4 flat, 5–7 short). This spec keeps the rule **verbatim**
(no retuning); the degeneracy is recorded in §10 row 2 and priced into §11.

## 3. Indicators

| Indicator | Params | Source |
|---|---|---|
| Currency 12-month spot return vs USD, `mom_c(t)` | per currency `c`: for USD-quote pairs (EUR_USD, GBP_USD, AUD_USD, NZD_USD) `mom_c(t) = close_p(t) / close_p(t−252) − 1`; for USD-base pairs (USD_JPY, USD_CAD, USD_CHF) `mom_c(t) = close_p(t−252) / close_p(t) − 1`; computed on the D1 frame using only bars closed at or before `t`; window 252 D1 bars (the CSV pseudocode's `pct_change(252)`) | private derivation from D1 OHLC (specify here per inventory rules; not added to `indicators.py`). Equivalent to the inventory-free ratio of two closes; no rolling window beyond the two endpoints. |
| Cross-sectional rank of `mom_c` | rank over the month's available universe `U(t)`, descending (rank 1 = highest momentum); exact ties broken by universe declaration order (EUR, GBP, JPY, AUD, CAD, NZD, CHF) — earlier-listed currency receives the better rank | private; mechanical sort, fully specified here |
| ATR | period 14, on D1, per traded pair | `indicators.atr(high, low, close, 14)` — exists; used ONLY for the contract-required catastrophic stop, never for the signal |

No rates, forwards, COT, VIX, DXY, or other non-price data are used. The source's "total
return" is approximated by **spot return** (no carry/roll component) — a deliberate,
flagged deviation recorded in §10 row 3 and the DATA-GAP. The banned
`detect_swing_points` is not used; no swing/pivot/fractal logic exists in this strategy.

## 4. Entry — long

"Long" = long the top-3 currencies vs USD (the CSV's `entry_logic_long`).

At the monthly decision bar (§8.1):

1. Compute `mom_c(t)` for every currency whose pair passes the data-sufficiency gate
   (§8.3); call the resulting set `U(t)`, the month's tradeable universe.
2. Rank `mom_c` descending over `U(t)`; `top3 = {c : rank(c) ≤ 3}`.
3. For each currency `c ∈ top3`, compute its net weight
   `w_c = (1/3)·1[c ∈ top3] − (1/3)·1[c ∈ bottom3]` where `bottom3 = {c : rank(c) ≥ |U(t)| − 2}`.
   On a universe of 6+ currencies `w_c = 1/3` here; on the degenerate 5-currency universe
   the median currency has `w_c = 0` (it is simultaneously rank-3-long and rank-3-short and
   the legs cancel) and **no order is emitted for its pair**.
4. For each `c` with `w_c > 0`, emit one `OrderIntent` on pair `p(c)`:
   - `direction = +1` for USD-quote pairs (EUR_USD, GBP_USD, AUD_USD, NZD_USD) — buying the
     pair = long the currency
   - `direction = −1` for USD-base pairs (USD_JPY, USD_CAD, USD_CHF) — selling the pair =
     long the currency
   - `size_fraction = |w_c| = 1/3`
5. Every leg carries the same `decision_bar`, stop (§6), and exit (§7).

- entry type: `market` (fills at open of bar t+1 per F1/F2 — conservative, one bar of drift)
- entry level: n/a (market)
- expires_after_bars: n/a for market entries (a market order fills at t+1 open or not at all)
- size_fraction formula: `|w_c|`, exactly `1/3` per active leg. `size_fraction` expresses
  the equal-weight tercile allocation in units of R per the contract ("relative allocation
  across legs of one idea"); it is not position sizing. Weights are NOT renormalised over
  the active legs — the source fixes 1/3 per tercile slot and the flat median slot is simply
  uninvested (§10 row 6). Total deployed fraction per month = (#active legs)/3: 4/3 on the
  live 5-pair universe (2 long + 2 short), 2.0 on the 7-pair universe.

## 5. Entry — short

Mirror of §4 ("short the bottom-3 currencies vs USD"):

1.–2. Identical `mom_c` and ranking as §4 steps 1–2; `bottom3 = {c : rank(c) ≥ |U(t)| − 2}`.
3. Net weight `w_c` as §4 step 3; on the degenerate 5-currency universe the median currency
   nets to zero and emits nothing (same pair as §4, never double-counted — the netting is
   computed once per currency, not once per side).
4. For each `c` with `w_c < 0`, emit one `OrderIntent` on pair `p(c)` with **reversed**
   direction relative to §4:
   - `direction = −1` for USD-quote pairs (short the pair = short the currency)
   - `direction = +1` for USD-base pairs (long the pair = short the currency)
   - `size_fraction = |w_c| = 1/3`
5. Same decision bar, stop, and exit as §4.

- entry type: `market`
- entry level: n/a
- expires_after_bars: n/a
- size_fraction: `1/3` per active leg

## 6. Stop

The source specifies **no per-trade stop** ("no per-trade stop (portfolio factor strategy)";
risk managed by equal weights, monthly re-evaluation, and diversification; documented max DD
−45.87% arose under that regime). The contract REQUIRES a `StopRule` on every `OrderIntent`.

- initial stop (conservative catastrophic stop, identical pattern to
  `SPEC-usd_carry_basket.md` §6), **anchored to a decision-bar-knowable price** (fleet rule:
  with market entries the fill is unknowable at emission, so `StopRule.price` must be
  declarable from the decision bar alone):
  `stop.price = close(decision_bar) − 3.0 × ATR(D1, 14)` for `direction=+1`;
  `stop.price = close(decision_bar) + 3.0 × ATR(D1, 14)` for `direction=−1`;
  where `close(decision_bar)` is the close of the month-end D1 decision bar and ATR(14) is
  computed on the D1 frame from bars closed at or before the decision bar. Both inputs are
  fully known at the decision bar's close, so `StopRule.price` is an absolute float at
  `OrderIntent` creation. The actual fill (next bar's open per F1/F2) will differ from the
  anchor; **realised R ≠ declared R** whenever the market moves between decision close and
  fill (month-end weekend gaps make this material) — F3/F6 handle the fill mechanics, the
  anchor stays declarable (§10 row 7). At 3× daily ATR, ≈ 3 typical days of range must be
  traversed adversely before the stop engages; it should bind only in gap/crisis scenarios,
  approximating the source's stop-free monthly hold while bounding worst-case loss per leg
  (F6 gap-through-stop fills at the open and can exceed 1R — accepted and reported). The
  tension between the stop-free source and the required StopRule is recorded in §10 row 1.
- move_to_breakeven_on: none
- trail: none

## 7. Exit legs

The exit is **time-based** (monthly hold, then rotate at the next rebalance). One leg per
order, fraction 1.0:

| Label | Fraction | Kind | Level formula |
|---|---|---|---|
| MONTH_END | 1.0 | `time` | `bars = 21` (≈ one calendar month of D1 trading days, measured on the primary D1 frame; engine resolves on H1 within those bars) |

Fractions sum to 1.0 per pair-order. There is deliberately only one leg: the source holds
the full position for the whole month and rotates; scale-outs would deviate from the
documented strategy. Month-length drift (19–23 trading days) is handled conservatively in
§10 row 5. Rotation happens because next month's decision bar emits the new basket; the
current month's position exits on its 21-bar time leg at approximately the next decision
bar, and any residual overlap is resolved by F12 (§10 row 4).

## 8. Filters

1. **Monthly cadence gate:** orders may be emitted only at the decision bar = the **last
   completed D1 bar of the calendar month**. D1 bars are stamped at their open (21:00 UTC);
   the final D1 bar of month M is the bar whose open date is the last trading day of M. That
   bar is fully knowable at its close (21:00 UTC on the last trading day of M). All
   non-month-end D1 bars emit nothing. Evaluated on the primary D1 frame; knowable at the
   decision bar's close (whether a bar is the month's last is knowable at its **open** from
   the trading calendar, taking the last bar that actually exists in the data).
2. **Data-sufficiency gate:** a pair enters `U(t)` only if it has at least **253 closed D1
   bars** at the decision bar (bars `t−252 … t` inclusive), and it is in `pairs_available`
   or is a completed Wave-1 addition per the harness rule (harness skips pairs with
   insufficient history, never fails). The Wave-1 cross pairs (GBP_JPY etc.) are excluded
   unconditionally — they add no new currency vs USD.
3. **No re-entry within the month:** at most one decision per month per pair. F12 (max 1
   concurrent position per strategy/pair/granularity) additionally prevents stacking.
4. **No trend/session/volatility/news filters exist in the source** and none are added.
5. **Out of scope (recorded, not implemented):** the source's "cash not used as margin
   invested at overnight rates". This is a sizing/margin-yield detail of a capital-weighted
   portfolio; the r-multiple backtest does no sizing and has no margin, so the overnight-rate
   component contributes nothing measurable and no rate data is ingested for it. Recorded in
   §10 row 8 and the DATA-GAP.

## 9. Causality audit

| Rule | Inputs | Fully known at |
|---|---|---|
| Monthly decision bar identification (§8.1) | Trading calendar; D1 bar timestamps stamped at open | Close of the last D1 bar of month M (21:00 UTC). Whether a bar is the month's last is knowable at its open from the calendar. |
| Currency momentum `mom_c(t)` (§3, §4.1) | `close(t)` and `close(t−252)` on the pair's D1 frame | Close of the decision bar `t`. Both endpoints are closed bars (`t−252` long closed; `t` is the decision bar itself). Standard trailing computation — no centred windows, no future data. |
| Cross-sectional ranking, top-3/bottom-3, net weights (§4.2–4.3, §5) | All `mom_c(t)` values, same decision bar | Close of the decision bar `t`. Ranking is a pure sort of quantities already known at `t`. No cross-pair look-ahead is possible: every pair's inputs come from bars ≤ `t`. |
| Data-sufficiency gate (§8.2) | Bar count per pair | Close of `t`; counting bars is causal. |
| Stop anchor and ATR(14) distance (§6) | Decision-bar D1 close; D1 OHLC for ATR | Close of the decision bar. `stop.price = close(decision_bar) ± 3.0 × ATR(D1,14)`; both inputs use only bars ≤ the decision bar (trailing ATR, no centred windows), so the stop is an absolute declarable float at `OrderIntent` emission — the unknowable next-bar fill is never referenced. |
| Market entry fill (§4/§5) | — | Order eligible from bar t+1 (F1); fills at t+1 open + adverse slippage (F2, F10). The strategy never sees t+1 data. |
| Catastrophic stop checks (§6) | H1 bars during holding period | Each H1 bar as it closes; the declared (decision-close-anchored) stop level is evaluated intrabar per F5/F6 using only bars ≥ t+1. |
| Time exit, 21 D1 bars (§7) | Bar count on the D1 frame | The exit bar is the 21st D1 bar after entry; knowable only as that bar closes. Resolved on H1 bars within the span per Contract Part D. |
| Monthly rotation / basket change (§7, §8.3) | Next month's `mom_c` ranking | Close of the next month's decision bar. A rank change cannot be acted on earlier: the strategy is declarative, cannot observe its own open position, and the contract has no close-existing-position intent — conservative by construction (§10 row 4). |

No indicator in this strategy uses centred windows, future-shifted series, or swing points;
the banned `detect_swing_points` is not used. There is no multi-timeframe context frame, so
the §4 MTF rule (context bar must have closed) is trivially satisfied — the only frame is
the primary D1 frame and every rule consumes it at or before its close.

## 10. Ambiguities resolved

| # | Ambiguity in the source | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | Source specifies **no per-trade stop** ("no per-trade stop (portfolio factor strategy)"); contract REQUIRES a `StopRule` on every order | Catastrophic stop at `3.0 × ATR(D1,14)` anchored to the decision close — wide enough to bind only in gap/crisis scenarios, preserving the source's economic behaviour while bounding worst-case loss per leg. Identical resolution to `SPEC-usd_carry_basket.md` §10 row 1. Documented −45.87% max DD was achieved with no stop, so any stop is a deviation; the widest defensible one minimises it. | (a) No stop — violates the contract, impossible. (b) Tight stop (e.g. 1×ATR) — converts a monthly macro position into a multi-day trade, measures something that is not the strategy. |
| 2 | Rule is "top-3/bottom-3" of a **10–20 currency universe**; only 5 currencies exist today (7 after Wave 1), so the terciles overlap | Keep top-3/bottom-3 **verbatim**, apply it mechanically to the available universe `U(t)`, and net the overlap: on the 5-currency universe the rank-3 currency is simultaneously long-1/3 and short-1/3 → `w_c = 0` → no order; the strategy degenerates to long-2/short-2 + 1 flat, honestly recorded here and in §2/§11. No retuning. | (a) Retune to top-2/bottom-2 on the reduced universe — changes the documented strategy to fit the data; exactly the overfitting the fleet rules prohibit. (b) Defer until 10+ currencies exist — no Wave-1 plan reaches 10; indefinite deferral of an implementable signal. (c) Emit both legs on the median pair (long AND short same pair) — contract-incoherent (F12 caps 1 concurrent position per pair; two opposite OrderIntents on one pair is not a nettable portfolio and inflates trade counts). |
| 3 | "Trailing 12-month **total return**" implies spot move + carry (interest differential / forward roll); no rate or forward data exists in the DB | Use **spot return only** (`close(t)/close(t−252) − 1`, direction-adjusted for USD-base pairs). For 12-month FX horizons the spot component dominates the carry component for most G10 pairs, so the ranking is largely preserved — but the omission is a real, flagged deviation from "total return", recorded here and in the DATA-GAP (impact section). | (a) Ingest rate series to add the carry component — disproportionate build for a secondary term; the core momentum signal is OHLCV-computable and unblocked. (b) Silent substitution without disclosure — prohibited. |
| 4 | Exit logic says "exit/rotate at monthly rebalance" — but v2 strategies are declarative, cannot see their own open positions, the contract has no close-existing-position intent, and F12 allows only 1 concurrent position per pair | The current month's position runs to its 21-bar time exit (or catastrophic stop); the new basket is acted on only at the **next monthly decision bar**. Since the time exit (21 D1 bars) approximately coincides with the next decision bar, practical overlap is ≤ a few days; any residual overlap is resolved by F12 refusing the new order, which is the conservative outcome (fewer trades, stale basket a few days longer). Residual risk direction: in long months the prior position may still be open at the new decision bar, so the month's new leg on that pair is skipped by F12 → under-deployment, never double-exposure. | (a) Immediate mid-month rotation — not expressible in the contract and would require position awareness the declarative interface deliberately forbids. (b) Shorter time exit so rotations are cleaner — deviates from the documented one-month hold. |
| 5 | "Hold one month" on a bar-count contract: calendar months have 19–23 D1 bars | Fixed `bars = 21` (long-run average trading days/month). In short months the position is held a few days past month-end; in long months it exits a few days early. Symmetric, mechanical, no discretion. Same resolution as `SPEC-usd_carry_basket.md` §10 row 5. | (a) Calendar-date exit ("close on last day of month") — not an ExitLeg kind; would require bespoke engine support. (b) W1 frame with bars=4–5 — 12–25% timing error per cycle and W1 data is stale (DATA_AVAILABILITY.md). |
| 6 | "Equal weight 1/3 each" with a degenerate/variable universe and a contract that forbids position sizing | `size_fraction = 1/3` per active leg, **not renormalised** over active legs: the source fixes 1/3 per tercile slot, so the flat median slot's capital is simply uninvested (deployed fraction 4/3 on 5 pairs, 2.0 on 7). Per-trade r-multiples are scale-invariant to `size_fraction`; the choice affects only pooled-equity reporting. | (a) Renormalise to `1/(#active legs)` — overstates per-leg allocation relative to the documented rule and changes pooled exposure between universe regimes. (b) Full 1.0 size_fraction per leg — 3× the intended per-leg risk. |
| 7 | Stop geometry needs an anchor price, but with `market` entries the fill (bar t+1 open) is unknowable at emission and `StopRule.price` must be an absolute float | Anchor the 3×ATR stop to the **decision bar's close** — fully knowable at emission (fleet rule). Consequence: the engine's declared R unit (`|entry_fill − stop.price|`) differs from the intended `3.0 × ATR` distance whenever the fill moves from the decision close; over a month-end weekend gap this is material, so **realised R ≠ declared R** is expected and must be stated in reports. F3/F6 resolve the fill pessimistically (gap-through → open); the anchor never depends on the unknowable fill. Identical resolution to `SPEC-usd_carry_basket.md` §10 row 7. | (a) Anchoring to `entry_fill` — undeclarable at emission, contract-impossible (inexpressible, not merely less conservative). (b) Pending limit at the decision close to force anchor = fill — replaces a guaranteed month-start entry with a conditional one (silently skips months where price never retraces); the source's rebalance is unconditional. |
| 8 | Risk management includes "cash not used as margin invested at overnight rates" and the data requirements list "overnight cash rates" | Out of scope: the r-multiple backtest does no position sizing and models no margin or cash balance, so the overnight-rate yield on uninvested margin has no measurable effect on any reported metric. No rate data is ingested for this purpose. Recorded in the DATA-GAP for completeness. | Ingesting overnight cash-rate series (FRED etc.) to model margin yield — adds a data build whose output cannot appear in an r-multiple result; revisit only if a capital-weighted equity simulation is ever commissioned. |
| 9 | "12-month lookback" could mean 252 D1 bars, 12 calendar months, or 52 W1 bars | **252 D1 bars** (the CSV pseudocode's `pct_change(252)`), computed on the primary D1 frame. Mechanical, matches the author's own code, and avoids month-length drift in the lookback. | (a) 12 calendar months — variable bar count (≈ 250–255), needs a date-offset lookup the pseudocode does not use. (b) 52 W1 bars — W1 is stale ~8 weeks (DATA_AVAILABILITY.md) and 4–5× coarser; decision frame stays D1. |

## 11. Expected behaviour

- **Trade frequency:** one rebalance per month → 12 decision events/year. Active legs per
  month: 4 on the live 5-pair universe (2 long + 2 short, median flat) → ≈ **48 trades/year**;
  6 on the 7-pair universe after Wave 1 → ≈ 72/year. Per (strategy, pair, granularity) cell:
  ~8–12 trades/year (each pair sits out the months its currency is the median; on the
  5-pair universe every pair is the median ~20% of months in expectation).
- **Warm-up cost per fold:** the 252-D1-bar lookback means the first **12 months of every
  36-month train window are signal-dead** (no rankable momentum). A 36-month train fold
  yields ~24 active months; a 6-month OOS fold yields ~6 decision events and ~24–36
  pooled leg-trades across pairs. From data start (2005-12-31) the first possible decision
  is ~end-2006.
- **What would make this strategy fail the gates:**
  1. **Degenerate universe on live data.** With 5 currencies, top-3/bottom-3 collapses to
     long-2/short-2 and ~83% of the universe is always positioned — there is almost no
     cross-sectional selection left, so the measured artefact is closer to "trend-follow
     the 5 majors" than to the documented 10–20-currency factor. Even after Wave 1 (7
     currencies), one-third of the documented diversification is missing. This is the
     dominant threat to fidelity.
  2. **Thin per-cell counts.** ~8–12 trades/year/pair and ~24–48 OOS trades per fold
     (pooled) invite `low_confidence` flags and possible minimum-trade/OOS-duration gate
     failures — arithmetic, not a verdict on the edge (cf. the contract's W1 statistical
     warning, applicable here in milder form).
  3. **Cost drag vs weak documented Sharpe.** 1.5 pips entry cost × ~48–72 entries/year
     against a factor whose documented in-sample Sharpe is only **0.30** and whose own
     OOS check is slightly negative; after realistic costs the mean r-multiple may not
     clear the gates even if the anomaly is real but attenuated.
  4. **Concentration and sign asymmetry.** All legs are a single USD-cross-sectional bet;
     on the 5-pair universe the book is 2 long + 2 short and a single trending pair
     dominates pooled results. Momentum crashes (sudden macro regime reversals — the
     documented −45.87% max DD occurred under no stop) land inside single folds; the
     catastrophic stop truncates individual legs but not the factor-level drawdown.
  5. **Regime dependence:** the academic result spans 1976–2010; post-2010 low-volatility
     regimes (and Quantpedia's own negative OOS) suggest the spread has compressed.
- **Is MODERATE justified?** Yes — arguably generous. The academic pedigree (Menkhoff et
  al.) is strong, but the documented Sharpe is 0.30 (weak for a monthly factor), the max
  drawdown is −45.87%, and Quantpedia's own OOS backtest is slightly negative — the CSV's
  reasoning field itself says the strategy "requires modern re-testing/optimization rather
  than blind deployment". As specified here the strategy is additionally handicapped by a
  degenerate 5-currency universe, a spot-only return (no carry component), and a
  contract-forced catastrophic stop the source did not have. MODERATE correctly encodes
  "real anomaly, deteriorating, test before trusting"; nothing in the rules as written
  supports an upgrade, and a pooled pass on the reduced universe should not be read as
  validation of the 10–20-currency factor.
