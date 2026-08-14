# DATA-GAP-strong_weak_analysis

## Recommendation

**Implement now with reduced coverage, and trigger the missing-cross ingest in parallel.** The strategy is computable today: the 13 pairs available after Wave 1 (5 live + 8 pending) touch all 8 major currencies, so the strength ranking and the strongest-vs-weakest pair selection both function. But 15 of the 28 crosses are absent, which (a) biases the per-currency strength sums — CHF is ranked on a single cross (USD_CHF), NZD on two — and (b) silently discards roughly half the candidate trade instruments whenever the strongest/weakest combination is a missing cross (the spec's conservative rule is *skip the bar*, §10 #4). All 15 missing crosses are standard OANDA instruments obtainable through the ingest pipeline that already exists, at zero licence cost and one overnight backfill. Deferring the strategy until the data lands is unnecessary; dropping it is unwarranted. The backtest report must state prominently that pre-ingest results measure a degraded-coverage variant of an already-reconstructed formula (see SPEC §10 #1, #7).

## What is missing

15 crosses of the 8-major matrix (USD, EUR, GBP, JPY, AUD, NZD, CAD, CHF), at D1 granularity (H1/H4 also needed since fills resolve on H1 and the standard ingest covers all granularities anyway):

AUD_CAD · AUD_CHF · AUD_JPY · CAD_CHF · CAD_JPY · CHF_JPY · EUR_CHF · EUR_NZD · GBP_AUD · GBP_CAD · GBP_CHF · GBP_NZD · NZD_CAD · NZD_CHF · NZD_JPY

No external/non-price series is missing — the strategy needs OHLCV only. W1 staleness is irrelevant (D1 strategy).

## Why the strategy needs it

CSV `target_pairs`: *"All 28 pairs from 8 majors (trade strongest currency vs weakest)"*, and `data_requirements`: *"Daily close OHLCV for all 28 major crosses to compute proprietary per-currency strength ranking"*. Both roles require the full matrix:

1. **Strength input:** the reconstruction sums each currency's oriented z-scores across *all* its crosses. With 13 pairs, EUR/USD/JPY are measured on 5–7 crosses while CHF gets 1 and NZD 2 — the ranking systematically under-weights thin currencies and can mis-rank exactly the currencies (CHF, NZD) that frequently sit at the strong/weak extremes.
2. **Trade instrument:** when best/worst is, say, GBP/NZD or CAD/JPY, no instrument exists and the bar is skipped. Expected signal loss: of the C(8,2) = 28 possible best/worst combinations, 15 (54%) are untradeable pre-ingest.

## How it could be obtained

**OANDA v20 REST — cheapest, already built.** All 15 crosses are standard OANDA CURRENCY instruments (the same source as the existing 13 pairs; EUR_CHF appears in the v20 `AccountInstruments` documentation, and the full 8-major cross matrix is part of OANDA's standard instrument list — confirm against the account's `GET v3/accounts/{accountID}/instruments` response before scheduling, as the tradable list varies slightly by regulatory division). No new vendor, no licence cost, no schema change. If any cross turns out to be unavailable on this account's division, it degrades gracefully: the spec already skips untradeable combinations and drops absent pairs from the strength sums.

## Recommended integration

Identical to the Wave-1 pair procedure (contract §7, Part F):

1. Insert `dim_asset` rows for the 15 symbols (`market_type='Forex'`, `is_active=true`), asset_ids continuing the existing sequence.
2. `python -m src.system1.ingestion.multi_timeframe_ingest --symbol <PAIR>` per pair (resumable via `ON CONFLICT ("timestamp", asset_id, granularity)`; ~130k H1 bars per pair to 2006; run overnight against practice rate limits).
3. Verify with the coverage query before declaring done; the harness skips pairs with insufficient history, so partial completion is safe.
4. No schema change, no strategy-code change: the spec's universe U is defined as "available pairs", so the strategy automatically picks up new crosses as they land.

## Impact if we proceed without it

The backtest would measure a **13-pair reduced-universe variant**: strength sums computed on unequal cross counts per currency (CHF = USD_CHF alone), and ~54% of strongest/weakest combinations skipped. The result is still informative — a negative verdict on the reduced universe almost certainly extends to the full one (more data cannot fix a dead edge), and the mechanics of ranking/trend/trail are fully exercised — but a *positive* verdict would carry an explicit caveat: ranking fidelity for CHF/NZD is unproven, and the trade-selection distribution differs from the author's 28-pair universe. Given the ingest is cheap and uses existing infrastructure, the reduced-coverage run should be treated as a smoke test, with the full-matrix re-run following the overnight backfill.
