# DATA-GAP-usd_carry_basket

**Strategy:** Quantpedia Dollar Carry Trade (USD vs developed-currency basket) — row 5 of forex_swing_strategies.csv
**Companion spec:** `SPEC-usd_carry_basket.md`

## Recommendation

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

## What is missing

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

## Why the strategy needs it (quoted from the CSV)

> **data_requirements:** "OHLCV FX spot/forward rates|3-month US Treasury rate|3-month rates (or forward discounts) of basket currencies"

> **entry_logic_long:** "Compute equal-weighted average forward discount (AFD) of the 10-currency basket vs USD (average 3-month foreign rate can substitute); if 3-month US Treasury rate > AFD go LONG USD and short the equal-weighted basket"

The entire entry condition is a comparison of two rate levels. OHLCV prices — the only data
we have — enter the strategy only through the contract-required ATR stop. Without the rate
series there is no signal, no direction, and nothing to backtest.

## How it could be obtained

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

## Recommended integration

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

## Impact if we proceed without it

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
