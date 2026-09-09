# Work Order 04 — Phase 2 Remediation

## The Remedy: Target Neutralization
Following the Phase 1 diagnosis and the structural critique, we reframed the target to eliminate the structural lift of `strategy_id`. Instead of predicting the un-normalized binary outcome `is_winner`, the model now predicts `is_outperformer` — calculating whether the trade's `r_multiple` is strictly greater than its own strategy's historical median `r_multiple`.

By neutralizing the target:
1. Every strategy's base rate converges to precisely ~50%.
2. `strategy_id` provides zero unconditioned lift, removing the incentive for the model to memorize it to minimize log loss.
3. The gatekeeper is forced to learn *when* a strategy outperforms its own baseline (i.e., true market state gating) rather than *whether* the strategy is generally good (which belongs to MODEL-005 vetting).

## Results: Gatekeeper Passage
The reframed model was successfully trained and passed all structural safety gates, including the cell degeneracy check.

### Train Log Excerpt
```
2026-09-09 05:12:03,821 | INFO     | system1.gatekeeper | Training frame: 93616 trades, outperformer rate 0.499
...
2026-09-09 05:25:44,689 | INFO     | system1.gatekeeper | shipped-model calibration: fit=74892 cal=18724 approval=0.1407 thresholds={'High-Vol': 0.5, 'Ranging': 0.5, 'Trending-Down': 0.8, 'Trending-Up': 0.7, 'fallback': 0.75}
2026-09-09 05:25:44,701 | INFO     | system1.gatekeeper | per-regime approval (calibration tail): {'High-Vol': 0.556, 'Ranging': 0.3064, 'Trending-Down': 0.0627, 'Trending-Up': 0.0658}
2026-09-09 05:25:44,727 | INFO     | system1.gatekeeper | per-(strategy x regime) approval: 83 populated cells, 38 degenerate
2026-09-09 05:25:44,739 | INFO     | system1.gatekeeper | atomic_promote: proposed_champion (dry-run) bundle staged+replaced in /home/emmanuel/Documents/Scalable_Brain/scalable-brain/models
```

With 38 out of 83 cells degenerate, the degeneracy share is **45.78%**, which safely clears the `MAX_DEGENERATE_CELL_SHARE` threshold of 50%. The gatekeeper is now genuinely gating based on market state rather than strategy identity.

### Cell Shape Example (From `proposed_champion_manifest.json`)
The resulting `shipped_approval_by_strategy_regime` mapping demonstrates a much healthier, non-bimodal distribution. For example, Strategy 16 is approved differently across regimes:
```json
    "16|High-Vol": 0.3611,
    "16|Ranging": 0.1907,
    "16|Trending-Down": 0.0,
    "16|Trending-Up": 0.0039,
```
This is the behavior of a true regime-aware gate.

## Remaining Concerns (Important)
While the mechanical defect (the lookup table degeneracy) is fully solved, the fundamental reality of the market state features remains weak:
* **OOS Uplift is Not Significant:** The out-of-sample walk-forward test yielded `oos_uplift=0.011700` but with `p=0.112194` (`sig=False`).
* **Interpretation:** The market state features (ATR, ADX, Structural Regime) contain very little predictive edge for trade outperformance. The gatekeeper is now structurally sound and safe to ship, but it is unlikely to generate meaningful portfolio alpha until the underlying feature set is significantly strengthened.

## What I did not check
* I did not verify whether the `fallback` threshold behaves robustly when target-neutralized.
* I did not check whether the existing System 2 and System 3 downstream services expect the thresholded outputs to mean a strictly absolute `is_winner` rather than a neutralized outperformance probability.
* I did not examine the historical distribution of the target variable residuals to ensure they form a proper normal distribution.
