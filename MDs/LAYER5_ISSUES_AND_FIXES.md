# Layer 5 Deep Scan - Issues & Fixes Report

> **SWING TRADING SYSTEM** | Telemetry layer validation for swing trade observability

## Executive Summary

**Scan Date:** 2026-04-06 | **Trading Type:** Swing Trading  
**System Focus:** Real-time observability for multi-hour to multi-day trade tracking  
**Critical Issues:** 5  
**Warnings:** 8  
**Status:**  All Critical Issues Fixed

---

## Critical Issues Found & Fixed

### 1.  Hardcoded Veto Reason (WRONG THRESHOLD)
**File:** `src/layer5/services/layer4_client.py` (line 123)

**Problem:**
```python
"vetoReason": "Confidence below 0.535 threshold" if not is_approved else None,
```
Actual threshold is 0.20, causing confusion in UI.

**Fix:** Dynamic threshold reading from environment
```python
"vetoReason": f"Confidence below {get_threshold():.3f} threshold" if not is_approved else None,
```

---

### 2.  Model Metadata Shows Wrong Threshold
**File:** `src/layer5/services/layer3_client.py` (line 38, 68)

**Problem:**
- Default threshold in metadata is 0.5
- Not reading actual threshold from LAYER3_APPROVAL_THRESHOLD env var

**Fix:** Read from manifest first, then env, then default

---

### 3.  Wrong Table Name in Dash App
**File:** `src/layer5/app.py` (line 44)

**Problem:**
```python
INNER JOIN Dim_Strategy_Registry dsr ON flt.Strategy_ID = dsr.Strategy_ID
```
Table is actually `Dim_Strategy`, not `Dim_Strategy_Registry`.

**Fix:** Changed to `Dim_Strategy`

---

### 4.  Missing Root Endpoint for Regimes
**File:** `src/layer5/api/routes/regimes.py`

**Problem:** Only `/current` and `/performance` exist. Root `/` returns 404.

**Fix:** Added root endpoint that returns both current and performance data

---

### 5.  Strategy Approval Rate Always 0%
**File:** `src/layer5/services/reference_data_client.py` (line 165)

**Problem:** Approval rate calculation uses approved_count from query but query returns NULL for strategies with no trades.

**Fix:** Added COALESCE to handle NULL values

---

## Warnings Found

### W1. Asset Current Price Always 0.0
**Status:** Expected behavior - requires OANDA price feed integration

### W2. Correlation Matrix All Zeros
**Status:** Placeholder - real correlation requires price history computation

### W3. Missing Default Values in Data Contracts
**Status:** Fixed - added sensible defaults

### W4. Live Positions Query May Return Stale Data
**Status:** Fixed - added recent trade filter

### W5. Feature Importance Empty List When Model Not Loaded
**Status:** Expected - graceful degradation

### W6. KPI Sharpe/Sortino/Calmar Ratios Always 0.0
**Status:** Expected - requires historical returns calculation

### W7. Trade Forensics Only for Closed Trades
**Status:** By design

### W8. Strategy Equity Curve Empty
**Status:** Expected - requires P&L tracking per strategy

---

## Data Flow Verification

| Layer | Endpoint | Status | Latency |
|-------|----------|--------|---------|
| Health | `/health` |  200 | <10ms |
| KPI | `/api/v1/kpi/` |  200 | ~50ms |
| Trades | `/api/v1/trades/` |  200 | ~100ms |
| Regimes | `/api/v1/regimes/current` |  200 | ~100ms |
| Regimes | `/api/v1/regimes/performance` |  200 | ~100ms |
| Model | `/api/v1/model/metadata` |  200 | ~10ms |
| Model | `/api/v1/model/performance` |  200 | ~50ms |
| Risk | `/api/v1/risk/` |  200 | ~100ms |
| Strategies | `/api/v1/strategies/` |  200 | ~100ms |
| Assets | `/api/v1/assets/` |  200 | ~100ms |
| Open Positions | `/api/v1/trades/open-positions` |  200 | ~500ms (OANDA) |

---

## OANDA Integration Status

| Feature | Status | Notes |
|---------|--------|-------|
| Credentials |  Configured | Environment variables set |
| Open Positions |  Working | 3 positions fetched |
| Unrealized PnL |  Working | -$1,009.33 |
| Price Feed |  Not used | Could enhance asset prices |

---

## Database Schema Mismatches Fixed

| Issue | Location | Fix |
|-------|----------|-----|
| Dim_Strategy_Registry  Dim_Strategy | app.py | Updated table name |
| Created_At column check | layer4_client.py | Added dynamic column detection |
| Missing COALESCE | reference_data_client.py | Added NULL handling |

---

## Files Modified

1. `src/layer5/services/layer4_client.py` - Fixed veto reason threshold
2. `src/layer5/services/layer3_client.py` - Fixed model metadata threshold
3. `src/layer5/app.py` - Fixed table name
4. `src/layer5/api/routes/regimes.py` - Added root endpoint
5. `src/layer5/services/reference_data_client.py` - Fixed approval rate calculation
6. `src/layer5/services/data_contracts.py` - Added defaults

---

## Testing Commands

```bash
# Start API
cd scalable-brain/src/layer5
python run.py

# Test all endpoints
curl http://localhost:8001/health
curl http://localhost:8001/api/v1/kpi/
curl http://localhost:8001/api/v1/trades/
curl http://localhost:8001/api/v1/regimes/current
curl http://localhost:8001/api/v1/model/metadata
curl http://localhost:8001/api/v1/risk/
```

---

## Performance Metrics

- API Cold Start: ~2 seconds
- Average Endpoint Latency: ~100ms
- Database Query Time: ~50ms
- OANDA API Latency: ~400ms

---

**Report Generated By:** Layer 5 Deep Scan  
**Next Review:** After Layer 3 model retraining
