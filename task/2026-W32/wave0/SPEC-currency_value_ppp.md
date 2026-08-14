# SPEC-currency_value_ppp

**Source:** row 44 of forex_swing_strategies.csv (CSV line 45) · https://quantpedia.com/strategies/currency-value-factor-ppp-strategy
**Conviction (author's):** MODERATE

**BLOCKING DEPENDENCY:** This strategy's signal is a PPP misvaluation requiring **OECD
Purchasing Power Parity figures and monthly CPI series per G10 currency (including USD)**.
Neither exists in the DB (`DATA_AVAILABILITY.md`: "Non-price data — none of it exists").
The full mechanics are specified below so implementation is mechanical once the data lands;
until then this strategy can emit **zero orders**. See `DATA-GAP-currency_value_ppp.md`.
No price-only proxy is substituted for the signal anywhere in this spec (§10 row 4 and the
DATA-GAP record why such a proxy measures a different phenomenon).

## 1. Hypothesis

Currencies trading far below their purchasing-power-parity fair value against the US dollar
tend to appreciate toward fair value over the following quarters, and currencies trading far
above PPP tend to depreciate, so a quarterly-rebalanced long-short portfolio of the three
most undervalued versus the three most overvalued G10 currencies earns a persistent
cross-sectional spread. The edge should persist because goods-market arbitrage and relative
inflation differentials pull exchange rates toward PPP over multi-year horizons — traded
goods cannot durably cost twice as much in one developed economy as another without flows
responding — while the adjustment is slow because goods prices are sticky, pass-through is
incomplete, and investors anchor on nominal levels and recent trends rather than slow-moving
fair value, leaving the misvaluation unexploited for quarters at a time. This is the
academically recognised FX *value* factor (PPP mean reversion; Aloosh/Bekaert, Deutsche Bank
source paper per the CSV); Quantpedia documents a 1989–2009 indicative 7.82% p.a., volatility
9.33%, Sharpe 0.36, max drawdown −39.38%, with low/negative correlation to equities in
stress — but Quantpedia's own out-of-sample check is slightly negative, so the anomaly may
be attenuating (§11).

## 2. Scope

- primary_granularity: **D1** — the cadence is quarterly (one rebalance decision per calendar
  quarter). D1 is the order-emission frame because a quarter is 62–66 trading days, cleanly
  expressible as a ~63-bar D1 time exit, whereas W1 (13 bars/quarter) cannot represent a
  one-quarter hold without ~8–15% timing error, and the W1 series in the DB is stale ~8 weeks
  (DATA_AVAILABILITY.md). D1 decisions are resolved on H1 bars per Contract Part D.
- context_granularities: [] — none. The signal is external macro data plus the decision bar's
  own close; no higher-timeframe price context is needed.
- simulate_on: H1
- pairs_requested (verbatim from CSV): "Universe of 10-20 currencies vs USD (G10 core)"
- pairs_available (live today): EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD → currencies
  EUR, GBP, JPY, AUD, CAD (5 non-USD currencies)
- pairs_pending (Wave-1 additions; harness skips insufficient history rather than failing):
  NZD_USD, USD_CHF → adds NZD, CHF → 7 non-USD currencies. (The other Wave-1 pairs —
  GBP_JPY, EUR_JPY, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD — are crosses and add no new
  currency-vs-USD series; they are irrelevant to this strategy.)
- pairs_missing (no Wave-1 plan): USD_DKK, USD_NOK, USD_SEK — the Scandinavian G10 legs —
  → combined with the PPP/CPI macro gap in `DATA-GAP-currency_value_ppp.md`.

**Universe degeneracy warning.** The documented rule is "long the 3 most undervalued / short
the 3 most overvalued". With the 5 live pairs there are only **5** non-USD currencies, so the
long tercile (ranks 1–3 by misvaluation) and the short tercile (ranks 3–5) overlap at the
median currency: the strategy degenerates to long-2 / short-2 with the median currency flat,
and ~83% of the universe is always positioned. Only after the Wave-1 additions land (7
currencies) do the terciles become non-degenerate (ranks 1–3 long, 4 flat, 5–7 short). This
spec keeps the rule **verbatim** (no retuning); the degeneracy is recorded in §10 row 2 and
priced into §11. Identical resolution to `SPEC-currency_momentum_factor.md` §2.

## 3. Indicators

The signal is a **macro misvaluation, not a price indicator**. Required series and derived
quantities:

| Indicator | Params | Source |
|---|---|---|
| OECD PPP per currency, `PPP_c(Y)` | annual, units of foreign currency per 1 USD, reference year Y, for EUR, GBP, JPY, AUD, CAD (+ NZD, CHF pending; DKK, NOK, SEK for the full G10) | **NOT IN DB** — external (OECD SDMX; see DATA-GAP). Knowable only under the publication-lag rule §8.2/§9. |
| CPI index per currency, `CPI_c(M)` | monthly index level (any base period, used only as a ratio), for each traded currency **and USD**, reference month M | **NOT IN DB** — external (OECD MEI / national statistics offices / FRED; see DATA-GAP). Knowable only under the publication-lag rule §8.2/§9. |
| PPP fair value, `ppp_fair_c(t)` | `ppp_fair_c(t) = PPP_c(Y(t)) × [ CPI_c(M(t)) / CPI_c(Dec(Y(t))) ] / [ CPI_US(M(t)) / CPI_US(Dec(Y(t))) ]` — the latest knowable OECD PPP extrapolated forward by the **relative** (foreign vs US) cumulative CPI change since the PPP reference year's December; in foreign-currency-per-USD units | private derivation from the two external series above; fully specified here. `Y(t)` and `M(t)` are defined by the lag rules in §4 steps 1–2. `CPI(Dec(Y))` is historical at decision time, hence knowable. |
| Spot in USD-per-currency, `spot_c(t)` | for USD-quote pairs (EUR_USD, GBP_USD, AUD_USD, NZD_USD): `spot_c(t) = close_p(t)`; for USD-base pairs (USD_JPY, USD_CAD, USD_CHF): `spot_c(t) = 1 / close_p(t)`; `close_p(t)` is the pair's D1 decision-bar close | private derivation from D1 OHLC (ratio/inversion of one close; no rolling window). Not added to `indicators.py`. |
| PPP fair value in USD-per-currency, `fair_c(t)` | `fair_c(t) = 1 / ppp_fair_c(t)` | private; exact reciprocal, fully specified |
| Misvaluation, `z_c(t)` | `z_c(t) = ( spot_c(t) − fair_c(t) ) / fair_c(t)`; `z < 0` = currency trades below PPP fair value = **undervalued** | private; pure function of the two quantities above, fully specified |
| Cross-sectional rank of `z_c` | rank over the quarter's available universe `U(t)`, **ascending** (rank 1 = lowest z = most undervalued); exact ties broken by universe declaration order (EUR, GBP, JPY, AUD, CAD, NZD, CHF) — earlier-listed currency receives the better (lower) rank | private; mechanical sort, fully specified here |
| ATR | period 14, on D1, per traded pair | `indicators.atr(high, low, close, 14)` — exists; used ONLY for the contract-required catastrophic stop, never for the signal |

**No PPP or CPI series exists in the DB.** ATR is the only indicator computed from existing
DB data. The banned `detect_swing_points` is not used; no swing/pivot/fractal logic exists in
this strategy.

## 4. Entry — long

"Long" = long the 3 most **undervalued** currencies vs USD (the CSV's `entry_logic_long`).

At the quarterly decision bar (§8.1):

1. **CPI horizon:** `M(t)` = the calendar month immediately preceding the decision bar's
   month. (CPI for month M is assumed knowable only after the close of the last D1 bar of
   month M+1 — §8.2/§9; at a quarter-end decision bar, CPI for the quarter's final month is
   NOT yet knowable, so the freshest usable print is the prior month's.)
2. **PPP horizon:** `Y(t)` = (calendar year of the decision bar) − 2. (An OECD PPP for
   reference year Y is assumed knowable only after the close of the last D1 bar of year Y+2
   — a conservative 24-month publication lag; §8.2/§9.)
3. Compute `ppp_fair_c(t)`, `fair_c(t)`, `spot_c(t)`, `z_c(t)` per §3 for every currency
   whose pair passes the data-sufficiency gate (§8.3); call the set `U(t)`.
4. Rank `z_c` ascending over `U(t)`; `long3 = {c : rank(c) ≤ 3}`;
   `short3 = {c : rank(c) ≥ |U(t)| − 2}` (the 3 highest z = most overvalued).
5. Net weight per currency: `w_c = (1/3)·1[c ∈ long3] − (1/3)·1[c ∈ short3]`.
   On a universe of 6+ currencies `w_c = 1/3` for longs; on the degenerate 5-currency
   universe the median currency (rank 3) is simultaneously long-1/3 and short-1/3, so
   `w_c = 0` and **no order is emitted for its pair**.
6. For each `c` with `w_c > 0`, emit one `OrderIntent` on pair `p(c)`:
   - `direction = +1` for USD-quote pairs (EUR_USD, GBP_USD, AUD_USD, NZD_USD) — buying the
     pair = long the currency
   - `direction = −1` for USD-base pairs (USD_JPY, USD_CAD, USD_CHF) — selling the pair =
     long the currency
   - `size_fraction = |w_c| = 1/3`
7. Every leg carries the same `decision_bar`, stop (§6), and exit (§7).

- entry type: `market` (fills at open of bar t+1 per F1/F2 — conservative, one bar of drift)
- entry level: n/a (market)
- expires_after_bars: n/a for market entries (a market order fills at t+1 open or not at all)
- size_fraction formula: `|w_c|`, exactly `1/3` per active leg. `size_fraction` expresses the
  equal-weight tercile allocation in units of R per the contract ("relative allocation across
  legs of one idea"); it is not position sizing. Weights are NOT renormalised over the active
  legs — the source fixes equal weights per tercile slot and the flat median slot is simply
  uninvested (§10 row 6). Total deployed fraction per quarter = (#active legs)/3: 4/3 on the
  live 5-pair universe (2 long + 2 short), 2.0 on the 7-pair universe.

## 5. Entry — short

Mirror of §4 ("short the 3 most **overvalued** currencies vs USD"):

1.–4. Identical horizons, misvaluation computation, and ranking as §4 steps 1–4;
   `short3 = {c : rank(c) ≥ |U(t)| − 2}`.
5. Net weight `w_c` as §4 step 5; on the degenerate 5-currency universe the median currency
   nets to zero and emits nothing (computed once per currency, not once per side — the same
   pair is never double-counted).
6. For each `c` with `w_c < 0`, emit one `OrderIntent` on pair `p(c)` with **reversed**
   direction relative to §4:
   - `direction = −1` for USD-quote pairs (short the pair = short the currency)
   - `direction = +1` for USD-base pairs (long the pair = short the currency)
   - `size_fraction = |w_c| = 1/3`
7. Same decision bar, stop, and exit as §4.

- entry type: `market`
- entry level: n/a
- expires_after_bars: n/a
- size_fraction: `1/3` per active leg

## 6. Stop

The source specifies **no per-trade stop** — it holds until the next rebalance, with risk
managed by equal weights, periodic re-evaluation, and diversification (the documented max
drawdown −39.38% arose under that regime). The contract REQUIRES a `StopRule` on every
`OrderIntent`.

- initial stop (conservative catastrophic stop, identical pattern to
  `SPEC-usd_carry_basket.md` §6 and `SPEC-currency_momentum_factor.md` §6), **anchored to a
  decision-bar-knowable price** (fleet rule: with market entries the fill is unknowable at
  emission, so `StopRule.price` must be declarable from the decision bar alone):
  `stop.price = close(decision_bar) − 3.0 × ATR(D1, 14)` for `direction=+1`;
  `stop.price = close(decision_bar) + 3.0 × ATR(D1, 14)` for `direction=−1`;
  where `close(decision_bar)` is the close of the quarter-end D1 decision bar and ATR(14) is
  computed on the D1 frame from bars closed at or before the decision bar. Both inputs are
  fully known at the decision bar's close, so `StopRule.price` is an absolute float at
  `OrderIntent` creation. The actual fill (next bar's open per F1/F2) will differ from the
  anchor; **realised R ≠ declared R** whenever the market moves between decision close and
  fill (quarter-end weekend gaps make this material) — F3/F6 handle the fill mechanics, the
  anchor stays declarable (§10 row 8). At 3× daily ATR, ≈ 3 typical days of range must be
  traversed adversely before the stop engages; it should bind only in gap/crisis scenarios,
  approximating the source's stop-free quarterly hold while bounding worst-case loss per leg
  (F6 gap-through-stop fills at the open and can exceed 1R — accepted and reported). The
  tension between the stop-free source and the required StopRule is recorded in §10 row 1.
- move_to_breakeven_on: none
- trail: none

## 7. Exit legs

The exit is **time-based** (quarterly hold, then rotate at the next rebalance). One leg per
order, fraction 1.0:

| Label | Fraction | Kind | Level formula |
|---|---|---|---|
| QUARTER_END | 1.0 | `time` | `bars = 63` (≈ one calendar quarter of D1 trading days, measured on the primary D1 frame; engine resolves on H1 within those bars) |

Fractions sum to 1.0 per pair-order. There is deliberately only one leg: the source holds the
full position for the whole quarter and rotates; scale-outs would deviate from the documented
strategy. Quarter-length drift (62–66 trading days) is handled conservatively in §10 row 5.
Rotation happens because next quarter's decision bar emits the new basket; the current
quarter's position exits on its 63-bar time leg at approximately the next decision bar, and
any residual overlap is resolved by F12 (§10 row 7).

## 8. Filters

1. **Quarterly cadence gate:** orders may be emitted only at the decision bar = the **last
   completed D1 bar of March, June, September, or December**. D1 bars are stamped at their
   open (21:00 UTC); the final D1 bar of the quarter is the bar whose open date is the last
   trading day of the quarter-end month. That bar is fully knowable at its close (21:00 UTC
   on the last trading day). All non-quarter-end D1 bars emit nothing. Evaluated on the
   primary D1 frame; whether a bar is the quarter's last is knowable at its **open** from the
   trading calendar, taking the last bar that actually exists in the data.
2. **Publication-lag gate (macro data):**
   - **CPI:** a CPI observation for reference month M is usable only at decision bars after
     the close of the last D1 bar of month M+1 (assumed one-full-month publication lag —
     conservative against the actual ~2–4 week lag of G10 CPI releases; §9). At a
     quarter-end decision bar this makes `M(t)` the month preceding the decision month
     (§4 step 1): the final month of the quarter is deliberately not yet knowable.
   - **PPP:** an OECD PPP observation for reference year Y is usable only at decision bars
     after the close of the last D1 bar of year Y+2 (assumed 24-month publication lag —
     conservative against OECD's actual release pattern; §9). This makes
     `Y(t) = year(t) − 2` (§4 step 2).
   - If the CPI series for any traded currency is unavailable at the lagged horizon, that
     currency is dropped from `U(t)` for the quarter (the terciles are computed over the
     survivors). If the **USD** CPI series or the PPP series is unavailable at the lagged
     horizon, emit nothing that quarter — the misvaluation is uncomputable for every
     currency.
3. **Data-sufficiency gate:** a pair enters `U(t)` only if (a) it is in `pairs_available` or
   a completed Wave-1 addition per the harness rule (harness skips pairs with insufficient
   history, never fails), (b) it has at least **15 closed D1 bars** at the decision bar so
   ATR(14) is defined, and (c) its currency's PPP and CPI series exist at the lagged horizons
   of §8.2. The Wave-1 cross pairs (GBP_JPY etc.) are excluded unconditionally — they add no
   new currency vs USD. DKK/NOK/SEK are excluded unconditionally (no pairs, no Wave-1 plan).
4. **No re-entry within the quarter:** at most one decision per quarter per pair. F12 (max 1
   concurrent position per strategy/pair/granularity) additionally prevents stacking; because
   the prior quarter's position exits on its 63-bar time leg at approximately the next
   decision bar, a rank change becomes effective at the following rebalance (§10 row 7).
5. **No trend/session/volatility/news filters exist in the source** and none are added.
6. **Out of scope (recorded, not implemented):** the source's "margin cash at overnight
   rates". This is a sizing/margin-yield detail of a capital-weighted portfolio; the
   r-multiple backtest does no sizing and has no margin, so the overnight-rate component
   contributes nothing measurable and no rate data is ingested for it. Recorded in §10 row 9
   and the DATA-GAP. Likewise "documented max drawdown −39.38%" and the equity-correlation
   hedge claim are reporting properties of the source's backtest, not implementable rules
   (no equity data exists to test the hedge property — DATA-GAP).

## 9. Causality audit

| Rule | Inputs | Fully known at |
|---|---|---|
| Quarterly decision bar identification (§8.1) | Trading calendar; D1 bar timestamps stamped at open | Close of the last D1 bar of the quarter-end month (21:00 UTC). Whether a bar is the quarter's last is knowable at its open from the calendar. |
| PPP observation `PPP_c(Y(t))` (§4.2) | External annual OECD PPP series with publication dates | **Assumed observation lag: 24 months after reference-year end.** A PPP for year Y is used only at decision bars after the close of the last D1 bar of year Y+2; at the end-of-December decision in year Y+2, `Y(t) = Y` first becomes usable. Rationale: OECD annual/benchmark PPPs are published roughly 1–3 years after the reference period and are revised; 24 months is a conservative fixed stand-in where true vintage publication dates are unavailable. Using a same-year or next-year PPP would be look-ahead by up to 2 years and is prohibited. If the DATA-GAP integration lands true `publish_date` vintages, those dates govern instead and this assumption becomes the fallback bound. |
| CPI observation `CPI_c(M(t))`, incl. USD (§4.1) | External monthly CPI index series per currency with publication dates | **Assumed observation lag: one full month.** CPI for reference month M is used only at decision bars after the close of the last D1 bar of month M+1. Rationale: G10 CPI prints land ~2–4 weeks after month-end (e.g. US CPI mid-following-month, euro-area final HICP ~2 weeks after flash, Japan ~3 weeks); one full month is conservative against every G10 release calendar. A CPI print for month M is **not** knowable at month M's close — using it would be look-ahead (the naive `resample().last().ffill()` pattern in the CSV pseudocode does exactly this if read literally). If true publication vintages land, they govern instead. |
| CPI base-month values `CPI(Dec(Y(t)))` (§3) | Same CPI series | Historical at decision time (at least 12 months stale under the lag rule above); trivially knowable. |
| `ppp_fair_c(t)`, `fair_c(t)`, `z_c(t)` (§3, §4.3) | Lagged PPP, lagged CPI, decision-bar close | Close of the decision bar. Pure arithmetic on quantities each shown knowable above. |
| `spot_c(t)` (§3) | Decision-bar D1 close of the pair (inverted for USD-base pairs) | Close of the decision bar `t`. No rolling window beyond the single closed bar. |
| Cross-sectional ranking, terciles, net weights (§4.4–4.5, §5) | All `z_c(t)` values, same decision bar | Close of the decision bar `t`. Ranking is a pure sort of quantities already known at `t`; every pair's inputs come from bars ≤ `t`, so no cross-pair look-ahead is possible. |
| Data-sufficiency gate (§8.3) | Bar count per pair; presence of lagged macro series | Close of `t`; counting bars and checking lagged series availability is causal. |
| Stop anchor and ATR(14) distance (§6) | Decision-bar D1 close; D1 OHLC for ATR | Close of the decision bar. `stop.price = close(decision_bar) ± 3.0 × ATR(D1,14)`; both inputs use only bars ≤ the decision bar (trailing ATR, no centred windows), so the stop is an absolute declarable float at `OrderIntent` emission — the unknowable next-bar fill is never referenced. |
| Market entry fill (§4/§5) | — | Order eligible from bar t+1 (F1); fills at t+1 open + adverse slippage (F2, F10). The strategy never sees t+1 data. |
| Catastrophic stop checks (§6) | H1 bars during holding period | Each H1 bar as it closes; the declared (decision-close-anchored) stop level is evaluated intrabar per F5/F6 using only bars ≥ t+1. |
| Time exit, 63 D1 bars (§7) | Bar count on the D1 frame | The exit bar is the 63rd D1 bar after entry; knowable only as that bar closes. Resolved on H1 bars within the span per Contract Part D. |
| Quarterly rotation / basket change (§7, §8.4) | Next quarter's lagged macro series and ranking | Close of the next quarter's decision bar. A rank change cannot be acted on earlier: the strategy is declarative, cannot observe its own open position, and the contract has no close-existing-position intent — conservative by construction (§10 row 7). |

No indicator in this strategy uses centred windows, future-shifted series, or swing points;
the banned `detect_swing_points` is not used. There is no multi-timeframe context frame, so
the Contract §4 MTF rule (context bar must have closed) is trivially satisfied — the only
price frame is the primary D1 frame and every rule consumes it at or before its close. The
external macro series obey the stricter publication-lag discipline stated above, which is the
macro analogue of the MTF rule: an observation informs a decision only after it is
*knowable*, not merely after its reference period ends.

## 10. Ambiguities resolved

| # | Ambiguity in the source | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | Source specifies **no per-trade stop** (hold to rebalance; risk managed by equal weights and diversification); contract REQUIRES a `StopRule` on every order | Catastrophic stop at `3.0 × ATR(D1,14)` anchored to the decision close — wide enough to bind only in gap/crisis scenarios, preserving the source's economic behaviour while bounding worst-case loss per leg. Identical resolution to `SPEC-usd_carry_basket.md` §10 row 1. Documented −39.38% max DD was achieved with no stop, so any stop is a deviation; the widest defensible one minimises it. | (a) No stop — violates the contract, impossible. (b) Tight stop (e.g. 1×ATR) — converts a quarterly macro position into a multi-day trade, measures something that is not the strategy. |
| 2 | Rule is "3 most undervalued / 3 most overvalued" of a **10–20 currency (G10) universe**; only 5 currencies exist today (7 after Wave 1), so the terciles overlap | Keep top-3/bottom-3 **verbatim**, apply it mechanically to the available universe `U(t)`, and net the overlap: on the 5-currency universe the rank-3 currency is simultaneously long-1/3 and short-1/3 → `w_c = 0` → no order; the strategy degenerates to long-2/short-2 + 1 flat, honestly recorded in §2 and §11. No retuning. Identical resolution to `SPEC-currency_momentum_factor.md` §10 row 2. | (a) Retune to top-2/bottom-2 on the reduced universe — changes the documented strategy to fit the data; exactly the overfitting the fleet rules prohibit. (b) Defer until 10+ currencies exist — no Wave-1 plan reaches 10; indefinite deferral. (c) Emit both legs on the median pair (long AND short same pair) — contract-incoherent (F12 caps 1 concurrent position per pair; two opposite OrderIntents on one pair is not a nettable portfolio and inflates trade counts). |
| 3 | Cadence: "Quarterly (or monthly) rebalancing" | **Quarterly** — fewer trades, less cost drag, less turnover noise on a factor whose documented horizon is multi-year mean reversion; also matches the CSV's own note that "slow-moving fundamentals suit swing horizons". Decision bar = last D1 bar of Mar/Jun/Sep/Dec; time exit 63 D1 bars. | Monthly rebalancing — 3× the trades and entry costs against a Sharpe-0.36 factor whose signal barely changes month to month (PPP fair value moves at CPI speed); rejected as the less conservative reading that flatters nothing but turnover. |
| 4 | Fair-value update formula: CSV text says "latest OECD PPP updated with monthly CPI and FX changes"; pseudocode is `ppp_fair = oecd_ppp * (1 + cpi.diff()/cpi.shift()) * fx_adj` with an undefined `fx_adj` | **Relative-PPP update, CPI only, no FX term:** `ppp_fair_c(t) = PPP_c(Y(t)) × [CPI_c(M(t))/CPI_c(Dec(Y(t)))] / [CPI_US(M(t))/CPI_US(Dec(Y(t)))]` — the standard relative-PPP formula (fair value drifts with the foreign-vs-US inflation differential). This is the economically meaningful reading and requires USD CPI as well as foreign CPI (§3). | (a) Literal pseudocode with an FX-change multiplier — makes fair value chase spot, mechanically collapsing the misvaluation `z` toward zero; the "signal" then measures nothing (a fair value that follows price can never be far from price). Inexpressible as a value factor; rejected as incoherent, not merely less conservative. (b) Foreign-CPI-only update (ignore US inflation) — omits half the relative-PPP differential; biases fair value in high-US-inflation regimes. (c) **Any price-only proxy for PPP** (deviation from an N-year rolling mean or a fixed historical anchor) — measures sample-anchored long-horizon mean reversion around a window-dependent mean, not PPP value; silently substitutes a different phenomenon under the strategy's name. Refused; see DATA-GAP §Impact. |
| 5 | Quote convention for misvaluation: PPP is conventionally quoted foreign-currency-per-USD while several traded pairs are USD-quote; the pseudocode's `z` never states its convention | Compute `z` in **USD-per-foreign-currency** units (§3): `z = (spot − fair)/fair` with `spot = close` for USD-quote pairs, `1/close` for USD-base pairs, `fair = 1/ppp_fair`. Then `z < 0` = undervalued and "long the lowest z" matches the pseudocode's `ranks.le(3)` directly. Fully mechanical, sign-unambiguous. | Computing `z` in foreign-per-USD units — mathematically the sign flips (`(1/x−1/y)/(1/y) = y/x − 1`), so the long/short masks would need inverting; keeping the pseudocode's mask direction verbatim under that convention would trade the factor **backwards**. Rejected as the error-prone reading; the chosen convention makes the pseudocode's mask literal and correct. |
| 6 | When are CPI prints knowable? Source is silent; pseudocode's `resample('QE').last().ffill()` pattern, read literally, uses quarter-end CPI at quarter-end | **One-full-month publication lag:** CPI for month M usable only after the close of the last D1 bar of M+1 (§8.2). At a quarter-end decision the freshest usable print is the quarter's second-to-last month... i.e. `M(t)` = decision month − 1. Every input is stale by construction. | (a) Zero-lag use of the quarter-final month's CPI at quarter-end — look-ahead by 2–4 weeks against every G10 release calendar; this is the naive-pandas reading of the pseudocode and is prohibited. (b) Exact per-country release calendars — more precise but unimplementable without a calendar feed we do not have; the uniform 1-month bound is conservative against all G10 calendars and needs no extra data. |
| 7 | When are OECD PPPs knowable, and which vintage? Source says "latest OECD PPP"; PPPs are annual, revised, and published years late | **Fixed 24-month publication lag** on the reference year (`Y(t) = year(t) − 2`; §8.2), applied to whatever series the DATA-GAP integration stores, with true `publish_date` vintages governing if/when they land. Revisions: the integration keeps vintages keyed by publication date (DATA-GAP schema), so a decision uses the value *first knowable* at that time, never a later revision. | (a) "Latest published PPP" used at its reference date — look-ahead by up to 2 years (the reference year hasn't even ended when its PPP is implicitly assumed known). (b) Current-vintage back-history (today's revised PPP series read backward) — the classic revised-macro look-ahead; prohibited. (c) Longer fixed lag (36 months) — arguably safer but discards usable information under OECD's actual release pattern; 24 months is already the conservative-but-not-wasteful bound and is stated prominently in §9. |
| 8 | Stop geometry needs an anchor price, but with `market` entries the fill (bar t+1 open) is unknowable at emission and `StopRule.price` must be an absolute float | Anchor the 3×ATR stop to the **decision bar's close** — fully knowable at emission (fleet rule). Consequence: the engine's declared R unit (`|entry_fill − stop.price|`) differs from the intended `3.0 × ATR` distance whenever the fill moves from the decision close; over a quarter-end weekend gap this can be material, so **realised R ≠ declared R** is expected and must be stated in reports. F3/F6 resolve the fill pessimistically (gap-through → open); the anchor never depends on the unknowable fill. | (a) Anchoring to `entry_fill` — undeclarable at emission, contract-impossible (inexpressible, not merely less conservative). (b) Pending limit at the decision close to force anchor = fill — replaces a guaranteed quarter-start entry with a conditional one (silently skips quarters where price never retraces); the source's rebalance is unconditional. |
| 9 | Risk management includes "margin cash at overnight rates" | Out of scope: the r-multiple backtest does no position sizing and models no margin or cash balance, so the overnight-rate yield on uninvested margin has no measurable effect on any reported metric. No rate data is ingested for this purpose. Recorded in the DATA-GAP for completeness. | Ingesting overnight cash-rate series to model margin yield — adds a data build whose output cannot appear in an r-multiple result; revisit only if a capital-weighted equity simulation is ever commissioned. |
| 10 | "Equal weight" per leg with a degenerate/variable universe and a contract that forbids position sizing | `size_fraction = 1/3` per active leg, **not renormalised** over active legs: the source fixes equal weights per tercile slot, so the flat median slot's capital is simply uninvested (deployed fraction 4/3 on 5 pairs, 2.0 on 7). Per-trade r-multiples are scale-invariant to `size_fraction`; the choice affects only pooled-equity reporting. Identical resolution to `SPEC-currency_momentum_factor.md` §10 row 6. | (a) Renormalise to `1/(#active legs)` — overstates per-leg allocation relative to the documented rule and changes pooled exposure between universe regimes. (b) Full 1.0 size_fraction per leg — 3× the intended per-leg risk. |
| 11 | "Hold until next quarterly/monthly rebalance" on a bar-count contract: calendar quarters have 62–66 D1 bars | Fixed `bars = 63` (long-run average trading days/quarter). In short quarters the position is held a few days past quarter-end; in long quarters it exits a few days early. Symmetric, mechanical, no discretion. Since the 63-bar time exit approximately coincides with the next decision bar, residual overlap is ≤ a few days and is resolved by F12 refusing the new order — the conservative outcome (fewer trades, stale basket held a few days longer; **under-deployment, never double-exposure**). | (a) Calendar-date exit ("close on last day of quarter") — not an ExitLeg kind; would require bespoke engine support. (b) Immediate mid-quarter rotation on rank change — not expressible in the contract (no close-existing-position intent) and would require position awareness the declarative interface deliberately forbids. (c) W1 frame with bars=13 — coarser timing error and W1 data is stale ~8 weeks (DATA_AVAILABILITY.md). |

## 11. Expected behaviour

- **Trade frequency:** one rebalance per quarter → 4 decision events/year. Active legs per
  quarter: 4 on the live 5-pair universe (2 long + 2 short, median flat) → ≈ **16 trades/year**;
  6 on the 7-pair universe after Wave 1 → ≈ 24/year. Per (strategy, pair, granularity) cell:
  ~2–4 trades/year (each pair sits out the quarters its currency is the median; on the
  5-pair universe every pair is the median ~20% of quarters in expectation). This is one of
  the lowest-frequency strategies in the 51-row set.
- **Warm-up cost:** the signal needs CPI history back to the PPP reference year's December
  plus 15 D1 bars for ATR — modest in D1 terms, but the *data* warm-up is dominated by the
  macro ingest depth (PPP vintages and CPI back-history are the binding constraint; see
  DATA-GAP). First decision possible only after both macro series are ingested.
- **What would make this strategy fail the gates:**
  1. **Blocking data gap.** With no PPP/CPI series the strategy emits zero orders and cannot
     be gated at all — the DATA-GAP is the primary obstacle.
  2. **Thin per-cell counts.** ~2–4 trades/year/pair means a 6-month OOS fold contains ~1–2
     decision events and ~4–12 pooled leg-trades. Expect `low_confidence` flags and probable
     failure of minimum-trade/OOS-duration gates on per-cell verdicts even if the pooled
     result is sound — arithmetic, not a verdict on the edge (the contract's W1 statistical
     warning applies here almost at full strength despite this being a D1 strategy).
  3. **Horizon mismatch.** PPP misvaluation mean-reverts with a half-life of years (the
     academic consensus for PPP deviation half-lives is ~3–5 years); the documented edge
     accrues over multi-year holds, but this strategy holds one quarter. Per-quarter expected
     convergence is a small fraction of the 3×ATR risk unit, so mean r-multiples will be
     small and noisy — the documented Sharpe is only **0.36** in-sample over 1989–2009.
  4. **Degenerate universe on live data.** With 5 currencies the terciles collapse to
     long-2/short-2 and ~83% of the universe is always positioned — almost no cross-sectional
     selection remains; the measured artefact is closer to "value-tilt the 5 majors" than to
     the documented G10 factor. Even after Wave 1 (7 currencies), a third of the documented
     diversification is missing (DKK/NOK/SEK have no ingestion plan at all).
  5. **Quantpedia's own OOS check is slightly negative.** The CSV's reasoning field says so
     explicitly ("OOS backtest slightly negative per Quantpedia note, so needs
     re-validation"); post-2009 folds may show the anomaly attenuated (crowding, low
     inflation-differential dispersion in the 2010s compresses relative-PPP drift, which is
     the update term of this strategy's fair value).
  6. **Cost drag is minor but non-zero:** 1.5 pips entry cost × ~16–24 entries/year — small
     in absolute terms, but against small per-trade expected convergence it is not
     negligible.
- **Is MODERATE justified?** As a literature claim, yes — arguably generously. PPP value is
  one of the canonical FX factors with real academic backing (Aloosh/Bekaert; Deutsche Bank
  source paper), but the documented Sharpe is 0.36 (weak), the max drawdown is −39.38%, and
  the source's own out-of-sample check is slightly negative. As specified here the strategy
  is additionally handicapped by a degenerate 5-currency universe, conservative publication
  lags (its freshest CPI is always one month stale, its PPP two years stale — appropriate,
  but it means the traded signal lags the source's backtest), a one-quarter hold against a
  multi-year half-life, and a contract-forced catastrophic stop the source did not have.
  MODERATE correctly encodes "canonical factor, weak documented stats, deteriorating, test
  before trusting" — and every one of those numbers was produced with actual PPP/CPI data
  and a full G10 universe. Until the macro series land, the implementable artefact is a
  specification, not a strategy; the rating must not be inherited by any price-only stand-in,
  and a pooled pass on the reduced universe should not be read as validation of the G10
  factor.
