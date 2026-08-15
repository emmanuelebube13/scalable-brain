Scalable Brain — Architecture Review & System 3 (Account Management) Integration Design


1. EXECUTIVE ASSESSMENT: YOUR SYSTEM IS STRONG

Your 8-layer architecture demonstrates real engineering discipline. The signal-to-execution pipeline (Layers 0–4) is production-stable with 915K+ signals processed and a working XGBoost gatekeeper. The database design (Fact/Dimension star schema) shows institutional thinking. The separation of concerns across layers is logical and defensible.

Honest verdict: You don't need to rebuild anything. You need THREE precise additions and TWO modifications.


2. HONEST REVIEW OF EACH LAYER

Layer 0: Strategy Qualification
• Status: Working. 915K signals processed suggests a healthy strategy library.
• Strength: Positive expectancy + 20-trade minimum + 1.15 profit factor — these are pragmatic, not overly restrictive.
• Gap: No per-regime performance attribution. A strategy might have 1.3 PF overall but 0.8 PF in high-volatility ranging regimes. Your K-Means regime detector (Layer 1) should feed back into Layer 0 vetting.

Layer 1: Market Regimes (K-Means on ATR + ADX)
• Status: Working. Hourly regime classification is a good choice for H1 signals.
• Strength: ATR + ADX are the right features. Separating trend from volatility is the correct mental model.
• Gap: K-Means is a hard clustering algorithm — it assigns each hour to exactly one regime with no uncertainty measure. Regimes in financial markets are probabilistic. A Gaussian Hidden Markov Model (HMM) would give you P(regime) for each state, which your XGBoost gatekeeper (Layer 3) could use as features. This is an upgrade, not a fix — K-Means works, HMM is better.
• Another gap: No regime persistence smoothing. Markets don't flip regimes every hour. A minimum 3–4 bar persistence rule would reduce false regime switches.

Layer 2: Signal Generation
• Status: Working. Generates signals on live H1 candles.
• Strength: Decoupled from execution — correct separation.
• Gap: None significant at this layer.

Layer 3: ML Gatekeeper (XGBoost, >0.75 confidence threshold)
• Status: Working. 35–45% AI approval rate.
• Assessment: The 35–45% approval rate is AGGRESSIVE filtering. This means 55–65% of your strategies' signals are being rejected. This is fine IF the filtered trades are significantly better than the rejected ones. You need to verify this with uplift analysis: compare P&L of approved signals vs. rejected signals out-of-sample.
• Gap: The 0.75 threshold is arbitrary (though reasonable). Consider dynamic thresholding — lower the threshold in high-confidence regimes where your model is historically more accurate, raise it in uncertain regimes.
• Gap: No FinBERT sentiment features yet (acknowledged in your issues). This is fine for now — add it after System 3 is working.

Layer 4: Live Executor
• Status: Working. ATR-based stops/targets + correlation guards.
• Strength: Dynamic ATR stops are correct. Correlation guards show you understand portfolio risk.
• CRITICAL GAP: Layer 4 is doing TWO jobs — (a) position-level execution (stops, targets) AND (b) portfolio-level risk (correlation guards). The account-level risk (drawdown limits, daily loss budgets, consecutive loss halts, demo/live state) is MISSING. This is exactly where System 3 fits.
• Gap: No circuit breaker system. No graduated demo-to-live deployment.

Layer 5: API Telemetry (FastAPI)
• Status: Backend exists, dashboards under construction.
• Gap: This should become the READ interface for System 3. The AMS writes state; Layer 5 reads and serves it.

Layer 6: Auditor
• Status: Planned but not implemented.
• Gap: This is the feedback loop that prevents strategy decay. Without it, a strategy that degrades will keep losing money until you notice manually. This is HIGH priority.

Layer 7: Broker Adapter (OANDA)
• Status: Designed but not actively trading live.
• This is your integration point — once System 3 is in place, Layer 7 should ONLY receive orders that passed through the AMS Decision Gate.


3. HOW YOUR 8 LAYERS MAP TO YOUR 3-SYSTEM VISION

Your three-system vision is clearer than your 8-layer breakdown for deployment. Here's the mapping:

SYSTEM 1: Model Building ("The Brain")
  ├─ Layer 0: Strategy Qualification
  ├─ Layer 1: Market Regime Detection
  ├─ Layer 2: Signal Generation
  ├─ Layer 3: ML Gatekeeper (XGBoost)
  └─ Auxiliary: NLP Intelligence (FinBERT) — pending
  
  Deployment: Runs on Computer 1 (your local training PC)
  Schedule: Continuous research + weekly model retraining

SYSTEM 2: Prediction & Execution ("The Hand")
  ├─ Layer 4: Live Executor (execution logic, stops, targets)
  ├─ Layer 7: Broker Adapter (OANDA REST API)
  └─ Layer 5: API Telemetry (read-only observability)
  
  Deployment: Runs on Computer 2 (your execution PC)
  Schedule: During market hours (Sun 22:00 – Fri 20:00 UTC)

SYSTEM 3: Account Management ("The Guardian") ← NEW
  ├─ Decision Gate (intercept between Layer 3 and Layer 4)
  ├─ Account State Manager (balance, equity, mode, drawdown)
  ├─ Risk Engine (sizing, circuit breakers, daily/weekly limits)
  ├─ Performance Tracker (equity curve, win/loss, strategy attribution)
  ├─ Graduated Deployment Manager (demo → live stages)
  ├─ Time-Based Rule Enforcer (weekends, sessions, drawdown cooling)
  └─ Layer 6: Auditor (post-trade reconciliation) — moved here
  
  Deployment: Runs on Computer 3 (lightweight, always-on)
  Schedule: 24/7 (can be a Raspberry Pi 4, old laptop, or small VPS)


4. WHERE SYSTEM 3 PLUGS INTO YOUR PIPELINE (CRITICAL)

System 3 sits as a DECISION GATE between Layer 3 (ML Gatekeeper) and Layer 4 (Live Executor). It does NOT replace any existing layer. It intercepts, evaluates, modifies, or rejects signals.

CURRENT PIPELINE (what you have now):

  Layer 2 (Signal Gen) 
      → Layer 3 (XGBoost Gatekeeper, score > 0.75) 
          → Layer 4 (Live Executor) 
              → Layer 7 (OANDA Broker)

NEW PIPELINE (with System 3):

  Layer 2 (Signal Gen)
      → Layer 3 (XGBoost Gatekeeper, score > 0.75)
          → [SYSTEM 3: ACCOUNT MANAGEMENT GATE]
              ├─ PASS: Modified signal (sized, validated) → Layer 4 (Live Executor)
              ├─ REDUCE: Signal with smaller position size → Layer 4
              ├─ DELAY: Hold signal, reassess next hour → Back to Layer 2
              └─ REJECT: Log reason, notify user → No execution
          
  Layer 4 (Live Executor) → executes approved orders
      → Layer 7 (OANDA Broker) → fills confirmed
          → [SYSTEM 3: POST-TRADE PROCESSOR]
              ├─ Update account state (balance, equity, P&L)
              ├─ Update consecutive win/loss counter
              ├─ Recalculate drawdown
              ├─ Check circuit breakers
              ├─ Log to Fact_Live_Trades + AMS_Journal
              └─ Update Layer 5 (Telemetry) for dashboard

This preserves your entire existing pipeline. System 3 is middleware.


5. SYSTEM 3: DETAILED COMPONENT DESIGN

5.1 Decision Gate: The 10-Layer Check

Every signal that passes Layer 3 (XGBoost > 0.75) must pass this sequential checklist:

Layer A: Account Mode Check
  • Is account in DEMO or LIVE mode?
  • If DEMO: pass with full logging (dry-run mode)
  • If LIVE: continue to next checks

Layer B: Circuit Breaker State
  • Is the account in ACTIVE, CAUTION, PAUSED, or CIRCUIT_BROKEN state?
  • CIRCUIT_BROKEN → REJECT all signals, notify user
  • PAUSED → REJECT all signals (manual pause)
  • CAUTION → Reduce position size by 50% (approaching drawdown limit)
  • ACTIVE → Full sizing allowed

Layer C: Daily Loss Budget
  • Has daily realized P&L dropped below -2% of starting balance?
  • YES → REJECT all new signals for remainder of UTC day
  • This prevents "revenge trading" by the algorithm

Layer D: Drawdown Proximity
  • Current drawdown from peak equity:
    - < 10% → Full sizing
    - 10–15% → Reduce size by 50%
    - 15–20% → Reduce size by 75%, only highest-confidence signals
    - ≥ 20% → CIRCUIT BREAKER → halt all trading, enter recovery review

Layer E: Consecutive Loss Check
  • Count consecutive closed losses (resets on any win):
    - 0–2 losses → Normal
    - 3 losses → Reduce size by 25%
    - 4 losses → Reduce size by 50%
    - 5 losses → REJECT all signals for 24 hours (cooling period)

Layer F: Strategy Regime Compatibility
  • Look up historical win rate of THIS strategy in THIS regime
  • If win rate < 35% in current regime → REJECT (strategy mismatch)
  • If win rate 35–45% → REDUCE size by 50%
  • If win rate > 45% → Normal sizing
  • If no data for strategy+regime combination → DEMO sizing only (0.1% risk)

Layer G: Position Sizing (Fractional Kelly + Context)
  • Base calculation (Quarter-Kelly):
      K = WinRate - [(1 - WinRate) / WinLossRatio]
      PositionRisk = AccountBalance × min(K × 0.25, MAX_RISK_PER_TRADE)
      MAX_RISK_PER_TRADE = 2.0% (configurable)
  
  • Context multipliers (applied sequentially):
      × Drawdown multiplier (from Layer D)
      × Consecutive loss multiplier (from Layer E)
      × Regime compatibility multiplier (from Layer F)
      × Account stage multiplier (demo=0.5, micro=0.5, small=0.75, full=1.0)
  
  • Final position size = BaseSize × all multipliers
  • Hard floor: never risk less than 0.1% (prevents micro-management)

Layer H: Open Position & Correlation Check
  • Max concurrent trades: 5 (configurable)
  • Max exposure per pair: 6% of equity
  • Max correlated exposure: 10% of equity (your existing Layer 4 correlation guards + this)
  • If adding this trade would breach any limit → REJECT

Layer I: Time-Based Rules
  • Friday after 18:00 UTC → REJECT (weekend gap risk)
  • First 4 hours after Sunday open → REJECT (gap assessment period)
  • Within 2 hours of major news events (from Fact_Macro_Events) → REJECT or REDUCE
  • If account lost ≥ 3 trades today AND it's after 20:00 UTC → REJECT (end-of-day protection)

Layer J: Final Approval
  • Signal passes ALL layers above
  • System 3 writes approved order to AMS_Outbound_Queue
  • Layer 4 polls queue and executes
  • Every decision (approve/reject/reduce + reasons) is logged to AMS_Decision_Log

5.2 Account State Machine

States:
  DEMO        → Paper trading, all logic runs, no real money at risk
  MICRO_LIVE  → Live account, max 1% risk per trade, $1K–$5K capital
  SMALL_LIVE  → Live account, max 1.5% risk per trade, $5K–$10K capital
  FULL_LIVE   → Live account, max 2% risk per trade, $10K+ capital
  
  Sub-states (apply to any above):
  ACTIVE      → Normal operations
  CAUTION     → Reduced sizing (drawdown > 10% or consecutive losses building)
  PAUSED      → Manual halt, no new trades
  CIRCUIT_BROKEN → Automatic halt, all positions closed, requires manual review
  RECOVERY    → Post-circuit, 0.5% max risk, demo validation for 1 week

Auto-transitions:
  • Any account → PAUSED: Manual command from user
  • PAUSED → ACTIVE: Manual command from user
  • ACTIVE → CAUTION: Drawdown > 10% OR 3 consecutive losses
  • CAUTION → ACTIVE: Drawdown recovers to < 8% AND win on next trade
  • Any → CIRCUIT_BROKEN: Drawdown ≥ 20% OR daily loss ≥ 3% OR 5 consecutive losses
  • CIRCUIT_BROKEN → RECOVERY: Manual review completed by user
  • RECOVERY → DEMO: Start 1-week demo validation
  • RECOVERY → previous stage: After 1 profitable week on demo

5.3 Database Schema Extensions (for your PostgreSQL)

System 3 needs three new tables in your existing ForexBrainDB:

Table: AMS_Account_State
  account_id          SERIAL PRIMARY KEY
  mode                VARCHAR(20)  -- DEMO, MICRO_LIVE, SMALL_LIVE, FULL_LIVE
  sub_state           VARCHAR(20)  -- ACTIVE, CAUTION, PAUSED, CIRCUIT_BROKEN, RECOVERY
  broker_account_id   VARCHAR(50)  -- OANDA account ID
  base_currency       VARCHAR(3)   -- USD
  starting_balance    DECIMAL(15,2)
  current_balance     DECIMAL(15,2)
  current_equity      DECIMAL(15,2)
  peak_equity         DECIMAL(15,2)
  current_drawdown_pct DECIMAL(5,2)
  daily_pnl           DECIMAL(15,2)
  daily_start_equity  DECIMAL(15,2)
  weekly_pnl          DECIMAL(15,2)
  weekly_start_equity DECIMAL(15,2)
  consecutive_wins    INTEGER
  consecutive_losses  INTEGER
  total_trades_today  INTEGER
  max_risk_per_trade_pct DECIMAL(5,2)
  circuit_break_reason VARCHAR(255) -- NULL if not broken
  last_updated        TIMESTAMP DEFAULT NOW()

Table: AMS_Decision_Log
  decision_id         SERIAL PRIMARY KEY
  timestamp           TIMESTAMP DEFAULT NOW()
  signal_id           INTEGER REFERENCES your_signal_table
  regime_at_decision  VARCHAR(50)
  strategy_name       VARCHAR(100)
  pair                VARCHAR(10)
  direction           VARCHAR(4)
  xgboost_score       DECIMAL(4,3)
  decision            VARCHAR(10)  -- APPROVED, REDUCED, DELAYED, REJECTED
  rejection_reason    VARCHAR(255) -- NULL if approved
  suggested_size      DECIMAL(10,5)  -- lots
  approved_size       DECIMAL(10,5)  -- lots after all gates
  account_balance     DECIMAL(15,2)
  account_drawdown_pct DECIMAL(5,2)
  consecutive_losses  INTEGER
  daily_pnl           DECIMAL(15,2)
  gate_failed         VARCHAR(2)   -- Which gate rejected (A-J)

Table: AMS_Circuit_Breaker_Log
  breaker_id          SERIAL PRIMARY KEY
  triggered_at        TIMESTAMP DEFAULT NOW()
  reset_at            TIMESTAMP  -- NULL until reset
  trigger_type        VARCHAR(50)  -- MAX_DRAWDOWN, DAILY_LIMIT, CONSECUTIVE_LOSS, MANUAL
  trigger_value       DECIMAL(10,2)  -- the actual value that triggered it
  threshold           DECIMAL(10,2)  -- the configured threshold
  action_taken        TEXT  -- description of what was closed/stopped
  reset_by            VARCHAR(50)  -- username or "auto"
  notes               TEXT

5.4 Integration with Your Existing Fact Tables

System 3 reads from:
  • Your existing signal tables (output of Layer 3)
  • Fact_Live_Trades (for open position tracking and P&L)
  • Fact_Macro_Events (for time-based news rules)

System 3 writes to:
  • AMS_Account_State (its own state tracking)
  • AMS_Decision_Log (every gate decision)
  • AMS_Circuit_Breaker_Log (every trigger event)
  • Your existing Fact_Live_Trades (trade execution records, via Layer 4)
  • Layer 5 FastAPI (telemetry push for dashboards)


6. WHAT TO ADD, MODIFY, AND KEEP AS-IS

6.1 ADD (New Components)

Component: System 3 Core Service
  Where: Computer 3 (dedicated lightweight machine)
  What: Python service with async event loop
  Why: Must be always-on, independent from training and execution
  Effort: ~2–3 weeks

Component: Decision Gate Module
  Where: Inside System 3
  What: 10-layer sequential checker (Layers A–J above)
  Why: Prevents account blowup regardless of strategy quality
  Effort: ~1 week

Component: Account State Manager
  Where: Inside System 3
  What: State machine (DEMO → MICRO → SMALL → FULL × ACTIVE/CAUTION/PAUSED/BROKEN/RECOVERY)
  Why: Enforces graduated deployment and circuit breakers
  Effort: ~3–4 days

Component: AMS Database Tables
  Where: Your existing PostgreSQL ForexBrainDB
  What: AMS_Account_State, AMS_Decision_Log, AMS_Circuit_Breaker_Log
  Why: System 3 needs its own tables, doesn't interfere with existing schema
  Effort: ~2 days

Component: Post-Trade Processor
  Where: Inside System 3
  What: Receives fill confirmations from Layer 4, updates all metrics
  Why: Closes the loop — every trade updates the account state
  Effort: ~3–4 days

Component: Notification Service
  Where: Inside System 3
  What: Telegram bot + email for trade entries, circuit breakers, daily summaries
  Why: You need to know what's happening without watching dashboards
  Effort: ~2–3 days

6.2 MODIFY (Existing Components)

Modification: Layer 4 (Live Executor)
  Change: Remove account-level risk logic. Keep ONLY:
    • ATR-based stop/target calculation
    • Order construction and submission to OANDA
    • Fill validation and slippage monitoring
    • Open position management (trailing stops, breakeven)
  
  Move to System 3:
    • Daily/weekly loss limits
    • Drawdown circuit breakers
    • Consecutive loss halts
    • Position sizing (Kelly calculation)
    • Correlation exposure caps (keep basic guard in Layer 4 as backup)
  
  Add:
    • Poll AMS_Outbound_Queue instead of receiving signals directly from Layer 3
    • After execution, push fill confirmation to AMS_Inbound_Queue

Modification: Layer 3 → Layer 4 Interface
  Change: Replace direct coupling with queue-based decoupling
  
  Before: Layer 3 calls Layer 4 directly (or shared memory)
  After: 
    • Layer 3 writes scored signals to Scored_Signal_Queue
    • System 3 reads from Scored_Signal_Queue, runs Decision Gate
    • System 3 writes approved orders to AMS_Outbound_Queue
    • Layer 4 reads from AMS_Outbound_Queue and executes
  
  Why: System 3 must sit between them. This also makes Layer 4 replaceable.

Modification: Layer 5 (FastAPI Telemetry)
  Change: Add new endpoints for System 3 data
  
  New endpoints:
    GET /api/account/state → Current AMS_Account_State
    GET /api/account/equity-curve → Equity curve history
    GET /api/account/decisions → Recent decision log
    GET /api/account/circuit-breakers → Circuit breaker history
    GET /api/account/strategy-performance → Per-strategy, per-regime stats
    GET /api/account/daily-summary → Today's P&L, trades, win rate

Modification: Layer 6 (Auditor) — Integration
  Change: Don't build Auditor as a separate batch job. Embed it in System 3.
  
  System 3 already tracks every trade outcome. Add:
    • Rolling 30-day Sharpe per strategy
    • Rolling 30-day win rate per strategy per regime
    • Strategy decay detection: if live win rate drops > 20% below backtest → flag
    • Automatic strategy suspension (move to quarantine) if decay detected

Keep as Layer 6 name but make it a subsystem of System 3.

6.3 KEEP AS-IS (No Changes Needed)

• Layer 0 (Strategy Qualification): Working well. Add per-regime stats later.
• Layer 1 (Market Regimes): K-Means works. Upgrade to HMM later if needed.
• Layer 2 (Signal Generation): No changes.
• Layer 3 (ML Gatekeeper): XGBoost is working. The 0.75 threshold is fine.
• Layer 7 (Broker Adapter): Build it as-is. It receives orders from Layer 4.
• Feature alignment module (feature_alignment.py): Critical fix, keep it.
• Your PostgreSQL schema (Fact/Dimension tables): Solid foundation.
• Docker/docker-compose setup: Good infrastructure.


7. IMPLEMENTATION ROADMAP

Phase 1: Foundation (Week 1–2)
  [ ] Create AMS_Account_State, AMS_Decision_Log, AMS_Circuit_Breaker_Log tables
  [ ] Build System 3 skeleton (Python async service, config loader, DB connection)
  [ ] Implement Decision Gate Layer A–C (mode, circuit state, daily budget)
  [ ] Add inter-process queue between Layer 3 and System 3 (Redis or PostgreSQL NOTIFY)
  [ ] Add inter-process queue between System 3 and Layer 4
  [ ] Modify Layer 4 to read from AMS_Outbound_Queue
  [ ] Test with DEMO account, single pair, single strategy

Phase 2: Risk Engine (Week 3–4)
  [ ] Implement Decision Gate Layer D–G (drawdown, consecutive loss, regime compatibility, Kelly sizing)
  [ ] Build account state machine with all transitions
  [ ] Implement circuit breaker logic with automatic actions
  [ ] Build post-trade processor (receives fills, updates state, recalculates metrics)
  [ ] Add daily/weekly P&L tracking and reset logic
  [ ] Add notification service (Telegram bot for critical alerts)
  [ ] Test circuit breakers with simulated drawdown scenarios

Phase 3: Advanced Features (Week 5–6)
  [ ] Implement Decision Gate Layer H–J (correlation, time-based rules, final approval)
  [ ] Build strategy decay detection (rolling Sharpe, win rate vs. backtest)
  [ ] Add Layer 5 FastAPI endpoints for account telemetry
  [ ] Build graduated deployment manager (stage tracking, auto-escalation/de-escalation)
  [ ] Add weekend/holiday management (Friday close protocol, Sunday gap assessment)
  [ ] Write comprehensive logging (structured JSON for all decisions)

Phase 4: Integration & Hardening (Week 7–8)
  [ ] End-to-end test: Layer 0 → 1 → 2 → 3 → System 3 → 4 → 7
  [ ] Stress test circuit breakers with historical crash scenarios (March 2020, etc.)
  [ ] Performance test: can System 3 handle signal throughput without adding >100ms latency?
  [ ] Security audit: API key storage, DB credentials, queue authentication
  [ ] Documentation: runbooks for circuit breaker reset, stage transitions, common issues
  [ ] Deploy to always-on Computer 3

Phase 5: Live Deployment (Week 9+)
  [ ] Run full pipeline on DEMO for 2 weeks
  [ ] Verify all metrics are tracking correctly
  [ ] Verify circuit breakers trigger correctly (simulate drawdown on demo)
  [ ] Switch to MICRO_LIVE ($1K–$5K) with 1% max risk
  [ ] Monitor for 4 weeks, review weekly reports
  [ ] If profitable with max DD < 10%: escalate to SMALL_LIVE


8. CRITICAL CONSIDERATIONS

8.1 Latency Impact

System 3 adds one hop between Layer 3 and Layer 4. For H1 trading (hourly signals), this is irrelevant — 10–50ms of decision gate latency is nothing on an hourly timeframe. For lower timeframes (M15, M5), you would need to optimize. Since you're on H1, you're fine.

8.2 What Happens If System 3 Crashes?

• Layer 4 should have a SAFETY MODE: if AMS_Outbound_Queue is stale for >5 minutes, PAUSE execution (don't trade without risk approval).
• Layer 3 should have a MAX_QUEUE_SIZE: if Scored_Signal_Queue grows >100 signals without System 3 consuming, stop generating new signals.
• System 3 should be the simplest, most reliable component — it does math, not ML. Minimize dependencies.

8.3 Backward Compatibility

Your existing Layer 3 output format should not change. System 3 consumes the same signal objects. If you need to disable System 3 for debugging, Layer 4 can have a BYPASS mode that reads directly from Layer 3 (with hardcoded conservative sizing). This is your emergency override.

8.4 The Human Override

You must be able to:
  • PAUSE all trading instantly (manual state change to PAUSED)
  • CLOSE all positions instantly (emergency flat)
  • RESET a circuit breaker (with mandatory notes field)
  • FORCE a stage change (e.g., force DEMO mode even if criteria say LIVE)
  • ADJUST any risk parameter in real-time (daily loss limit, max drawdown, etc.)

All overrides are logged to AMS_Circuit_Breaker_Log with full audit trail.


9. SUMMARY: WHAT YOU'RE BUILDING

Your Scalable Brain system is already a strong institutional-grade pipeline. You're not fixing anything — you're adding the final piece that separates a research tool from a deployable trading business.

System 3 (Account Management) is the guardian that:
  1. Knows your account state (demo/live, balance, drawdown, recent history)
  2. Remembers every loss and win (consecutive counters, regime performance)
  3. Enforces hard limits you cannot override in the heat of the moment (circuit breakers)
  4. Sizes positions based on mathematical edge AND current context (fractional Kelly + multipliers)
  5. Gradually exposes real capital only after proven performance (staged deployment)
  6. Tells you what happened and why (decision logs, notifications, telemetry)

It sits between your ML brain (System 1) and your execution hand (System 2), making sure every signal is appropriate for YOUR account, in THIS regime, on THIS day, given YOUR recent results.

Build it in 8 weeks. Test it for 4. Then go live with confidence.
