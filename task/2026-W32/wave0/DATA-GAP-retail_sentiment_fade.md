# DATA-GAP-retail_sentiment_fade

## Recommendation

**Defer the backtest until sentiment data accumulates — but start forward ingestion immediately, and implement the strategy code now.** There is no reduced-coverage option: the signal IS the external feed, and zero rows of sentiment data exist in the DB, so running the backtest today would measure nothing (not a degraded version of the strategy — literally zero trades). Do not drop the strategy: the spec is mechanically complete, the behavioural hypothesis is legitimate and distinctive (the only alternative-data strategy in the 51-row fleet), and the fix is cheap — a daily/hourly snapshot ingest into a new `fact_sentiment` table. The realistic timeline to a first statistically thin evaluation is 12–24 months of forward accumulation; a 36-month-training walk-forward fold cannot be satisfied before ~3 years of history exist. That is arithmetic, and the eventual report must say so rather than presenting a thin result as a verdict.

## What is missing

- **Per-pair retail long/short ratio time series** for EUR_USD, GBP_USD, USD_JPY (and any future pairs): percent of open retail positions long and short, count-of-positions basis.
- **Cadence needed:** at least one snapshot per day; hourly preferable (cheap to store, enables tighter lag assumptions later). The SPEC's conservative assumption is a **24-hour minimum publication-to-use lag** (§9 rule S1).
- **Causality-critical fields:** each record must carry the vendor's nominal observation timestamp AND the publication/ingest timestamp — sentiment vendors publish with lag and sometimes restate values, so "when could we have known this number" is the whole ballgame for an honest backtest.
- Nothing else is missing: all three named pairs have full D1/H1 price history; SMA/ATR are in the indicator inventory. This is purely a non-price feed gap (DATA_AVAILABILITY: "No COT positioning, no economic calendar... no news sentiment").

## Why the strategy needs it

The CSV's `data_requirements` field: **"OHLCV|Retail long/short ratio via Ziwox JSON API|Fast and slow SMA"**, and both entry conditions are gated on the external series: *"If Retail Short Ratio >= 60% (crowd heavily short) ... BUY contrarian"* and mirror. Without the ratio series there is no signal to implement — every trade decision reads the feed.

## How it could be obtained

| Source | What it offers | Licence / availability (honest assessment) |
|---|---|---|
| **Ziwox API** (the source's vendor) | REST/JSON retail-sentiment endpoint; free API key after Ziwox Terminal registration; also bundles COT and "fundamental bias" data | **Small vendor, informal terms, continuity risk.** Historical depth is undocumented — appears to serve current/near-current snapshots, not deep history. Suitable as the forward-ingest source (it is what the strategy documents), unsuitable for backfill. |
| **OANDA open position ratios** | Retail long/short ratios for OANDA's own client book — the same broker our price data comes from | Historically published via OANDA Labs with ~1 year of history; availability via the documented v20 REST API is **uncertain** (labs endpoints have been moved/retired over time — needs hands-on verification before relying on it). If available, cheapest option: already have OANDA credentials. |
| **Myfxbook Community Outlook** | Long/short %, volumes, avg entry prices across 70+ symbols | Official sentiment API: **$50/month or $500/year**, ≤2,880 requests/day, **no historical download** (community feature requests outstanding) — forward accumulation only. Unofficial scrapers exist (e.g. Apify actor) — ToS risk; not recommended for a system of record. |
| **IG client sentiment** | IG client positioning, surfaced via DailyFX | IG Labs API is free with an IG account (live or demo); historical depth limited. Reasonable secondary/cross-check source. |
| **Dukascopy SWFX Sentiment Index** | Public count-based sentiment on SWFX marketplace participants | Free, public web endpoints with some historical series — the best candidate for partial backfill, but it measures Dukascopy's crowd, not Ziwox's. |
| **Derivable from existing data?** | — | **No.** There is no honest derivation of retail positioning from OHLCV. A price-momentum or tick-volume proxy would be a different strategy wearing this one's name. Explicitly rejected (SPEC §8). |

## Recommended integration

1. **Schema:** new table `fact_sentiment`:
   `(asset_id INT REFERENCES dim_asset, source TEXT, observed_at TIMESTAMPTZ, published_at TIMESTAMPTZ, ingested_at TIMESTAMPTZ DEFAULT now(), long_ratio_pct NUMERIC, short_ratio_pct NUMERIC, basis TEXT CHECK (basis IN ('positions','volume')), sample_size INT NULL, PRIMARY KEY (asset_id, source, observed_at))`.
   `published_at` is non-negotiable — the SPEC's causality rule reads `published_at ≤ decision_time − 24h`. Write path belongs to ingestion only (research modules never write `fact_*`).
2. **dim_asset:** no change — sentiment rows reference existing asset_ids 1/2/3 (EUR_USD, GBP_USD, USD_JPY).
3. **Ingest job:** new `sentiment_ingest.py` modelled on the existing OANDA ingest pattern: poll the Ziwox JSON API (primary) hourly, snapshot every poll (never overwrite — restatements become new rows keyed by `observed_at`/`ingested_at`), run via cron. Optionally add OANDA position ratios as a second `source` row per observation for cross-vendor validation.
4. **Strategy wiring:** the Wave-2 implementation loads `fact_sentiment` through a read-only accessor alongside `load_ohlcv_readonly`, applies the 24h eligibility rule, and otherwise follows the SPEC verbatim.

## Impact if we proceed without it

There is no "without it" that measures this strategy: zero sentiment rows → zero signals → an empty trade frame. A backtest run before ingestion starts is not degraded, it is vacuous. If we instead substitute a price-derived proxy, the backtest would measure a momentum/mean-reversion strategy and falsely carry this strategy's name — worse than no result, because it could be promoted or killed on evidence about a different system. The correct interim posture: implement the code against `fact_sentiment` now (unit-testable with synthetic sentiment fixtures), start ingestion now, and treat the strategy as EXPERIMENTAL-in-accumulation until ≥12–24 months of snapshots exist. Even then, the first walk-forward evaluation will return `low_confidence` on trade count — which is the expected, honest verdict for a slow daily signal on a young dataset.
