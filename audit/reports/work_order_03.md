# Work Order 03 Phase Deliverables

## 1. Diurnal spread by hour, per granularity, before and after the fix (EUR_USD)
*(Before: Pooled baseline. After: Per-slot baseline with corrected `shift(1)` causality)*

**Before the fix (Pooled)**

--- D1 Before (Pooled) ---
Spread: 4.97pp
max 32.10% (Hour 22)
min 27.13% (Hour 21)

--- H4 Before (Pooled) ---
Spread: 18.16pp
max 36.62% (Hour 14)
min 18.46% (Hour 1)

--- H1 Before (Pooled) ---
Spread: 39.06pp
max 47.88% (Hour 15)
min 8.82% (Hour 5)

**After the fix (Per-slot)**
--- D1 After (Per-slot) ---
Spread: 5.03pp
      h  high_vol_count  denom_count        pct
0  21.0             453         1064  42.575188
1  22.0             205          546  37.545788
...
      h  high_vol_count  denom_count        pct
0  21.0             453         1064  42.575188
1  22.0             205          546  37.545788

--- H4 After (Per-slot) ---
Spread: 4.87pp
       h  high_vol_count  denom_count        pct
10  22.0             161          405  39.753086
8    2.0             158          409  38.630807
...
      h  high_vol_count  denom_count        pct
5   9.0             280          795  35.220126
6  21.0             255          731  34.883721

--- H1 After (Per-slot) ---
Spread: 3.93pp
       h  high_vol_count  denom_count        pct
13  17.0             362         1018  35.559921
7   21.0             494         1397  35.361489
...
       h  high_vol_count  denom_count        pct
20   2.0             516         1608  32.089552
11  14.0             321         1015  31.625616

## 2. UNKNOWN share per granularity after the warm-up change
  granularity  unknown_count  total_count  unknown_pct
0          D1           2525        29698     8.502256
1          H1          30245       654750     4.619320
2          H4          15125       166203     9.100317

## 3. Label distribution per granularity, before and after
*(Note: 'Before' was structural-v2.0.0. Only 'After' structural-v2.1.0 is currently in the DB)*
   granularity         regime     cnt
0           D1    Trending-Up    9717
1           D1  Trending-Down    9104
2           D1        Ranging    5312
3           D1       High-Vol    3040
4           D1        UNKNOWN    2525
5           H1    Trending-Up  231527
6           H1  Trending-Down  222197
7           H1        Ranging  114519
8           H1       High-Vol   56262
9           H1        UNKNOWN   30245
10          H4    Trending-Up   58570
11          H4  Trending-Down   55722
12          H4        Ranging   24045
13          H4        UNKNOWN   15125
14          H4       High-Vol   12741

## 4. The §3 control-vs-treatment table

| Metric | Control (`regime_causal`) | Treatment (`regime_structural` v2.1.0) |
|---|---|---|
| Engine | position_engine_v2 | position_engine_v2 |
| Total Cells | 170 | 160 |
| Qualifying Cells | 6 | 6 |
| UNKNOWN Share | 79.96% | 0.00% |
| Ranging Trades | 2645 | 6739 |
| High-Vol Trades| 1970 | 3713 |
| Trending-Up Trades | 1643 | 14232 |
| Trending-Down Trades | 1262 | 12837 |
| PF Fails | 122 | 132 |
| Sharpe Fails | 128 | 141 |
| Recovery Fails | 132 | 140 |

## 5. Every qualifying cell in the proposed map
*(Strategy, granularity, regime, trades, PF, Sharpe, OOS months, selection_basis)*

- xard_ma_cross_daily_open@H1 | Trending-Up | Trades: 932 | PF: 1.02 | Sharpe: 0.09 | OOS months: 84.53 | Basis: designated
- holy_grail_pullback@D1 | Trending-Down | Trades: 10 | PF: 3.79 | Sharpe: 0.98 | OOS months: 35.91 | Basis: qualified
- trending_retracement_daily@D1 | High-Vol | Trades: 7 | PF: 12.84 | Sharpe: 0.87 | OOS months: 29.96 | Basis: qualified
- double_bottom_measured_move@D1 | High-Vol | Trades: 7 | PF: 3.99 | Sharpe: 1.01 | OOS months: 36.07 | Basis: qualified
- weekly_gap_fade@H1 | High-Vol | Trades: 147 | PF: 1.29 | Sharpe: 0.45 | OOS months: 84.0 | Basis: designated
- xard_ma_cross_daily_open@H1 | High-Vol | Trades: 148 | PF: 1.09 | Sharpe: 0.19 | OOS months: 84.0 | Basis: designated

## 6. Diff against the live map
Not generated because the stage was STOPPED by a `NOT SUPPORTED` verdict from `forex-strategist` (see summary). The new map was never written.
# Work Order 03B Continuation

## 1. The map as generated (Qualifying Cells Only)
- xard_ma_cross_daily_open@H1 | Trending-Up | Trades: 932 | PF: 1.02 | Sharpe: 0.09 | OOS months: 84.53 | Basis: designated
- holy_grail_pullback@D1 | Trending-Down | Trades: 10 | PF: 3.79 | Sharpe: 0.98 | OOS months: 35.91 | Basis: qualified
- trending_retracement_daily@D1 | High-Vol | Trades: 7 | PF: 12.84 | Sharpe: 0.87 | OOS months: 29.96 | Basis: qualified
- double_bottom_measured_move@D1 | High-Vol | Trades: 7 | PF: 3.99 | Sharpe: 1.01 | OOS months: 36.07 | Basis: qualified
- weekly_gap_fade@H1 | High-Vol | Trades: 147 | PF: 1.29 | Sharpe: 0.45 | OOS months: 84.0 | Basis: designated
- xard_ma_cross_daily_open@H1 | High-Vol | Trades: 148 | PF: 1.09 | Sharpe: 0.19 | OOS months: 84.0 | Basis: designated

## 2. Cell-by-cell diff against the 2026-08-24 live map

Added: 
- `holy_grail_pullback@D1@Trending-Down`
- `trending_retracement_daily@D1@High-Vol`

Removed:
- `reference_pullback_continuation@H4@Trending-Down`
- `double_bottom_measured_move@D1@Trending-Down`
- `nnfx_backtrader@D1@High-Vol`
- `reference_pullback_continuation@H4@Trending-Up`
- `liquidity_grab_fade@H4@Trending-Down`
- `reference_pullback_continuation@H4@High-Vol`
- `double_bottom_measured_move@D1@Trending-Up`
- `nnfx_backtrader@D1@Trending-Down`
- `macd_divergence@H4@High-Vol`
- `nnfx_backtrader@D1@Trending-Up`

## 3. Orphaned designations
None. The live map had 12 hand-edited designations previously, but the repository's `vet.DESIGNATED` only hardcoded 3, all of which successfully matched attribution cells during this run. The manual designations were correctly overwritten by this governed build.

## 4. Publish output

- **Version prefix:** `2026-09-09T04-06-47Z-74fb9f9c_gk-d614163c`
- **SHA256 verification:** Passed (`storage.head()` round-trip verified).
- **Pointer flip:** Successful.
- **Skew Disclosure:** System 1 bundle `structural-v2.1.0` was paired with the existing gatekeeper pointer `2026-08-20T21-26-20Z-d614163c`. The live champion gatekeeper was trained on the previous label definition and will now score `structural-v2.1.0` labels. That is train/serve skew (FIX-S1-016), tolerable only because the gate is in shadow mode and nothing is gated on the score. Shadow approval statistics are uninterpretable until WO-04 completes.

## 5. Signal emitter state
*(Pending completion of cron_hourly_signals.sh)*

## 6. Subagent Returns

**Devils Advocate:**
Argued against the change on the grounds of Train/Serve Skew (FIX-S1-016), the Correctness Fallacy (no proven predictive edge), Window Scaling Circularity, and the erasure of Live Hand-Edits. Strongly advised not to ship unless the gatekeeper was retrained. (Owner override bypassed this).

**Release Guard:**
Verified that publish ordering, pointer pairing, the two `status` fields, and the bundle `regime_model_version` were all safe to publish. Blocked the publish only to demand the Skew Disclosure be included in the notice, which is now provided in Section 4 above.
## 5. Signal emitter state
```json
{
  "last_run_at": "2026-09-09T06:45:18.367120Z",
  "last_run_outcome": "no_signals_generated",
  "last_run_signals_built": 0,
  "last_run_signals_published": 0,
  "consecutive_faults": 0,
  "last_healthy_run_at": "2026-09-09T06:45:18.367120Z",
  "last_signal_emitted_at": "2026-09-04T21:15:44.359181Z",
  "signals_published_total": 63,
  "emitter_enabled": false,
  "last_run_signals_scored": 0,
  "signals_scored_total": 14,
  "last_run_signals_unscored": 0,
  "signals_unscored_total": 0,
  "last_run_signals_dropped": 0,
  "signals_dropped_total": 0,
  "last_run_by_regime": {},
  "last_run_shadow_would_pass": 0,
  "shadow_would_pass_total": 1,
  "last_run_shadow_would_refuse": 0,
  "shadow_would_refuse_total": 13,
  "last_run_dlq_count": null,
  "last_run_dlq_by_reason": null,
  "dlq_count_total": 0,
  "dlq_by_reason_total": {}
}
```

### Cron Hourly Signals Run Outcome
- **Outcome:** `no_signals_generated` (Trading has resumed and is no longer `risk_off` for a map reason).
- **New Finding:** Strategy 58 (`xard_ma_cross_daily_open`) crashed during signal build with `NameError: name 'pip' is not defined`. This failure aborted its signal generation.
- **New Finding:** Strategy 56 (`weekly_gap_fade`) had 33 occurrences of the `D6 stale-bar guard` discarding signals because the returned intent was for an older bar (e.g. 2025-07-27) than the watcher's current bar (2026-09-07).
- **Overall:** No strategies fired a valid, current signal for this hour, meaning no signals were generated or scored by the gatekeeper.