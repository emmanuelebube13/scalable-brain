# DATA-GAP-weekly_gap_fade

## Recommendation

**Implement now with reduced coverage.** Nothing here blocks the build: the spec
(`SPEC-weekly_gap_fade.md`) runs today on USD_JPY plus EUR_USD, GBP_USD, AUD_USD, USD_CAD,
and it degrades gracefully — the harness simply skips declared-but-unbackfilled pairs, and
the missing spread feed is replaced by the sanctioned 1.0-pip cost-model constant. **Do not
defer, do not drop** — but read the Wave-2 verdict with two caveats: the author's documented
pair (GBP/JPY) may be absent from the first run, and the backtest trades smaller gaps than
the author did.

## What is missing

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

## Why the strategy needs it

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

## How it could be obtained

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

## Recommended integration (concrete)

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

## Impact if we proceed without it

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
