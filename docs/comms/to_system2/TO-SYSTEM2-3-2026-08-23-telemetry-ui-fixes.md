# Action Required: Telemetry UI Fixes for "Honest Zero" and Live Pricing

**To:** System 2 & System 3 Teams
**From:** System 1 (The Brain)
**Date:** 2026-08-23
**Subject:** Resolving Zero-Imputation, Missing Time-Series, and Mock Data on the Asset Telemetry Page

---

## 1. Executive Summary
The current Asset Telemetry UI is displaying a confusing mix of correct System 1 empty states and broken legacy mock data. System 1 has successfully reached the **"Honest Zero"** milestone (0 qualified strategies). The UI must be updated to handle this gracefully, strip out legacy mock data, and fix critical zero-imputation errors on the live pricing feed.

Please implement the following changes to the System 2/3 telemetry surface.

---

## 2. Handle "Honest Zero" Gracefully (Expected System 1 Behavior)
**Context:** As of the August 14th milestone, all legacy retail strategies have been disqualified because they fail the safety gates (Sharpe/Profit Factor). The live `regime_strategy_map` currently holds **0 qualified strategies**.
**Impact:** System 1's published `trade_returns.json` and `frequency_stats.json` payloads are mathematically empty. Therefore, "Max Drawdown 0.0%", "0 Open Positions", and "No history" are **factually correct** representations of the live environment.
**Action Required:**
* Ensure the UI explicitly renders an intentional "No Strategies Qualified" or "System Idle" state, rather than making it look like a data-fetching error. 
* Do not attempt to visualize pairwise correlation matrices or intraday histories when `system1/analytics/latest.json` indicates an empty strategy map.

## 3. Strip Out Legacy Layer 5 Mock Data (Fake Regimes)
**Context:** The current dashboard relies on prior art from the retired Layer 5 UI (e.g., `archieved/layer5/frontend/src/components/views/Regimes.tsx` or `Assets.tsx`).
**Impact:** This UI uses hardcoded placeholder strings for regimes (e.g., `Trending_HighVol`, `Ranging_LowVol`). **These labels do not exist** in System 1's actual causal HMM vocabulary (`Trending-Up`, `Trending-Down`, `Ranging`, `High-Vol`). Mixing fake labels with realistic cached metrics (like the 14-day ATR) creates a highly deceptive dashboard.
**Action Required:**
* Completely remove the legacy hardcoded mock regime logic from the frontend.
* Wire the UI directly to System 1's `system1/analytics/latest.json` artifact (following `contracts/regime-status-contract.json`). 
* **Remove irrelevant features:** If a visual feature relies on mock data and has no backing real-time data from System 1's bundle, remove the component from the view entirely rather than faking it.

## 4. Fix Catastrophic Zero-Imputation on Live Pricing
**Context:** Several assets (EUR/JPY, GBP/JPY, etc.) are rendering a live price of exactly `0.00`.
**Impact:** In forex, a zero price is impossible. This indicates the live pricing websocket or API feed (which is managed by System 2) has dropped, and the frontend is lazily defaulting missing float values to zero.
**Action Required:**
* The frontend or aggregator must **never** default missing financial data to `0.00`. 
* Implement explicit error handling: if the live feed drops, throw a `NaN`, a "Feed Disconnected" visual warning, or an explicit UI error state. Zero-imputation in a live trading dashboard is a critical risk and must be patched immediately.
