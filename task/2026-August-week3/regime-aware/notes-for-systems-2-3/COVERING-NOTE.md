# Systems 2 & 3 Regime-Aware Telemetry Bundle

**Status:** Trial data available
**From:** Computer 1 / System 1
**Action Required:** Read the attached `DASHBOARD-NOTE.md` and schema. Telemetry dashboard update suggested.

## 1. What is new
We are running a trial routing our strategy universes by market regime (e.g. trend_following strategies only trade when Trending). To make this visible, we are now publishing a regime status artifact that details the current regime, whether each strategy is trading or gated off, and the strategy's regime mask.

## 2. What you need to do
Please review `DASHBOARD-NOTE.md` and `contracts/regime-status-contract.json`. They define the shape of the new artifact and our suggestions for rendering it. The view is yours to build.

## 3. What you are NOT blocked on
We are currently publishing this artifact to object storage under the `system1/regime_status/latest.json` pointer. You can begin integrating it into your dashboard whenever you are ready.

**Attachments:**
- `DASHBOARD-NOTE.md`
- `contracts/regime-status-contract.json`
