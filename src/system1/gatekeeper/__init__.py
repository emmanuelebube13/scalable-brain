"""MODEL-006 — ML gatekeeper: regime features + dynamic threshold + OOS uplift.

Trains an XGBoost gatekeeper on the backtested trades (point-in-time regime probability
features + market features → win/loss), calibrates a regime-aware dynamic approval
threshold within a turnover band, and runs a walk-forward OOS uplift study (approved vs
rejected P&L with a bootstrap significance test) that gates promotion. Champion artifact
contract (model/preprocessor/manifest + SHA256) is preserved for the Layer 4 loader.
"""
