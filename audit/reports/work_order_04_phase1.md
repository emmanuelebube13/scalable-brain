# Work Order 04 — Phase 1 Diagnosis

## Raw Script Output
**Script 1 (In-Sample and Univariate Stats):**
```text
--- Q1: Strategy ID dominance ---
Total rows: 18489
Number of strategies: 51
Top 5 strategies share: 57.98%
Base rate (win rate) by strategy:
Min: 0.00%, Max: 100.00%, Std: 19.18%

--- Q2: Market State Learnability (Excluding strategy_id) ---
AUC without strategy_id (in-sample): 0.5998
Are there any approved trades? 1423 out of 18489

--- Q3: Numeric feature univariate associations ---
atr_value: r = -0.0152 (p=0.0386)
adx_value: r = -0.0334 (p=0.0000)
prob_causal_trending_up: r = -0.0245 (p=0.0009)
prob_causal_trending_down: r = 0.0020 (p=0.7843)
prob_causal_ranging: r = 0.0070 (p=0.3404)
prob_causal_high_vol: r = 0.0154 (p=0.0367)

--- Q4: Is the target well-posed? ---
Overall win rate: 40.47%
Overall R-multiple mean: -0.0610
If base rate varies wildly by strategy (see Q1), predicting 'is_winner' unconditionally forces the model to just memorize strategy baserates.

--- Q5: Was the incumbent ever non-degenerate? ---
models/champion_manifest.json: 84 / 88 degenerate (95.5%)
./mlruns/6/718fe0cea2124503b0f5043542499d3e/artifacts/champion_manifest.json: 66 / 71 degenerate (93.0%)
./mlruns/6/ceb75b4000b54f98819e4a4c80c012e8/artifacts/champion_manifest.json: 84 / 88 degenerate (95.5%)
```

**Script 2 (Out-Of-Sample CV):**
```text
OOS AUC without strategy_id: 0.5367 +/- 0.0030
```

## Agent Reviews
1. **Measurement-Reviewer Verdict: NOT SUPPORTED & SUPPORTED (with caveats)** [View Conversation](conversation://14c4f9b1-581c-411d-acff-101aa71498e9)
   * `measurement-reviewer` ruled the point-biserial claim "NOT SUPPORTED" because pooling across 51 strategies from two incompatible engines (`backtest_engine_v1` and `position_engine_v2`) is a category error. 
   * It ruled the "ill-posed target" claim "SUPPORTED", noting that the unconditioned model minimizes log loss by memorizing heterogeneous group base rates, though the root flaw is the cross-engine pooling.
2. **Devil's Advocate Verdict:** [View Conversation](conversation://44e624aa-5191-4def-a622-a99204f1c716)
   * Retiring the gatekeeper is a massive fail-open. It acts as an implicit strategy allocation filter protecting the portfolio from 0% win-rate strategies.
   * Suggested Remediation: **Target Neutralization**. Predict `r_multiple` relative to the strategy mean, stripping `strategy_id` of its structural lift.

## Verdict
**This is a fixable model, but the target must be reframed.** 
The premise of predicting a raw, un-normalized outcome across 51 strategies with wildly varying base rates forces the model to memorize `strategy_id`. Throwing the model away would constitute a massive fail-open. Remediation path (Phase 2): Target Neutralization (predicting `r_multiple` minus `strategy_median_r_multiple`).

## What I did not check
* I did not check if the individual orphaned rows (strategies 7/8/9) could be filtered out to resolve the cross-engine pooling; I followed the directive "Flag, do not fix."
* I did not check the live performance implications of the exact 0% win-rate strategies if they were to bypass the model.
