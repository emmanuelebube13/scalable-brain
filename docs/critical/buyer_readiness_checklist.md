# Scalable Brain Buyer Readiness Checklist - Swing Trading Edition

> **SWING TRADING SYSTEM** | Pre-sale and deployment checklist for swing trading system

**Status:** draft  
**Trading Type:** Swing Trading (multi-hour to multi-day trade execution)  
**Purpose:** A pre-sale and pre-licensing checklist for deciding whether Scalable Brain is ready to be sold to a broker, enterprise buyer, or institutional partner.

Use this checklist before:
- pitching OANDA or any other broker
- signing a licensing deal
- onboarding external users
- running live capital with third-party oversight

Completion rule:
- Treat every unchecked item as a blocker unless explicitly marked `non-blocking`.
- Do not claim production readiness until every item in Sections 1 through 8 is complete and evidenced.

## 1. Product Definition

- [ ] Define the exact product being sold: research platform, signal engine, execution module, telemetry stack, or full managed system.
- [ ] Write a one-paragraph buyer value proposition that states what problem the system solves.
- [ ] Identify the target buyer profile: broker, prop desk, hedge fund, retail platform, or analytics vendor.
- [ ] Define the commercial boundary of the product: what is included, what is excluded, and what is custom work.
- [ ] Produce a short architecture summary for non-technical buyers.
- [ ] Document whether the product is sold as software, licensed IP, service, or internal-use tooling.
- [ ] Define expected deployment model: on-prem, private cloud, managed service, or hybrid.
- [ ] Define whether the buyer gets source code, binaries, API access, or dashboard-only access.
- [ ] Define the support model: business hours, 24/7, best effort, or SLA-backed.

Exit criteria:
- A buyer can understand the offering in 2 minutes and the contract scope in 1 page.

## 2. Architecture Integrity

- [ ] Verify Layer 0 qualification is fully reproducible from the current codebase and DB state.
- [ ] Verify Layer 1 regime ingestion uses a stable contract and does not infer labels differently in live mode.
- [ ] Verify Layer 2 signal generation is deterministic for identical inputs.
- [ ] Verify Layer 3 model training uses only supported granularities and rejects unsupported data.
- [ ] Verify Layer 4 consumes upstream artifacts only and does not recompute regime or signal logic.
- [ ] Verify Layer 5 telemetry reads from authoritative tables and does not mutate trading state.
- [ ] Verify Layer 6 audit closes the loop on actual trade outcomes.
- [ ] Verify Layer 7 execution uses a broker-safe adapter and does not bypass Layer 4 gates.
- [ ] Remove or explicitly document every legacy fallback path that weakens the live contract.
- [ ] Confirm the champion model contract is materially present and consumed consistently.

Evidence to collect:
- [ ] Layer 3 champion artifact files exist in the model path.
- [ ] Layer 4 startup logs show the intended model path and contract version.
- [ ] No hidden code path silently bypasses risk or ML gating.

Exit criteria:
- The live path is a strict pipeline, not a collection of loosely coupled scripts.

## 3. Data And Contract Quality

- [ ] Document every upstream and downstream table used by the trading pipeline.
- [ ] Verify column-level schema compatibility for all tables used by Layers 1 to 6.
- [ ] Enforce granularity alignment across regime, signal, outcome, and execution tables.
- [ ] Validate that `Fact_Trade_Outcomes` and `Fact_Live_Trades` cannot leak future information into training.
- [ ] Add data validation for missing, duplicate, stale, or out-of-order records.
- [ ] Add schema checks for optional columns so live code fails gracefully when columns are absent.
- [ ] Validate all timestamps use the same timezone and are normalized consistently.
- [ ] Define data freshness thresholds for market prices, regime labels, signals, and outcomes.
- [ ] Record lineage fields for every generated dataset and model artifact.
- [ ] Create a rollback plan for bad data loads and corrupted tables.

Specific contract checks:
- [ ] Layer 1 and Layer 2 rows align by asset, strategy, timestamp, and granularity.
- [ ] Layer 3 training rows join only on approved keys.
- [ ] Layer 4 execution never acts on stale or partially written records.
- [ ] Layer 5 dashboard surfaces stale-data warnings.

Exit criteria:
- Every live decision can be traced back to a validated input record set.

## 4. Model Governance

- [ ] Define the champion selection rule in writing.
- [ ] Require a manifest for every promoted model.
- [ ] Store model hash, preprocessing hash, training data snapshot, metrics, and threshold in the manifest.
- [ ] Record who approved the champion, when it was approved, and why it was approved.
- [ ] Store validation metrics for train, validation, and test splits separately.
- [ ] Store calibration metrics and threshold diagnostics separately from headline accuracy.
- [ ] Prove that training-serving features match exactly or define controlled differences.
- [ ] Add a drift review process with explicit retraining triggers.
- [ ] Add a model retirement rule so obsolete models cannot remain live indefinitely.
- [ ] Document how the system behaves when the champion artifact is missing.

Required governance artifacts:
- [ ] Model card
- [ ] Training run report
- [ ] Manifest with hashes
- [ ] Approval record
- [ ] Drift report
- [ ] Retirement or replacement record

Exit criteria:
- A third party can audit which model was live on any date and why it was chosen.

## 5. Risk And Execution Controls

- [ ] Implement a global kill switch.
- [ ] Add a broker-state reconciliation step before each live order.
- [ ] Add a portfolio-level exposure cap that is based on actual notional risk, not only the number of positions.
- [ ] Add per-asset and per-strategy exposure limits.
- [ ] Add an equity curve or drawdown halt rule.
- [ ] Add an order retry policy for transient broker failures.
- [ ] Add idempotency so duplicate orders cannot be sent on restart.
- [ ] Add partial-fill handling.
- [ ] Add slippage validation against recent market conditions.
- [ ] Add price sanity checks before submission.
- [ ] Add emergency cancel logic for open orders if upstream state changes.
- [ ] Add hard rules for trading around market closures, illiquid windows, and news-risk windows.
- [ ] Ensure position sizing is calculated from validated risk inputs, not hardcoded assumptions.
- [ ] Ensure correlation checks reflect crisis correlation risk, not only recent Pearson correlation.
- [ ] Ensure the system can halt automatically when data quality or model confidence degrades.

Suggested acceptance evidence:
- [ ] A deliberate failure in one layer cannot trigger uncontrolled trading.
- [ ] The system can prove it will not trade when a gate fails.
- [ ] Open positions in the database match broker truth after reconciliation.

Exit criteria:
- No live order can bypass risk, exposure, or reconciliation controls.

## 6. Security And Access Control

- [ ] Add authentication for all operator and admin APIs.
- [ ] Add role-based access control for read, trade, model, and admin actions.
- [ ] Remove permissive default CORS behavior where it is not required.
- [ ] Store secrets outside the repository and outside plaintext `.env` for production.
- [ ] Add secret rotation procedures for API keys, DB credentials, and broker credentials.
- [ ] Log every administrative action with user, timestamp, action, and reason.
- [ ] Restrict who can promote models, change thresholds, or toggle live trading.
- [ ] Audit every route that can affect live systems or model governance.
- [ ] Validate that logs do not leak secrets, tokens, or account credentials.
- [ ] Add environment-specific protection so dev defaults cannot reach production.

Exit criteria:
- No unauthorized user can view, change, or execute live-trading actions.

## 7. Testing And Verification

- [ ] Add unit tests for Layer 0 qualification logic.
- [ ] Add unit tests for Layer 1 regime labeling and label stability.
- [ ] Add unit tests for Layer 2 signal generation rules.
- [ ] Add unit tests for Layer 3 training, threshold selection, and manifest generation.
- [ ] Add unit tests for Layer 4 gating, risk checks, and execution decision branches.
- [ ] Add unit tests for Layer 7 broker adapter behavior.
- [ ] Add integration tests for the end-to-end pipeline.
- [ ] Add regression tests for known historical edge cases.
- [ ] Add failure-path tests for missing model files, missing DB columns, API errors, and broker rejections.
- [ ] Add a dry-run test mode that exercises execution flow without sending real orders.
- [ ] Add replay tests to confirm the same input snapshot produces the same output.
- [ ] Add coverage reporting with a target threshold.

Minimum test expectation before sale:
- [ ] Core layer contracts are covered by automated tests.
- [ ] A test failure blocks release.
- [ ] Production-safe paths are verified on every change.

Exit criteria:
- The system can survive a release without depending on manual inspection.

## 8. Observability And Operations

- [ ] Add structured logs for every decision and veto.
- [ ] Add execution metrics: approved trades, vetoed trades, failed orders, slippage, and fill rate.
- [ ] Add model metrics: confidence distribution, calibration, approval rate, and drift indicators.
- [ ] Add data freshness metrics for price, regime, signal, and outcome feeds.
- [ ] Add alerting for broker disconnects, DB outages, empty signal windows, and abnormal veto spikes.
- [ ] Add dashboard indicators that clearly show live vs stale vs failed states.
- [ ] Add runbooks for each major failure mode.
- [ ] Add incident escalation paths and ownership.
- [ ] Add post-incident review templates.
- [ ] Confirm logs are retained long enough for audit and debugging.

Exit criteria:
- An operator can tell within 60 seconds whether the system is healthy, stale, or unsafe.

## 9. Compliance And Commercial Risk

- [ ] Decide whether the product triggers financial regulation, broker oversight, or licensing obligations.
- [ ] Review whether the system is being sold as a decision-support tool or an automated trading system.
- [ ] Review marketing language so it does not overstate profitability or guarantees.
- [ ] Add disclaimers for research, backtest, and forward-performance limitations.
- [ ] Add a legal review of the broker integration and data access terms.
- [ ] Add a privacy review for any personal or account-related data.
- [ ] Add a data retention and deletion policy.
- [ ] Add a customer support escalation policy for trade disputes.
- [ ] Add a model risk management policy.
- [ ] Add a business continuity and disaster recovery plan.

Exit criteria:
- Legal, compliance, and commercial exposure have been reviewed before any external sale.

## 10. Buyer Due Diligence Package

- [ ] Prepare a system architecture diagram.
- [ ] Prepare a data-flow diagram.
- [ ] Prepare a model governance packet.
- [ ] Prepare a security summary.
- [ ] Prepare an operations runbook.
- [ ] Prepare a test coverage summary.
- [ ] Prepare a known limitations document.
- [ ] Prepare a release history and changelog.
- [ ] Prepare a support and escalation policy.
- [ ] Prepare a demo environment separate from any live account.

Exit criteria:
- A buyer can perform due diligence without asking for undocumented tribal knowledge.

## 11. Go / No-Go Gate

- [ ] All critical items are complete.
- [ ] No open issue can directly trigger live trading without human approval.
- [ ] No open issue can corrupt model governance or auditability.
- [ ] No open issue can expose secrets or internal admin access.
- [ ] No open issue can invalidate the training-serving contract.
- [ ] No open issue can hide losses, skipped trades, or broker failures.
- [ ] A final sign-off exists from engineering, risk, and business ownership.

Go criteria:
- [ ] The system is safe enough to demo.
- [ ] The system is safe enough to license.
- [ ] The system is safe enough to trade with real capital under oversight.

No-go criteria:
- [ ] Any critical blocker remains unresolved.
- [ ] The buyer cannot independently audit the live behavior.
- [ ] The system can trade without a complete chain of accountability.

## 12. Suggested Priority Order

1. Kill switch, reconciliation, and execution safety
2. Authentication, RBAC, and secret handling
3. Model governance, drift monitoring, and retraining loop
4. Test suite and release gates
5. Audit trail, observability, and buyer due diligence package

## 13. Evidence Log

Use this section to record proof for each completed item.

- [ ] Evidence link or note for product definition
- [ ] Evidence link or note for architecture integrity
- [ ] Evidence link or note for data contract validation
- [ ] Evidence link or note for model governance
- [ ] Evidence link or note for risk controls
- [ ] Evidence link or note for security and access control
- [ ] Evidence link or note for testing and verification
- [ ] Evidence link or note for observability and operations
- [ ] Evidence link or note for compliance and commercial review
