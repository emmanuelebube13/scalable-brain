# Proposed Fixes Register

Central, prioritized list of proposed fixes (bugs, design flaws, validity gaps) found across all
systems. Each entry is a self-contained proposal a reviewer (or LLM judge) can evaluate cold:
**evidence → root cause → fix → validation → rollout**. We work these in **priority order**.

## How this folder works
- One file per fix, named `FIX-<system>-<NNN>-<slug>.md` (e.g. `FIX-S1-001-metrics-engine.md`).
- Filed under the owning system: `system-1/`, `system-2/`, `system-3/`, or `cross-cutting/`.
- Status flows: **Proposed → Approved → Implemented → Verified → Promoted/Closed**.
- Severity: **P0** (blocks/corrupts results, fix first) · **P1** (important, distorts trust) ·
  **P2** (cleanup/quality).

## Register

| ID | Title | System | Severity | Status | Owner | Link |
|----|-------|--------|----------|--------|-------|------|
| FIX-S1-001 | Financial-metrics engine: Sharpe annualization + unbounded max-drawdown | System 1 | **P0** | ✅ Closed — promoted (run 5bfa38bc) + bundled to Computer 2 (2026-06-26T22-53-39Z) | — | [link](system-1/FIX-S1-001-metrics-engine.md) |
| FIX-S1-002 | "OOS≥60mo" gate measures in-sample span, not true out-of-sample | System 1 | **P1** | Implemented (log-only) — true OOS via walk-forward folds; `oos_fail` 0→8, 11/80 cells now below the 60-mo gate; live map untouched, pending promotion sign-off | — | [link](system-1/FIX-S1-002-oos-not-true-out-of-sample.md) |
| FIX-S1-003 | Regimes don't discriminate strategy performance (map premise inert) | System 1 | **P1** | Proposed (investigation) | — | [link](system-1/FIX-S1-003-regimes-do-not-discriminate.md) |
| FIX-S1-004 | Per-regime weights collapse on duplicate strategy_id (Ranging weight 5e-8, not 1.0) | System 1 | **P0** | ✅ Verified (log-only) — Ranging corrected 5e-8→1.0 in `proposed_strategy_weights.json`; live artifact untouched, pending promotion sign-off | — | [link](system-1/FIX-S1-004-weights-collapse-duplicate-strategy-id.md) |
| FIX-S1-005 | Regime labels non-causal (in-sample HMM fit + smoothing) leak future into attribution + gatekeeper OOS | System 1 | **P1** | Implemented (log-only) — causal walk-forward labels emitted+consumed; leakage test green; OOS uplift did NOT shrink (0.0319→0.0405, still sig); live champion/map untouched, pending sign-off | — | [link](system-1/FIX-S1-005-regime-labels-non-causal-leakage.md) |
| FIX-S1-006 | Retrain deployment gates `oos_uplift_ok` & `beats_incumbent` never reject | System 1 | **P1** | Implemented (log-only) — both inert gates armed: `oos_uplift_ok` now requires `uplift≥MIN_UPLIFT and significant` (MODEL-006 threaded in, fails CLOSED on missing result / `--allow-missing-uplift` override), serializer persists `regime_accuracy` so `beats_incumbent` can compare; gate-can-fire tests red-before/green-after; 105→114 passed; live champion/map untouched, pending sign-off | — | [link](system-1/FIX-S1-006-deployment-gates-never-reject.md) |
| FIX-S3-001 | Correlation & exposure gates blind to open positions (never fire); veto reasons unlogged | System 3 | **P1** | Proposed | — | [link](system-3/FIX-S3-001-correlation-exposure-gates-blind.md) |
| FIX-S3-002 | "25% exposure" cap is a position count (`len*10`), not a notional fraction | System 3 | **P1** | Proposed | — | [link](system-3/FIX-S3-002-exposure-cap-unit-confusion.md) |
| FIX-S3-003 | Kelly sizing inert (always capped at 2%) on a stale, wrong-signed edge | System 3 | **P1** | Proposed | — | [link](system-3/FIX-S3-003-kelly-sizing-inert-and-stale-edge.md) |
| FIX-S3-004 | 2% risk cap computed in quote currency, not account currency (JPY/CAD pairs) | System 3 | **P1** | Proposed | — | [link](system-3/FIX-S3-004-risk-cap-quote-currency-units.md) |
| FIX-S3-005 | Trade auditor scans entry bar inclusive (pre-fill leakage) + brittle float-match patch | System 3 | **P2** | Proposed | — | [link](system-3/FIX-S3-005-auditor-entry-bar-leakage-and-float-match.md) |
| FIX-XC-001 | Regime label leaks future data (HMM forward-backward posterior) into every downstream join | Cross-cutting | **P0** | Proposed | — | [link](cross-cutting/FIX-XC-001-regime-label-lookahead-leak.md) |
| FIX-XC-002 | Regime table written by undocumented HMM producer; Layer-3 reads 5 regime features that are 100% NULL | Cross-cutting | **P1** | Proposed | — | [link](cross-cutting/FIX-XC-002-regime-producer-provenance-null-features.md) |
| FIX-XC-003 | Live DB password committed in git-tracked files (and history) | Cross-cutting | **P1** | Proposed | — | [link](cross-cutting/FIX-XC-003-db-password-committed-in-tracked-files.md) |
| FIX-S2-001 | Live ML gatekeeper scores every signal on an all-NaN feature row at the wrong threshold (champion-artifact contract break) | System 2 | **P0** | Proposed | — | [link](system-2/FIX-S2-001-champion-contract-break.md) |
| FIX-S2-002 | Live OANDA fills recorded as FAILED (broker adapter return-contract mismatch) | System 2 | **P0** | Proposed | — | [link](system-2/FIX-S2-002-broker-return-contract.md) |
| FIX-S2-003 | Live pipeline can never act on existing data (H1 default vs H4-only signals; 60-min freshness vs H4 cadence) | System 2 | **P1** | Proposed | — | [link](system-2/FIX-S2-003-granularity-and-freshness-mismatch.md) |
| FIX-XC-004 | Granularity handoff gaps (H1 signals missing; D1 regime produced-but-unconsumed) | Cross-cutting | **P2** | Proposed | — | [link](cross-cutting/FIX-XC-004-granularity-handoff-gaps.md) |

> **Automated discovery:** to hunt for more of these, run the reusable
> [System Audit Agent prompt](SYSTEM_AUDIT_AGENT_PROMPT.md) (one agent per system). It files new
> `FIX-*` entries here. FIX-S1-001/002/003 are the exemplar bar it must clear.

## Notes
- **FIX-S1-001** is implemented and validated on real data (drawdowns now bounded 0–100%, Sharpe
  realistic). The only remaining step is regenerating + **promoting** the corrected
  regime→strategy map after sign-off.
- **FIX-S1-002** was surfaced while fixing S1-001; it does not produce impossible numbers but
  **overstates confidence** in qualified strategies, so it is the next priority after S1-001 closes.
