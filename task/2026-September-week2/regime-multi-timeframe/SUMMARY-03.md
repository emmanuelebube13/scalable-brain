# Work Order 03 Summary (Handoff to WO-04)

## What Was Done & What Changed
1. **Intraday Volatility De-seasonalisation**: Changed the baseline volatility calculation in `src/regime/structural.py` to compare each bar against its own time-of-day slot's trailing history, using `groupby(atr_pct.index.time).transform(lambda g: g.shift(1).rolling(...).mean())`. 
2. **Warm-up Recomputation**: Removed the static row-index based warm-up in `build_structural_labels` and replaced it with a dynamic `[vol_zscore.isna()] = UNKNOWN` mask.
3. **Gatekeeper Inference Fix**: Modified `src/gatekeeper/features.py` to READ structural labels directly from `fact_regime_structural` using a strict DB join, failing loudly if labels are missing.
4. **Vetting Orphaned Designations Fix**: Modified `src/vetting/vet.py` to identify and report `DESIGNATED` configuration cells that matched no attribution cells.
5. **Labels Built & Map Evaluated**: Re-derived all structural labels for D1/H4/H1 (`structural-v2.1.0`), producing 802k rows. Generated and evaluated both control (`regime_causal`) and treatment (`regime_structural`) attribution metrics and map reports.

## What is Now True (Numbers)
- **Coverage**: The UNKNOWN share successfully dropped from 79.96% to exactly 0.00% across all evaluated trades. The label itself correctly reserves ~4% to 9% as UNKNOWN for warmup depending on granularity.
- **Diurnal Spread**: The diurnal volatility spread dropped significantly (e.g. from 39.06pp to 2.79pp on H1, and 18.16pp to 2.74pp on H4) proving the arithmetic fix worked.
- **Map Quality**: Despite perfect coverage, the absolute map quality did not show yield improvements. Qualifying cells remained flat at 6, and total core metric failures (Sharpe, Profit Factor) actually increased compared to the control run.

## What Each Agent Found
- **Structure Warden**: Found everything structurally sound and properly located.
- **Leakage Hunter**: Confirmed that the `shift(1)` within the per-slot `groupby` strictly preserved causality. No future leakage.
- **Measurement Reviewer**: Concluded that while coverage reached 100%, there was no statistical evidence that map quality improved; in fact, core metric failures increased.
- **Forex Strategist**: **[VERDICT: NOT SUPPORTED / DEFINITIVELY BROKEN]**. Evaluated the conceptual change and concluded that a per-slot de-seasonalised baseline turns a structural market regime into an intraday relative anomaly score. It breaks temporal persistence (causing the label to flicker hour by hour) and arbitrarily spans a full calendar year to gather 252 bars, smearing macro environments together.

## What I Could Not Do & What Was Not Checked
- **Could Not Publish Live Map**: Because the `Forex Strategist` explicitly rejected the conceptual change as "DEFINITIVELY BROKEN", and WO-03 states *"A CONFIRMED leakage or NOT SUPPORTED verdict stops the stage. Do not work around a finding,"* the stage was **STOPPED**. No live map was generated, vetted, or published.
- **What Was Not Checked**: `devils-advocate` and `release-guard` gates were not run because the stage was aborted prior to generating a live map. The downstream gatekeeper degeneracy was not evaluated (out of scope).

## The One Thing To Check Before This Goes Live
This change **must not go live**. The owner must evaluate the `Forex Strategist` finding. If intraday regimes are required, the baseline logic must be re-architected to use a pooled trailing window of recent chronological bars (e.g., 1-2 weeks) rather than an isolated time-of-day history. Until then, `structural-v2.1.0` remains conceptually broken.

## 03B Continuation
- **What Changed:** The owner explicitly overturned the `NOT SUPPORTED` verdict from the `forex-strategist` and authorized a live write of the proposed `structural-v2.1.0` map. We vetted the map (dropping 10 old cells and adding 2, leaving 6 total qualifying cells), generated the live state, published the new System 1 model set, and flipped the pointer to resume system operations.
- **Did Trading Resume?:** Yes. The `last_run_outcome` is no longer `risk_off` due to the frozen map. The cron job completed successfully.
- **What to Watch Over the Next 24 Hours:**
  1. **Strategy 58 Crash (`xard_ma_cross_daily_open`)**: This strategy threw a `NameError: name 'pip' is not defined` during signal build and failed to emit signals. This is a critical runtime defect in the strategy code that needs immediate fixing if this cell is meant to fire.
  2. **Strategy 56 Stale-Bar Guard (`weekly_gap_fade`)**: This strategy fired 33 intents for old bars (e.g., 2025-07) that were successfully caught and discarded by the D6 stale-bar guard. Ensure this strategy's internal timekeeping is correct.
  3. **Train-Serve Skew (`FIX-S1-016`)**: The live gatekeeper is still trained on causal HMM labels but is now scoring `structural-v2.1.0` labels. The system is failing open, and shadow approval statistics will remain uninterpretable until WO-04 completes retraining the gatekeeper.
  4. **Data Corruption Risk from Vet**: As found by the `db-guardian`, the `vet.py` script executes runtime DDL (`ALTER TABLE`) and full-table rewriting (`UPDATE`) which violates schema constraints and idempotent write volume rules. This needs refactoring.
