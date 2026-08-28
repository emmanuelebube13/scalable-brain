# Agent prompt — replace the telemetry dashboard's mock Strategy Breakdown with live data

Run this in the **System 2 / System 3 repo** (the one that owns the telemetry dashboard and
API). Nothing in System 1 needs to change — everything below is already published and
verified live in GCS as of 2026-08-24 01:34 UTC.

## The problem

The **Strategies → Strategy Breakdown** page renders six hardcoded mock cards:
`Momentum_Breakout`, `Mean_Reversion`, `Regime_Adaptive`, `Trend_Following`,
`Volatility_Breakout`, `Statistical_Arbitrage`, all with category "Quantitative" and
mostly `0.0% / +0.00R / 0.00`.

**None of those strategies exist.** They are invented names. The real live strategies are
five completely different ones. A page showing confident zeros for strategies that do not
exist is worse than an empty page — it is the same failure as the Assets page rendering
`[]` as "System Idle".

## What to build

Replace the mock array with data fetched at runtime from GCS. **Do not hardcode strategy
names, categories or metrics.** When System 1 publishes a new model set or changes the
map, the page must reflect it on the next refresh with no code change and no redeploy.

### Where the data lives

Three objects in bucket `scalable-brain-artifacts`. Two are pointers — resolve them each
time, never cache the resolved path indefinitely, because the version changes on every
publish.

**1. Which strategies are live** — `latest.json` (bucket root)

```
latest.json
  .status                     must be "published"; if "withdrawn", NOTHING is live
  .model_set_id               identity to display and to key your cache on
  .artifacts[]                find the one where name == "regime_strategy_map.json"
                              and GET its .path
```

Then fetch that map. Its shape:

```
.regimes["Trending-Up"|"Trending-Down"|"Ranging"|"High-Vol"] -> [ cell, ... ]
  cell.strategy_id            int
  cell.strategy_key           e.g. "xard_ma_cross_daily_open"
  cell.selection_basis        "qualified" | "designated"   <- display this, see below
  cell.metrics.profit_factor  <- PROFIT FACTOR
  cell.metrics.win_rate       <- WIN RATE (fraction, multiply by 100)
  cell.metrics.trade_count    <- sample size, display it
  cell.metrics.sharpe, .max_drawdown, .recovery_factor, .oos_months
  cell.gate_failures[]        present on designated cells — the gates it failed
```

**2. Category and description** — `system1/analytics/latest.json` → `.path` →
`strategy_catalog.json`

```
.strategies[]
  .strategy_id     STRING here, int in the map — cast before joining
  .name            == strategy_key in the map
  .family          <- CATEGORY  ("trend-following", "gap-fade", ...)
  .description, .entries, .exits, .indicators   available if you want detail rows
  .qualified       bool
```

**3. Per-trade returns for expectancy** — same analytics path → `frequency_stats.json`

```
.cells[]   one row per (strategy_id, regime, granularity, pair)
  .n_trades, .win_rate, .avg_win_r, .avg_loss_r, .trades_per_month
```

### Computing expectancy — read this carefully, there is a sign trap

`avg_loss_r` in `frequency_stats.json` is **negative**. `avg_loss` in
`risk/strategy_stats/latest.json` is **positive**. They are different conventions in
different files. Getting this backwards produces plausible-looking numbers that are
completely wrong — an early attempt here produced +1.35R for a strategy whose profit
factor is 1.11.

Per cell, aggregate across pairs weighted by trade count:

```
e_pair       = win_rate * avg_win_r + (1 - win_rate) * avg_loss_r     # ADD, do not subtract
expectancy_R = Σ(e_pair * n_trades) / Σ(n_trades)
```

Treat a null `avg_win_r` or `avg_loss_r` as 0 (they occur when a cell had no winners or
no losers — 3 of 31 cells today).

**Do not** use `risk/strategy_stats/latest.json` for this card. It is pooled across all
regimes per strategy, while win rate and profit factor here are per-regime. Mixing them
puts three numbers from two different populations on one card.

### Verified expected output

Fetch the three objects, join, and you must reproduce exactly this. If you do not, the
join or the sign convention is wrong — fix it rather than adjusting the expectation.

| Strategy | Category | Regime | Basis | Win rate | Expectancy | PF | Trades |
|---|---|---|---|---|---|---|---|
| xard_ma_cross_daily_open | trend-following | Trending-Up | designated | 37.0% | +0.0715R | 1.11 | 448 |
| liquidity_grab_fade | liquidity-sweep | Trending-Down | qualified | 69.2% | +0.0317R | 8.28 | 26 |
| macd_divergence | momentum-divergence | High-Vol | qualified | 75.0% | +0.0224R | 13.58 | 40 |
| weekly_day_reversal_ea | calendar-anomaly | High-Vol | qualified | 40.0% | +3.4963R | 6.76 | 10 |
| xard_ma_cross_daily_open | trend-following | High-Vol | designated | 39.5% | +0.1524R | 1.25 | 344 |
| weekly_gap_fade | gap-fade | High-Vol | designated | 52.0% | +0.0344R | 1.30 | 200 |

**5 distinct strategies, 6 cards** — `xard_ma_cross_daily_open` is live in two regimes with
different metrics in each. Render **one card per (strategy × regime) cell**, not per
strategy, because every metric here is regime-conditioned. Put the regime on the card.

### UI requirements

- Keep the existing card layout and the WIN RATE / EXPECTANCY / PROFIT FACTOR trio.
- **Category** replaces the hardcoded "Quantitative" subtitle. If `family` is null, render
  "Uncategorised" — never blank, never invented.
- **Show `selection_basis`.** `qualified` means it cleared every gate on measurement.
  `designated` means a human published it **despite failing gates** — three of the six
  live cells are designated, including the one most likely to fire. Visually distinguish
  them (a badge), and surface `gate_failures` on hover or expand. Do not present a
  designated strategy as if it had qualified.
- **Show trade count next to expectancy.** `weekly_day_reversal_ea` reads +3.4963R off
  **10 trades** — that number is noise and must not look like an edge. A reader needs the
  denominator to discount it.
- Replace the `ACTIVE` badge with something true. Cells only fire when their regime is the
  current one, so most are dormant at any moment. If you have the current regime per pair
  (`system1/regime_status/latest.json`), mark cells `LIVE` vs `DORMANT`; if not, drop the
  badge rather than assert ACTIVE.

### Failure behaviour — non-negotiable

- If `latest.json` has `status: "withdrawn"`, render "No model set is live" explicitly.
  Do not fall back to the last known set.
- If a fetch fails, render an error state. **Never render 0.0% / +0.00R / 0.00 as though
  they were measurements.** Zeros that mean "no data" are how this page ended up
  misreporting in the first place.
- Show `model_set_id` and the analytics `generated_at_utc` somewhere on the page, so a
  reader can tell how fresh the numbers are and which artifact they describe.

### Access

The dashboard's service account needs read on `scalable-brain-artifacts` for the keys
above. System 1's `system1-rw` is write-scoped and must not be reused. If the read is
denied, that is a one-line IAM grant, not a reason to hardcode.

### Caching

Poll `latest.json` and `system1/analytics/latest.json` on your normal refresh interval;
they are small. Cache the resolved artifacts keyed on `model_set_id` / analytics
`version`, and invalidate when either changes. Those versions change on every publish,
which is exactly the signal that the strategy set may have changed.

## Done when

Reproducing the verified table above from live GCS with no strategy name, category or
metric hardcoded anywhere; designated cells visibly marked; trade counts shown; and
pointing the page at a withdrawn model set produces an explicit "nothing live" state
rather than zeros.
