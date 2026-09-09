# Scalable-Brain Audit Report

**Run ID:** 2026-09-05_1145
**Mode:** FULL

## Summary

| Severity | PASS | FAIL | INCONCLUSIVE |
|---|---|---|---|
| **P0** | 1 | 3 | 0 |
| **P1** | 0 | 1 | 0 |
| **P2** | 0 | 0 | 0 |
| **P3** | 0 | 0 | 0 |

## Findings

### [A1] D1 bar timestamp semantics - P0

**Status:** FAIL

**Verdict:** D1 bars are reproduced by [T, T+24h) meaning the timestamp marks the open. This confirms a P0 lookahead if D1 timestamp is treated as close.

**Evidence:**
- `total_bars_checked`: 100
- `matches_prev_window`: 0
- `matches_next_window`: 90
- `sample_records`: [{'asset_id': 1, 'timestamp': '2023-12-05 22:00:00', 'd1_ohlc': {'Open': 1.079395, 'High': 1.08048, 'Low': 1.075865, 'Close': 1.076435}, 'prev_window_ohlc': {'Open': 1.08354, 'High': 1.084755, 'Low': 1.077805, 'Close': 1.07983}, 'next_window_ohlc': {'Open': 1.079395, 'High': 1.08048, 'Low': 1.075865, 'Close': 1.076435}, 'match_prev': False, 'match_next': True}, {'asset_id': 1, 'timestamp': '2008-10-03 21:00:00', 'd1_ohlc': {'Open': 1.37745, 'High': 1.37745, 'Low': 1.37745, 'Close': 1.37745}, 'prev_window_ohlc': {'Open': 1.38206, 'High': 1.39085, 'Low': 1.370195, 'Close': 1.3773}, 'next_window_ohlc': {'Open': 1.37745, 'High': 1.37745, 'Low': 1.37745, 'Close': 1.37745}, 'match_prev': False, 'match_next': True}, {'asset_id': 1, 'timestamp': '2006-08-08 21:00:00', 'd1_ohlc': {'Open': 1.283355, 'High': 1.290255, 'Low': 1.276385, 'Close': 1.286055}, 'prev_window_ohlc': {'Open': 1.284055, 'High': 1.28935, 'Low': 1.280755, 'Close': 1.283255}, 'next_window_ohlc': {'Open': 1.283355, 'High': 1.290255, 'Low': 1.276385, 'Close': 1.286055}, 'match_prev': False, 'match_next': True}, {'asset_id': 1, 'timestamp': '2012-08-05 21:00:00', 'd1_ohlc': {'Open': 1.23978, 'High': 1.24434, 'Low': 1.234195, 'Close': 1.24004}, 'prev_window_ohlc': {'Open': 1.23863, 'High': 1.23993, 'Low': 1.23774, 'Close': 1.23974}, 'next_window_ohlc': {'Open': 1.23978, 'High': 1.24434, 'Low': 1.234195, 'Close': 1.24004}, 'match_prev': False, 'match_next': True}, {'asset_id': 1, 'timestamp': '2011-11-17 22:00:00', 'd1_ohlc': {'Open': 1.3458, 'High': 1.36139, 'Low': 1.34472, 'Close': 1.35255}, 'prev_window_ohlc': {'Open': 1.34631, 'High': 1.353985, 'Low': 1.34221, 'Close': 1.34577}, 'next_window_ohlc': {'Open': 1.3458, 'High': 1.36139, 'Low': 1.34472, 'Close': 1.35255}, 'match_prev': False, 'match_next': True}, {'asset_id': 1, 'timestamp': '2011-05-22 21:00:00', 'd1_ohlc': {'Open': 1.412565, 'High': 1.414685, 'Low': 1.396975, 'Close': 1.40479}, 'prev_window_ohlc': {'Open': 1.41561, 'High': 1.41561, 'Low': 1.41094, 'Close': 1.412585}, 'next_window_ohlc': {'Open': 1.412565, 'High': 1.414685, 'Low': 1.396975, 'Close': 1.40479}, 'match_prev': False, 'match_next': True}, {'asset_id': 1, 'timestamp': '2009-06-13 21:00:00', 'd1_ohlc': {'Open': 1.40105, 'High': 1.40336, 'Low': 1.3992, 'Close': 1.39965}, 'prev_window_ohlc': None, 'next_window_ohlc': {'Open': 1.40105, 'High': 1.40336, 'Low': 1.3992, 'Close': 1.39965}, 'match_prev': False, 'match_next': True}, {'asset_id': 1, 'timestamp': '2008-07-15 21:00:00', 'd1_ohlc': {'Open': 1.591225, 'High': 1.594865, 'Low': 1.580105, 'Close': 1.582655}, 'prev_window_ohlc': {'Open': 1.590825, 'High': 1.603885, 'Low': 1.586585, 'Close': 1.591135}, 'next_window_ohlc': {'Open': 1.591225, 'High': 1.594865, 'Low': 1.580105, 'Close': 1.582655}, 'match_prev': False, 'match_next': True}, {'asset_id': 1, 'timestamp': '2025-02-10 22:00:00', 'd1_ohlc': {'Open': 1.03092, 'High': 1.038165, 'Low': 1.029215, 'Close': 1.036125}, 'prev_window_ohlc': {'Open': 1.02925, 'High': 1.033655, 'Low': 1.02838, 'Close': 1.030705}, 'next_window_ohlc': {'Open': 1.03092, 'High': 1.038165, 'Low': 1.029215, 'Close': 1.036125}, 'match_prev': False, 'match_next': True}, {'asset_id': 1, 'timestamp': '2020-12-16 22:00:00', 'd1_ohlc': {'Open': 1.21991, 'High': 1.227285, 'Low': 1.218995, 'Close': 1.22685}, 'prev_window_ohlc': {'Open': 1.21522, 'High': 1.221265, 'Low': 1.21251, 'Close': 1.21998}, 'next_window_ohlc': {'Open': 1.21991, 'High': 1.227285, 'Low': 1.218995, 'Close': 1.22685}, 'match_prev': False, 'match_next': True}]

---

### [A2] End-to-end label knowability - P0

**Status:** FAIL

**Verdict:** Backtest trade at signal bar 2026-07-31 20:00:00+00:00 used regime 'High-Vol' from regime bar 2026-07-31 20:00:00+00:00. Label was computable at 2026-07-31 21:00:00+00:00, while signal was computable at 2026-07-31 21:00:00+00:00. Delta is 0.0 hours. A delta <= 0 indicates lookahead since the batch regime job would not have completed instantly.

**Evidence:**
- `signal_bar_time`: 2026-07-31T20:00:00+00:00
- `label_value`: High-Vol
- `label_knowable_at_time`: 2026-07-31T21:00:00+00:00
- `signal_computable_at_time`: 2026-07-31T21:00:00+00:00
- `delta_hours`: 0.0

**Notes:** Verified against backtest trades joined with fact_market_regime_v2 in src/attribution/attribute.py.

---

### [A4] merge_asof direction and tolerance - P0

**Status:** FAIL

**Verdict:** merge_asof uses direction='backward' but lacks an explicit tolerance.

**Evidence:**
- `exact_call`:     merged = pd.merge_asof(
        decision_times.sort_values("bar_time"),
        labels,
        on="bar_time",
        direction="backward",
    ).set_index("bar_time")
- `max_observed_label_age_hours`: 23.0
- `signals_older_than_48h`: 0

**Notes:** Max observed label age: 23.0 hours. Flagged 0 signals older than 48 hours.

---

### [D3] NULL-at-edge rule - P0

**Status:** PASS

**Verdict:** No live-path consumer violates the NULL-at-edge rule.

**Evidence:**
- `null_columns_at_edge`: ['atr_percentile_20d', 'trend_alignment_score', 'volatility_regime', 'session_volume_z', 'h4_trend_direction', 'd1_trend_direction', 'regime_causal', 'prob_causal_trending_up', 'prob_causal_trending_down', 'prob_causal_ranging', 'prob_causal_high_vol', 'causal_label_method', 'causal_fold_id', 'cluster_centroids_json', 'label_map_json']
- `live_files_checked`: ['src/signals/run.py', 'src/signals/build.py', 'src/gatekeeper/score.py', 'src/gatekeeper/features.py']

**Notes:** Live routing and scoring build features on the fly (e.g. regime_structural) and do not read regime_causal or other edge-NULL columns.

---

### [B1_B2] Cost Model: Price semantics and omitted spread magnitude - P1

**Status:** FAIL

**Verdict:** B1: Trades enter and exit at Mid prices (OHLC) +/- slippage. Spread is NOT deducted from realized R (it hits dollar PnL only). B2: Computed median stop distance is 57.50 pips. Spread (1 pip) as % of R is 1.74%.

**Evidence:**
- `median_stop_pips`: 57.50000000000033
- `spread_pips`: 1.0
- `spread_pct_of_r`: 1.7391304347825987
- `b1_prices`: Mid (OHLC + slippage)
- `b1_spread_in_r`: False

**Notes:** R-multiples are spread-free by construction, overstating true edge.

---

