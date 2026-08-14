# Data availability — `fact_market_prices`

**Measured 2026-08-09** against the live `ForexBrainDB`. Do not assume anything beyond this.

## Pairs present (`dim_asset`)

| asset_id | symbol | market_type |
|--:|---|---|
| 1 | EUR_USD | Forex |
| 2 | GBP_USD | Forex |
| 3 | USD_JPY | Forex |
| 4 | AUD_USD | Forex |
| 5 | USD_CAD | Forex |

**Five pairs. That is all.** Any strategy naming another pair produces a `DATA-GAP` note.

## Granularity coverage (per pair; counts are representative)

| Granularity | Bars/pair | From | To | Usable? |
|---|--:|---|---|---|
| **H1** | ~130,400 | 2006-01-01 | **2026-08-07** | ✅ current — the workhorse |
| **H4** | ~33,100 | 2006-01-01 | **2026-08-07** | ✅ current |
| **D1** | ~5,900 | 2005-12-31 | **2026-08-06** | ✅ current |
| W1 | 1,068 | 2005-12-30 | 2026-06-12 | ⚠️ **stale ~8 weeks**; refresh pending (Wave 1, agent G) |
| M30 | ~256,000 | 2006-01-01 | 2026-05-01 | ❌ stale ~14 weeks; **not** in the allowed set |
| M15 | ~511,000 | 2006-01-01 | 2026-05-01 | ❌ stale ~14 weeks; **not** in the allowed set |

Allowed granularities for research after Wave 1: **H1, H4, D1, W1**. M15/M30 are out of
scope — they are stale and no source strategy needs them (one row mentions M15; treat it as
a data gap).

## Pairs being added in Wave 1

`dim_asset` rows are written by Wave 1; the **backfill is an overnight operator job** and may
not be complete when Wave 2 runs. Write strategies to declare these pairs; the harness skips
pairs with insufficient history rather than failing.

GBP_JPY · EUR_JPY · NZD_USD · USD_CHF · EUR_GBP · EUR_AUD · AUD_NZD · EUR_CAD

**`XAU_USD` is excluded on purpose** — not Forex; `calculate_pips()` and margin conventions
assume FX. Two strategies name it; both get a data-gap note.

## Data shape

`research_data.load_ohlcv_readonly(pair, granularity, lookback_years=10)` returns a frame
indexed by UTC `timestamp` with columns: `Open`, `High`, `Low`, `Close`, `Volume`.

- **Bars are stamped at their OPEN.** A D1 bar at `2026-08-05T21:00Z` covers 21:00 on the
  5th → 21:00 on the 6th. This is the single most important fact for multi-timeframe
  causality: that bar is not knowable until `2026-08-06T21:00Z`.
- **`Volume` is OANDA tick count, not traded volume.** Any strategy whose edge rests on real
  volume gets a data-gap note. Tick volume is a usable proxy for activity, but say so.
- The market is closed Friday 21:00 → Sunday 21:00 UTC. Gaps there are normal, not defects.
- Column case: `Open` and `Close` are capitalised in the DB and must be double-quoted in
  SQL; the loader renames `high`/`low`/`volume` to `High`/`Low`/`Volume` for you.

## Non-price data — none of it exists

No COT positioning, no economic calendar, no options data, no VIX, no DXY series, no news
sentiment. `fact_macro_events` exists but is not populated for this purpose.

Scanning the CSV's `data_requirements`, the affected count is small — a handful of rows
mention options, calendar, VIX, DXY or tick volume. **Most of the 51 are derivable from OHLCV
alone.** The real gaps are pairs and W1, not exotic feeds.
