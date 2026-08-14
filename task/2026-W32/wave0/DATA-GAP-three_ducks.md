# DATA-GAP-three_ducks

## Recommendation

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

## What is missing

- **M5 OHLCV history** for EUR_USD and GBP_USD (the named pairs) — and for any further
  pairs only if the unbounded "any" in `target_pairs` is ever honoured (the SPEC
  conservatively restricts to the two named pairs).
- **Granularity admission** in the research stack: contract v2
  `VALID_GRANULARITIES = ("H1","H4","D1","W1")` and the loader's allowed set both exclude
  M5. Wave 1 allowed granularities after its work: H1, H4, D1, W1 only.
- **Nearest existing data is unusable:** M15/M30 exist (~511k / ~256k bars/pair,
  2006→2026-05) but are stale ~14 weeks, outside the allowed set — and M15 cannot be
  resampled *down* to M5. Nothing is derivable from current data.

## Why the strategy needs it

The trigger logic is explicitly M5-scoped; quoting the CSV row:

- `timeframes`: **"H4 (trend)|H1 (confirm)|M5 (trigger)"**
- `data_requirements`: **"OHLCV on H4|H1|M5|60 SMA on all three timeframes"**
- `entry_logic_long`: **"...on M5 buy when price crosses above its 60 SMA, ideally with a
  break of the last M5 swing high"**
- `risk_management`: **"SL below M5/H1 swing low (short-term)… or fixed 25-30 pips"**

The H4/H1 ducks (both current to 2026-08-07) are fully supported today. Only the M5
trigger frame — its 60 SMA, the 20-bar breakout window, and the stop geometry the
25–30 pip option is calibrated to — is blocked. Two of three ducks cannot fly alone.

## How it could be obtained

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

## Recommended integration

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

## Impact if we proceed without it

There is no honest partial implementation: with M5 absent the strategy emits **zero
orders** and the backtest measures nothing — not a degraded strategy, an empty one. The
only "proceed anyway" option is the H1 trigger variant, which would measure an H1
breakout system wearing this strategy's name and would likely *understate* the design
(its 25-pip stop is below H1 noise). Deferral costs one overnight ingest and two
one-line allow-list edits; that is clearly the right trade.
