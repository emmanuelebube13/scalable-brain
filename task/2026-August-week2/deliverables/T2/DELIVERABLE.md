# T2 Refresh `fact_trade_outcomes` Deliverable

## Before/After Comparison

```diff
2c2
< 134407|2016-08-03 10:00:00-03|2026-07-24 16:00:00-03
---
> 134500|2016-08-19 16:00:00-03|2026-08-14 17:00:00-03
5,6c5,6
< H1|115668|2016-08-03 10:00:00-03|2026-07-24 16:00:00-03
< H4|18739|2016-08-15 22:00:00-03|2026-07-24 06:00:00-03
---
> H1|115752|2016-08-19 16:00:00-03|2026-08-14 17:00:00-03
> H4|18748|2016-08-31 06:00:00-03|2026-08-14 10:00:00-03
9,18c9,18
< 1|13109|2026-07-24 16:00:00-03
< 2|6292|2026-07-24 06:00:00-03
< 3|6292|2026-07-24 06:00:00-03
< 4|24117|2026-07-24 09:00:00-03
< 5|17308|2026-07-24 08:00:00-03
< 6|11146|2026-07-24 08:00:00-03
< 7|13934|2026-07-24 06:00:00-03
< 8|13934|2026-07-24 06:00:00-03
< 9|27383|2026-07-24 08:00:00-03
< 10|892|2026-07-22 03:00:00-03
---
> 1|13120|2026-08-14 13:00:00-03
> 2|6306|2026-08-14 17:00:00-03
> 3|6306|2026-08-14 17:00:00-03
> 4|24145|2026-08-14 12:00:00-03
> 5|17319|2026-08-14 13:00:00-03
> 6|11143|2026-08-14 06:00:00-03
> 7|13934|2026-08-14 09:00:00-03
> 8|13934|2026-08-14 09:00:00-03
> 9|27399|2026-08-14 13:00:00-03
> 10|894|2026-07-31 11:00:00-03
21,22c21,22
< f|41002
< t|93405
---
> f|40945
> t|93555
```

## Run Details
- **Exact Command Line:** `python -m src.layer0.persist_trade_outcomes --granularities H1,H4 --lookback-years 10`
- **Runtime:** Started at ~02:25:25 UTC, Finished at 02:28:13 UTC (Runtime: ~2 minutes 48 seconds)
- **Final `DONE:` line:** `2026-08-15 02:28:13 | INFO     | DONE: {'strategies': 10, 'backtests': 100, 'trades': 134500}`

## Checks

| # | Check | Pass/Fail | Actual Value |
|---|---|---|---|
| 1 | **min timestamp** | PASS | `2016-08-19 16:00:00-03` |
| 2 | **max timestamp** | PASS | `2026-08-14 17:00:00-03` |
| 3 | **total rows** | PASS | `134500` |
| 4 | **rows vs snapshot** | PASS | Gained 93 rows (134,500 vs 134,407). This is a net positive change within the acceptable rolling window variation. |
| 5 | **granularities** | PASS | H1: 115,752, H4: 18,748 (both populated) |
| 6 | **strategy ids** | PASS | All 10 strategies are present, and proportions align with the baseline. |
| 7 | **is_oos** | PASS | Both `t` (93555) and `f` (40945) present, no NULLs. |

## Snapshot Data
- **Snapshot Table:** `fact_trade_outcomes_bak_20260815`
- **Row Count:** 134,407

## Notes
- As instructed, I deliberately did not touch attribution, vetting, or the orchestrator.
- I noticed that strategy 10 was rebuilt with seemingly valid rows (894 rows) as expected due to the deliberate look-ahead in `range_stochastic.py`. I have not touched it.
- **Attribution and vetting are now stale against these new outcomes**.
