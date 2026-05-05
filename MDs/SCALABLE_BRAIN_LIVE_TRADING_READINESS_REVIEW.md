# Scalable Brain - Live Swing Trading Readiness Review

> ** SWING TRADING SYSTEM** | Comprehensive readiness assessment for live swing trade deployment

## Comprehensive System Analysis & 1-Month Remediation Plan

**Date:** April 8, 2026  
**System Version:** Current (as of 2026-04-06 fixes)  
**Trading Type:** Swing Trading (multi-hour to multi-day directional moves)  
**Review Scope:** All 8 Layers + Infrastructure for Swing Trade Execution  
**Status:**  NOT READY FOR LIVE TRADING - Multiple Critical Issues Identified

---

## EXECUTIVE SUMMARY

This document provides a deep technical review of the Scalable Brain quantitative trading system and outlines a 4-week remediation plan to prepare it for live trading on a real account.

### Current System State
- **8-Layer Architecture:** Fully implemented
- **Database:** SQL Server with active schema
- **ML Model:** Champion model deployed but confidence scores very low (0.13-0.25)
- **OANDA Integration:** Practice account configured, API functional
- **Last 24h Activity:** 1000 signals processed, 0 approved for execution, 0 trades executed

### Key Finding: Zero Trade Execution
**Critical Issue:** The system is processing signals but approving ZERO trades for execution.

From logs (2026-04-08):
```
Total signals: 1000
ML approved: 0
Executed: 0
Decision counters: skipped_no_regime=563, vetoed_model=437
```

---

## SECTION 1: CRITICAL ISSUES REQUIRING IMMEDIATE ATTENTION

###  CRITICAL #1: ML Gatekeeper Never Approves Trades

**Problem:**
- Model confidence scores range from 0.132 to 0.237
- Threshold is set to 0.400 (previously 0.20, recently increased)
- 437 out of 1000 signals vetoed due to low confidence
- 563 signals skipped due to missing regime data

**Impact:** ZERO trades are being executed. The system is effectively a very expensive data collector.

**Root Cause Analysis:**
1. **Model Underconfidence:** The RandomForest model was trained on limited data with poor feature-target relationships
2. **Threshold Mismatch:** Current threshold (0.40) is too high for the model's output distribution
3. **Feature Engineering Issues:** Training vs inference feature distributions may differ
4. **Training Data Quality:** The supervised learning signal may be weak

**Evidence from Logs:**
```
Decision: vetoed_model | Confidence: 0.237 | Threshold: 0.400
Decision: vetoed_model | Confidence: 0.204 | Threshold: 0.400
Decision: vetoed_model | Confidence: 0.132 | Threshold: 0.400
```

**Recommended Actions:**
1. Lower threshold back to 0.20 in .env (was previously working)
2. Retrain model with more diverse training data
3. Implement calibration (Platt scaling/isotonic regression)
4. Add model performance monitoring dashboard

---

###  CRITICAL #2: Missing Regime Data for USD_CAD

**Problem:**
- 563 signals (56.3%) skipped due to "No matching regime in Fact_Market_Regime_V2"
- Affects USD_CAD consistently
- Other assets (USD_JPY, GBP_USD) have regime data

**Impact:** More than half of potential trades are being discarded before ML evaluation.

**Evidence from Logs:**
```
Veto/Skip by asset: USD_CAD[skipped_no_regime=563] | USD_JPY[vetoed_model=215] | GBP_USD[vetoed_model=222]
```

**Possible Causes:**
1. Layer 1 regime pipeline not running for all assets
2. Asset ID mismatch between Dim_Asset and regime table
3. Granularity mismatch (H1 vs H4)
4. Regime data ingestion cron job failing silently

---

###  CRITICAL #3: Threshold Configuration Inconsistency

**Problem:**
- `.env` file shows `LAYER3_APPROVAL_THRESHOLD=0.20`
- Logs show threshold being applied as 0.400
- Layer 5 client may be overriding threshold

**Impact:** Confusion about actual operational threshold, risk of unexpected behavior.

**Files to Check:**
- `.env` - Should be 0.20
- `src/layer5/services/layer3_client.py` - May have hardcoded default
- `src/layer4_executor/live_pipeline.py` - Reads from manifest first

---

###  CRITICAL #4: Model Retraining Frequency & Data Pipeline

**Problem:**
- Model appears stale or poorly calibrated
- Confidence scores are very low (<0.25) for all signals
- No evidence of recent successful retraining

**Evidence:**
- All confidence scores clustered in 0.13-0.25 range
- No distribution - suggests model is guessing
- Model may not have learned meaningful patterns

---

###  CRITICAL #5: Risk of Accidental Live Trading

**Problem:**
- Environment variable `OANDA_ENV=practice` is set
- But there's also `OANDA_ACCOUNT_ID` (without _DEMO suffix)
- Layer 7 executor defaults to practice but could be switched

**Impact:** If someone changes OANDA_ENV to "live", real money trades could execute immediately.

---

## SECTION 2: DATA VALIDATION CONCERNS

###  D2.1: Feature Alignment Risk

**Status:** Partially Fixed (April 5, 2026)

**Previous Issue:**
- `align_features_for_inference()` was imported but not defined
- ColumnTransformer expected 52 features, got 45

**Current State:**
- Feature alignment module created
- But validation needed to confirm it's working correctly

**Validation Required:**
```bash
# Test feature alignment
python -c "from src.layer3_ml.feature_alignment import align_features_for_inference; print('OK')"
```

---

###  D2.2: Training Data Verification

**Questions Needing Answers:**
1. How many training samples does the model have?
2. What's the class distribution (winners vs losers)?
3. Are features properly normalized?
4. Is there data leakage between train/test?

**Validation Query:**
```sql
SELECT 
    COUNT(*) as total_samples,
    SUM(CASE WHEN Is_Winner = 1 THEN 1 ELSE 0 END) as winners,
    SUM(CASE WHEN Is_Winner = 0 THEN 1 ELSE 0 END) as losers
FROM Fact_Trade_Outcomes
WHERE Is_Winner IS NOT NULL;
```

---

###  D2.3: Signal Quality Assessment

**Current Layer 2 Output:**
- 1000 signals in recent run
- All from small set of strategies (Strategy 1, 2, 5)
- No diversity in signal sources

**Concerns:**
- Strategy concentration risk
- All strategies may be variants of same approach
- No correlation between strategies

---

###  D2.4: Regime Data Quality

**Issues:**
- USD_CAD missing regime data entirely
- Regime labels inconsistent (Trending_HighVol, Ranging_HighVol)
- No validation that regimes make sense

**Validation Query:**
```sql
SELECT 
    Asset_ID,
    Granularity,
    COUNT(*) as regime_count,
    MIN(Timestamp) as earliest,
    MAX(Timestamp) as latest
FROM Fact_Market_Regime_V2
GROUP BY Asset_ID, Granularity;
```

---

## SECTION 3: POINTS OF REVIEW BY LAYER

### LAYER 0: Strategy Qualification  STABLE

**Status:** Functional

**Observations:**
- Multiple qualification reports exist (2026-04-03 to 2026-04-04)
- Bypass mode available for rapid strategy deployment
- Walk-forward optimization implemented

**Concerns:**
- Some strategies commented out as "extremely slow or zero-trade on H4"
- Bypass mode could promote unqualified strategies

**Files to Review:**
- `src/layer0/qualify_strategies.py` - Parameter grid logic
- `results/qualification_report_*.md` - Performance metrics

---

### LAYER 1: Regime Detection  PARTIAL FAILURE

**Status:** Partial - USD_CAD not being processed

**Strengths:**
- KMeans clustering with silhouette scoring
- Incremental mode for performance
- Proper temp-table + MERGE upsert pattern

**Weaknesses:**
- Not all assets getting regime data
- Silhouette threshold (0.25) may be too strict
- No alerts when regime generation fails

**Evidence from Logs:**
- Multiple regime_ingest_v2 logs from 2026-04-06
- Pattern suggests USD_CAD being skipped

**Action Items:**
1. Run Layer 1 manually for all assets to diagnose
2. Check if USD_CAD has sufficient price history
3. Verify Dim_Asset has USD_CAD with correct Asset_ID

---

### LAYER 2: Signal Generation  FUNCTIONAL

**Status:** Working but output quality uncertain

**Strengths:**
- Fully data-driven, no hardcoded strategies
- MERGE upsert for idempotency
- Batch processing with transaction support

**Weaknesses:**
- High signal volume (1000 in one run) suggests over-trading
- No signal quality scoring visible
- All signals have same directionality patterns

**Evidence:**
```
2026-04-08 11:02:10,361 | Total signals: 1000
```

**Review Needed:**
- Signal distribution by strategy
- Signal quality metrics
- Time-of-day analysis

---

### LAYER 3: ML Gatekeeper  POOR PERFORMANCE

**Status:** Running but not useful

**Strengths:**
- Champion model manifest system
- Feature alignment fixes applied
- Comprehensive feature engineering

**Critical Weaknesses:**
1. **Confidence scores too low** - Never exceeds 0.25
2. **Model not learning** - Flat distribution of predictions
3. **Threshold too high** - 0.40 when model outputs <0.25

**Diagnostic Commands:**
```bash
# Check model manifest
cat models/champion_manifest.json

# Check model feature importance
python -c "import joblib; m = joblib.load('models/champion_model.pkl'); print(m.feature_importances_)"

# Test inference with known good data
python src/layer4_executor/live_pipeline.py --dry-run --granularity H1
```

---

### LAYER 4: Live Execution  FUNCTIONAL

**Status:** Operational but vetoing everything

**Strengths:**
- Complete pipeline with 6 stages
- Proper risk parameter calculation
- Correlation gate implemented
- Email alerts configured

**Operational Issues:**
1. All trades vetoed at ML stage
2. No trades reaching correlation gate
3. Email alerts may fire too frequently

**Code Quality Issues:**
```python
# Line 1159 in live_pipeline.py - DUPLICATE RETURN
def prepare_features_for_inference(...) -> pd.DataFrame:
    ...
    return df  # First return
    
    return df  # Dead code - never reached
```

**SMTP Configuration Present:**
- Email alerts configured in .env
- Could spam inbox with 1000 vetoes per run

---

### LAYER 5: API + Dashboard  MOSTLY FIXED

**Status:** Stable after April 6 fixes

**Recent Fixes (from LAYER5_ISSUES_AND_FIXES.md):**
- Hardcoded veto reason fixed
- Model metadata threshold corrected
- Table name corrected (Dim_Strategy_Registry  Dim_Strategy)
- Root endpoint added for regimes

**Known Limitations:**
- KPI ratios (Sharpe/Sortino/Calmar) always 0.0
- Correlation matrix placeholder
- Asset prices require OANDA feed integration

**Testing Status:**
All endpoints returning 200 OK with ~100ms latency.

---

### LAYER 6: Trade Auditor  FUNCTIONAL

**Status:** Working

**Strengths:**
- M1 chunked analysis using official OANDA API
- Resolves SL/TP hits from price history
- Updates Fact_Live_Trades with Actual_Outcome

**Limitations:**
- Only processes trades >1 hour old
- No partial fill handling
- Slippage not tracked

---

### LAYER 7: Broker Executor  DEMO ONLY

**Status:** Practice account only

**Configuration:**
- OANDA_ENV=practice
- OANDA_ACCOUNT_ID_DEMO configured
- OANDA_ACCOUNT_ID also present (for live)

**Risk:**
- Easy to accidentally switch to live
- No additional confirmation for live trading
- Position sizing assumes $10,000 balance

**Position Sizing Logic:**
```python
ASSUMED_BALANCE = Decimal('10000.00')  # Hardcoded
MAX_RISK_PERCENT = Decimal('0.02')     # 2% hard cap
MAX_RISK_DOLLARS = Decimal('200.00')   # $200 max
```

---

## SECTION 4: SECURITY & OPERATIONAL RISKS

###  S4.1: Credential Exposure

**Finding:** `.env` file contains plaintext credentials

**Exposed:**
- Database password: `DB_PASS=Emm5$manuel`
- OANDA API Key: `OANDA_API_KEY= 5de5a147...`
- SMTP password: `SMTP_PASS=qwgnmwehrdqvwcmy`

**Risk:** If repo is pushed to GitHub, credentials compromised.

**Recommendation:** Add `.env` to `.gitignore` immediately.

---

###  S4.2: No Live Trading Safeguards

**Missing:**
- No confirmation step before live trade
- No maximum daily loss limit
- No circuit breaker for consecutive losses
- No position size validation against actual account balance

---

###  S4.3: Email Alert Spam Risk

**Configuration:**
- SMTP enabled with Gmail
- Email sent on EVERY approved trade
- Could send 100+ emails if threshold lowered

---

## SECTION 5: 1-MONTH REMEDIATION PLAN

### WEEK 1: DATA & MODEL DIAGNOSTICS

**Goal:** Understand why model is underconfident and fix data pipeline

#### Day 1-2: Data Quality Audit
- [ ] Run data validation queries on all fact tables
- [ ] Verify Fact_Market_Regime_V2 has data for ALL assets
- [ ] Check Fact_Trade_Outcomes has labeled data for training
- [ ] Validate signal-to-outcome linkage

#### Day 3-4: Model Diagnostics
- [ ] Load champion model and inspect feature importances
- [ ] Run model on training data to verify it can learn
- [ ] Check prediction distribution on historical signals
- [ ] Verify feature engineering produces consistent output

#### Day 5-7: Fix Layer 1 Data Gap
- [ ] Manually run regime ingestion for USD_CAD
- [ ] Debug why USD_CAD is being skipped
- [ ] Implement alerting for missing regime data
- [ ] Set up cron job monitoring

**Deliverable:** Data quality report + fixed regime pipeline

---

### WEEK 2: MODEL RETRAINING & CALIBRATION

**Goal:** Build a model that can actually approve trades

#### Day 8-10: Training Data Preparation
- [ ] Join signals with outcomes for complete training set
- [ ] Analyze class balance (winners vs losers)
- [ ] Create stratified train/validation/test splits
- [ ] Feature engineering validation

#### Day 11-12: Model Training
- [ ] Train new RandomForest with class balancing
- [ ] Experiment with XGBoost and LightGBM
- [ ] Hyperparameter optimization
- [ ] Cross-validation with time-series split

#### Day 13-14: Model Calibration
- [ ] Apply Platt scaling to calibrate probabilities
- [ ] Validate calibration on holdout set
- [ ] Set threshold based on calibration curve
- [ ] Create champion manifest with new model

**Deliverable:** New calibrated model with >0.5 confidence on good signals

---

### WEEK 3: PAPER TRADING VALIDATION

**Goal:** Verify system works end-to-end without risking money

#### Day 15-17: Dry Run Testing
- [ ] Lower threshold to 0.20
- [ ] Run Layer 4 in dry-run mode for 3 days
- [ ] Collect approval rate statistics
- [ ] Validate risk parameters calculation

#### Day 18-19: Practice Account Trading
- [ ] Enable OANDA practice execution
- [ ] Monitor trade execution quality
- [ ] Track slippage vs expected prices
- [ ] Verify position sizing is reasonable

#### Day 20-21: Performance Analysis
- [ ] Calculate win rate on practice trades
- [ ] Compare actual vs expected R:R ratios
- [ ] Review Layer 6 auditor accuracy
- [ ] Adjust thresholds based on results

**Deliverable:** 3-day practice trading report with metrics

---

### WEEK 4: LIVE TRADING PREPARATION

**Goal:** Prepare for live trading with safeguards

#### Day 22-23: Risk Management Implementation
- [ ] Add daily loss limit (e.g., $500 max)
- [ ] Implement consecutive loss circuit breaker
- [ ] Add confirmation for live environment
- [ ] Create position size limits per asset

#### Day 24-25: Monitoring & Alerting
- [ ] Set up trade execution dashboard
- [ ] Configure alerts for system errors
- [ ] Create daily P&L summary email
- [ ] Implement heartbeat monitoring

#### Day 26-27: Documentation & Procedures
- [ ] Write runbook for daily operations
- [ ] Document emergency shutdown procedure
- [ ] Create trading hours schedule
- [ ] Set up backup/restore procedures

#### Day 28: Final Review & Go/No-Go Decision
- [ ] Review all 4 weeks of data
- [ ] Validate model performance
- [ ] Test all safeguards
- [ ] Make go/no-go decision

**Deliverable:** Live trading readiness certificate

---

## SECTION 6: IMMEDIATE ACTION ITEMS (DO TODAY)

### Stop-Gap Measures to Enable Some Trading:

1. **Lower ML Threshold (Temporary)**
   ```bash
   # In .env
   LAYER3_APPROVAL_THRESHOLD=0.15
   ```

2. **Fix USD_CAD Regime Data**
   ```bash
   cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain
   python src/layer1_regime/Fact_market_regime_v2.py --symbol USD_CAD --full-rebuild
   ```

3. **Add .env to .gitignore**
   ```bash
   echo ".env" >> /home/emmanuel/Documents/Scalable_Brain/scalable-brain/.gitignore
   ```

4. **Fix Dead Code in Layer 4**
   ```python
   # In src/layer4_executor/live_pipeline.py around line 1159
   # Remove duplicate "return df"
   ```

5. **Test Email Configuration**
   ```bash
   python -c "from src.layer4_executor.live_pipeline import send_email; send_email('Test alert')"
   ```

---

## SECTION 7: SUCCESS METRICS FOR LIVE TRADING

Before going live, system must achieve:

| Metric | Target | Current |
|--------|--------|---------|
| Signal Approval Rate | 5-15% | 0% |
| Model Confidence (approved) | >0.50 | N/A |
| Daily Trade Count | 2-10 | 0 |
| Regime Data Coverage | 100% | ~45% |
| Practice Account Win Rate | >40% | Unknown |
| Average R:R Ratio | >1.5:1 | Unknown |
| System Uptime | >99% | Unknown |

---

## APPENDIX A: SQL VALIDATION QUERIES

### A.1: Check Training Data Volume
```sql
SELECT 
    'Fact_Signals' as table_name, COUNT(*) as row_count FROM Fact_Signals
UNION ALL
SELECT 'Fact_Trade_Outcomes', COUNT(*) FROM Fact_Trade_Outcomes WHERE Is_Winner IS NOT NULL
UNION ALL
SELECT 'Fact_Market_Regime_V2', COUNT(*) FROM Fact_Market_Regime_V2
UNION ALL
SELECT 'Fact_Live_Trades', COUNT(*) FROM Fact_Live_Trades;
```

### A.2: Check Asset Coverage
```sql
SELECT 
    d.Asset_ID,
    d.Symbol,
    COUNT(f.Timestamp) as signal_count,
    COUNT(r.Timestamp) as regime_count
FROM Dim_Asset d
LEFT JOIN Fact_Signals f ON d.Asset_ID = f.Asset_ID
LEFT JOIN Fact_Market_Regime_V2 r ON d.Asset_ID = r.Asset_ID
WHERE d.Is_Active = 1
GROUP BY d.Asset_ID, d.Symbol
ORDER BY regime_count ASC;
```

### A.3: Check Model Input Data
```sql
SELECT TOP 10
    fs.Timestamp,
    fs.Asset_ID,
    fs.Strategy_ID,
    fs.Signal_Value,
    fto.Is_Winner,
    fmr.Regime_Label,
    fmr.ATR_Value
FROM Fact_Signals fs
INNER JOIN Fact_Trade_Outcomes fto ON fs.Asset_ID = fto.Asset_ID 
    AND fs.Strategy_ID = fto.Strategy_ID 
    AND fs.Timestamp = fto.Timestamp
INNER JOIN Fact_Market_Regime_V2 fmr ON fs.Asset_ID = fmr.Asset_ID 
    AND fs.Granularity = fmr.Granularity
WHERE fto.Is_Winner IS NOT NULL
ORDER BY fs.Timestamp DESC;
```

---

## APPENDIX B: SYSTEM FILES REFERENCE

### Core Pipeline Files
- `src/layer0/qualify_strategies.py` - Strategy qualification
- `src/layer1_regime/Fact_market_regime_v2.py` - Regime detection
- `src/layer2_signals/generate_signals.py` - Signal generation
- `src/layer3_ml/training/train_ml_gatekeeper.py` - ML training
- `src/layer4_executor/live_pipeline.py` - Live execution
- `src/layer5/run.py` - API server
- `src/layer6_auditor/trade_auditor.py` - Trade auditing
- `src/layer7/oanda_executor.py` - Broker execution

### Configuration
- `.env` - Environment variables (NOT IN GIT)
- `shell/cron_layer4_pipeline.sh` - Execution cron
- `shell/cron_layer3_retrain_biweekly.sh` - Retraining cron

### Logs
- `logs/layer4_execution.log` - Execution log
- `logs/regime_ingest_v2_*.log` - Regime pipeline logs

### Models
- `models/champion_model.pkl` - Current ML model
- `models/champion_manifest.json` - Model metadata
- `models/champion_preprocessor.pkl` - Feature preprocessor

---

## CONCLUSION

The Scalable Brain system has a solid architectural foundation but is **NOT READY for live trading** in its current state. The primary blocker is the ML gatekeeper which vetoes 100% of trades due to low confidence scores and missing regime data.

Following the 4-week remediation plan will:
1. Fix data quality issues
2. Retrain and calibrate the ML model
3. Validate end-to-end operation on practice account
4. Implement risk safeguards
5. Prepare monitoring and procedures

**Estimated time to live trading readiness: 3-4 weeks** with dedicated effort.

---

*Document prepared by: System Analysis*  
*Date: April 8, 2026*  
*Classification: Internal - Trading System Review*
