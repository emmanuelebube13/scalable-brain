# Work Order 05 — Holdout Cut

## 1. Trade counts either side of the cut, per granularity, per engine

**Script Output:**
```text
--- Q1: Trade counts ---
  engine_version granularity  is_holdout  num_trades
0             v1          H1       False        7760
1             v1          H1        True        4307
2             v1          H4       False        3524
3             v1          H4        True        1992
4             v2          D1       False        2210
5             v2          D1        True        1402
6             v2          H1       False       31984
7             v2          H1        True       18111
8             v2          H4       False       14171
9             v2          H4        True        8155
```

## 2. Strategies with <30 post-cut trades

**Script Output:**
```text
--- Q2: Strategies with <30 post-cut trades ---
   strategy_id  post_cut_trades
0           27                2
1           40                9
2           25               10
3           23               15
4           46               18
5           17               20
6           31               21
7           53               25
8           57               28
9           19               29
```

## 3. Proof that stage-1 metrics changed as expected

The walk-forward bounds were updated to cap OOS windows strictly before the `2023-01-01` holdout cut. 

When re-running `attribute.py` (which recomputed all OOS metrics) and `vet.py` (which reapplied the gates) under this new constraint, the proposed map shifted significantly compared to the live champion map (which was built before the cut was enforced):
```text
Old cells qualifying: 6
New cells qualifying: 9
Added cells (previously rejected but now qualify without 2023+ data):
  - bb_midline_break@High-Vol
  - strong_weak_analysis@High-Vol
  - precision_swing@Ranging
  - reference_pullback_continuation@Trending-Up
  - mtf_swing_weekly_pivots@Trending-Up

Removed cells (previously qualified but now fail without 2023+ data):
  - double_bottom_measured_move@High-Vol
  - holy_grail_pullback@Trending-Down
```
This confirms that the Stage 1 metrics are now calculating over the isolated pre-2023 window, proving the mechanism works.

## 4. How many of the 17,583 orphaned rows fall after the cut

**Script Output:**
```text
--- Q4: Orphaned rows after cut ---
   is_holdout  num_trades
0       False       11284
1        True        6299
```
*(Sum: 11,284 + 6,299 = 17,583 trades for strategies 7/8/9)*
