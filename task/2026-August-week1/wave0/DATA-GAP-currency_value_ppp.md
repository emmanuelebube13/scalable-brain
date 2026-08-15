# DATA-GAP-currency_value_ppp

**Strategy:** Quantpedia Currency Value Factor — PPP Strategy (row 44 of forex_swing_strategies.csv)
**Companion spec:** `SPEC-currency_value_ppp.md`

## Recommendation

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

## What is missing

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

## Why the strategy needs it (quoted from the CSV)

> **data_requirements:** "OECD Purchasing Power Parity figures|monthly CPI changes|OHLCV FX rates"

> **entry_logic_long:** "Compute fair PPP value per currency from latest OECD PPP updated with monthly CPI and FX changes; go LONG the 3 most undervalued currencies (lowest PPP fair value) vs USD, equal weight"

The entire entry condition is a comparison of spot prices against a PPP-derived fair value.
OHLCV prices — the only data we have — enter the strategy through the spot half of the
misvaluation ratio and the contract-required ATR stop. Without the PPP and CPI series there
is no fair value, no misvaluation, no ranking, and nothing to backtest. (Note: the spec
resolves the pseudocode's undefined "FX changes" update term to the standard relative-PPP
formula — fair value drifts with the foreign-vs-US CPI differential, so USD CPI is required
too; SPEC §10 row 4.)

## How it could be obtained

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

## Recommended integration

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

## Impact if we proceed without it

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
