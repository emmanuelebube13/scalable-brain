# ML Gatekeeper: Inference-Time Features

The champion ML Gatekeeper has been retrained using purely inference-time features:
- `regime_structural` (computed from real-time price history)
- `atr_value`
- `adx_value`

All look-ahead features (`prob_causal_*`, `regime_causal`) were completely removed from the training pipeline to fix the train/serve skew that was causing live signals to be rejected due to missing features.

## Dry-Run Training Results (MODEL-006 Variant)
- **OOS Uplift**: 0.048377
- **P-Value**: 0.000100 (Significant: True)
- **OOS Approval Rate**: 0.2009
- **Shipped Approval Rate**: 0.0790

The candidate model successfully trains and emits valid structural metrics. However, per the instructions, this model has *not* been promoted to production. The bundle is staged locally in `models/champion_model.pkl` and `models/champion_manifest.json` for owner review.
