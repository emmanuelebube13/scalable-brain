# DATA-GAP-daily_fib_retracement

## Recommendation

**Implement now with reduced coverage (no news filter), and revisit once a calendar feed is budgeted.** The missing data is an economic calendar driving a *risk-avoidance overlay* ("exclude any pair with NFP or interest-rate announcements due within 24h") — it is not the strategy's claimed edge, which is the Fibonacci retracement entry and trailing structure. Omitting the filter leaves the backtest trading a superset of the author's setups; that is honest and measurable, whereas dropping the strategy would discard an otherwise fully specifiable daily system, and silently proxying the calendar would contaminate attribution. A **static, hand-maintained NFP + central-bank decision schedule** is a viable cheap partial proxy for a future pass (flagged below — it must never be introduced silently).

## What is missing

- An **economic event calendar** with, at minimum: event timestamp, affected currency, event type, and importance — sufficient to answer, at any daily decision bar, "does either currency of this pair have an NFP release or an interest-rate announcement scheduled within the next 24 hours?"
- `fact_macro_events` exists in the schema but **is not populated** for this purpose (per DATA_AVAILABILITY.md). No other calendar, news, or sentiment feed exists in the DB.
- Specifically needed event classes: US Non-Farm Payrolls (affects all USD pairs), and rate decisions of the Fed, ECB, BoJ, BoE, RBA, RBNZ, SNB, BoC (mapped to pair currencies).

## Why the strategy needs it

CSV `target_pairs` field, verbatim: **"FX majors and minors; exclude any pair with NFP or interest-rate announcements due within 24h"**. The `edge_description` reinforces it: "News filter eliminates event risk for next 24h". The author's risk model treats event windows as untradeable — retracement levels of a day containing (or preceding) a scheduled shock are, in his framing, unreliable because the event reprices the range rather than continuing it.

## How it could be obtained

1. **Vendor API (cleanest):** TradingEconomics or FinancialModelingPrep economic-calendar endpoints — machine-readable historical + forward calendars covering all required central banks and NFP. Both are paid/licensed (TradingEconomics ~tiered subscription; FMP has a calendar tier); licence terms must be checked before ingestion. Finnhub offers an economic calendar on paid tiers as an alternative.
2. **OANDA v20 REST:** does **not** expose an economic calendar — the existing ingest path cannot cover this gap. (OANDA's Labs/portal shows events but not via the v20 API.)
3. **Forex Factory / investing.com scraping:** the strategy originates on Forex Factory and its calendar (including the weekly XML historically available) is the canonical source, but programmatic scraping violates their ToS; investing.com's "API" is unofficial and unstable. **Not recommended** for a research pipeline that must be reproducible and licensed.
4. **Derivable partial proxy (static schedule, flagged):** NFP is the first Friday of each month at 12:30 UTC (13:30 during US-vs-Europe DST mismatch weeks); FOMC meets ~8 times/year on pre-announced dates; ECB/BoE/BoJ/RBA/BoC/RBNZ/SNB decisions are also scheduled well in advance. A hand-maintained static table of these dates **derivable from public announcements at zero licence cost** would cover the author's two named event classes for the major central banks. Limitations, stated prominently: it cannot capture unscheduled/emergency decisions or non-rate high-impact releases (CPI, GDP), it requires manual maintenance, and historical backfills must use the *actual historical* decision dates, not the modern schedule — otherwise it is look-ahead of a different kind. **This proxy is NOT baked into the Wave-2 spec; it is an option for a later, deliberate integration.**

## Recommended integration

1. Add rows to the existing `fact_macro_events` table (schema change if needed): `event_time_utc`, `currency` (ISO), `event_type` (`NFP`, `RATE_DECISION`, …), `importance`, `source`, `ingested_at`.
2. Ingest via a licensed vendor API (option 1) as a new module, e.g. `python -m src.system1.ingestion.economic_calendar_ingest --source tradingeconomics --since 2005`, backfilling history to 2005 to match D1 coverage. If the static proxy (option 4) is chosen instead, ship it as a versioned CSV in the repo with an explicit `source=static_manual` marker.
3. Strategy-side: at each D1 decision bar, join events on `(currency ∈ pair_currencies) AND (event_time_utc ∈ (decision_close, decision_close + 24h])` — the window must open **at** the decision close, not the bar open, to stay causal.

## Impact if we proceed without it

The backtest measures **the strategy minus its event-avoidance overlay**: all Fib entries that pass trend + zone conditions, including those on the eve of NFP/rate days the author would skip. Consequences:

- **More trades** than the author would take (superset) — event-eve entries add variance, plausibly including some large-gap stops (F6 resolves these honestly, so realised losses beyond 1R will be visible).
- **Countervailing optimism:** the F10 cost model's flat 1.0-pip spread does not widen around events, so event-window execution costs are *understated*. The two distortions partially offset, and the net direction is uncertain — which is exactly why the SPEC (§8, §10 #5) discloses rather than proxies.
- **Still informative:** the core claim — do 50–61.8% retracements of the prior day's range, traded with a 75% invalidation, have edge in EMA50 trends — is fully testable without the calendar. If the unfiltered variant fails the gates, the filter cannot have been the difference-maker for the core edge (it only removes trades); if it passes, a second run with the calendar would quantify the overlay's contribution. Proceeding without it is the right first measurement.
