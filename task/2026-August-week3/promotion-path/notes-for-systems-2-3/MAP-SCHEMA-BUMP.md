# SYSTEM 2/3 MAP SCHEMA BUMP NOTIFICATION

## 1. Schema Version Bump to 2.0.0
We are bumping the `regime_strategy_map.json` contract to `schema_version` `"2.0.0"`.

## 2. Action Required (System 2 & 3)
* **`selection_basis` is now required.** Entries will be marked as either `"qualified"` or `"designated"`.
* **A `"designated"` strategy HAS NOT passed the gates.** It is explicitly forced into the map despite failing one or more strict performance thresholds.
* System 3 **must size designated strategies differently** or refuse them entirely based on risk tolerance. The `gate_failures` field carries exactly what the strategy failed.
* **`direction` and `exits` are now required.** You must use the declared direction (`long`, `short`, or `both`) and exits from the map instead of inferring them from the regime label (which led to the 2026-08-02 incident).

## 3. Informational Changes
* **`gate_failures`, `designated_by`, `designated_reason`, and `designated_at_utc`** are required for all `"designated"` strategies.
* **Honest metrics travel in the manifest.** For designated strategies, we now include:
  - `oos_trade_count`
  - `ci_mean_r` (bootstrap CI on mean R)
  - `pairs_passed_fraction`
  - `max_pair_share`
  - `tail_dependence` (total R with the top 3 winners removed)
* `status` and `qualification_run_id` survive the bump unchanged.
