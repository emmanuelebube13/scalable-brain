# DATA-GAP-financial_regime_index

## Recommendation

**DEFER — do not implement in Wave 2; revisit only if the macro-ingest is built anyway.** This is the deepest data gap in the CSV: the strategy's entire signal is computed from **nine external daily series, none of which exist in the database and none of which are obtainable through the existing OANDA FX ingest**. Three further reasons compound the data cost:

1. **The author's own conviction is EXPERIMENTAL, with explicitly no performance claims** ("the edge is unverified … the author makes no performance claims"). We would be buying nine feeds and a cross-calendar alignment engine to test a hypothesis its own author does not vouch for.
2. **The signal thresholds are unknown.** The long threshold, always-long floor, and exit lines are Pine-script inputs not reproduced in the CSV. The SPEC declares reconstructed conventions (+0.50 / +1.00 / 0.00 / −0.50 / 0.00), but before any results are trusted, the published script's defaults should be extracted from the TradingView page and substituted. Until then, even a perfect backtest measures a parameterisation we invented.
3. **The cost is real but bounded.** All nine series are available free (stooq / Yahoo Finance for ETF and index closes; FRED for yields, VIX and a DXY proxy). The engineering is a new ingest path plus holiday/calendar alignment against the 24/5 FX clock — roughly a 1–2 day build, but it is a *new class* of data (non-OANDA, non-FX, US-market-calendar) that nothing else in the 51-strategy set needs.

**Do not DROP yet**: the data is free, the SPEC is fully written and implementable the day the series land, and the macro composite may be reusable as a regime filter for other strategies later. **Do not implement now**: defer until (a) the macro ingest exists for its own sake, and (b) the Pine defaults are recovered. If neither happens by the end of the initiative, drop quietly — nothing else depends on this row. A pragmatic middle path if the initiative wants an early read: prototype the composite offline in a notebook against stooq/FRED CSVs before committing to a schema.

## What is missing

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

## Why the strategy needs it

The CSV is unambiguous that the composite *is* the strategy:

- `data_requirements`: "Macro multi-asset series: SPY|ACWI|HYG|LQD|VIX|DXY|US02Y|US10Y|BIL daily closes|z-scored log returns|price SMA filter"
- `entry_logic_long`: "Composite BFCI (inverse-volatility-weighted, optionally winsorized z-scores of 8 macro components with sign flips for credit, 2Y yield, DXY, VIX, BIL/SPY liquidity) crosses above long threshold …"

Without these series there is no BFCI, no trigger, and no slope gate — only the SMA200 price filter survives, which is a generic trend-follower, not this strategy. **Substituting FX-derived risk-on/off proxies (e.g. AUD/JPY as a sentiment gauge) was considered and rejected**: it would silently test a different hypothesis, violating the no-invented-data rule. There is no honest reduced-coverage version.

## How it could be obtained

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

## Recommended integration

1. New table **`fact_macro_series`**: `(series_id TEXT, obs_date DATE, value DOUBLE, vintage_date DATE DEFAULT CURRENT_DATE, source TEXT, pulled_at TIMESTAMPTZ, PRIMARY KEY (series_id, obs_date, vintage_date))` — deliberately separate from `fact_market_prices` (different calendar, different provenance, non-OANDA licence terms).
2. New ingest module (e.g. `src/system1/ingestion/macro_series_ingest.py`) with two loaders: FRED (series id list `DGS2, DGS10, VIXCLS`) and stooq (`spy.us, acwi.us, hyg.us, lqd.us, bil.us`, adjusted closes). Resumable via `MAX(obs_date)` per series, mirroring the existing FX ingest pattern. Overnight backfill: FRED from 1990; stooq histories start at ETF inception (BIL 2007-05, ACWI 2008-03, HYG/LQD 2007-04) — **effective composite history starts ~2008**, so the 2006–2008 FX history is unusable for this strategy; note this in the backtest report.
3. Research accessor beside `research_data.load_ohlcv_readonly`: `load_macro_series(series_ids, start, end)` returning a date-indexed frame; the strategy joins it onto the FX D1 index with the SPEC §9 shift. Read-only, like everything else in the research sandbox.
4. Extract the Pine script's threshold defaults from the TradingView source page and, if they differ from the SPEC's reconstructed +0.50/+1.00/0.00/−0.50/0.00, amend the SPEC before Wave 2 runs it.

## Impact if we proceed without it

There is **no meaningful reduced-coverage run**. Dropping components changes the weighting and sign structure of every remaining z-score (inverse-vol weights renormalise over a different set), so a "partial BFCI" backtest would measure a different composite and could not be cited for or against the strategy. The only executable residue is the SMA200 trend gate, which is not this strategy and would flatter or damn it by accident.

The cost of deferral is correspondingly low: one EXPERIMENTAL strategy out of 51 waits, and the three FX majors it would trade are already covered by ~19 other rows. The cost of *implementing* without the data — or with silent FX proxies — is a contaminated result worse than none. Defer; build the macro ingest if and when it earns its keep across more than one strategy; extract the Pine defaults at the same time; then run the SPEC exactly as written.
