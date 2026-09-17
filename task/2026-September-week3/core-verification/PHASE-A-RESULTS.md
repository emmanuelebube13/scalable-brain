# Phase A — fair-execution re-measure: results (2026-09-17)

**What changed in the measurement** (owner go-ahead 2026-09-17; FIX-S1-022/023 + strategy-30 floor):
per-pair pip resolution reaches every stored order; same-bar SL/TP collisions resolved by
M15 walk (5 of 12,319 OOS trades remain `sl_tp_ambiguous`, stop-first); `r_multiple` is
net of a 2.4-pip round-trip cost; strategy 30 rejects sub-0.5 R:R setups.

**Evidence:** ranking `results/reports/STRATEGY_RANKING.md` (run `ed334191`, 10:28Z) vs the
01:05Z pre-fix ranking (in git at commit 8d0929b). Bank: 12,319 OOS v2 trades, net mean R
**−0.0911** (the −0.07 era figure is not comparable — different definition AND the 56k
orphan removal).

## Who moved and why

| strategy | pre-fix meanR | post-fix (net) | driver |
|---|---|---|---|
| inside_bar_reversal | −0.119 (gross era) | −0.006 | collision fix (+0.115) net of costs |
| smashing_forex_2 | −0.442 | −0.306 | JPY pip fix; still CI-negative |
| three_candle_swing_reversal | −1.15 (audit era) | −0.187 | JPY pip fix |
| riding_trend_retracement | −4.59 (audit era) | −1.146 | JPY pip fix; still worst in house |
| mtf_swing_weekly_pivots | +0.024 | **−0.025** | costs erased it (was in the live map) |
| precision_swing | +0.078 | +0.050 | costs; survives, still best volume-backed |
| kiss_h4 / currency_momentum | +0.02 / +0.001 | ≈ −0.00 | costs — they were spread-thin all along |
| weekly_gap_fade (designated) | −0.008 | −0.020, Sharpe −2.6, CI [−.049,+.012] | costs; **owner should reconsider the designation** |
| bb_midline_break | ~0.000 | −0.080 pooled | costs; its High-Vol CELL still qualifies (PF 1.63, n=56) |

**Qualification impact:** proposed map falls 7 → **4 cells** (43 Trending-Up, 22 Ranging,
13 High-Vol qualified + 56 High-Vol designated). 35/41/50/53 no longer clear the gates
under honest execution. Pooled: **0 of 42 pass all gates** (unchanged) and the only
CI-clear-of-zero strategy remains the integrity-disqualified one.

## Phase B tier assignment (from this ranking)

- **Tier 1 (qualification candidates):** none yet on pooled evidence. Closest:
  `precision_swing` (n=245, +0.050, 5 pairs balanced) and `strong_weak_analysis`
  (n=59, +0.102). Both need either more sample or a demonstrated conditioning edge.
- **Tier 2 (grow the sample, no judgment):** `double_bottom_measured_move` (+0.164, n=14),
  `reference_pullback_continuation` (+0.228 but 2 pairs), `ma_crossover_swing` (n=31),
  `nnfx_backtrader` (+0.140, n=49).
- **Tier 3 (retire via `is_active=false` — CI clear of zero on the NEGATIVE side):**
  `smashing_forex_2` [−0.428,−0.177] n=975; `riding_trend_retracement` [−2.096,−0.338];
  `liquidity_grab_fade` [−0.126,−0.020] n=331 (post-floor). These are the first
  statistically honest retirement decisions the platform can make. **Owner sign-off
  requested** (retirement is reversible; rows/history stay).

## Watch items
- The 2.4-pip flat cost is a bracket midpoint; refine per pair from Systems 2/3 live fills
  before treating near-zero strategies (kiss_h4, currency_momentum) as definitively dead.
- Only 5 ambiguous-exit trades — the M15 walk resolved 97%+ of collisions.
- `weekly_gap_fade@H1@High-Vol` designation now sits on a pooled Sharpe of −2.6 —
  owner decision needed (it is an owner override; not withdrawn unilaterally).
