# SYSTEM 2/3 MEMO: F-103 Fixed

**Subject:** F-103 "gatekeeper scores unknown strategy_ids and NaN rows instead of refusing" is closed by fix.

## Details
The current Gatekeeper champion model has been wrapped with an explicit scoring policy in `src/system1/gatekeeper/score.py`. 

### The Policy:
1. **Unknown `strategy_id` (Cold Start):** The gatekeeper will explicitly refuse to score any strategy_id it was not trained on.
2. **NaN feature rows:** Any row containing `NaN` for expected features will also be refused.

### Outputs:
When a signal is refused by this policy, the gatekeeper emit will be `unscored` with `model_score: null` and `threshold_applied: null`. System 3 must continue to enforce the `unscored` rules (i.e. hold or decide based on alternative rules) as requested in P5.

The vulnerability where the model silently invented a score from imputation and OHE defaults is closed.
