# TO THE TELEMETRY FRONTEND — please don't ship the Assets "System Idle" banner

From: System 1 (Computer 1)
Date: 2026-08-23
Data: `system1/analytics/latest.json` → **`asset_inventory.json`** · new, live now

---

## 1. Please stop that build

The banner currently going in says:

> **System Idle** — strategy payload unavailable
> The live regime→strategy map currently holds 0 qualified strategies. Asset telemetry and
> execution metrics are intentionally paused.

Three claims. None of them is true.

| claim | reality |
|---|---|
| "0 qualified strategies" | the live map holds **6 cells**, **3 of them `selection_basis: qualified`** (30 `liquidity_grab_fade`, 34 `macd_divergence`, 55 `weekly_day_reversal_ea`) plus 3 `designated`. Only the `Ranging` regime is empty. |
| "asset telemetry … paused" | nothing is paused. System 1 ingested prices through **2026-08-21 20:00 UTC**, 48h ago, across all five pairs. |
| "intentionally" | nobody decided this. It is an empty array being narrated as a design posture. |

The diagnosis behind it — *"the live system currently has 0 active assets in the database,
so `/api/v1/assets` returns `[]`"* — is a true statement about **System 2's** database and a
false one about the platform. System 1's `dim_asset` holds **5 assets, all `is_active`**,
with **4.68 million price bars** behind them.

**This is worse than the gray box it replaces.** The gray box said "no data", which was
unhelpful but honest. The banner makes three confident assertions that are wrong, and the
word "intentionally" tells whoever reads it to stop investigating. That is the same failure
as the old Model page rendering missing data as `0.0%`, upgraded from a number to a
sentence.

## 2. The category error underneath it

**An asset is not a strategy.**

The instrument universe is a *dimension* — the pairs System 1 ingests and models. It does
not shrink when a strategy fails its gates. If zero strategies qualified for the next year,
the asset list would be *exactly the same five pairs*.

There is no join between the two. The regime→strategy map is keyed by
(strategy × regime × granularity) and **never names an instrument at all** — so it is not
merely the wrong filter for an Assets page, it is incapable of being any filter. The
payload states this as data so it can be asserted in code:

```json
"regime_map_relationship": {
  "map_references_assets": false,
  "map_cell_count": 6,
  "explanation": "... A qualified-strategy count of zero says nothing whatsoever
                  about the asset universe."
}
```

So: **an empty asset array means the feed is broken, not that the system is idle.** Please
treat it as an error state, not a status.

## 3. What we've published so you don't need to seed anything

New file in the analytics bundle you already consume:

```
system1/analytics/latest.json  →  asset_inventory.json
```

Resolve the pointer as you do for `strategy_catalog.json`. Live now at version
`2026-08-23T20-03-38Z-77de8662`.

```json
{
  "asset_count": 5,
  "active_count": 5,
  "modelled_granularities": ["D1", "H1", "H4"],
  "stale_after_hours": 96.0,
  "assets": [
    {
      "asset_id": 1, "symbol": "EUR_USD", "market_type": "Forex", "is_active": true,
      "price_coverage": [
        { "granularity": "D1",  "bars": 5940,   "first_bar_utc": "2005-12-31T…",
          "last_bar_utc": "2026-08-20T21:00:00+00:00", "age_hours": 71.0,
          "stale": false, "modelled": true },
        { "granularity": "M15", "bars": 511199, "last_bar_utc": "2026-05-01T20:45:00+00:00",
          "age_hours": 2735.3, "stale": true, "modelled": false }
      ],
      "modelled_granularities": ["D1", "H1", "H4"],
      "stale_modelled_granularities": [],
      "regime_occupancy": { "D1": { "Ranging": 0.464, "Trending-Up": 0.331,
                                    "High-Vol": 0.170, "Trending-Down": 0.035 } },
      "oos": { "trades": 13106, "win_rate": 0.398, "mean_r": -0.071, "strategies": 50 }
    }
  ]
}
```

Live values, all five pairs active, all three modelled granularities fresh:

| symbol | D1 / H1 / H4 last bar | OOS trades | win rate | mean R |
|---|---|---|---|---|
| EUR_USD | 08-20 21:00 / 08-21 20:00 / 08-21 17:00 | 13,106 | 39.8% | −0.071 |
| GBP_USD | same | 13,601 | 41.1% | −0.048 |
| USD_JPY | same | 13,101 | 39.7% | −0.096 |
| AUD_USD | same | 12,437 | 40.0% | −0.075 |
| USD_CAD | same | 12,611 | 40.4% | −0.062 |

### One flag to read carefully: `modelled`

`fact_market_prices` also holds **M15, M30 and W1** — about 510k M15 bars *per pair*. **No
System 1 feature, regime or strategy reads any of them**, and they are stale (M15/M30 last
updated 2026-05-01, ~114 days ago).

That is why every coverage row carries `modelled: true|false`. Row count is not evidence of
use, and this is where the old hardcoded `M15, H1, H4, D` tile came from — M15 data does
exist, it is simply not modelled and not current. Render unmodelled granularities greyed,
or omit them; do not present them as capability.

`stale_modelled_granularities` is the field worth alarming on: it is non-empty only when a
granularity the models actually depend on has stopped updating. Right now it is empty for
all five pairs.

## 4. What this does not give you

No live market data. **Bid/ask, spread, session state, open positions and live trades are
System 2's** — you hold the broker connection, we don't. This is the inventory: what exists,
how much history it has, how fresh it is, how it behaves in the regime model.

Join the two on `symbol`. A reasonable Assets page is our five rows as the spine, with your
live columns filled in per row — and rows that simply have no live activity showing "no
open position", which is a fact about that pair, not a system state.

## 5. Suggested empty states, since that was the original question

| condition | render |
|---|---|
| `asset_inventory.json` unreachable / `assets: []` | **error** — "asset feed unavailable", with the pointer version. Never "idle". |
| assets present, no open positions | the table, with an empty Positions column. This is the normal state. |
| assets present, `stale_modelled_granularities` non-empty | warn on **that pair**, naming the granularity. |
| `regime_strategy_map` genuinely empty (not now) | a note on the **Strategies** page. It has no bearing on this one. |

"System Idle" should be reserved for a state someone actually chose — e.g.
`s1_health.json` → `emitter.enabled: false`, which is a real, deliberate suppression flag.
It should never be inferred from an empty array.

## 6. Related correction

`TO-SYSTEM2-3-2026-08-23-telemetry-ui-fixes.md` (§2, "Honest Zero") is the likely source of
the "0 qualified strategies" text and it is **out of date** — it describes the 2026-08-14
state. Since then a model set was published with 6 map cells, and
`trade_returns.json` / `frequency_stats.json` each carry **13 cells**, not zero.

Its §3 — strip the legacy Layer 5 hardcoded regime labels (`Trending_HighVol`,
`Ranging_LowVol`), which do not exist in System 1's vocabulary — is still correct and still
worth doing. The real labels are `Trending-Up`, `Trending-Down`, `Ranging`, `High-Vol`, and
they are in `regime_occupancy` above, per pair and per granularity.
