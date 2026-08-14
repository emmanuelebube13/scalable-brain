# Wave 0 — Data Gap Register

**Scalable Brain · 51-strategy research fleet · compiled 2026-08-10**

This document collates the 20 `DATA-GAP` notes produced during Wave 0 (strategy specification extraction). Of the 51 documented forex swing strategies, 31 are fully implementable against existing and Wave-1-pending data; the 20 in this register have a data dependency a decision-maker should rule on. Each note leads with its recommendation; the engineering detail follows for whoever executes it.

**How to read:** Group 1 items block their strategy's signal entirely but are nearly free to fix (start ingestion now, defer the backtest). Group 2 items are single-symbol or single-granularity ingests on the existing OANDA v20 path. Group 3 items do not block anything — the strategy runs today on reduced coverage, and the gap note records what is missing and how to close it if desired.

## Summary table

| Strategy | What is missing | Recommendation |
|---|---|---|
| `usd_carry_basket` | 3-month interest rates for USD + 9 basket currencies; USD_DKK/NOK/SEK pairs | Status: BLOCKING — the strategy can emit zero orders until this gap is closed. |
| `currency_value_ppp` | OECD PPP figures + monthly CPI for the G10 | Status: BLOCKING — the strategy can emit zero orders until this gap is closed. |
| `financial_regime_index` | Nine external daily series: SPY, ACWI, HYG, LQD, VIX, DXY, US02Y, US10Y, BIL | DEFER — do not implement in Wave 2; revisit only if the macro-ingest is built anyway. |
| `retail_sentiment_fade` | Retail long/short positioning feed (Ziwox API or equivalent) | Defer the backtest until sentiment data accumulates — but start forward ingestion immediately, and implement the strategy code now. |
| `three_ducks` | M5 granularity (trigger timeframe) for EUR_USD/GBP_USD | Defer implementation until M5 data lands — and ingest M5 now via the existing OANDA v20 path. |
| `nzdjpy_median_ma_retrace` | NZD_JPY — the strategy's only pair | Defer the backtest until NZD_JPY data lands; implement the Wave-2 spec now; drop the strategy rather than proxy it if the ingest is declined. |
| `currency_momentum_factor` | Universe breadth: 5–7 currencies available vs 10–20 requested | Implement now with reduced coverage — this gap is NOT blocking. |
| `daily_fib_retracement` | Economic calendar for the news-avoidance filter | Implement now with reduced coverage (no news filter), and revisit once a calendar feed is budgeted. |
| `double_bottom_measured_move` | AUD_CAD (documented example pair) | Implement now with reduced coverage; add AUD_CAD to the Wave-1 overnight backfill as a cheap opportunistic extra, but do not block Wave 2 on it. |
| `h4_box_breakout` | AUD_JPY, CHF_JPY, CAD_JPY | Implement now with reduced coverage, and queue the three missing JPY crosses for ingestion alongside the Wave-1 batch. |
| `h4_crossover_21_89_macd` | GBP_CHF, EUR_CHF | Implement now with reduced coverage (10 of 12 pairs), and add the two CHF crosses via the standard Wave-1 ingest procedure when convenient — do not defer, do not drop. |
| `ma_crossover_swing` | XAU_USD — deliberate platform policy exclusion | Implement now with reduced coverage — run the strategy on the three live FX pairs it names (EUR_USD, GBP_USD, USD_JPY) and record XAU_USD as excluded. |
| `mtf_swing_weekly_pivots` | Index instruments — out of platform scope | Implement now with reduced coverage (FX majors only). |
| `smash_days` | GBP_NZD, NZD_CHF (plus ~15 unnamed crosses of the 28-pair basket) | Implement now with reduced coverage. The strategy is fully specified and testable today on the 5 live pairs (AUD_USD, USD_CAD, EUR_USD, GBP_USD, USD_JPY), and coverage rises to 13 cells automatically  |
| `strong_weak_analysis` | 15 of 28 major crosses needed for the full strength matrix | Implement now with reduced coverage, and trigger the missing-cross ingest in parallel. |
| `sunday_breakout` | EUR_JPY (Wave-1 pending); W1 staleness caps the ATR knowability horizon | Implement now with reduced coverage. Run the strategy on GBP_USD immediately (all required granularities exist back to 2006). |
| `three_candle_swing_reversal` | H12 granularity (D1 chosen instead); GBP_CAD, GBP_NZD; XAU_USD excluded | Implement now with reduced coverage. The strategy is fully testable today on D1 with EUR_USD, USD_CAD, USD_JPY (live) plus NZD_USD (Wave-1 pending, not a gap). |
| `weekly_gap_fade` | GBP_JPY (Wave-1 pending); no historical spread series (1.0-pip cost-model proxy, flagged) | Implement now with reduced coverage. Nothing here blocks the build: the spec (`SPEC-weekly_gap_fade.md`) runs today on USD_JPY plus EUR_USD, GBP_USD, AUD_USD, USD_CAD, and it degrades gracefully — the |
| `weekly_range_reversal` | GBP_CAD — the author's headline pair | Implement now with reduced coverage — and add GBP_CAD to the Wave-1 ingestion list as a ninth pair. |
| `xard_ma_cross_daily_open` | XAU_USD — deliberate platform policy exclusion | Implement now with reduced coverage (FX pairs only); do not chase XAU_USD. |

---

## Group 1 — Blocking external feeds (start ingestion now; defer signals until data lands)

### usd_carry_basket

**Strategy:** Quantpedia Dollar Carry Trade (USD vs developed-currency basket) — row 5 of forex_swing_strategies.csv
**Companion spec:** `SPEC-usd_carry_basket.md`

#### Recommendation

**Status: BLOCKING — the strategy can emit zero orders until this gap is closed.**

**Defer live signal generation until the rate data lands — but start the ingestion now,
because it is nearly free, and implement the strategy spec in parallel against the
`fact_macro_rates` schema proposed below.**

Reasoning, in order:

1. **Do not implement with a price proxy.** A momentum/trend stand-in measures a different
   factor (see "Impact if we proceed without it" below). Shipping it under the name "Dollar
   Carry Trade" would attach the source's HIGHLY_RECOMMENDED conviction and Sharpe 0.66 to
   an artefact that has earned neither — exactly the kind of silent substitution this
   initiative's causality rules exist to prevent.
2. **Do not drop.** This is one of the few academically anchored rows in the CSV (Lustig–
   Roussanov–Verdelhan; Quantpedia "Strong"; 26-year documented track record), it is
   explicitly described as *loosely correlated with conventional carry* — i.e. additive to
   the existing FX book — and its monthly cadence fits the D1/H4/W1 infrastructure with no
   exotic requirements. Dropping a defensible, diversifying strategy over a solvable data
   plumbing task would be the worst outcome.
3. **The blocker is cheap to remove.** FRED and OECD are free, daily, programmatic, and
   cover every required currency. This is a one-to-two-day ingestion build, not a data
   purchase decision. Only the Bloomberg/Refinitiv "exact forward discount" upgrade carries
   real cost, and the methodology does not require it.
4. **Proceed at reduced pair coverage** (5 pairs now, 7 after Wave 1, 10 if/when Scandies
   are added) with the AFD recomputed over the traded universe — the spec (§10 row 3)
   records why renormalising beats waiting for all ten.

#### What is missing

Two distinct gaps, in order of severity:

**1. Interest-rate / forward-discount series (the signal itself — nothing to trade without it):**

| Series | Currencies needed | In DB? |
|---|---|---|
| 3-month US Treasury rate (daily, annualised) | USD | No |
| 3-month rates (or 3-month forward points, convertible to implied yield) | EUR, GBP, JPY, AUD, CAD — the 5 tradeable currencies | No |
| Same, for the pending Wave-1 additions | NZD, CHF | No |
| Same, for the full documented basket | DKK, NOK, SEK | No |

`DATA_AVAILABILITY.md` is explicit: "Non-price data — none of it exists. No COT positioning,
no economic calendar, no options data, no VIX, no DXY series…" There are no rate tables,
no forward curves, no proxy.

**2. Basket pairs (coverage gap — strategy is tradeable at reduced coverage without them):**

- USD_DKK, USD_NOK, USD_SEK — not in the DB **and not in the Wave-1 additions list**. These
  are the three Scandinavian legs of the 10-currency basket and require a new ingestion
  decision (OANDA practice supports USD/NOK and USD/SEK; USD/DKK availability should be
  confirmed with the broker feed before promising it).
- NZD_USD, USD_CHF — planned Wave-1 additions; backfill may be incomplete when Wave 2 runs.
  The spec treats them as conditional.

#### Why the strategy needs it (quoted from the CSV)

> **data_requirements:** "OHLCV FX spot/forward rates|3-month US Treasury rate|3-month rates (or forward discounts) of basket currencies"

> **entry_logic_long:** "Compute equal-weighted average forward discount (AFD) of the 10-currency basket vs USD (average 3-month foreign rate can substitute); if 3-month US Treasury rate > AFD go LONG USD and short the equal-weighted basket"

The entire entry condition is a comparison of two rate levels. OHLCV prices — the only data
we have — enter the strategy only through the contract-required ATR stop. Without the rate
series there is no signal, no direction, and nothing to backtest.

#### How it could be obtained

**US 3-month rate (easy, free):**
- **FRED** `DGS3MO` (3-Month Treasury Constant Maturity) or `DTB3` (3-Month T-Bill secondary
  market), daily, back to 1982/1954 respectively. Free REST API, public domain, publication
  lag ~1 business day. This is the obvious primary source.

**Foreign 3-month rates (free but heterogeneous):**
- **OECD Main Economic Indicators / short-term interest rates** (3-month interbank or T-bill
  per country): EUR area, UK, Japan, Australia, Canada, New Zealand, Switzerland, Denmark,
  Norway, Sweden all covered. Free API (SDMX), monthly or daily depending on series; some
  series end or change definition around LIBOR cessation (2021–2023) — needs a mapping to
  successor benchmarks (€STR/SONIA/TONA/SARON/SOFR term rates, or national 3-month T-bill
  yields).
- **National central banks** (ECB, BoE, BoJ, RBA, BoC, RBNZ, SNB, Danmarks Nationalbank,
  Norges Bank, Riksbank): authoritative 3-month T-bill or interbank series, free, mixed
  formats and cadences. Higher integration cost per currency; use OECD where it suffices.
- **FRED** also carries a handful of foreign series (e.g. some OECD-sourced rates) —
  worth checking before writing ten national-bank ingesters.

**Forward discounts (the academically exact input — costly):**
- **Bloomberg BGN / Refinitiv (LSEG)** 3-month FX forward points for all 10 pairs;
  implied rate differential = `(F/S − 1) × (12/3)`. Institutional licences — material cost
  (five figures p.a. per terminal-class feed) and redistribution restrictions that may
  conflict with storing derived series in a research DB. Given CIP, this adds precision
  (exact forward-implied differential, no benchmark-definition drift) but not concept.
- Cheaper middle path: **Dukascopy / TrueFX / broker forward quotes** — quality and history
  depth are poor for a 20-year backtest; not recommended for the primary series.

**Realistic recommendation on sources:** FRED for USD + OECD/national-bank series for the
nine foreign currencies. Zero licence cost, sufficient history (most series reach the
1980s–1990s), and the Quantpedia methodology explicitly permits the rate substitute.
Bloomberg/Refinitiv forward points are the upgrade path, not the entry ticket.

#### Recommended integration

Concrete, minimal, reversible:

1. **New table `fact_macro_rates`** (research-side; the "nothing writes to `fact_*`" rule
   applies to strategy code — ingestion jobs are the sanctioned writers):
   - `series_id` (e.g. `US_3M_TBILL`, `EUR_3M_INTERBANK`, …), `obs_date` (date the rate
     refers to), `publish_date` (first date the value was publicly knowable — **required**;
     the spec's causality rule consumes `publish_date`, not `obs_date`), `value` (annualised
     %), `source`, `ingested_at`.
   - Primary key `(series_id, obs_date, publish_date)` so revisions are kept, not
     overwritten — vintage-aware from day one, avoiding the classic revised-macro
     look-ahead bug.
2. **Ingest path:** one small scheduled job per source family — `fred_rates_ingest.py`
   (US) and `oecd_rates_ingest.py` (foreign, with a per-country series mapping table).
   Daily cron after the FX ingest; resumable by `MAX(obs_date)` like the price ingest.
   ~20 series × ~10k rows: trivial volume by the standards of `fact_market_prices`.
3. **Access:** extend `research_data.py` with a read-only
   `load_rate_series(series_id, as_of=None)` that filters on `publish_date <= as_of` — the
   causality contract enforced in the data layer, so 51 strategy authors cannot get it
   wrong individually.
4. **Pairs:** confirm broker availability of USD_DKK/USD_NOK/USD_SEK; if supported, add to
   the Wave-1-style pair backfill queue (they serve other strategies too — Scandies appear
   nowhere else in the 13-pair plan, so this is the only row demanding them).

#### Impact if we proceed without it

If the gap is ignored and a price-only substitute is traded, the backtest would measure
**trend/momentum, not carry**. Carry and momentum are distinct, empirically
weakly-correlated FX factors: carry pays for holding high-rate currencies; momentum pays
for buying recent winners. They coincide often enough (rate differentials persist, so
carry signals drift slowly and prices trend) to *look* similar in a short sample, and
diverge precisely when it matters — carry crashes (2008, March 2020) are episodes where
high-rate currencies gap down and momentum whipsaws late. A momentum proxy backtest would
therefore (a) flatter or slander the strategy depending on which regime dominates the test
window, (b) fail to reproduce the documented low correlation to conventional carry that is
the strategy's portfolio value, and (c) contaminate cross-strategy correlation analysis in
the research sandbox by silently duplicating whatever momentum strategies already exist in
the 51-row set. It is still *informative* — as a momentum strategy, under its own name,
with its own conviction rating. It is not informative about the Dollar Carry Trade.

The only costless-without-rates artefact worth producing now is the scaffold: pair-universe
gating, monthly decision calendar, ATR-stop and time-exit wiring — all verifiable against
synthetic rate fixtures. Every verdict on edge waits for `fact_macro_rates`.

---

### currency_value_ppp

**Strategy:** Quantpedia Currency Value Factor — PPP Strategy (row 44 of forex_swing_strategies.csv)
**Companion spec:** `SPEC-currency_value_ppp.md`

#### Recommendation

**Status: BLOCKING — the strategy can emit zero orders until this gap is closed.**

**Defer live signal generation until the PPP and CPI data land — but start the ingestion now,
because it is nearly free, and implement the strategy spec in parallel against the
`fact_macro_ppp` / `fact_macro_cpi` schema proposed below.**

Reasoning, in order:

1. **Do not implement with a price-only proxy.** A deviation-from-rolling-mean or
   deviation-from-anchor stand-in measures sample-anchored long-horizon mean reversion, not
   PPP value (see "Impact if we proceed without it" below). Shipping it under the name
   "Currency Value Factor — PPP" would attach the source's academic pedigree and documented
   1989–2009 track record to an artefact that has earned neither — exactly the kind of
   silent substitution this initiative's causality rules exist to prevent.
2. **Do not drop.** This is one of the few academically anchored rows in the CSV (PPP value
   is a canonical FX factor — Aloosh/Bekaert, Deutsche Bank source paper; Quantpedia
   documents 1989–2009 indicative 7.82% p.a., Sharpe 0.36), it claims low/negative
   correlation to equities in stress — a hedge property with genuine portfolio value — and
   its quarterly cadence fits the D1/H1 infrastructure with no exotic execution requirements.
   Dropping a defensible, diversifying factor over a solvable data-plumbing task would be the
   worst outcome.
3. **The blocker is cheap to remove.** The OECD SDMX API is free, programmatic, and covers
   both PPP and CPI for every required currency; national statistics offices and FRED are
   free fallbacks. This is a one-to-three-day ingestion build (the PPP vintage/publication-date
   handling is the only subtle part), not a data-purchase decision. Only the
   Bloomberg/Refinitiv "exact release-vintage" upgrade carries real cost, and the
   conservative fixed-lag convention in the spec (§8.2/§9) makes even that optional.
4. **Proceed at reduced pair coverage** (5 currencies now, 7 after Wave 1) with the terciles
   computed verbatim over the traded universe — the spec (§10 row 2) records why keeping the
   top-3/bottom-3 rule with overlap netting beats retuning or waiting for all ten.

#### What is missing

Two distinct gaps, in order of severity:

**1. Macro valuation series (the signal itself — nothing to trade without them):**

| Series | Coverage needed | Cadence / history | In DB? |
|---|---|---|---|
| OECD Purchasing Power Parities, foreign currency per USD | EUR, GBP, JPY, AUD, CAD (live) + NZD, CHF (Wave-1 pending) + DKK, NOK, SEK (full G10) | Annual; ideally back to the 1980s to cover the DB's 2006–2026 price history plus warm-up; **publication/vintage dates required** (PPPs are revised) | No |
| CPI index levels (monthly), per currency **including USD** | Same currency list + USD | Monthly; back to ≥1990; publication dates or a defensible uniform lag | No |

`DATA_AVAILABILITY.md` is explicit: "Non-price data — none of it exists. No COT positioning,
no economic calendar, no options data, no VIX, no DXY series…" There are no PPP tables, no
CPI tables, no macro calendar. `fact_macro_events` exists but is not populated for this
purpose.

**2. Basket pairs (coverage gap — strategy is tradeable at reduced coverage without them):**

- USD_DKK, USD_NOK, USD_SEK — not in the DB **and not in the Wave-1 additions list**. These
  are the three Scandinavian G10 legs and require a new ingestion decision (OANDA practice
  supports USD/NOK and USD/SEK; USD/DKK availability should be confirmed with the broker
  feed before promising it).
- NZD_USD, USD_CHF — planned Wave-1 additions; backfill may be incomplete when Wave 2 runs.
  The spec treats them as conditional.
- The Wave-1 cross pairs (GBP_JPY, EUR_JPY, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD) add no new
  currency-vs-USD series and are irrelevant here.

#### Why the strategy needs it (quoted from the CSV)

> **data_requirements:** "OECD Purchasing Power Parity figures|monthly CPI changes|OHLCV FX rates"

> **entry_logic_long:** "Compute fair PPP value per currency from latest OECD PPP updated with monthly CPI and FX changes; go LONG the 3 most undervalued currencies (lowest PPP fair value) vs USD, equal weight"

The entire entry condition is a comparison of spot prices against a PPP-derived fair value.
OHLCV prices — the only data we have — enter the strategy through the spot half of the
misvaluation ratio and the contract-required ATR stop. Without the PPP and CPI series there
is no fair value, no misvaluation, no ranking, and nothing to backtest. (Note: the spec
resolves the pseudocode's undefined "FX changes" update term to the standard relative-PPP
formula — fair value drifts with the foreign-vs-US CPI differential, so USD CPI is required
too; SPEC §10 row 4.)

#### How it could be obtained

**OECD SDMX API (primary recommendation — free, one integration):**
- OECD publishes PPPs (benchmark and annual series, national-currency-per-USD) and monthly
  CPI (Main Economic Indicators) for all ten G10 currencies via the free SDMX REST API
  (`sdmx.oecd.org`), with history back decades. One ingester covers both series families and
  all currencies. Licence: free for use, attribution required.
- Caveat that drives the schema below: OECD PPPs are **revised** (benchmark rebasing every
  few years rewrites history), and release timing is irregular (~1–3 years after the
  reference period). The ingest must capture *publication vintage*, or the spec's fixed
  24-month lag assumption (SPEC §8.2/§9) is the governing fallback.

**National statistics offices (free, heterogeneous — fallback/supplement for CPI):**
- US BLS (CPI), Eurostat (HICP), UK ONS, Japan Statistics Bureau, StatCan, ABS, SNB, RBNZ —
  all free, all with real release calendars (~2–4 weeks after month-end). Ten different
  formats; use only where OECD MEI coverage or timeliness is inadequate.
- **FRED** carries many of these series (e.g. `CPIAUCSL` for the US, plus OECD-sourced CPI
  for several countries) and — uniquely valuable — **ALFRED vintage dates** for US series,
  giving true publication-time data for the USD leg. Free REST API.

**Bloomberg / Refinitiv (paid path — optional upgrade):**
- Exact release-vintage PPP/CPI history and economist-consensus release calendars.
  Institutional licences — material cost (five figures p.a. per terminal-class feed) and
  redistribution restrictions that may conflict with storing derived series in a research
  DB. Adds precision (true publication timestamps for every country, no fixed-lag
  assumption), not concept. Not required: the spec is deliberately written so a fixed
  conservative lag (CPI +1 month, PPP +24 months) is causally safe without vintage data.

**Realistic recommendation on sources:** OECD SDMX for both PPP and CPI across all ten
currencies, FRED/ALFRED as cross-check and for US vintages. Zero licence cost, history deep
enough to cover the full 2006–2026 price backtest with warm-up.

#### Recommended integration

Concrete, minimal, reversible:

1. **New tables** (research-side; the "nothing writes to `fact_*`" rule applies to strategy
   code — ingestion jobs are the sanctioned writers):
   - `fact_macro_ppp`: `series_id` (e.g. `PPP_EUR_USD_OECD`, …), `ref_year` (year the PPP
     refers to), `publish_date` (first date the value was publicly knowable — **required**;
     the spec's causality rule consumes `publish_date`, not `ref_year`; where the source
     gives no vintage, store `ref_year + 24 months` as the synthetic publish date, matching
     the spec's conservative assumption), `value` (foreign currency per 1 USD), `source`,
     `ingested_at`. Primary key `(series_id, ref_year, publish_date)` — revisions kept, never
     overwritten. Vintage-aware from day one, avoiding the classic revised-macro look-ahead
     bug.
   - `fact_macro_cpi`: `series_id` (e.g. `CPI_US`, `CPI_EUR`, …), `ref_month`,
     `publish_date` (real release date where known; else `ref_month + 1 month` synthetic,
     matching the spec's one-month lag), `index_value`, `source`, `ingested_at`. Primary key
     `(series_id, ref_month, publish_date)`.
2. **Ingest path:** one small scheduled job per source family — `oecd_sdmx_ingest.py` (PPP
   + CPI for all currencies, with a per-country series-mapping table) and optionally
   `fred_cpi_ingest.py` (US + cross-checks). Monthly cron after the FX ingest; resumable by
   `MAX(ref_period)` like the price ingest. Volume is trivial by `fact_market_prices`
   standards: ~10 PPP series × ~40 years × a few vintages + ~10 CPI series × ~400 months.
3. **Access:** extend `research_data.py` with a read-only
   `load_macro_series(table, series_id, as_of=None)` that filters on `publish_date <= as_of`
   — the causality contract enforced in the data layer, so strategy authors cannot get the
   vintage rule wrong individually.
4. **Pairs:** confirm broker availability of USD_DKK/USD_NOK/USD_SEK; if supported, add to
   the Wave-1-style pair backfill queue (these serve other G10-basket strategies in the
   51-row set as well — the carry and momentum factor rows demand the same three).

#### Impact if we proceed without it

If the gap is ignored and a price-only substitute is traded, the backtest would measure
**sample-anchored long-horizon mean reversion, not PPP value**. The natural proxies —
deviation of spot from an N-year rolling mean, or from a fixed historical anchor rate — fail
in specific, demonstrable ways:

1. **They ignore inflation differentials, which are the strategy's entire update mechanism.**
   Relative PPP says fair value *drifts* with the foreign-vs-US CPI differential. A price
   mean does not drift with fundamentals; over a 20-year window containing the post-2010
   low-inflation regime and the 2021–2023 inflation spike, a fixed anchor or rolling mean
   mislabels fair value in exactly the episodes where PPP value would have moved most.
2. **They are window-dependent.** "Deviation from a 5-year rolling mean" changes sign
   depending on the arbitrary window; PPP fair value is pinned by an external measurement.
   The proxy's ranking — the whole signal — is an artefact of the lookback choice.
3. **They flatter or slander by regime.** In range-bound decades the proxy looks like the
   factor; in trending decades (USD cycles 2014–2016, 2021–2022) "distance from the mean" is
   just anti-momentum, and the proxy silently correlates with whatever reversal strategies
   already exist in the 51-row set — contaminating cross-strategy correlation analysis.
4. **The hedge property is untestable anyway.** The source's "low/negative correlation to
   equities in stress" claim cannot be verified on any implementation without an equity
   series, which also does not exist in the DB; it remains a reporting claim from the
   source's backtest, recorded in SPEC §8.6, not a testable property here.

A price-proxy backtest is still *informative* — as a long-horizon reversal strategy, under
its own name, with its own conviction rating. It is not informative about the Currency Value
Factor.

The only costless-without-macro-data artefact worth producing now is the scaffold: pair-
universe gating, quarterly decision calendar, misvaluation/ranking/netting arithmetic against
synthetic PPP/CPI fixtures, ATR-stop and 63-bar time-exit wiring. Every verdict on edge
waits for `fact_macro_ppp` and `fact_macro_cpi`.

---

### financial_regime_index

#### Recommendation

**DEFER — do not implement in Wave 2; revisit only if the macro-ingest is built anyway.** This is the deepest data gap in the CSV: the strategy's entire signal is computed from **nine external daily series, none of which exist in the database and none of which are obtainable through the existing OANDA FX ingest**. Three further reasons compound the data cost:

1. **The author's own conviction is EXPERIMENTAL, with explicitly no performance claims** ("the edge is unverified … the author makes no performance claims"). We would be buying nine feeds and a cross-calendar alignment engine to test a hypothesis its own author does not vouch for.
2. **The signal thresholds are unknown.** The long threshold, always-long floor, and exit lines are Pine-script inputs not reproduced in the CSV. The SPEC declares reconstructed conventions (+0.50 / +1.00 / 0.00 / −0.50 / 0.00), but before any results are trusted, the published script's defaults should be extracted from the TradingView page and substituted. Until then, even a perfect backtest measures a parameterisation we invented.
3. **The cost is real but bounded.** All nine series are available free (stooq / Yahoo Finance for ETF and index closes; FRED for yields, VIX and a DXY proxy). The engineering is a new ingest path plus holiday/calendar alignment against the 24/5 FX clock — roughly a 1–2 day build, but it is a *new class* of data (non-OANDA, non-FX, US-market-calendar) that nothing else in the 51-strategy set needs.

**Do not DROP yet**: the data is free, the SPEC is fully written and implementable the day the series land, and the macro composite may be reusable as a regime filter for other strategies later. **Do not implement now**: defer until (a) the macro ingest exists for its own sake, and (b) the Pine defaults are recovered. If neither happens by the end of the initiative, drop quietly — nothing else depends on this row. A pragmatic middle path if the initiative wants an early read: prototype the composite offline in a notebook against stooq/FRED CSVs before committing to a schema.

#### What is missing

**Nine external daily series** (signal inputs — blocking):

| Series | Role in composite | In DB? |
|---|---|---|
| SPY (S&P 500 ETF) daily close | EQ_US component | No — not FX, not in `dim_asset` |
| ACWI (MSCI world ETF) daily close | EQ_WORLD component | No |
| HYG (high-yield bond ETF) daily close | CREDIT component (HYG/LQD) | No |
| LQD (investment-grade bond ETF) daily close | CREDIT component | No |
| VIX daily close | VIX component (sign-flipped) | No — explicitly listed as absent in DATA_AVAILABILITY.md |
| DXY (dollar index) daily close | USD component (sign-flipped) | No — explicitly listed as absent |
| US02Y (2-year Treasury yield) daily | Y2 component (sign-flipped) | No |
| US10Y (10-year Treasury yield) daily | SLOPE component (10Y−2Y) | No |
| BIL (1–3 month T-bill ETF) daily close | LIQ component (BIL/SPY, sign-flipped) | No |

**Three non-FX execution targets** (secondary — the three FX majors in the stated scope are live, so this does not block by itself): SPY and ES futures (not FX instruments, not in `dim_asset`, not obtainable via OANDA FX ingest), and gold/XAU_USD (deliberately excluded by policy — pip/margin conventions assume FX).

#### Why the strategy needs it

The CSV is unambiguous that the composite *is* the strategy:

- `data_requirements`: "Macro multi-asset series: SPY|ACWI|HYG|LQD|VIX|DXY|US02Y|US10Y|BIL daily closes|z-scored log returns|price SMA filter"
- `entry_logic_long`: "Composite BFCI (inverse-volatility-weighted, optionally winsorized z-scores of 8 macro components with sign flips for credit, 2Y yield, DXY, VIX, BIL/SPY liquidity) crosses above long threshold …"

Without these series there is no BFCI, no trigger, and no slope gate — only the SMA200 price filter survives, which is a generic trend-follower, not this strategy. **Substituting FX-derived risk-on/off proxies (e.g. AUD/JPY as a sentiment gauge) was considered and rejected**: it would silently test a different hypothesis, violating the no-invented-data rule. There is no honest reduced-coverage version.

#### How it could be obtained

All nine are free at daily granularity; **none come from OANDA v20** (the existing ingest is FX-candles only), so a new loader is required either way.

| Series | Cheapest source | Licence / cost | Notes |
|---|---|---|---|
| SPY, ACWI, HYG, LQD, BIL daily closes | stooq CSV (`https://stooq.com/q/d/l/?s=spy.us&i=d`, same pattern for acwi.us, hyg.us, lqd.us, bil.us) — no key, scriptable | Free for personal/research use; no redistribution | Use adjusted/total-return closes where offered — HYG/LQD/BIL pay large distributions, and price-only returns would badly misstate the CREDIT and LIQ components. Yahoo Finance (`yfinance`, `^`-style download) is the fallback; unofficial API, ToS restrict redistribution/scraping at scale — fine for a research snapshot. Paid, cleaner alternatives if this graduates beyond research: Tiingo (~$10/mo) or Polygon (~$29/mo) for adjusted ETF history |
| VIX daily close | CBOE official CSV (`https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv`) or FRED `VIXCLS` | CBOE: free download, redistribution restricted — store values, don't republish; FRED: free, public API | Prefer FRED `VIXCLS` for a single uniform loader |
| DXY daily close | stooq (`dx.f` / `dx` symbols) or Yahoo (`DX-Y.NYB`) | DXY itself is an ICE-licensed index; vendor redistribution restricted | **Methodological caveat:** if licensing is a concern, FRED `DTWEXBGS` (broad trade-weighted dollar, daily, free, US-government work) is a legitimate but *different* series — the USD component would measure a broader basket. Flag whichever is chosen in the spec's §10. SPEC as written assumes ICE DXY composition |
| US02Y | FRED `DGS2` (daily, constant maturity) | Free; FRED API needs a no-cost key | Not revised (no vintage problem) |
| US10Y | FRED `DGS10` | Free | As above |

Recommended single-vendor path: **FRED for DGS2, DGS10, VIXCLS (and optionally DTWEXBGS); stooq for the five ETF closes.** Two small loaders, no licence spend.

**Alignment/calendar issues (the real engineering cost):**
- US markets run ~252 days/yr with holidays (plus early closes); FX runs 24/5. The composite must be forward-filled onto the FX D1 calendar using only observations whose US trading day has **closed**, with the conservative +1-day availability shift declared in SPEC §9 (absorbs the 20:00/21:00 UTC DST ambiguity around the FX day boundary).
- A staleness guard (SPEC §8: no entries if the newest macro observation is > 10 calendar days old) covers holiday clusters and silent feed outages.
- Vintage: ETF/index/yield series are not revised, so a simple `asof` join suffices; a vintage column is still recommended for auditability and future macro series that *are* revised.

#### Recommended integration

1. New table **`fact_macro_series`**: `(series_id TEXT, obs_date DATE, value DOUBLE, vintage_date DATE DEFAULT CURRENT_DATE, source TEXT, pulled_at TIMESTAMPTZ, PRIMARY KEY (series_id, obs_date, vintage_date))` — deliberately separate from `fact_market_prices` (different calendar, different provenance, non-OANDA licence terms).
2. New ingest module (e.g. `src/system1/ingestion/macro_series_ingest.py`) with two loaders: FRED (series id list `DGS2, DGS10, VIXCLS`) and stooq (`spy.us, acwi.us, hyg.us, lqd.us, bil.us`, adjusted closes). Resumable via `MAX(obs_date)` per series, mirroring the existing FX ingest pattern. Overnight backfill: FRED from 1990; stooq histories start at ETF inception (BIL 2007-05, ACWI 2008-03, HYG/LQD 2007-04) — **effective composite history starts ~2008**, so the 2006–2008 FX history is unusable for this strategy; note this in the backtest report.
3. Research accessor beside `research_data.load_ohlcv_readonly`: `load_macro_series(series_ids, start, end)` returning a date-indexed frame; the strategy joins it onto the FX D1 index with the SPEC §9 shift. Read-only, like everything else in the research sandbox.
4. Extract the Pine script's threshold defaults from the TradingView source page and, if they differ from the SPEC's reconstructed +0.50/+1.00/0.00/−0.50/0.00, amend the SPEC before Wave 2 runs it.

#### Impact if we proceed without it

There is **no meaningful reduced-coverage run**. Dropping components changes the weighting and sign structure of every remaining z-score (inverse-vol weights renormalise over a different set), so a "partial BFCI" backtest would measure a different composite and could not be cited for or against the strategy. The only executable residue is the SMA200 trend gate, which is not this strategy and would flatter or damn it by accident.

The cost of deferral is correspondingly low: one EXPERIMENTAL strategy out of 51 waits, and the three FX majors it would trade are already covered by ~19 other rows. The cost of *implementing* without the data — or with silent FX proxies — is a contaminated result worse than none. Defer; build the macro ingest if and when it earns its keep across more than one strategy; extract the Pine defaults at the same time; then run the SPEC exactly as written.

---

### retail_sentiment_fade

#### Recommendation

**Defer the backtest until sentiment data accumulates — but start forward ingestion immediately, and implement the strategy code now.** There is no reduced-coverage option: the signal IS the external feed, and zero rows of sentiment data exist in the DB, so running the backtest today would measure nothing (not a degraded version of the strategy — literally zero trades). Do not drop the strategy: the spec is mechanically complete, the behavioural hypothesis is legitimate and distinctive (the only alternative-data strategy in the 51-row fleet), and the fix is cheap — a daily/hourly snapshot ingest into a new `fact_sentiment` table. The realistic timeline to a first statistically thin evaluation is 12–24 months of forward accumulation; a 36-month-training walk-forward fold cannot be satisfied before ~3 years of history exist. That is arithmetic, and the eventual report must say so rather than presenting a thin result as a verdict.

#### What is missing

- **Per-pair retail long/short ratio time series** for EUR_USD, GBP_USD, USD_JPY (and any future pairs): percent of open retail positions long and short, count-of-positions basis.
- **Cadence needed:** at least one snapshot per day; hourly preferable (cheap to store, enables tighter lag assumptions later). The SPEC's conservative assumption is a **24-hour minimum publication-to-use lag** (§9 rule S1).
- **Causality-critical fields:** each record must carry the vendor's nominal observation timestamp AND the publication/ingest timestamp — sentiment vendors publish with lag and sometimes restate values, so "when could we have known this number" is the whole ballgame for an honest backtest.
- Nothing else is missing: all three named pairs have full D1/H1 price history; SMA/ATR are in the indicator inventory. This is purely a non-price feed gap (DATA_AVAILABILITY: "No COT positioning, no economic calendar... no news sentiment").

#### Why the strategy needs it

The CSV's `data_requirements` field: **"OHLCV|Retail long/short ratio via Ziwox JSON API|Fast and slow SMA"**, and both entry conditions are gated on the external series: *"If Retail Short Ratio >= 60% (crowd heavily short) ... BUY contrarian"* and mirror. Without the ratio series there is no signal to implement — every trade decision reads the feed.

#### How it could be obtained

| Source | What it offers | Licence / availability (honest assessment) |
|---|---|---|
| **Ziwox API** (the source's vendor) | REST/JSON retail-sentiment endpoint; free API key after Ziwox Terminal registration; also bundles COT and "fundamental bias" data | **Small vendor, informal terms, continuity risk.** Historical depth is undocumented — appears to serve current/near-current snapshots, not deep history. Suitable as the forward-ingest source (it is what the strategy documents), unsuitable for backfill. |
| **OANDA open position ratios** | Retail long/short ratios for OANDA's own client book — the same broker our price data comes from | Historically published via OANDA Labs with ~1 year of history; availability via the documented v20 REST API is **uncertain** (labs endpoints have been moved/retired over time — needs hands-on verification before relying on it). If available, cheapest option: already have OANDA credentials. |
| **Myfxbook Community Outlook** | Long/short %, volumes, avg entry prices across 70+ symbols | Official sentiment API: **$50/month or $500/year**, ≤2,880 requests/day, **no historical download** (community feature requests outstanding) — forward accumulation only. Unofficial scrapers exist (e.g. Apify actor) — ToS risk; not recommended for a system of record. |
| **IG client sentiment** | IG client positioning, surfaced via DailyFX | IG Labs API is free with an IG account (live or demo); historical depth limited. Reasonable secondary/cross-check source. |
| **Dukascopy SWFX Sentiment Index** | Public count-based sentiment on SWFX marketplace participants | Free, public web endpoints with some historical series — the best candidate for partial backfill, but it measures Dukascopy's crowd, not Ziwox's. |
| **Derivable from existing data?** | — | **No.** There is no honest derivation of retail positioning from OHLCV. A price-momentum or tick-volume proxy would be a different strategy wearing this one's name. Explicitly rejected (SPEC §8). |

#### Recommended integration

1. **Schema:** new table `fact_sentiment`:
   `(asset_id INT REFERENCES dim_asset, source TEXT, observed_at TIMESTAMPTZ, published_at TIMESTAMPTZ, ingested_at TIMESTAMPTZ DEFAULT now(), long_ratio_pct NUMERIC, short_ratio_pct NUMERIC, basis TEXT CHECK (basis IN ('positions','volume')), sample_size INT NULL, PRIMARY KEY (asset_id, source, observed_at))`.
   `published_at` is non-negotiable — the SPEC's causality rule reads `published_at ≤ decision_time − 24h`. Write path belongs to ingestion only (research modules never write `fact_*`).
2. **dim_asset:** no change — sentiment rows reference existing asset_ids 1/2/3 (EUR_USD, GBP_USD, USD_JPY).
3. **Ingest job:** new `sentiment_ingest.py` modelled on the existing OANDA ingest pattern: poll the Ziwox JSON API (primary) hourly, snapshot every poll (never overwrite — restatements become new rows keyed by `observed_at`/`ingested_at`), run via cron. Optionally add OANDA position ratios as a second `source` row per observation for cross-vendor validation.
4. **Strategy wiring:** the Wave-2 implementation loads `fact_sentiment` through a read-only accessor alongside `load_ohlcv_readonly`, applies the 24h eligibility rule, and otherwise follows the SPEC verbatim.

#### Impact if we proceed without it

There is no "without it" that measures this strategy: zero sentiment rows → zero signals → an empty trade frame. A backtest run before ingestion starts is not degraded, it is vacuous. If we instead substitute a price-derived proxy, the backtest would measure a momentum/mean-reversion strategy and falsely carry this strategy's name — worse than no result, because it could be promoted or killed on evidence about a different system. The correct interim posture: implement the code against `fact_sentiment` now (unit-testable with synthetic sentiment fixtures), start ingestion now, and treat the strategy as EXPERIMENTAL-in-accumulation until ≥12–24 months of snapshots exist. Even then, the first walk-forward evaluation will return `low_confidence` on trade count — which is the expected, honest verdict for a slow daily signal on a young dataset.

---

## Group 2 — Defer backtest until a cheap ingest lands

### three_ducks

#### Recommendation

**Defer implementation until M5 data lands — and ingest M5 now via the existing OANDA v20
path.** This is a scheduling problem, not a data-availability problem: the feed, the ingest
code, and both named pairs already exist; the gap is one overnight-class backfill job plus
admitting "M5" into two granularity allow-lists.

- **Do NOT port the trigger to H1.** An H1-substituted variant (cross of the H1 60 SMA +
  20-bar H1 breakout with a 25-pip stop) is a *different strategy*: ~12× fewer bars, a
  different noise structure, and a stop that is sub-noise at H1 resolution (H1 ranges
  routinely exceed 25 pips, so F5 stop-first resolution would dominate in a way the
  M5-native strategy never experiences). Publishing that result under this strategy's
  name is exactly the "measures something that is not the strategy" failure contract v2
  exists to prevent. If leadership wants that variant, it should be specified and reviewed
  as its own strategy row.
- **Do NOT drop.** The system is a documented classic, the H4/H1 ducks are fully supported
  today, and the missing piece is cheap and mechanical to obtain.
- **Sequence:** (1) ingest M5 for EUR_USD and GBP_USD; (2) admit "M5" into contract v2
  `VALID_GRANULARITIES` and `research_data._ALLOWED_GRANULARITIES`; (3) implement
  `SPEC-three_ducks.md` exactly as written — every M5-dependent rule is already marked
  **[M5-BLOCKED]**, so no re-specification is needed on the day data lands.

#### What is missing

- **M5 OHLCV history** for EUR_USD and GBP_USD (the named pairs) — and for any further
  pairs only if the unbounded "any" in `target_pairs` is ever honoured (the SPEC
  conservatively restricts to the two named pairs).
- **Granularity admission** in the research stack: contract v2
  `VALID_GRANULARITIES = ("H1","H4","D1","W1")` and the loader's allowed set both exclude
  M5. Wave 1 allowed granularities after its work: H1, H4, D1, W1 only.
- **Nearest existing data is unusable:** M15/M30 exist (~511k / ~256k bars/pair,
  2006→2026-05) but are stale ~14 weeks, outside the allowed set — and M15 cannot be
  resampled *down* to M5. Nothing is derivable from current data.

#### Why the strategy needs it

The trigger logic is explicitly M5-scoped; quoting the CSV row:

- `timeframes`: **"H4 (trend)|H1 (confirm)|M5 (trigger)"**
- `data_requirements`: **"OHLCV on H4|H1|M5|60 SMA on all three timeframes"**
- `entry_logic_long`: **"...on M5 buy when price crosses above its 60 SMA, ideally with a
  break of the last M5 swing high"**
- `risk_management`: **"SL below M5/H1 swing low (short-term)… or fixed 25-30 pips"**

The H4/H1 ducks (both current to 2026-08-07) are fully supported today. Only the M5
trigger frame — its 60 SMA, the 20-bar breakout window, and the stop geometry the
25–30 pip option is calibrated to — is blocked. Two of three ducks cannot fly alone.

#### How it could be obtained

- **OANDA v20 REST — cheapest, already built.** OANDA supports granularity "M5"; the same
  `multi_timeframe_ingest` path used for H1/H4/D1/W1 applies unchanged. No new vendor, no
  licence, no schema change.
- **Volume:** ~12× the H1 store (~130k bars/pair) ⇒ **≈1.5M bars/pair** back to 2006
  (≈3× the existing M15 store of ~511k). At the v20 5,000-bars/request cap that is
  ~300 requests/pair; the two named pairs ≈ 600 requests total — an overnight job against
  practice rate limits, resumable via the existing
  `ON CONFLICT ("timestamp", asset_id, granularity)` semantics.
- **Derivation from existing data:** impossible — no current granularity finer than H1
  exists; M15 is stale and 3× too coarse.
- **Other vendors** (Dukascopy tick, TrueFX): unnecessary; would add licensing and a
  second provenance for no benefit.

#### Recommended integration

1. `python -m src.system1.ingestion.multi_timeframe_ingest --granularity M5 --symbol EUR_USD`
   then `--symbol GBP_USD`. (Loop the remaining fleet pairs only if "any" is honoured —
   the SPEC does not require it.)
2. **No `dim_asset` change needed** — both pairs already exist (asset_id 1 and 2);
   granularity is a column, not an asset.
3. Add `"M5"` to `VALID_GRANULARITIES` in `contract_v2.py` and to
   `research_data._ALLOWED_GRANULARITIES`. Decide the loader window: `lookback_years=10`
   (~730k M5 bars/pair) satisfies the walk-forward minimum (36mo train) with ample margin;
   full-2006 history is optional.
4. **simulate_on semantics:** this strategy's native frame (M5) is *finer* than H1, so the
   contract §5 "decide native, resolve on H1" mechanism is inapplicable — fills resolve on
   M5 natively (F5 applies at M5 resolution). The required both-ways delta report becomes
   native-M5 vs H1-aggregated, if wanted.
5. Add M5 to the Saturday refresh cron (which already let W1 lapse ~8 weeks) and record
   freshness monitoring so the new frame does not silently stale.

#### Impact if we proceed without it

There is no honest partial implementation: with M5 absent the strategy emits **zero
orders** and the backtest measures nothing — not a degraded strategy, an empty one. The
only "proceed anyway" option is the H1 trigger variant, which would measure an H1
breakout system wearing this strategy's name and would likely *understate* the design
(its 25-pip stop is below H1 noise). Deferral costs one overnight ingest and two
one-line allow-list edits; that is clearly the right trade.

---

### nzdjpy_median_ma_retrace

#### Recommendation

**Defer the backtest until NZD_JPY data lands; implement the Wave-2 spec now; drop the strategy rather than proxy it if the ingest is declined.** Reasoning, in order:

1. **"Implement now with reduced coverage" is impossible here.** The strategy names exactly one pair, and that pair is missing. Reduced coverage equals zero pairs equals no backtest at all. The spec itself is complete and Wave-2-ready (no interpretive decisions remain), so the code can be written in Wave 2 regardless; only the run is blocked.
2. **Deferral is cheap.** NZD_JPY is a standard OANDA v20 instrument and the ingest pipeline already exists; adding it is one `dim_asset` row plus one more symbol on the already-planned overnight Wave-1 backfill job (~130k H1 bars). Marginal cost is near zero.
3. **Drop is the fallback, and it is a live option.** The CSV itself carries the warnings: curve-fit to a single pair, reward:risk below 1:1 (0.4% TP vs 0.5% SL) resting on an unverified high win rate, and supporting evidence that exists only as chart images. If the operator judges one extra overnight symbol not worth the maintenance surface for a single MODERATE-conviction strategy, dropping loses little. What must **not** happen is silent substitution of NZD_USD or GBP_JPY (SPEC §10 #7) — a proxy backtest would measure a different strategy and attribute the result to this one.

#### What is missing

- **Pair:** NZD_JPY (`target_pairs` reads, verbatim: `NZD/JPY`). It is absent from the 5 live `dim_asset` pairs **and** absent from the 8 Wave-1 additions — a genuine gap, not a pending item.
- **Granularity:** H1 only — the standard granularity the pipeline already produces; nothing exotic.
- **External series:** none. The strategy needs H1 OHLC only (median price and session clock are derivable from OHLCV + timestamps). No rates, calendar, COT, or real-volume requirement exists in this row.

#### Why the strategy needs it

- `target_pairs`: `NZD/JPY`
- `data_requirements`: `H1 OHLCV | MA(5) and MA(50) computed on median price (H+L)/2 | round-hour timestamp filter 07:00-13:00 London`

The strategy is single-pair by design ("single-pair specialization", `risk_management` field); the pair is not one ingredient among several, it is the entire instrument universe.

#### How it could be obtained

- **OANDA v20 REST (cheapest, already built):** NZD_JPY is a standard OANDA instrument on the same practice feed the existing pairs come from. The Wave-1 pair-addition procedure applies unchanged — this is the recommended path.
- **Another vendor:** unnecessary; no licence or cost case to make while OANDA serves the pair.
- **Derivable from existing data:** **No.** A synthetic NZD_JPY cross built as NZD_USD × USD_JPY would require NZD_USD (itself only Wave-1 pending) and would produce a synthetic series whose spreads, gaps, and timestamp alignment do not match a real tradable cross; fills and the round-hour session behaviour would be fabricated. Rejected explicitly.

#### Recommended integration

Identical to the Wave-1 pair procedure (CONTRACT §7):

1. Insert `dim_asset` row: symbol `NZD_JPY`, `market_type='Forex'`, `is_active=true`.
2. Backfill: `python -m src.system1.ingestion.multi_timeframe_ingest --symbol NZD_JPY` (H1 suffices for this strategy; H4/D1 come along with the standard job). Resumable (`ON CONFLICT` + resume from `MAX(timestamp)`); expect ~130k H1 bars back to 2006 — fold it into the same overnight run as the eight Wave-1 pairs.
3. Verify coverage with the standard coverage query before Wave 2 runs the strategy; the harness skips pairs with insufficient history rather than failing, so a half-landed backfill degrades gracefully to "no result" rather than a wrong one.
4. JPY pip convention check: `calculate_pips()` / `get_pip_value()` must use the 0.01 JPY pip for NZD_JPY. USD_JPY is live, so the JPY convention presumably already exists — Wave 1 should assert it explicitly for the new cross rather than assume.

#### Impact if we proceed without it

There is **no partial backtest**: the strategy has one pair, so without NZD_JPY it simply does not run, and the correct outcome is an empty result with this gap note attached — not a proxy result. The informative-loss calculation is: we forgo testing whether a session-filtered median-MA retrace signal on a thin JPY cross can sustain the ~57–58% net win rate its negative-RR bracket demands (SPEC §11). Given the strategy's self-declared curve-fit risk and image-only evidence, that is a tolerable loss.

One caveat that survives **even if the data lands** (also flagged in SPEC §8 and §10 #6): the mandated cost model (F10: 1.0-pip spread, 0.5-pip entry slippage) is the only spread series that exists, and real NZD/JPY retail spreads are typically 1.5–3 pips. Against a ~35-pip TP, each understated spread pip is ~3% of the target. Results for this pair will carry an optimistic cost bias that must be stated in the report; it cannot be fixed at strategy level because F10's constants are mandated for cross-strategy comparability.

---

## Group 3 — Implement now with reduced coverage

### currency_momentum_factor

**Strategy:** Quantpedia Currency Momentum Factor (12-month cross-sectional) — row 43 of forex_swing_strategies.csv
**Companion spec:** `SPEC-currency_momentum_factor.md`

#### Recommendation

**Implement now with reduced coverage — this gap is NOT blocking.**

The core signal (trailing 12-month return per currency vs USD) is computable entirely from
OHLCV data that already exists. What is missing is **breadth**, not the signal: the
documented strategy ranks 10–20 currencies, while the DB has 5 non-USD currencies today and
at most 7 after the Wave-1 backfills. On today's 5-currency universe the top-3/bottom-3 rule
is degenerate (it collapses to long-2/short-2 with the median currency flat — see SPEC §2
and §10 row 2), so results before Wave-1 completes should be read as a thin-universe
approximation, not as a test of the documented factor. Do not defer: the strategy is
implementable, the degeneracy is fully declared in the spec, and the walk-forward harness
already skips pairs with insufficient history. Do not drop: this is one of the few
academically anchored rows in the CSV (Menkhoff, Sarno, Schmeling & Schrimpf). If a
decision-maker wants the *documented* factor rather than a 7-currency sketch, the fix is
ordinary OANDA pair ingestion (below) — a scheduling decision, not a purchase.

#### What is missing

1. **Universe breadth (the real gap).** The CSV requests a "Universe of 10-20 currencies vs
   USD (majors + liquid minors)". Available/planned USD pairs cover only: EUR, GBP, JPY,
   AUD, CAD (live) + NZD, CHF (Wave 1) = **7 currencies maximum**. Reaching even the low end
   of 10 requires additional USD pairs with **no Wave-1 plan**, e.g. USD_DKK, USD_NOK,
   USD_SEK, USD_SGD, USD_MXN, USD_HKD (any three of which reach 10). (The Wave-1 cross pairs
   GBP_JPY, EUR_JPY, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD add no new currency-vs-USD series
   and are irrelevant here.)
2. **"Total return" carry component (minor, accepted deviation).** The signal as documented
   is a 12-month *total* return (spot + interest differential). No rate or forward data
   exists in the DB ("Non-price data — none of it exists", DATA_AVAILABILITY.md), so the
   spec uses spot return only (SPEC §10 row 3). For 12-month G10 horizons the spot component
   dominates; the ranking is largely, not perfectly, preserved.
3. **Overnight cash rates (cosmetic, out of scope).** Listed in the CSV's data requirements
   for "cash not used as margin invested at overnight rates". The r-multiple backtest does
   no sizing and models no margin or cash balance, so this component cannot appear in any
   reported metric. Not ingested (SPEC §10 row 8).

#### Why the strategy needs it

Verbatim from the CSV:

- `target_pairs`: "Universe of 10-20 currencies vs USD (majors + liquid minors)"
- `data_requirements`: "OHLCV daily FX spot or futures prices vs USD|overnight cash rates"
- `risk_management`: "Equal-weighted legs; cash not used as margin invested at overnight
  rates; diversification across 10-20 instruments; documented max drawdown -45.87%"

The diversification is not decoration: a cross-sectional factor's Sharpe comes from holding
many independent legs so idiosyncratic currency noise cancels. At 5–7 currencies the
published 0.30 Sharpe / 7.61% p.a. profile is not what is being measured.

#### How it could be obtained

- **Additional USD pairs:** OANDA v20 REST — the cheapest path, and the ingestion pipeline
  already exists. OANDA practice supports USD/NOK, USD/SEK, USD/SGD, USD/MXN, USD/HKD;
  USD/DKK availability should be confirmed against the broker feed before promising it.
  Same procedure as the Wave-1 additions: insert `dim_asset` rows, then
  `python -m src.system1.ingestion.multi_timeframe_ingest --symbol <PAIR>` (resumable,
  overnight backfill ~130k H1 bars/pair to 2006).
- **Carry component of total return (optional):** 3-month rates per currency from FRED
  (free, programmatic; e.g. `DGS3MO` for USD and OECD/national series for the rest) — same
  schema as proposed in `DATA-GAP-usd_carry_basket.md` (`fact_macro_rates`). Only worth
  building if the carry strategy's ingestion proceeds anyway; do not build it for this
  strategy alone.
- **Overnight cash rates for margin yield:** FRED, free — but there is nothing to wire it
  to in an r-multiple backtest. Only relevant if a capital-weighted equity simulation is
  ever commissioned.

#### Recommended integration

1. Now: nothing. Implement `SPEC-currency_momentum_factor.md` as written; the harness
   degrades gracefully (skips pairs with insufficient history).
2. Wave-1 completion: verify NZD_USD and USD_CHF D1 coverage (≥ 253 closed D1 bars) so the
   universe reaches 7 currencies and the top-3/bottom-3 rule becomes non-degenerate.
3. Optional breadth upgrade (new decision, not Wave 1): pick three additional USD pairs
   (suggest USD_NOK, USD_SEK, USD_SGD for liquidity and G10/liquid-minor mix), insert
   `dim_asset` rows (`market_type='Forex'`, `is_active=true`), run the standard ingest
   command per pair overnight, verify with the coverage query. No schema change is needed —
   the spec's universe `U(t)` is declared mechanically from whichever pairs pass the
   data-sufficiency gate, so new pairs are picked up automatically once they have 253 D1
   bars (~12 months after their backfill start of 2006, i.e. immediately for full backfills).
4. Only if the carry component is wanted: land the `fact_macro_rates` ingestion from the
   usd_carry_basket gap document, then extend `mom_c` to `spot_return + (r_c − r_US)`; this
   is a spec revision, not a Wave-2 implementer decision.

#### Impact if we proceed without it

The backtest measures a **5-currency (later 7-currency) cross-sectional momentum sketch**
instead of the documented 10–20-currency factor. Specifically:

- On 5 currencies the tercile rule is degenerate: ranks 1–2 long, 4–5 short, rank 3 flat —
  ~83% of the universe is always positioned, so the cross-sectional selection (the actual
  anomaly) is barely exercised; results will look like plain multi-pair trend-following.
- Diversification is 2–3× thinner than documented, so portfolio-level statistics (Sharpe,
  drawdown) will be materially worse than the published 0.30 / −45.87% and per-pair
  concentration higher. A pooled pass would not validate the documented factor; a pooled
  fail would not refute it.
- The signal ranking itself is otherwise honest: spot return is OHLCV-derived and causal;
  omitting the carry component perturbs ranks only at the margin for G10 pairs.

**Verdict: still informative** as a pilot of the anomaly's post-2010 survival on the majors
— which is exactly what the CSV's own reasoning asks for ("requires modern re-testing") —
provided every report carries the thin-universe caveat and does not inherit the published
10–20-currency performance claims.

---

### daily_fib_retracement

#### Recommendation

**Implement now with reduced coverage (no news filter), and revisit once a calendar feed is budgeted.** The missing data is an economic calendar driving a *risk-avoidance overlay* ("exclude any pair with NFP or interest-rate announcements due within 24h") — it is not the strategy's claimed edge, which is the Fibonacci retracement entry and trailing structure. Omitting the filter leaves the backtest trading a superset of the author's setups; that is honest and measurable, whereas dropping the strategy would discard an otherwise fully specifiable daily system, and silently proxying the calendar would contaminate attribution. A **static, hand-maintained NFP + central-bank decision schedule** is a viable cheap partial proxy for a future pass (flagged below — it must never be introduced silently).

#### What is missing

- An **economic event calendar** with, at minimum: event timestamp, affected currency, event type, and importance — sufficient to answer, at any daily decision bar, "does either currency of this pair have an NFP release or an interest-rate announcement scheduled within the next 24 hours?"
- `fact_macro_events` exists in the schema but **is not populated** for this purpose (per DATA_AVAILABILITY.md). No other calendar, news, or sentiment feed exists in the DB.
- Specifically needed event classes: US Non-Farm Payrolls (affects all USD pairs), and rate decisions of the Fed, ECB, BoJ, BoE, RBA, RBNZ, SNB, BoC (mapped to pair currencies).

#### Why the strategy needs it

CSV `target_pairs` field, verbatim: **"FX majors and minors; exclude any pair with NFP or interest-rate announcements due within 24h"**. The `edge_description` reinforces it: "News filter eliminates event risk for next 24h". The author's risk model treats event windows as untradeable — retracement levels of a day containing (or preceding) a scheduled shock are, in his framing, unreliable because the event reprices the range rather than continuing it.

#### How it could be obtained

1. **Vendor API (cleanest):** TradingEconomics or FinancialModelingPrep economic-calendar endpoints — machine-readable historical + forward calendars covering all required central banks and NFP. Both are paid/licensed (TradingEconomics ~tiered subscription; FMP has a calendar tier); licence terms must be checked before ingestion. Finnhub offers an economic calendar on paid tiers as an alternative.
2. **OANDA v20 REST:** does **not** expose an economic calendar — the existing ingest path cannot cover this gap. (OANDA's Labs/portal shows events but not via the v20 API.)
3. **Forex Factory / investing.com scraping:** the strategy originates on Forex Factory and its calendar (including the weekly XML historically available) is the canonical source, but programmatic scraping violates their ToS; investing.com's "API" is unofficial and unstable. **Not recommended** for a research pipeline that must be reproducible and licensed.
4. **Derivable partial proxy (static schedule, flagged):** NFP is the first Friday of each month at 12:30 UTC (13:30 during US-vs-Europe DST mismatch weeks); FOMC meets ~8 times/year on pre-announced dates; ECB/BoE/BoJ/RBA/BoC/RBNZ/SNB decisions are also scheduled well in advance. A hand-maintained static table of these dates **derivable from public announcements at zero licence cost** would cover the author's two named event classes for the major central banks. Limitations, stated prominently: it cannot capture unscheduled/emergency decisions or non-rate high-impact releases (CPI, GDP), it requires manual maintenance, and historical backfills must use the *actual historical* decision dates, not the modern schedule — otherwise it is look-ahead of a different kind. **This proxy is NOT baked into the Wave-2 spec; it is an option for a later, deliberate integration.**

#### Recommended integration

1. Add rows to the existing `fact_macro_events` table (schema change if needed): `event_time_utc`, `currency` (ISO), `event_type` (`NFP`, `RATE_DECISION`, …), `importance`, `source`, `ingested_at`.
2. Ingest via a licensed vendor API (option 1) as a new module, e.g. `python -m src.system1.ingestion.economic_calendar_ingest --source tradingeconomics --since 2005`, backfilling history to 2005 to match D1 coverage. If the static proxy (option 4) is chosen instead, ship it as a versioned CSV in the repo with an explicit `source=static_manual` marker.
3. Strategy-side: at each D1 decision bar, join events on `(currency ∈ pair_currencies) AND (event_time_utc ∈ (decision_close, decision_close + 24h])` — the window must open **at** the decision close, not the bar open, to stay causal.

#### Impact if we proceed without it

The backtest measures **the strategy minus its event-avoidance overlay**: all Fib entries that pass trend + zone conditions, including those on the eve of NFP/rate days the author would skip. Consequences:

- **More trades** than the author would take (superset) — event-eve entries add variance, plausibly including some large-gap stops (F6 resolves these honestly, so realised losses beyond 1R will be visible).
- **Countervailing optimism:** the F10 cost model's flat 1.0-pip spread does not widen around events, so event-window execution costs are *understated*. The two distortions partially offset, and the net direction is uncertain — which is exactly why the SPEC (§8, §10 #5) discloses rather than proxies.
- **Still informative:** the core claim — do 50–61.8% retracements of the prior day's range, traded with a 75% invalidation, have edge in EMA50 trends — is fully testable without the calendar. If the unfiltered variant fails the gates, the filter cannot have been the difference-maker for the core edge (it only removes trades); if it passes, a second run with the calendar would quantify the overlay's contribution. Proceeding without it is the right first measurement.

---

### double_bottom_measured_move

#### Recommendation

**Implement now with reduced coverage; add AUD_CAD to the Wave-1 overnight backfill as a cheap opportunistic extra, but do not block Wave 2 on it.** Reasoning, in order:

1. **AUD_CAD is a documented example, not the instrument universe.** The strategy's `target_pairs` is "FX pairs - majors and crosses (GBP/JPY|AUD/CAD examples on page)" — the pair universe is generic; GBP/JPY and AUD/CAD are the page's two worked chart examples. The backtest is fully informative on the 13-pair universe (5 live + 8 Wave-1 pending, which already includes GBP_JPY, the other documented example).
2. **Adding it is near-free if the operator chooses to.** AUD_CAD is a standard OANDA v20 instrument on the same practice feed; it is one more `dim_asset` row and one more symbol on the already-planned overnight Wave-1 ingest (~130k H1 bars). The only reason it is a gap at all is that the CSV's aggregate demand table ranked it below the cut — only this row names it.
3. **Do not proxy it.** No synthetic AUD_CAD built from AUD_USD × USD_CAD, and no silent substitution of AUD_USD or USD_CAD alone. A proxy backtest would measure a different series (fabricated spreads, gaps, and session alignment) and attribute the result to this strategy. If the operator declines the extra ingest, proceed on 13 pairs and record AUD_CAD as untested — a stated omission, not a fabricated cell.

#### What is missing

- **Pair:** AUD_CAD. Absent from the 5 live `dim_asset` pairs AND absent from the 8 Wave-1 additions (GBP_JPY · EUR_JPY · NZD_USD · USD_CHF · EUR_GBP · EUR_AUD · AUD_NZD · EUR_CAD) — a genuine gap, not a pending item.
- **Granularity:** D1 for decisions, H1 for fill resolution — the standard granularities the pipeline already produces; nothing exotic.
- **External series:** none. The row's `data_requirements` is "OHLCV only (swing-point pattern recognition)". No rates, calendar, COT, or real-volume requirement.

#### Why the strategy needs it

- `target_pairs` (verbatim): `FX pairs - majors and crosses (GBP/JPY|AUD/CAD examples on page)`
- `risk_management` (verbatim): `... worked examples: GBP/JPY +774 pips, AUD/CAD +597 pips`

AUD/CAD carries one of the only two concrete performance datapoints the source offers (the +597-pip worked example). Without the pair, that example cannot be reproduced or refuted on our own data — the only pair-level evidence check this row allows is halved. The strategy itself, however, is pair-generic; nothing in the entry, exit, or filter logic is AUD/CAD-specific.

#### How it could be obtained

- **OANDA v20 REST (cheapest, already built):** AUD_CAD is a standard OANDA instrument. The Wave-1 pair-addition procedure applies unchanged — recommended path if the operator wants the example pair covered.
- **Another vendor:** unnecessary; no licence or cost case to make while OANDA serves the pair.
- **Derivable from existing data:** **No** — explicitly rejected. AUD/CAD ≈ AUD_USD × USD_CAD is arithmetically constructible from two live pairs, but the synthetic series would have fabricated spreads (sum of two legs' spreads), misaligned gaps and session boundaries, and no real fillable quotes; every fill, stop, and measured-move outcome on it would be invented. Rejected per the no-invented-data rule.

#### Recommended integration

Identical to the Wave-1 pair procedure (CONTRACT §7):

1. Insert `dim_asset` row: symbol `AUD_CAD`, `market_type='Forex'`, `is_active=true`.
2. Backfill: `python -m src.system1.ingestion.multi_timeframe_ingest --symbol AUD_CAD` — fold into the same overnight run as the eight Wave-1 pairs. Resumable (`ON CONFLICT` + resume from `MAX(timestamp)`); expect ~130k H1 bars back to 2006.
3. Verify with the standard coverage query before Wave 2 runs; the harness skips pairs with insufficient history rather than failing, so a half-landed backfill degrades gracefully to "no result".
4. Pip convention check: assert `calculate_pips()` / `get_pip_value()` handle AUD_CAD with the standard 4-decimal (0.0001) pip — no JPY involvement, so this should be the default path, but Wave 1 should assert it for the new row rather than assume.

#### Impact if we proceed without it

The strategy runs on 13 pairs instead of 14; the backtest measures the same rules on a slightly smaller cross-section. **The loss is evidential, not structural:** we forgo the ability to reproduce the source's +597-pip AUD/CAD worked example on our own data, which is one of only two concrete claims in the row (the GBP/JPY +774-pip example remains testable once the Wave-1 GBP_JPY backfill lands). Given the strategy's pair-generic logic and the fact that the author's conviction rests on worked examples rather than a statistical sample anyway, proceeding without AUD_CAD is still informative — the pooled 13-pair OOS gates are the verdict that matters, and one additional mid-liquidity cross would not change a pooled pass/fail except at the margin. If the ingest is declined, the report must list AUD_CAD as an untested documented-example pair, not silently drop it from the requested-universe accounting.

---

### h4_box_breakout

#### Recommendation
**Implement now with reduced coverage, and queue the three missing JPY crosses for
ingestion alongside the Wave-1 batch.** Two of the five requested pairs (GBP_JPY, EUR_JPY)
are already Wave-1 additions — pending, not gaps — and they are the two most liquid and
most volatile JPY crosses, i.e. the pairs where the strategy's premise (weekly
range-expansion on volatile JPY crosses) is strongest. The remaining three (AUD_JPY,
CHF_JPY, CAD_JPY) are standard OANDA v20 instruments obtainable with the exact ingest
procedure Wave 1 is already running; there is no reason to defer or drop the strategy.
Caveat: with **zero** of the five pairs live today, the strategy is untestable until at
least the GBP_JPY/EUR_JPY backfill completes — schedule this strategy's Wave-2 run after
that backfill is verified.

#### What is missing
1. **Pairs:** AUD_JPY, CHF_JPY, CAD_JPY — all granularities (H1 for fill resolution,
   H4 for decisions). Not in `dim_asset` (only 5 pairs live) and **not** in the Wave-1
   addition list (GBP_JPY · EUR_JPY · NZD_USD · USD_CHF · EUR_GBP · EUR_AUD · AUD_NZD ·
   EUR_CAD — note Wave-1 adds USD_CHF and the CAD *majors*, not these JPY crosses).
2. **Secondary (minor): historical spread series** for JPY crosses. The source triggers
   at "box + 10–20 pips + spread"; no spread data exists in `fact_market_prices`. The spec
   uses the 1.0-pip cost-model constant as a declared proxy (SPEC §8/§10 row 2). This is a
   flagged proxy, not a blocker, and does not require new ingestion to proceed.

#### Why the strategy needs it
CSV `target_pairs`: **"GBP/JPY | EUR/JPY | AUD/JPY | CHF/JPY | CAD/JPY"** — the strategy is
*defined* as a JPY-cross system; the recommendation reasoning states the edge is
"opening-week range resolution on volatile JPY crosses". Running it on substitute pairs
(e.g. the live USD_JPY) would measure a different instrument set than the strategy
documents; running it on 2 of 5 pairs measures the strategy on its two strongest cells but
drops the AUD/CAD/CHF funding-currency diversification the basket implies.

#### How it could be obtained
**OANDA v20 REST — cheapest, already built.** AUD_JPY, CHF_JPY, and CAD_JPY are all
standard OANDA instruments; the existing `multi_timeframe_ingest` pipeline handles them
with zero code changes. The spread series is *not* worth obtaining: historical OANDA
spread is not served by the candles endpoint, tick-level pricing would be a different
vendor (e.g. Dukascopy tick data, free with registration, or TrueFX, free) and a schema
change — disproportionate for a 1-pip-scale buffer term; keep the declared proxy.

#### Recommended integration
Per the Wave-1 procedure (CONTRACT_V2 §7):
1. Insert three `dim_asset` rows (`market_type='Forex'`, `is_active=true`) for
   AUD_JPY, CHF_JPY, CAD_JPY.
2. `python -m src.system1.ingestion.multi_timeframe_ingest --symbol AUD_JPY` (and likewise
   CHF_JPY, CAD_JPY). Resumable (`ON CONFLICT`, resumes from `MAX(timestamp)`); ~130k H1
   bars/pair to 2006 — run overnight with the Wave-1 batch.
3. Verify with the coverage query before declaring done; the Wave-2 harness already skips
   pairs with insufficient history, so a partial backfill degrades gracefully.
No schema change needed. The strategy spec (SPEC-h4_box_breakout.md §2) already declares
the pairs; no spec edit is required when data lands.

#### Impact if we proceed without it
The backtest measures the strategy on **GBP_JPY + EUR_JPY only** (once their Wave-1
backfill lands). That is still informative: these are the highest-volatility,
highest-liquidity JPY crosses and the natural home of the claimed edge, so a failure here
is a strong verdict against the strategy everywhere. What is lost: (a) 60% of the intended
basket, so pooled trade counts drop ~3/5 and per-cell diversification across funding
currencies (AUD, CAD, CHF behave differently under risk-on/risk-off) is untested; (b) any
verdict is exposed to GBP- and EUR-specific idiosyncrasy. Conclusion: proceed on two
pairs, publish per-cell verdicts, and treat the three missing crosses as an ingest task,
not a research blocker.

---

### h4_crossover_21_89_macd

#### Recommendation

**Implement now with reduced coverage (10 of 12 pairs), and add the two CHF crosses via the standard Wave-1 ingest procedure when convenient — do not defer, do not drop.** The strategy is a generic trend-pullback system with no CHF-specific logic; GBP_CHF and EUR_CHF are simply 2 of 12 cells in a pooled test. Losing them trims dispersion coverage (and removes two historically range-prone, post-2015-floor-removal CHF series that would likely have been among the harder cells), but it does not change what the backtest measures or threaten validity. Both instruments are standard OANDA v20 symbols, so closing the gap is an overnight operator job identical in kind to the eight Wave-1 pair additions already planned — the cheapest possible fix on the menu.

#### What is missing

- **Pairs (primary gap):** GBP_CHF and EUR_CHF, at H4 (signals), D1 (stop structure), and H1 (fill resolution). Neither exists in `dim_asset` (5 live pairs: EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD) and neither is in the Wave-1 addition list (GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD). Note: USD_CHF IS in the Wave-1 list and is **pending, not a gap**. The other seven named pairs (EURGBP, EURAUD, EURJPY, GBPJPY, USDCHF pending; EURUSD, GBPUSD, AUDUSD, USDCAD, USDJPY live) are covered.
- **Secondary items (not pair data; recorded here per the no-silent-proxy rule):**
  - No holiday/economic calendar feed exists. The source's "no trading on major US holidays" is implemented in the SPEC via a static, date-arithmetic US-federal-holiday list (derivable, flagged in SPEC §8 and §10 row 7). A real calendar feed would only refine this slightly; not worth obtaining on its own.
  - No fundamental/news data exists. The source's "~10-15 min daily fundamental check" is discretionary and non-mechanical; it is dropped with no proxy substituted.

#### Why the strategy needs it

The CSV `target_pairs` field names twelve pairs verbatim: `EURUSD|GBPUSD|AUDUSD|USDCAD|EURGBP|EURAUD|EURJPY|GBPJPY|USDJPY|GBPCHF|USDCHF|EURCHF`. The author's documented hand-compiled backtest (Jan 2009 - Oct 2010) ran "across 12 pairs", so the CHF crosses are part of the evidence base the conviction rating rests on; dropping them means the modern re-test covers a strict subset of the author's sample.

#### How it could be obtained

**OANDA v20 REST — cheapest, already built.** GBP_CHF and EUR_CHF are standard OANDA instruments on the same practice endpoint the existing `multi_timeframe_ingest` already pulls. No new vendor, no licence, no schema change beyond a `dim_asset` row. Backfill cost: ~130k H1 bars per pair to 2006, same as the Wave-1 pair jobs; run overnight against rate limits. (If OANDA history for these crosses proved thin pre-2010, Dukascopy tick data is the usual fallback vendor — but check OANDA coverage first; there is no reason to expect a problem for CHF crosses.)

#### Recommended integration

1. Insert `dim_asset` rows: `(symbol='GBP_CHF', market_type='Forex', is_active=true)` and `(symbol='EUR_CHF', market_type='Forex', is_active=true)` — pip conventions are standard (0.0001), so `calculate_pips`/`get_pip_value` need no changes.
2. `python -m src.system1.ingestion.multi_timeframe_ingest --symbol GBP_CHF` then `--symbol EUR_CHF` (resumable via `ON CONFLICT`; overnight).
3. Verify with the coverage query (H1/H4/D1 to ~2006, current to ingest date) before enabling the cells.
4. No SPEC change is required: the strategy already declares both pairs; the harness skips pairs with insufficient history and picks them up automatically once the backfill lands.

#### Impact if we proceed without it

The backtest runs on 10 cells (5 live + 5 Wave-1 pending) instead of 12. What is measured is unchanged in kind — pooled and per-cell r-multiples of the same mechanical system — just over fewer cells. Two honest caveats: (a) the author's 2009-2010 evidence base included these pairs, so pooled results are not directly comparable to the author's log on coverage grounds (they are already non-comparable on exit-rule grounds, see SPEC §10 row 5); (b) CHF crosses post-2015 are lower-volatility and range-prone, so the missing cells plausibly biased toward the harder end — proceeding without them, if anything, mildly flatters the pooled result, which the report should note. The result remains fully informative for a gate decision.

---

### ma_crossover_swing

#### Recommendation

**Implement now with reduced coverage** — run the strategy on the three live FX pairs it names (EUR_USD, GBP_USD, USD_JPY) and record XAU_USD as excluded. XAU_USD is a **deliberate policy exclusion, not a missing feed**: gold is not Forex, and the system's pip-value, margin, and `calculate_pips()` conventions all assume FX pairs (CONTRACT §7; DATA_AVAILABILITY). Adding it would require changes to shared infrastructure far beyond this strategy, and the strategy loses nothing essential without it — it is explicitly "asset-agnostic" MA-cross logic that three liquid majors exercise fully. Do not defer and do not drop.

#### What is missing

- **Pair:** XAU_USD (spot gold vs USD) — named in the row's `target_pairs`. No granularity of XAU_USD exists in `fact_market_prices`, and none is planned in Wave 1.
- Everything else the strategy needs (D1/H4/H1 OHLCV for the three FX pairs, EMA/SMA/MACD/ATR inputs) is present and current.

#### Why the strategy needs it

The CSV's `target_pairs` field reads: `EURUSD|GBPUSD|USDJPY|XAUUSD|asset-agnostic, applies to FX majors`. Gold is one of four explicitly named instruments — the author's published demo traded equities/ETFs and metals-style instruments, so XAUUSD was part of the intended validation universe. However, the immediately following clause ("asset-agnostic, applies to FX majors") shows the author regards the logic as instrument-independent; gold is illustrative, not load-bearing.

#### How it could be obtained

- **Not obtainable under current conventions** — this is the honest answer. OANDA v20 REST *does* serve XAU_USD candles (the ingest path already built could fetch it at zero development cost), but the exclusion is a system-design decision, not a data-access problem: `calculate_pips()`, pip values, and margin assumptions in the shared codebase are hard-coded to FX conventions. Half-supporting gold would silently mis-price every trade.
- To support it properly (a future initiative, not this wave): add a `market_type='Metals'` asset class with metal-specific `pip_size`/`pip_value` (e.g. 0.01 or 0.1 USD per ounce conventions) and margin handling, insert a `dim_asset` row, then run the standard ingest: `python -m src.system1.ingestion.multi_timeframe_ingest --symbol XAU_USD`. That is a shared-infrastructure change with its own review, and should not be smuggled in as a side effect of one research strategy.

#### Recommended integration

None for Wave 1/2. Declare `pairs_available = [EUR_USD, GBP_USD, USD_JPY]` in the strategy metadata and note the XAU_USD exclusion in the report header, so the coverage gap is visible rather than silent. If a metals asset class is ever built, this strategy requires no spec change to pick it up — its logic is instrument-agnostic.

#### Impact if we proceed without it

The backtest measures the MA-cross-with-confirmation edge on three FX majors only. That is still fully informative for the strategy's stated hypothesis: the logic has no gold-specific component (no session, no safe-haven flow, no DXY input), and EUR_USD / GBP_USD / USD_JPY span the major USD regimes. The only loss is breadth of evidence — a pass on three FX pairs is weaker corroboration of the "asset-agnostic" claim than a pass on three pairs plus gold would have been, and the report should say exactly that rather than over-claiming instrument independence.

---

### mtf_swing_weekly_pivots

#### Recommendation

**Implement now with reduced coverage (FX majors only).** The gap is incidental, not structural: every entry/exit rule in the source is defined on FX price action, the four explicitly named pairs (EURUSD, GBPUSD, USDJPY, AUDUSD) are all live in `fact_market_prices`, and USD_CAD covers the generic "FX majors" clause. Only the trailing "liquid indices" phrase is unfulfillable, and no rule depends on it. Deferring or dropping the strategy over this would discard a fully testable FX strategy for a catch-all instrument class the author never specified.

#### What is missing

- **Instrument class: liquid stock/CFD indices** (e.g. US500, NAS100-type instruments — the source does not name specific ones). No index instrument exists in `dim_asset`; the five assets are all Forex, and the Wave-1 additions (GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD) are also all Forex.
- Nothing else: no granularity gap (H4 decision frame, D1 context, H1 fill resolution are all current), no external series gap (no rates/calendar/COT/VIX used), and no W1 dependency — the weekly pivot levels were dropped as non-load-bearing (SPEC §10 #3), so the stale W1 series is moot for this strategy.

#### Why the strategy needs it

Only via the `target_pairs` field: `EURUSD|GBPUSD|USDJPY|AUDUSD|FX majors and liquid indices`. No entry, exit, or filter rule references any index; the phrase is a coverage wish, not a logic input.

#### How it could be obtained

- **OANDA v20 REST (cheapest, already built):** OANDA practice accounts carry CFD indices (e.g. `SPX500_USD`, `NAS100_USD`, `US30_USD`). The existing `multi_timeframe_ingest` could fetch them with no new vendor code.
- **Caveat (the real blocker):** this project's pip-value, margin, and `calculate_pips()` conventions assume FX pairs (the same reason `XAU_USD` was deliberately excluded). Index CFDs have different pip/point definitions and contract sizes, so ingesting the prices is trivial but making the cost model and r-multiple arithmetic correct for them is a small design task, not a data task.

#### Recommended integration

If index coverage is ever wanted: insert `dim_asset` rows with `market_type='IndexCFD'` (a new type — do **not** reuse `'Forex'`), extend `get_pip_value()`/`calculate_pips()` with per-instrument point definitions, then run `python -m src.system1.ingestion.multi_timeframe_ingest --symbol SPX500_USD` (etc.) per instrument. Until that convention work is scheduled, do nothing — the strategy is unaffected.

#### Impact if we proceed without it

The backtest measures the strategy on five FX majors instead of "FX majors plus indices". All entry/exit logic is identical; the only loss is cross-asset-class diversification of the sample (fewer cells, and all cells share FX-specific regime behaviour such as central-bank-driven trends). That is still fully informative about the strategy's documented edge — the trend/pullback hypothesis is stated on FX charts in the source — and per-cell verdicts will honestly show FX-only coverage. If the strategy qualifies on FX, a later index extension is a pure data/convention task with no re-specification needed.

---

### smash_days

#### Recommendation
**Implement now with reduced coverage.** The strategy is fully specified and testable today on the 5 live pairs (AUD_USD, USD_CAD, EUR_USD, GBP_USD, USD_JPY), and coverage rises to 13 cells automatically as the 8 Wave-1 pair additions land. The two explicitly named pairs that are NOT in the Wave-1 plan (GBP_NZD, NZD_CHF) and the unnamed balance of the author's "28 leading pairs" should be treated as an optional later expansion, not a blocker: both named pairs are standard OANDA v20 instruments obtainable through the existing ingest pipeline with zero new engineering. Notably, running on the reduced universe has a genuine methodological upside — the OP himself warns that the setup double-counts correlated AUD/NZD themes when run across 28 pairs, and the current universe contains far fewer AUD/NZD crosses, so the reduced-coverage backtest is less exposed to the strategy's own known concentration defect. Do not defer; do not drop.

#### What is missing
1. **Pairs:** GBP_NZD and NZD_CHF — explicitly named in `target_pairs` ("e.g. GBP/NZD | NZD/CHF | AUD/USD | USD/CAD") but absent from both the 5 live pairs and the 8 Wave-1 additions (GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD). Beyond these, the author runs the setup across "28 leading forex pairs"; only 13 of the conventional 28 majors/crosses are on the current plan, leaving roughly 15 further crosses (e.g. GBP_AUD, GBP_CAD, NZD_JPY, NZD_CAD, CHF_JPY, AUD_CHF, AUD_CAD, EUR_NZD, EUR_CHF, GBP_CHF …) uncovered.
2. **Granularity:** none. D1 is live and current (to 2026-08-06); H1 for fill resolution is current (to 2026-08-07).
3. **External series (secondary):** an economic-calendar / event feed, needed for the author's "avoids trading during extreme volatility/event risk" filter. No calendar, news, or sentiment data exists in the system. This filter has been **dropped** from the spec under the no-invented-data rule (SPEC §8, §10 #4) rather than proxied.

#### Why the strategy needs it
- Pairs — `target_pairs`, verbatim: *"28 leading forex pairs (e.g. GBP/NZD | NZD/CHF | AUD/USD | USD/CAD)"*. A ~1–3 signals/month/pair setup is pair-count-hungry: on 5 pairs the pooled trade count may be thin for the gates; the author's design assumes breadth across 28 instruments.
- Calendar — `risk_management`, verbatim: *"avoids trading during extreme volatility/event risk"*. Without an event feed, signals that fire into known binary events (central-bank decisions, CPI) are taken in the backtest that the author would have skipped.

#### How it could be obtained
1. **GBP_NZD, NZD_CHF (and any further crosses):** OANDA v20 REST — cheapest path, already built. Both are standard OANDA instruments on the practice feed the existing ingester already polls. Procedure is identical to the Wave-1 additions: insert `dim_asset` rows, run the resumable multi-timeframe ingest overnight.
2. **Economic calendar:** not obtainable from existing data and not derivable from OHLCV without changing the filter's meaning (a volatility proxy screens *realized* volatility, not *scheduled event* risk). If ever required, a third-party calendar API (e.g. Trading Economics or Finnhub economic-calendar endpoints; licence/cost per vendor, typically a paid tier for historical depth back to 2006) would be needed. **Recommendation: do not procure.** The filter is discretionary risk hygiene, not part of the edge; its absence is disclosed in the spec and biases the backtest toward *more* trades in event windows — visible, conservative-direction, and acceptable for a research verdict.
3. The remaining ~15 unnamed crosses: same OANDA route as (1), but low priority — the 13-cell universe already covers the most liquid pairs and avoids redundant AUD/NZD theme overlap.

#### Recommended integration
For GBP_NZD and NZD_CHF, if approved:
1. Insert `dim_asset` rows: `symbol='GBP_NZD'`, `market_type='Forex'`, `is_active=true`; same for `NZD_CHF`.
2. Run: `python -m src.system1.ingestion.multi_timeframe_ingest --symbol GBP_NZD` (and likewise `NZD_CHF`) — the ingest is resumable (`ON CONFLICT ("timestamp", asset_id, granularity)`); expect ~130k H1 bars per pair of overnight backfill to 2006.
3. No schema change required. The smash_days spec already declares pairs via metadata; the harness skips pairs with insufficient history, so the strategy runs today and simply gains cells as pairs land. No strategy-code change will be needed.

#### Impact if we proceed without it
- **Pairs:** the backtest measures the smash-day edge on the 5–13 most liquid USD-centric pairs instead of 28. That is still fully informative for the go/no-go question — the hypothesis (5-day exhaustion snapback) is not pair-specific, and EUR_USD/GBP_USD/USD_JPY are the deepest markets where such an edge should show first if it exists. What is lost is breadth-smoothing of the pooled result and the two explicitly named pairs; per-cell verdicts will make any pair-dependence visible. Trade-count risk is mitigated by ~20 years of D1 history (~5,900 bars/pair) and by the Wave-1 additions roughly tripling cell count.
- **Calendar filter:** the backtest takes signals into event windows that the author would skip. Direction of bias: more trades, likely slightly worse average outcome (event-window entries have gap-prone next sessions, and F3/F6 resolve those gaps adversely) — i.e. conservative for qualification purposes. Disclosed in SPEC §8 and §10 #4.

---

### strong_weak_analysis

#### Recommendation

**Implement now with reduced coverage, and trigger the missing-cross ingest in parallel.** The strategy is computable today: the 13 pairs available after Wave 1 (5 live + 8 pending) touch all 8 major currencies, so the strength ranking and the strongest-vs-weakest pair selection both function. But 15 of the 28 crosses are absent, which (a) biases the per-currency strength sums — CHF is ranked on a single cross (USD_CHF), NZD on two — and (b) silently discards roughly half the candidate trade instruments whenever the strongest/weakest combination is a missing cross (the spec's conservative rule is *skip the bar*, §10 #4). All 15 missing crosses are standard OANDA instruments obtainable through the ingest pipeline that already exists, at zero licence cost and one overnight backfill. Deferring the strategy until the data lands is unnecessary; dropping it is unwarranted. The backtest report must state prominently that pre-ingest results measure a degraded-coverage variant of an already-reconstructed formula (see SPEC §10 #1, #7).

#### What is missing

15 crosses of the 8-major matrix (USD, EUR, GBP, JPY, AUD, NZD, CAD, CHF), at D1 granularity (H1/H4 also needed since fills resolve on H1 and the standard ingest covers all granularities anyway):

AUD_CAD · AUD_CHF · AUD_JPY · CAD_CHF · CAD_JPY · CHF_JPY · EUR_CHF · EUR_NZD · GBP_AUD · GBP_CAD · GBP_CHF · GBP_NZD · NZD_CAD · NZD_CHF · NZD_JPY

No external/non-price series is missing — the strategy needs OHLCV only. W1 staleness is irrelevant (D1 strategy).

#### Why the strategy needs it

CSV `target_pairs`: *"All 28 pairs from 8 majors (trade strongest currency vs weakest)"*, and `data_requirements`: *"Daily close OHLCV for all 28 major crosses to compute proprietary per-currency strength ranking"*. Both roles require the full matrix:

1. **Strength input:** the reconstruction sums each currency's oriented z-scores across *all* its crosses. With 13 pairs, EUR/USD/JPY are measured on 5–7 crosses while CHF gets 1 and NZD 2 — the ranking systematically under-weights thin currencies and can mis-rank exactly the currencies (CHF, NZD) that frequently sit at the strong/weak extremes.
2. **Trade instrument:** when best/worst is, say, GBP/NZD or CAD/JPY, no instrument exists and the bar is skipped. Expected signal loss: of the C(8,2) = 28 possible best/worst combinations, 15 (54%) are untradeable pre-ingest.

#### How it could be obtained

**OANDA v20 REST — cheapest, already built.** All 15 crosses are standard OANDA CURRENCY instruments (the same source as the existing 13 pairs; EUR_CHF appears in the v20 `AccountInstruments` documentation, and the full 8-major cross matrix is part of OANDA's standard instrument list — confirm against the account's `GET v3/accounts/{accountID}/instruments` response before scheduling, as the tradable list varies slightly by regulatory division). No new vendor, no licence cost, no schema change. If any cross turns out to be unavailable on this account's division, it degrades gracefully: the spec already skips untradeable combinations and drops absent pairs from the strength sums.

#### Recommended integration

Identical to the Wave-1 pair procedure (contract §7, Part F):

1. Insert `dim_asset` rows for the 15 symbols (`market_type='Forex'`, `is_active=true`), asset_ids continuing the existing sequence.
2. `python -m src.system1.ingestion.multi_timeframe_ingest --symbol <PAIR>` per pair (resumable via `ON CONFLICT ("timestamp", asset_id, granularity)`; ~130k H1 bars per pair to 2006; run overnight against practice rate limits).
3. Verify with the coverage query before declaring done; the harness skips pairs with insufficient history, so partial completion is safe.
4. No schema change, no strategy-code change: the spec's universe U is defined as "available pairs", so the strategy automatically picks up new crosses as they land.

#### Impact if we proceed without it

The backtest would measure a **13-pair reduced-universe variant**: strength sums computed on unequal cross counts per currency (CHF = USD_CHF alone), and ~54% of strongest/weakest combinations skipped. The result is still informative — a negative verdict on the reduced universe almost certainly extends to the full one (more data cannot fix a dead edge), and the mechanics of ranking/trend/trail are fully exercised — but a *positive* verdict would carry an explicit caveat: ranking fidelity for CHF/NZD is unproven, and the trade-selection distribution differs from the author's 28-pair universe. Given the ingest is cheap and uses existing infrastructure, the reduced-coverage run should be treated as a smoke test, with the full-matrix re-run following the overnight backfill.

---

### sunday_breakout

#### Recommendation

**Implement now with reduced coverage.** Run the strategy on GBP_USD immediately (all required granularities exist back to 2006). Treat EUR_JPY as a declared-but-skippable cell until the Wave 1 backfill is verified, and cap any analysis window at the last date for which weekly ATR is honestly knowable from the stale W1 feed (see below) unless the Wave 1 W1 refresh lands first. Neither gap blocks the build; both cap its coverage.

#### What is missing

1. **EUR_JPY price data.** One of the two pairs the strategy names. `dim_asset` currently holds only EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD. EUR_JPY is on the Wave 1 addition list, but its backfill is "an overnight operator job and may not be complete when Wave 2 runs" (DATA_AVAILABILITY.md).
2. **Current W1 bars.** W1's last bar is 2026-06-12, stale ~8 weeks against H1/H4/D1 data that runs to 2026-08-07. The refresh is pending (Wave 1, agent G).

#### Why the strategy needs it

- CSV `target_pairs`: **"GBP/USD | EUR/JPY"** — half the requested coverage is EUR/JPY, and the source author traded exactly these two pairs live (GBP/USD primary, EUR/JPY with a variant rule set; see SPEC §10.7).
- CSV `data_requirements`: **"weekly ATR(14)"** — the take-profit distance is ½ × weekly ATR(14) (CSV `exit_logic`). The ATR is computed from W1 bars, causally aligned so that only fully completed weeks enter (SPEC §3). With W1 ending 2026-06-12, every trading week after mid-June 2026 lacks the completed W1 bars its decision requires; signals in the last ~8 weeks of H1/H4 history cannot compute an honest TP level and must be dropped, not proxied with stale ATR values.

#### How it could be obtained

- **EUR_JPY:** the Wave 1 procedure already specified in the contract (Part F): insert the `dim_asset` row (`market_type='Forex'`, `is_active=true`), then `python -m src.system1.ingestion.multi_timeframe_ingest --symbol EUR_JPY`. Ingest is resumable; ~130k H1 bars back to 2006 against OANDA practice rate limits; overnight job. Verify with the coverage query before enabling the cell.
- **W1 refresh:** `python -m src.system1.ingestion.multi_timeframe_ingest --granularity W1`, plus the already-mandated investigation of why the Saturday cron stalled. Both items are Wave 1 scope; nothing new is being requested here — this note exists so the dependency is visible on this strategy's critical path.

#### Recommended integration (concrete)

1. Declare `pairs = [GBP_USD, EUR_JPY]` in the strategy metadata exactly as the CSV requests; rely on the documented harness behaviour of skipping pairs with insufficient history rather than failing.
2. Before any run, compute the ATR-knowability horizon: the latest decision bar allowed is the last Sunday candle whose preceding 14 completed W1 bars all exist. With W1 at 2026-06-12, the analysis window ends in mid-June 2026; do not pad with stale ATR values (that would silently change the TP distance and inflate/deflate r-multiples).
3. When Wave 1 reports EUR_JPY coverage verified and W1 refreshed, re-run with no spec change — the spec is already written for both pairs and current W1.
4. In the report, state per-cell coverage explicitly: which pairs ran, and the date range actually evaluated versus requested.

#### Impact if we proceed without it

- **EUR_JPY absent:** results cover GBP_USD only — the pair the author primarily traded, so the core hypothesis is still tested. Lost: the second cell, any cross-pair dispersion read (Contract Part G), and validation of the author's two-pair live claim. Acceptable for Wave 2; must be labelled single-pair in the report.
- **W1 stale:** the evaluation window loses its most recent ~8 weeks. For a walk-forward backtest spanning 2006–2026 this trims only the tail of the final fold; material impact is low, but the fold report must flag the truncation (F11-style) rather than presenting a shortened window as full coverage. If the strategy were ever considered for live/paper forwarding, stale W1 would be a hard blocker — the TP distance would be computed from 2-month-old volatility.
- **No silent proxies:** no substitute pair (e.g., GBP_JPY as "close to EUR/JPY") and no ATR substitution (e.g., D1 ATR × √5) is permitted; both would change the strategy being measured.

---

### three_candle_swing_reversal

#### Recommendation
**Implement now with reduced coverage.** The strategy is fully testable today on D1 with EUR_USD, USD_CAD, USD_JPY (live) plus NZD_USD (Wave-1 pending, not a gap). D1 is the source's own primary timeframe and the spec's conservative choice, so the H12 gap costs nothing. GBP_CAD and GBP_NZD are cheap, standard OANDA additions — recommend adding them to the Wave-1 pair batch since they are named only by this strategy and would otherwise be silently dropped. XAU_USD: **drop permanently** — it is excluded by policy (not Forex; pip/margin conventions assume FX) and no workaround should be built.

#### What is missing
1. **H12 granularity** — named in `timeframes` ("D1 primary|H12|H4 confirmation"). Not in the allowed set {H1, H4, D1, W1}; not present in `fact_market_prices`.
2. **GBP_CAD** — named in `target_pairs`; not among the 5 live pairs and NOT in the Wave-1 addition list (GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD).
3. **GBP_NZD** — same status as GBP_CAD.
4. **XAU_USD** — named in `target_pairs`; deliberately excluded by policy (DATA_AVAILABILITY.md: "not Forex; `calculate_pips()` and margin conventions assume FX").

#### Why the strategy needs it
- `timeframes`: "D1 primary|H12|H4 confirmation|H1 only in direction of D1 trend" — H12 is one of the author's traded frames; the thread trades the pattern on H4/H12/D1.
- `target_pairs`: "EURUSD|NZDUSD|USDCAD|USDJPY|GBPCAD|GBPNZD|XAUUSD" — GBP-cross and gold coverage is part of the author's claimed opportunity set.

#### How it could be obtained
1. **H12 — derivable from existing data, no new ingest.** Resample H4 (or H1) bars, grouped on the OANDA day boundary (D1 bars open at 21:00 UTC). Each H12 bar = 3 consecutive H4 bars (or 12 H1 bars): `Open` = open of first child bar, `High` = max of child highs, `Low` = min of child lows, `Close` = close of last child bar, `Volume` = sum of child tick counts. H12 bars stamped 21:00Z (covering 21:00→09:00) and 09:00Z (09:00→21:00). The H4 frame is already aligned to the same 21:00Z day boundary, so grouping is unambiguous — verify by asserting every group's first child timestamp mod 12h ∈ {21:00Z, 09:00Z}. Cost: a pure transform; no rate limits, no vendor. If Wave 2 wants the H12 variant, the resampler belongs in the strategy's own module or the research loader, NOT in shared ingestion (granularity allow-list is H1/H4/D1/W1).
2. **GBP_CAD, GBP_NZD — standard OANDA v20 REST ingest (cheapest; pipeline already built).** Both are ordinary OANDA-tradable FX crosses. Insert `dim_asset` rows (`market_type='Forex'`, `is_active=true`), then `python -m src.system1.ingestion.multi_timeframe_ingest --symbol GBP_CAD` (and `GBP_NZD`). Resumable (`ON CONFLICT` + resume from `MAX(timestamp)`); expect ~130k H1 bars each back to 2006 — one overnight job for both. They were simply not ranked into the Wave-1 batch (each is named by only this one strategy).
3. **XAU_USD — obtainable from OANDA (XAU_USD is a standard v20 instrument) but excluded by policy.** Supporting it would require pip-value and margin conventions that the system explicitly does not implement for metals. Do not half-support; record as a permanent exclusion.

#### Recommended integration
- **Now (Wave 2):** run the strategy on EUR_USD, USD_CAD, USD_JPY, NZD_USD (pending) at D1 only. No ingest needed.
- **Optional pair extension:** two `dim_asset` inserts (`GBP_CAD`, `GBP_NZD`, `market_type='Forex'`, `is_active=true`) + two overnight ingest commands as above; verify with the standard coverage query before enabling.
- **Optional H12 variant (only if the D1 result is promising):** private resampling function in the strategy module per the derivation above; no schema change, no allow-list change. Treat H12 as a reporting variant, not a second qualification path.
- **XAU_USD:** none. Document exclusion in the strategy report.

#### Impact if we proceed without it
- **Pairs:** coverage is 4 of 7 requested (57%). The two missing GBP crosses are the author's highest-volatility named instruments, so the backtest will under-represent the strategy's behaviour in fast, wide-ranging markets; results will be biased toward the behaviour on EUR_USD/USD_CAD/USD_JPY/NZD_USD. Still informative: D1 counter-trend reversal mechanics do not depend on the specific cross, and the pooled verdict remains a fair test of the pattern itself.
- **H12:** none for the declared D1 spec. The H12 variant would roughly double signal frequency versus D1 (two bars per day instead of one); without it we simply test the coarser, slower version — which is the conservative reading anyway.
- **XAU_USD:** gold's trend/volatility character differs materially from FX, but the exclusion is policy, not oversight; the report should state that one of the author's named instruments was untestable by design.

---

### weekly_gap_fade

#### Recommendation

**Implement now with reduced coverage.** Nothing here blocks the build: the spec
(`SPEC-weekly_gap_fade.md`) runs today on USD_JPY plus EUR_USD, GBP_USD, AUD_USD, USD_CAD,
and it degrades gracefully — the harness simply skips declared-but-unbackfilled pairs, and
the missing spread feed is replaced by the sanctioned 1.0-pip cost-model constant. **Do not
defer, do not drop** — but read the Wave-2 verdict with two caveats: the author's documented
pair (GBP/JPY) may be absent from the first run, and the backtest trades smaller gaps than
the author did.

#### What is missing

1. **Average-spread-per-pair data.** The strategy's only filter — "gap size ≥ 5× average
   spread" — requires a spread series. `fact_market_prices` holds OHLCV only;
   DATA_AVAILABILITY.md states plainly: "Non-price data — none of it exists." There is no
   spread column, no quote feed, no historical spread table for any pair.
2. **GBP_JPY price history (the author's preferred — and only documented — pair).**
   GBP_JPY is a confirmed Wave-1 addition, but the backfill is an overnight operator job
   (~130k H1 bars per pair against OANDA practice rate limits) and DATA_AVAILABILITY.md
   warns it "may not be complete when Wave 2 runs." EUR_JPY ("other JPY pairs") is in the
   same position, as are NZD_USD and USD_CHF (remaining majors).
3. **W1 staleness — explicitly NOT a gap for this strategy.** The spec was deliberately
   re-based onto H1 (decisions) + D1 (stop context only), both current to 2026-08-07, so the
   ~8-week-stale W1 series is never read. Recorded here only so reviewers do not double-count
   it as a blocker.

#### Why the strategy needs it

- Spread: the CSV `data_requirements` field reads, verbatim:
  *"Standard OHLCV D1/W1 bars|Average spread per pair"*. The entry conditions read:
  *"...and gap size >= 5x average spread, open Long/Short at Monday market open"*. The filter
  is the entire trade-selection mechanism — without a spread value the threshold cannot be
  computed as written.
- GBP/JPY: the CSV `target_pairs` field reads, verbatim:
  *"GBP/JPY preferred|Other JPY pairs|All major pairs tradeable simultaneously"*, and the
  `recommendation_reasoning` field's only empirical evidence is: *"page documents a tested
  example: GBP/JPY 6 of 7 gaps correct, net +1,612 pips over 7 weeks (2010 sample)"*. The
  edge claim is pair-specific; JPY crosses gap more than USD majors because of the Sunday-open
  Asia liquidity pattern, so results on EUR_USD/USD_CAD alone would under-represent the
  strategy as documented.

#### How it could be obtained

1. **Spread:** (a) accept the 1.0-pip fixed proxy from the F10 cost model — the only spread
   figure the system sanctions, already used for the 134,520 live `fact_trade_outcomes` rows
   (threshold = 5.0 pips; *chosen in the spec*); or (b) procure historical average-spread
   estimates per pair from broker published data (OANDA publishes historical typical spreads)
   and store them as a small static lookup — note this is an estimate, not a time series, and
   would still need a governance decision since it is new non-OHLCV data.
2. **GBP_JPY / EUR_JPY / NZD_USD / USD_CHF:** already proceduralised — insert `dim_asset`
   rows (`market_type='Forex'`, `is_active=true`), then run
   `python -m src.system1.ingestion.multi_timeframe_ingest --symbol <PAIR>` per pair
   (resumable; overnight). No new engineering, only operator time and a completion check.

#### Recommended integration (concrete)

1. **Now (Wave 0/1):** ship the spec as written — 1.0-pip proxy, threshold 5.0 pips, pairs
   declared as `[USD_JPY, EUR_USD, GBP_USD, AUD_USD, USD_CAD, GBP_JPY, EUR_JPY, NZD_USD,
   USD_CHF]`; the harness skips pairs with insufficient history by design.
2. **Wave 1 operator job:** complete the GBP_JPY backfill first among the pending pairs (it
   is the documented pair for this strategy and is named by 7 other rows), then EUR_JPY.
   Verify with the coverage query before Wave 2 reads results.
3. **Wave 2 reporting:** the report MUST state (a) which pairs actually ran, (b) that the
   5.0-pip threshold uses the cost-model proxy, not the author's historical GBP/JPY spread
   (2–4 pips in 2010 ⇒ the author effectively traded ≥10–20 pip gaps), and (c) that per-fold
   trade counts are ~10–17 per pair (weekly frequency), so per-cell `low_confidence` flags
   are expected arithmetic, not a defect.
4. **Do not** procure an external spread dataset for Wave 2. If the pooled result is marginal,
   *then* consider option 1(b) as a sensitivity analysis, not a re-specification.

#### Impact if we proceed without it

- **Coverage impact (moderate, temporary):** if the GBP_JPY backfill misses Wave 2, the first
  verdict rests on USD_JPY as the sole JPY cross plus four USD majors. Weekend gaps on
  EUR_USD/USD_CAD are smaller and rarer, so trade counts and edge will likely read *lower*
  than the strategy as documented. This biases toward rejection, not toward a false pass —
  an acceptable direction for a research gate.
- **Threshold impact (permanent unless revisited):** the 5.0-pip proxy admits smaller gaps
  than the author traded. Expect more trades with thinner per-trade edge; a failed gate under
  the proxy does not falsify the author's 10–20-pip-gap variant, and the report must say so.
- **No correctness impact:** no silent substitution was made — the spec never pretends USD_JPY
  is GBP/JPY, and the proxy is a declared constant, not invented data. Fills, costs, and the
  weekend-boundary causality are unaffected.
- **Re-run cost:** once GBP_JPY lands, re-running this strategy is a metadata-level event
  (the pair is already declared); no spec or engine change is required.

---

### weekly_range_reversal

#### Recommendation
**Implement now with reduced coverage — and add GBP_CAD to the Wave-1 ingestion list as a ninth pair.** The strategy is fully testable today on `GBP_USD` plus the four other live majors (the author explicitly generalises to "other ranging major/minor pairs"), so the missing pair must not block the build. But GBP_CAD is the author's *headline* instrument, it is unambiguously Forex (no XAU-style exclusion applies), and it costs exactly one `dim_asset` row plus one resumable OANDA ingest command — the cheapest possible gap to close. Deferring the whole strategy for one pair would waste a clean, mechanical spec; dropping GBP_CAD permanently would discard the cell the author actually traded.

#### What is missing
- **Pair:** `GBP_CAD` (GBPCAD), all granularities (this strategy needs H1 only).
- Not in the live 5-pair universe (`EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD`) and — unlike 8 other named pairs — **not in the Wave-1 addition list** (`GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD`). This is an oversight in the Wave-1 demand extraction, not a deliberate exclusion.
- No granularity or external-feed gap: the strategy needs only H1 OHLCV (CCI, rolling 336-bar range, pip size — all derivable).

#### Why the strategy needs it
The CSV `target_pairs` field names it first: **`GBPCAD|GBPUSD|Other ranging major/minor pairs`**. The author's system was demonstrated on GBPCAD — a high-ATR cross famous for multi-week ranges, which is precisely the regime the hypothesis (§1 of the SPEC) depends on. GBPUSD is the named fallback; "other ranging pairs" maps to the rest of the universe but is an interpolation, not the author's evidence base.

#### How it could be obtained
**OANDA v20 REST — the cheapest path, already built.** GBP_CAD is a standard OANDA instrument; the existing `multi_timeframe_ingest` pipeline needs no code change, only a `dim_asset` row and one command. Expected backfill: ~130k H1 bars to 2006, overnight at practice rate limits, resumable via `ON CONFLICT ("timestamp", asset_id, granularity)` — identical in every respect to the 8 pairs already scheduled. No vendor, licence, or cost considerations arise.

#### Recommended integration
1. Insert `dim_asset` row: `symbol='GBP_CAD'`, `market_type='Forex'`, `is_active=true` (next free `asset_id`, currently 6+ depending on Wave-1 ordering).
2. `python -m src.system1.ingestion.multi_timeframe_ingest --symbol GBP_CAD` (H1 suffices for this strategy; H4/D1/W1 come free with the standard job and serve the rest of the fleet).
3. Verify with the standard coverage query before declaring done, per CONTRACT_V2 §7.
4. No schema change. Pip convention: GBP_CAD is a CAD-quote pair at 0.0001 — confirm `calculate_pips()`/`get_pip_value()` handle it identically to USD_CAD (already live), which they should by construction.
5. Add `GBP_CAD` to `pairs_available` in SPEC-weekly_range_reversal §2 marked **pending**, alongside the Wave-1 list.

#### Impact if we proceed without it
The backtest would measure the strategy on `GBP_USD`, `EUR_USD`, `USD_JPY`, `AUD_USD`, `USD_CAD` (plus pending Wave-1 pairs) — 5–13 cells instead of 6–14. That is still fully informative about the *rules*: the hypothesis is a generic range-reversion claim, not a GBPCAD-specific one, and five live pairs give an adequate pooled sample. What is lost is (a) the single cell with the strongest a-priori regime fit (GBPCAD's ranging reputation is why the author chose it), creating mild adverse-selection risk in the pooled verdict — if the strategy passes without its best pair, the verdict is if anything conservative; (b) fidelity to the source, since the author's own demonstrations are unverifiable. Net: proceed without it now; ingest GBP_CAD overnight and re-run the cell when it lands — the marginal cost of both actions is near zero.

---

### xard_ma_cross_daily_open

#### Recommendation

**Implement now with reduced coverage (FX pairs only); do not chase XAU_USD.** Gold is one of the strategy's two named instrument classes, but XAU_USD is *deliberately excluded* from this platform — it is not Forex, and `calculate_pips()`, pip values, and margin conventions all assume FX pairs. Half-supporting gold would corrupt the r-multiple accounting that every gate consumes. The MA-cross + daily-open core of the strategy is instrument-agnostic, so the 13 FX pairs (5 live, 8 Wave-1 pending) give a fully informative backtest of the documented rules. Revisit gold only if and when the platform adopts a non-FX asset class with its own pip/margin conventions — that is a platform decision, not a strategy-level one.

#### What is missing

- **Pair:** XAU_USD ("Gold"), named verbatim in `target_pairs` as `Majors and minors|Gold`.
- Not missing: any granularity (H1 suffices — the daily open and ADR are derivable from H1 bars at the 21:00 UTC boundary), and any external series (no rates/calendar/COT/volume requirements in this row).

#### Why the strategy needs it

The CSV's `target_pairs` field reads: `Majors and minors|Gold`. The XARD system family was built and demonstrated by its author heavily on gold charts; gold is a first-class instrument in the source thread, not an incidental mention. Excluding it removes one of the two instrument classes the system was designed for.

#### How it could be obtained

- **OANDA v20 REST (cheapest, already built):** XAU_USD is a standard OANDA instrument; the existing ingest pipeline could pull it with one additional symbol — the *data* is trivially obtainable.
- **The blocker is not data, it is conventions:** the platform's pip-value, margin, and r-multiple conventions assume FX (DATA_AVAILABILITY.md states XAU_USD is "excluded on purpose"). Supporting gold requires a `dim_asset` market_type decision ('Metals'), a pip-size convention for XAU (e.g. 0.1 or 0.01 per "pip"), and a margin model — changes to shared infrastructure that are out of scope for this strategy and must not be made as a side effect.
- **Derivable from existing data:** no. Gold prices cannot be synthesised from FX pairs.

#### Recommended integration

None now. If the platform ever adopts metals:

1. Decide the pip/margin convention for XAU_USD (platform-level, System-3 input needed).
2. Insert `dim_asset` row: symbol `XAU_USD`, `market_type='Metals'`, `is_active=true`.
3. Backfill: `python -m src.system1.ingestion.multi_timeframe_ingest --symbol XAU_USD` (H1, H4, D1; resumable, ~130k H1 bars).
4. Note: gold's trading day/session break differs from the FX 21:00 UTC convention (gold has a daily settlement break ~21:00–22:00 UTC); the spec's 21:00 UTC day-boundary definition for the daily open and ADR would need a per-asset review before results on gold are comparable to the FX cells.

#### Impact if we proceed without it

The backtest measures the strategy's documented MA-cross + daily-open rules on FX only. This is still informative: the entry/exit mechanics are price-series-agnostic, and 13 FX pairs provide a far larger statistical sample than one metal would. The loss is external validity for the author's original use case — if the system's edge was concentrated in gold's trend character (deep intraday trends, wide ADR), the FX result will understate (or simply misrepresent) the author's lived experience with the system. That caveat is stated in SPEC §11. Proceeding without gold is the correct trade: a clean 13-pair FX answer now beats a contaminated cross-asset answer built on FX-assumption accounting.

---
