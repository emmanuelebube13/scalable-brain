# Algorithmic Trading System — Complete Architecture v2.0
## Integrated Account Management, Risk Control & Multi-Computer Execution

---

## 1. SYSTEM OVERVIEW

Your trading system now evolves from two computers to **three logical systems** with five subsystems. The Account Management System (AMS) sits as the central nervous system between your Training Cluster and Execution Engine.

### Logical Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL SERVICES                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────────────┐  │
│  │ OANDA API    │  │ Object Store │  │ Notification Services           │  │
│  │ (Price/Trade)│  │ (S3/MinIO)   │  │ (Email/Telegram/SMS)            │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────────────────────────────┘  │
└─────────┼─────────────────┼──────────────────────────────────────────────────┘
          │                 │
          ▼                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    COMPUTER 1: TRAINING CLUSTER                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  SUBSYSTEM 1: DATA INGESTION ENGINE                                 │    │
│  │  • OANDA API client (500 candles/request)                           │    │
│  │  • Multi-timeframe: D1 (primary) + H4 (entry) + W1 (context)       │    │
│  │  • Historical backfill: 2005-present                                │    │
│  │  • Feature engineering: returns, ATR, volatility, regime features   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  SUBSYSTEM 2: REGIME DETECTION ENGINE                               │    │
│  │  • 4-State Gaussian HMM (Trending-Up, Trending-Down, Ranging, Vol)   │    │
│  │  • Features: returns(1), ATR(14), price_position(20), vol(20)       │    │
│  │  • Retraining: Weekly (Sunday 00:00 UTC)                            │    │
│  │  • Regime persistence smoothing (minimum 3 bars to switch)          │    │
│  └────────────────────────┬────────────────────────────────────────────┘    │
│                           │                                                │
│                           ▼                                                │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  SUBSYSTEM 3: STRATEGY LIBRARY & VETTING ENGINE                     │    │
│  │  • Strategy repository (trend-following, mean-reversion, breakout)   │    │
│  │  • Vetting gate: Profit Factor≥1.5, Sharpe≥0.8, MaxDD≤25%,         │    │
│  │    WinRate≥40%, Recovery≥3.0, OOS≥60 months                        │    │
│  │  • Per-regime performance attribution                                │    │
│  │  • Strategy ranking per regime                                       │    │
│  └─────────────┬───────────────────────────────────────────────────────┘    │
│                │                                                            │
│                ▼ Upload                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  MODEL SERIALIZER: Packages artifacts for Computer 2                │    │
│  │  Output: hmm_model.joblib + strategy_weights.json +                  │    │
│  │          regime_strategy_map.json + model_metadata.json              │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└────────────────────────────────────┬────────────────────────────────────────┘
                                     │
                                     ▼ Upload (timestamped)
┌─────────────────────────────────────────────────────────────────────────────┐
│                        CLOUD OBJECT STORAGE                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐ │
│  │ models/      │  │ configs/     │  │ performance/ │  │ latest.json     │ │
│  │ hmm_*.joblib │  │ risk_*.json  │  │ equity.json  │  │ (pointer file)  │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └─────────────────┘ │
└────────────────────────────────────┬────────────────────────────────────────┘
                                     │
                    ┌────────────────┴────────────────┐
                    │                                 │
                    ▼ Poll 15 min                     ▼ Write-back
┌─────────────────────────────────────┐   ┌───────────────────────────────────┐
│     COMPUTER 2: EXECUTION ENGINE    │   │  COMPUTER 3: ACCOUNT MANAGEMENT   │
│                                     │   │         SYSTEM (AMS)              │
│  ┌─────────────────────────────┐   │   │                                   │
│  │ Model Downloader & Validator│   │   │  ┌─────────────────────────────┐ │
│  │ • Check latest.json hash    │   │   │  │ RISK MANAGEMENT ENGINE      │ │
│  │ • Download if changed       │   │   │  │ • Position Sizing Calculator│ │
│  │ • Validate checksum         │   │   │  │ • Kelly Criterion (1/4)     │ │
│  └──────────┬──────────────────┘   │   │  │ • Drawdown circuit breakers │ │
│             │                      │   │  │ • Daily/Weekly loss limits  │ │
│             ▼                      │   │  │ • Correlation exposure cap  │ │
│  ┌─────────────────────────────┐   │   │  │ • Volatility adjuster       │ │
│  │ Live Regime Detector        │   │   │  └──────────┬──────────────────┘ │
│  │ (HMM predict on live data)  │   │   │             │                    │
│  └──────────┬──────────────────┘   │   │             ▼                    │
│             │                      │   │  ┌─────────────────────────────┐ │
│             ▼                      │   │  │ PERFORMANCE TRACKER         │ │
│  ┌─────────────────────────────┐   │   │  │ • Equity curve monitoring   │ │
│  │ Signal Generator            │   │   │  │ • Win/loss log              │ │
│  │ • Strategy selector per     │◀──┼───┤  │ • Strategy performance heat │ │
│  │   detected regime           │   │   │  │   map per regime            │ │
│  │ • Generates raw signal      │   │   │  │ • Rolling Sharpe/Calmar     │ │
│  └──────────┬──────────────────┘   │   │  │ • Trade duration analytics  │ │
│             │                      │   │  └──────────┬──────────────────┘ │
│             ▼                      │   │             │                    │
│  ┌─────────────────────────────┐   │   │             ▼                    │
│  │ Order Execution Engine      │◀──┼───┤  ┌─────────────────────────────┐ │
│  │ • OANDA REST API            │   │   │  │ ACCOUNT STATE MANAGER       │ │
│  │ • Practice → Live toggle    │   │   │  │ • Account balance tracking  │ │
│  │ • Slippage monitoring       │   │   │  │ • Open position registry    │ │
│  │ • Fill validation           │   │   │  │ • P&L real-time calculator  │ │
│  └──────────┬──────────────────┘   │   │  │ • Margin usage monitor      │ │
│             │                      │   │  │ • Currency pair exposure    │ │
│             │                      │   │  └──────────┬──────────────────┘ │
│             ▼                      │   │             │                    │
│  ┌─────────────────────────────┐   │   │             ▼                    │
│  │ Trade Logger & Reporter     │───┼───▶│  ┌─────────────────────────────┐ │
│  │ • Every trade → JSON log    │   │   │  │ DECISION GATE               │ │
│  │ • Push to object storage    │   │   │  │ • Should we trade today?    │ │
│  │ • Update performance/       │   │   │  │ • Should we trade this pair?│ │
│  │   equity.json               │   │   │  │ • What size?                │ │
│  │ • Notification trigger      │   │   │  │ • Which strategy?           │ │
│  └─────────────────────────────┘   │   │  │ • Max concurrent trades?    │ │
│                                     │   │  │ • Hold or close existing?  │ │
│                                     │   │  └─────────────────────────────┘ │
└─────────────────────────────────────┘   └───────────────────────────────────┘

         │                                          ▲
         │                                          │
         └──────────────────────────────────────────┘
                    Decision Flow: AMS approves/denies/modifies
                    every trade decision from Execution Engine
```

---

## 2. ACCOUNT MANAGEMENT SYSTEM (AMS) — DETAILED DESIGN

### 2.1 Core Philosophy

The AMS operates on **five inviolable principles**:

1. **Preservation over Profit**: The system's primary job is to prevent ruin
2. **Dynamic Sizing**: Position size adapts to account state, not just setup quality
3. **Regime-Aware Risk**: Risk budget expands/contracts based on historical performance per regime
4. **Circuit Breakers**: Hard stops that override the strategy when thresholds are breached
5. **Full Transparency**: Every decision is logged, auditable, and explainable

### 2.2 Account States (State Machine)

```
                    ┌─────────────┐
                    │   DEMO      │
                    │  (Practice) │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
         ┌────────┐  ┌──────────┐  ┌──────────┐
         │ PAUSED │  │ ACTIVE   │  │ CAUTION  │
         │        │  │ (Normal) │  │ (Reduce) │
         └───┬────┘  └────┬─────┘  └────┬─────┘
             │            │             │
             │    ┌───────┴───────┐     │
             │    │               │     │
             │    ▼               ▼     │
             │ ┌─────────────────────────┐
             └▶│      CIRCUIT BROKEN     │
               │     (Trading Halted)    │
               └─────────────────────────┘
                          │
                          ▼ Manual Reset
               ┌─────────────────────────┐
               │    RECOVERY MODE        │
               │  (0.5% risk, review)    │
               └─────────────────────────┘
```

| State | Description | Risk Level | Action |
|-------|------------|------------|--------|
| **DEMO** | Practice account, no real money | Normal | Full system, validate signals |
| **ACTIVE** | Normal trading | Full (1-2% per trade) | Standard operations |
| **CAUTION** | Approaching drawdown limit | Reduced (0.5% per trade) | Halve position sizes, reduce frequency |
| **PAUSED** | Manual pause or scheduled break | Zero | No new trades, manage existing only |
| **CIRCUIT BROKEN** | Hard stop triggered | Zero | All positions closed, trading halted |
| **RECOVERY** | Post-circuit review period | Minimal (0.5% max) | Gradual re-entry with reduced risk |

### 2.3 The Decision Gate (Core Logic)

Every trade goes through the **Decision Gate** — a sequential checklist that MUST all pass:

```python
# Pseudocode for Decision Gate
def decision_gate(signal, account_state, market_state):
    """
    Returns: APPROVED(modified_signal) or REJECTED(reason)
    """
    
    # LAYER 1: Account State Check
    if account_state.status in [PAUSED, CIRCUIT_BROKEN, RECOVERY]:
        return REJECTED(f"Account status: {account_state.status}")
    
    # LAYER 2: Daily Risk Budget Check
    if account_state.daily_pnl <= RISK_CONFIG.daily_loss_limit:
        return REJECTED("Daily loss limit reached")
    
    # LAYER 3: Drawdown Check
    current_drawdown = calculate_drawdown(account_state.equity_curve)
    if current_drawdown >= RISK_CONFIG.max_drawdown_percent:
        return REJECTED(f"Max drawdown breached: {current_drawdown:.2f}%")
    
    # LAYER 4: Consecutive Loss Check
    if account_state.consecutive_losses >= RISK_CONFIG.max_consecutive_losses:
        return REJECTED(f"Max consecutive losses: {account_state.consecutive_losses}")
    
    # LAYER 5: Open Position Check
    if len(account_state.open_positions) >= RISK_CONFIG.max_concurrent_trades:
        return REJECTED("Max concurrent trades reached")
    
    # LAYER 6: Pair-Specific Exposure Check
    pair_exposure = sum(p.size for p in account_state.open_positions if p.pair == signal.pair)
    if pair_exposure >= RISK_CONFIG.max_pair_exposure_percent:
        return REJECTED(f"Max exposure for {signal.pair} reached")
    
    # LAYER 7: Correlated Exposure Check
    correlated_exposure = calculate_correlated_exposure(
        signal.pair, account_state.open_positions
    )
    if correlated_exposure >= RISK_CONFIG.max_correlated_exposure_percent:
        return REJECTED("Correlated exposure limit reached")
    
    # LAYER 8: Volatility Regime Check
    current_vol = get_current_volatility(signal.pair, signal.timeframe)
    if current_vol > RISK_CONFIG.max_volatility_threshold:
        # Reduce position size instead of rejecting
        signal.position_size *= RISK_CONFIG.volatility_reduction_factor
    
    # LAYER 9: Position Sizing (Kelly Criterion)
    kelly_size = kelly_position_size(
        win_rate=STRATEGY_STATS[signal.strategy].win_rate,
        avg_win=STRATEGY_STATS[signal.strategy].avg_win,
        avg_loss=STRATEGY_STATS[signal.strategy].avg_loss,
        account_balance=account_state.balance,
        kelly_fraction=0.25  # Quarter-Kelly
    )
    signal.position_size = min(signal.position_size, kelly_size)
    
    # LAYER 10: Timeframe & Trade Duration Check
    if signal.expected_duration > RISK_CONFIG.max_trade_duration_hours:
        return REJECTED(f"Expected duration {signal.expected_duration}h exceeds max")
    
    # LAYER 11: Weekend/Holiday Check
    if is_near_weekend(signal.entry_time, signal.timeframe):
        return REJECTED("Entry too close to market close (weekend gap risk)")
    
    return APPROVED(signal)
```

---

## 3. RISK MANAGEMENT ENGINE — SUBSYSTEM DETAIL

### 3.1 Position Sizing Algorithm (Fractional Kelly)

```
┌─────────────────────────────────────────────────────────────────┐
│              POSITION SIZING PIPELINE                           │
│                                                                 │
│  INPUT:                                                         │
│  • Account Balance: $10,000 (live) / $100,000 (demo)         │
│  • Strategy Win Rate (W): 0.48 (48%)                           │
│  • Average Win/Loss Ratio (R): 2.1                             │
│  • Kelly Fraction: 0.25 (Quarter-Kelly)                        │
│  • Current Drawdown: 5%                                        │
│  • Current Regime: Low-Volatility Trending                     │
│                                                                 │
│  STEP 1: Full Kelly Calculation                                 │
│  K% = W - [(1 - W) / R]                                       │
│  K% = 0.48 - [(0.52) / 2.1]                                   │
│  K% = 0.48 - 0.248 = 0.232 (23.2%)                            │
│                                                                 │
│  STEP 2: Quarter-Kelly                                          │
│  QK% = 0.232 * 0.25 = 5.8% → CAPPED AT 2% MAX                │
│  Risk Amount = $10,000 * 0.02 = $200 MAX                       │
│                                                                 │
│  STEP 3: Drawdown Adjustment                                    │
│  If drawdown > 10%: reduce by 50%                               │
│  If drawdown > 15%: reduce by 75%                               │
│  If drawdown > 20%: CIRCUIT BREAK                              │
│  Current: 5% drawdown → NO REDUCTION                           │
│                                                                 │
│  STEP 4: Regime Performance Adjustment                          │
│  If strategy win rate in CURRENT regime < 40%:                 │
│    Reduce size by 50%                                           │
│  If strategy has NO historical data in regime:                 │
│    Use DEMO size only (0.1% risk)                               │
│                                                                 │
│  STEP 5: Volatility Adjustment (ATR-Based)                     │
│  ATR(14) on D1 = 45 pips                                      │
│  Stop Loss = 1.5 * ATR = 67.5 pips                            │
│  Position Size = $200 / (67.5 pips * $0.10/pip)               │
│  Position Size = 0.296 standard lots → ROUNDED: 0.30 lots      │
│                                                                 │
│  OUTPUT: 0.30 lots, $200 risk, 67.5 pip stop                   │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Circuit Breaker System (Multi-Layer)

| Level | Trigger | Action | Reset Condition |
|-------|---------|--------|-----------------|
| **Soft Stop** | Daily loss ≥ 2% equity | Reduce size 50%, pause 30 min | Manual resume or next day |
| **Daily Limit** | Daily loss ≥ 3% equity | STOP trading for 24h | Next UTC midnight |
| **Weekly Limit** | Weekly loss ≥ 6% equity | STOP for week, reduce to 0.5% next week | Following Monday |
| **Max Drawdown** | Peak-to-trough ≥ 20% | Close ALL positions, enter RECOVERY | Manual review + 1 week demo |
| **Consecutive Loss** | 5 losses in a row | STOP, require manual review | After 24h cooling period |
| **Margin Call Proximity** | Margin used ≥ 80% | Close largest losing position | Below 60% margin used |
| **Correlation Shock** | Correlated pairs all losing | Close all correlated positions | Next trading session |
| **Volatility Spike** | VIX-equivalent > 2σ | Reduce all positions 50% | Normalized volatility |

### 3.3 Account Metrics Tracked (Real-Time)

#### A. Per-Trade Metrics (logged immediately)
```json
{
  "trade_id": "TXN-20250618-001",
  "timestamp": "2025-06-18T14:30:00Z",
  "pair": "EUR_USD",
  "direction": "LONG",
  "strategy": "trend_following_ma_cross",
  "regime_at_entry": "low_vol_trending",
  "entry_price": 1.0850,
  "stop_loss": 1.0783,
  "take_profit": 1.0985,
  "position_size": 0.30,
  "risk_amount_usd": 200.00,
  "risk_percent": 2.0,
  "expected_risk_reward": 1:2.0,
  "expected_duration_hours": 48,
  "account_balance_at_entry": 10000.00,
  "account_equity_at_entry": 10000.00,
  "margin_used_percent": 5.4,
  "consecutive_loss_count_at_entry": 0,
  "daily_pnl_at_entry": 0,
  "drawdown_at_entry": 5.0
}
```

#### B. Continuous Metrics (updated every tick)

| Metric | Formula | Alert Threshold |
|--------|---------|----------------|
| **Equity** | Balance + Unrealized P&L | — |
| **Margin Level** | (Equity / Used Margin) × 100 | < 150% (warning), < 120% (close) |
| **Open Risk** | Sum of (distance to stop × position size × pip value) for all open trades | > 5% equity |
| **Heat Index** | Total exposure as % of equity | > 15% (reduce), > 25% (halt) |
| **Daily P&L** | Sum of realized + unrealized today | — |
| **Daily Win Rate** | Wins today / Total trades today | < 30% after 5 trades (pause) |
| **Running Sharpe** | Rolling 30-day return / rolling 30-day std | < 0.5 (review strategy) |
| **Calmar Ratio** | Annualized return / Max drawdown | < 1.0 (reduce size) |
| **Expectancy per Trade** | (Win% × Avg Win) - (Loss% × Avg Loss) | < 0 (stop strategy) |

#### C. Periodic Reports (generated automatically)

| Report | Frequency | Contents |
|--------|-----------|----------|
| **Daily Summary** | 21:00 UTC (pre-close) | Trades taken, P&L, win rate, drawdown, open positions |
| **Weekly Report** | Sunday 20:00 UTC | Weekly P&L, regime distribution, strategy performance, equity curve chart |
| **Monthly Deep Dive** | Last day of month | All metrics, strategy attribution, regime analysis, recommended adjustments |
| **Quarterly Review** | End of quarter | Full system audit, strategy retirement/activation, regime model revalidation |

---

## 4. WHAT DATA COMPUTER 3 (AMS) NEEDS

You asked what data the execution computer needs. Here is the complete data specification:

### 4.1 From Object Storage (downloaded by Computer 2)

| File | Source | Update Frequency | Size |
|------|--------|-----------------|------|
| `hmm_regime_model_YYYYMMDD.joblib` | Computer 1 | Weekly | ~2 MB |
| `strategy_weights_YYYYMMDD.json` | Computer 1 | Weekly | ~50 KB |
| `regime_strategy_map_YYYYMMDD.json` | Computer 1 | Weekly | ~20 KB |
| `model_metadata_YYYYMMDD.json` | Computer 1 | Weekly | ~5 KB |
| `latest.json` (pointer) | Computer 1 | Weekly | ~200 B |

### 4.2 From OANDA API (live stream, Computer 2)

| Data | Endpoint | Frequency | Purpose |
|------|----------|-----------|---------|
| **Live candles** | `/v3/instruments/{pair}/candles` | Every H4 close (for D1 signals) | Regime detection, signal generation |
| **Account summary** | `/v3/accounts/{ID}/summary` | Every 60 seconds | Balance, equity, margin, P&L |
| **Open positions** | `/v3/accounts/{ID}/openPositions` | Every 30 seconds | Position tracking, exposure calc |
| **Open trades** | `/v3/accounts/{ID}/openTrades` | Every 30 seconds | Active trade management |
| **Trade history** | `/v3/accounts/{ID}/transactions` | Every 5 minutes | Performance tracking, stats |
| **Pricing stream** | `/v3/accounts/{ID}/pricing/stream` | WebSocket (real-time) | Unrealized P&L, stop monitoring |

### 4.3 From Computer 2 → AMS (internal API, every 30 seconds)

| Data | Purpose |
|------|---------|
| Current signal (pair, direction, strategy, confidence) | AMS evaluates against risk rules |
| Current regime detection (all 4 states + confidence %) | Regime-aware risk adjustment |
| Pending orders list | Prevent duplicate/conflicting orders |
| Order fill confirmations | Update position registry |
| Trade close notifications | Update P&L, statistics, consecutive loss count |

### 4.4 AMS Local State (persisted to SQLite/PostgreSQL)

| Table | Data | Retention |
|-------|------|-----------|
| `equity_curve` | Timestamp, balance, equity, drawdown % | All history |
| `trade_journal` | Every trade with full metadata (see 3.3A) | All history |
| `daily_summary` | Date, P&L, trades count, win rate, max DD | All history |
| `circuit_breaker_log` | Every trigger event, reason, action taken | All history |
| `regime_exposure` | Time in each regime, P&L per regime | Last 365 days |
| `strategy_performance` | Per-strategy: win rate, Sharpe, max DD, expectancy | Last 365 days |
| `risk_state` | Current state machine state, active limits | Current only |

---

## 5. TRADE LIFECYCLE (Complete Flow)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         TRADE LIFECYCLE                                     │
└─────────────────────────────────────────────────────────────────────────────┘

PHASE 1: SIGNAL GENERATION (Computer 2)
─────────────────────────────────────────
1. Model Loader: Download latest model from Object Storage
2. Regime Detector: Process latest D1/H4 candles through HMM
3. Strategy Selector: Look up regime → ranked strategies map
4. Signal Generator: Run top-ranked strategy on current price data
5. Raw Signal: {pair, direction, entry, stop, target, strategy, regime}

PHASE 2: AMS DECISION GATE (Computer 3)
─────────────────────────────────────────
6. Account State Check: ACTIVE? Proceed. CIRCUIT BROKEN? Reject.
7. Risk Budget Check: Daily loss < 3%? Proceed. ≥ 3%? Reject.
8. Drawdown Check: Current DD < 20%? Proceed. ≥ 20%? CIRCUIT BREAK.
9. Consecutive Loss Check: < 5 in a row? Proceed. ≥ 5? Reject.
10. Position Limit Check: Open trades < max? Proceed. Full? Reject.
11. Pair Exposure Check: This pair exposure < 6%? Proceed.
12. Correlation Check: Correlated exposure < 10%? Proceed.
13. Kelly Sizing: Calculate Quarter-Kelly size for this strategy
14. Regime Adjustment: Reduce size if strategy underperforms in current regime
15. Volatility Sizing: ATR-based stop → position size calculation
16. Duration Check: Expected hold < 72 hours? Proceed.
17. Weekend Check: Entry before Friday 18:00 UTC? Proceed.
18. FINAL OUTPUT: Approved signal with final position size, or REJECTED with reason

PHASE 3: ORDER EXECUTION (Computer 2)
───────────────────────────────────────
19. Order Builder: Construct OANDA order JSON
20. Pre-Trade Snapshot: Record account state (balance, equity, margin)
21. Order Submission: POST to /v3/accounts/{ID}/orders
22. Fill Validation: Confirm fill price within slippage tolerance (max 2 pips)
23. Position Registration: Add to AMS open_positions table
24. Stop/Take-Profit Validation: Confirm orders are active on broker

PHASE 4: ACTIVE POSITION MONITORING (Computer 2 + AMS)
────────────────────────────────────────────────────────
25. Price Monitoring: Subscribe to pricing stream for this pair
26. Unrealized P&L: Calculate every tick, update AMS
27. Trailing Stop Management: Adjust stop if profit > 1R (breakeven at 1R)
28. Time-Based Exit: If trade open > expected_duration, reduce target or close
29. Regime Shift Check: If regime changes unfavorably, consider early exit
30. Margin Monitor: Ensure margin level stays > 150%

PHASE 5: TRADE CLOSE (Computer 2 + AMS)
─────────────────────────────────────────
31. Close Trigger: Stop loss, take profit, time exit, or manual close
32. Order Submission: Close position via OANDA API
33. Fill Confirmation: Record actual exit price
34. P&L Calculation: Realized P&L = (exit - entry) × size ± financing
35. Trade Journal: Write complete trade record to database
36. Statistics Update: Update win/loss, consecutive count, daily P&L
37. Equity Curve: Append new equity point
38. Drawdown Recalculation: Check if new peak or trough
39. Circuit Breaker Evaluation: Check if any threshold breached
40. Notification: Send trade result (win/loss, P&L, duration, exit reason)

PHASE 6: POST-TRADE ANALYSIS (AMS, batch)
───────────────────────────────────────────
41. Strategy Attribution: Update per-strategy performance metrics
42. Regime Attribution: Update per-regime P&L statistics
43. Duration Analysis: Track actual vs expected hold times
44. Slippage Analysis: Compare expected vs actual fill prices
45. Consecutive Loss Update: Increment or reset counter
46. Next-Day Forecast: Estimate available risk budget for tomorrow
```

---

## 6. CONFIGURATION FILES

### 6.1 Risk Configuration (`risk_config.json`)

```json
{
  "account": {
    "mode": "demo",
    "demo_balance_usd": 100000,
    "live_balance_usd": 10000,
    "currency": "USD",
    "max_leverage": 30,
    "broker": "oanda"
  },
  "position_sizing": {
    "method": "quarter_kelly",
    "kelly_fraction": 0.25,
    "max_risk_per_trade_percent": 2.0,
    "min_risk_per_trade_percent": 0.1,
    "atr_multiplier_for_stop": 1.5,
    "max_position_size_lots": 1.0
  },
  "circuit_breakers": {
    "daily_loss_limit_percent": 3.0,
    "weekly_loss_limit_percent": 6.0,
    "max_drawdown_percent": 20.0,
    "max_consecutive_losses": 5,
    "soft_stop_loss_percent": 2.0,
    "soft_stop_pause_minutes": 30,
    "margin_warning_percent": 150,
    "margin_close_percent": 120,
    "volatility_spike_std": 2.0,
    "volatility_reduction_factor": 0.5
  },
  "exposure_limits": {
    "max_concurrent_trades": 5,
    "max_trades_per_day": 8,
    "max_trades_per_pair_per_day": 2,
    "max_pair_exposure_percent": 6.0,
    "max_correlated_exposure_percent": 10.0,
    "max_total_heat_percent": 15.0
  },
  "trade_parameters": {
    "timeframe": "D1",
    "entry_timeframe": "H4",
    "context_timeframe": "W1",
    "max_trade_duration_hours": 72,
    "min_trade_duration_hours": 6,
    "friday_close_hour_utc": 18,
    "sunday_open_hour_utc": 22,
    "allow_overnight": true,
    "allow_over_weekend": false,
    "trailing_stop_activation_r": 1.0,
    "breakeven_activation_r": 1.0
  },
  "pairs": {
    "primary": ["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD"],
    "secondary": ["USD_CAD", "EUR_GBP", "EUR_JPY"],
    "correlation_groups": [
      ["EUR_USD", "GBP_USD", "AUD_USD"],
      ["USD_JPY", "EUR_JPY"],
      ["USD_CAD", "AUD_USD"]
    ]
  },
  "notification": {
    "trade_entry": true,
    "trade_exit": true,
    "circuit_breaker": true,
    "daily_summary": true,
    "weekly_report": true,
    "channels": ["telegram", "email"]
  }
}
```

---

## 7. ADDITIONAL SYSTEMS TO ADD/MODIFY

Based on your requirements and best practices, here are the systems you should build, modify, or review:

### 7.1 NEW: Trade Journal & Analytics System

**Why**: You can't improve what you don't measure. Every trade must be recorded with full context for later analysis.

**Components**:
- SQLite database with the tables listed in section 4.4
- Automated trade recording (no manual entry)
- Pre-trade snapshot (account state at entry)
- Post-trade analysis (slippage, duration, regime accuracy)
- Equity curve generator (matplotlib visualization)
- Sharpe ratio calculator (rolling 30-day)
- Drawdown analysis (max, average, recovery time)

**Implementation**: Python + SQLite + pandas. Runs on Computer 3 (AMS).

### 7.2 NEW: Correlation Monitor

**Why**: Forex pairs are correlated. EUR/USD and GBP/USD move together ~85% of the time. Taking both in the same direction doubles your risk.

**What it does**:
- Calculates rolling 30-day correlation matrix (Pearson)
- Groups pairs by correlation (> 0.7 = correlated)
- Enforces max correlated exposure (default: 10% of equity)
- Prevents taking opposing positions in highly correlated pairs (natural hedge reduces profit potential)

**Configuration**:
```json
"correlation_groups": [
  ["EUR_USD", "GBP_USD", "AUD_USD"],
  ["USD_JPY", "EUR_JPY", "GBP_JPY"],
  ["USD_CAD", "AUD_USD"],
  ["EUR_GBP"]
]
```

### 7.3 NEW: Weekend & Holiday Manager

**Why**: Weekend gaps can blow through stops. Major holidays have thin liquidity and wild moves.

**Rules**:
- No new entries after Friday 18:00 UTC (4 hours before close)
- Close all positions by Friday 20:00 UTC (configurable)
- No trading on major holidays (Christmas, New Year's, Good Friday, July 4th)
- First 4 hours after Sunday open (22:00 UTC): reduced size (50%)

### 7.4 NEW: Notification & Alert System

**Notifications you need**:

| Event | Urgency | Channels | Content |
|-------|---------|----------|---------|
| Trade entry | Normal | Telegram + Email | Pair, direction, size, stop, target, strategy |
| Trade exit (win) | Normal | Telegram | P&L, duration, exit reason, running P&L today |
| Trade exit (loss) | Normal | Telegram | P&L, duration, exit reason, consecutive losses |
| Soft stop triggered | High | Telegram + Email | Daily loss %, pause duration, action taken |
| Circuit breaker | CRITICAL | All channels | Full account state, all positions closed, review required |
| Daily summary | Normal | Email | P&L, trades, win rate, open positions, equity chart |
| Weekly report | Normal | Email | Full performance report with charts |
| Model updated | Normal | Telegram | New model deployed, strategy rankings changed |
| Margin warning | High | Telegram + Email | Current margin %, action required |

### 7.5 NEW: Graduated Live Deployment System

**Your demo → live transition plan**:

| Stage | Duration | Account | Risk Level | Criteria to Advance |
|-------|----------|---------|------------|-------------------|
| **Paper Trading** | 4 weeks | Demo ($100K) | 2% per trade | 2+ weeks profitable, no circuit breaks |
| **Micro Live** | 4 weeks | Live ($1K-$5K) | 1% per trade | Profitable month, max DD < 10% |
| **Small Live** | 8 weeks | Live ($5K-$10K) | 1.5% per trade | 2 consecutive profitable months |
| **Full Live** | Ongoing | Live ($10K+) | 2% per trade | 3 consecutive profitable months, max DD < 15% |

**Auto-escalation rules** (in `risk_config.json`):
- After N profitable days, increase size by 25% (up to max)
- After M consecutive losses, decrease size by 50% (down to min)
- Max drawdown < 10% for 30 days → allow increase to next stage

### 7.6 MODIFY: Strategy Vetting — Add Live Performance Gate

**Current**: Strategies are vetted on historical backtests only.
**Required**: Add live/demo performance requirements before a strategy can use full size.

**Live vetting criteria**:
- Minimum 20 live/demo trades before full sizing
- Live win rate within ±10% of backtest win rate
- Live average win/loss within ±15% of backtest
- If live performance diverges > 20% from backtest → PAUSE strategy, investigate

### 7.7 MODIFY: Model Retraining — Add Performance Trigger

**Current**: Weekly retraining on schedule.
**Enhanced**: Also retrain when:
- Rolling 14-day Sharpe drops below 0.3 (strategy degradation)
- Regime detection accuracy < 70% (model drift)
- Any circuit breaker triggers (emergency retrain)

---

## 8. TRADE DURATION & MANAGEMENT RULES

For your swing trading approach (2–3 day holds):

### 8.1 Expected Duration by Strategy Type

| Strategy Type | Min Hold | Target Hold | Max Hold | Timeframe |
|--------------|----------|-------------|----------|-----------|
| Trend Following | 24h | 48-72h | 96h | D1 entry, H4 management |
| Mean Reversion | 6h | 12-24h | 48h | H4 entry, H1 management |
| Breakout | 12h | 24-48h | 72h | D1 entry, H4 management |
| Momentum | 24h | 48h | 72h | D1 entry, H4 management |

### 8.2 Time-Based Exit Rules

```
At 50% of max_duration: Check if trade is profitable
  → If profitable AND price stalling: Move stop to breakeven
  → If losing: Tighten stop to 50% of original distance

At 75% of max_duration:
  → If profitable: Close 50% of position, trail remainder
  → If losing: Close immediately (time stop)

At 100% of max_duration:
  → Close entire position regardless of P&L (hard time stop)
```

### 8.3 Weekend Management

```
Friday 16:00 UTC (T-4h from close):
  → Mark all positions for weekend review

Friday 18:00 UTC (T-2h from close):
  → If position is losing: CLOSE (avoid gap risk on loser)
  → If position is winning (> 1R profit): 
     → Move stop to breakeven, HOLD through weekend
     → OR close 50%, let remainder run with breakeven stop

Friday 20:00 UTC (market close):
  → All remaining positions must have breakeven or better stops
  → Send "Weekend Position Report" with all open trades

Sunday 22:00 UTC (market open):
  → First 4 hours: NO new entries (gap assessment period)
  → If gap opened against position and stop hit: Accept loss, log gap slippage
  → If gap opened in favor: Adjust trailing stops, resume normal operations
```

---

## 9. COMPLETE SYSTEM CHECKLIST

Use this to track your build progress:

### Computer 1: Training Cluster
- [ ] Data Ingestion Engine (OANDA API client)
- [ ] Feature engineering pipeline
- [ ] 4-State Gaussian HMM for regime detection
- [ ] Strategy backtesting framework
- [ ] Strategy vetting engine (all 8 metrics)
- [ ] Regime-strategy matching engine
- [ ] Model serialization & upload to Object Storage
- [ ] Weekly retraining scheduler
- [ ] Performance-triggered retraining

### Computer 2: Execution Engine
- [ ] Model downloader & validator (from Object Storage)
- [ ] Live regime detector
- [ ] Signal generator (strategy selector)
- [ ] OANDA order execution engine
- [ ] Fill validation & slippage monitoring
- [ ] Active position manager (stops, trailing, time exits)
- [ ] Trade logger & reporter
- [ ] Real-time pricing stream handler

### Computer 3: Account Management System (NEW)
- [ ] **Risk Management Engine**
  - [ ] Position sizing calculator (Kelly)
  - [ ] Drawdown circuit breakers (multi-layer)
  - [ ] Daily/weekly loss limit enforcer
  - [ ] Consecutive loss tracker
  - [ ] Correlation exposure monitor
  - [ ] Volatility adjuster
- [ ] **Performance Tracker**
  - [ ] Equity curve monitor
  - [ ] Win/loss journal
  - [ ] Strategy performance heat map
  - [ ] Rolling Sharpe/Calmar calculator
  - [ ] Trade duration analytics
- [ ] **Account State Manager**
  - [ ] Balance/equity tracker
  - [ ] Open position registry
  - [ ] P&L real-time calculator
  - [ ] Margin usage monitor
  - [ ] Currency pair exposure tracker
- [ ] **Decision Gate**
  - [ ] 11-layer approval pipeline
  - [ ] Rejection reason logging
  - [ ] Override audit trail (manual interventions)
- [ ] **Trade Journal Database**
  - [ ] SQLite schema design
  - [ ] Automated trade recording
  - [ ] Query interface for analysis
- [ ] **Notification System**
  - [ ] Telegram bot integration
  - [ ] Email alerts (SMTP)
  - [ ] Templated messages per event type
- [ ] **Graduated Deployment Manager**
  - [ ] Stage tracking (Paper → Micro → Small → Full)
  - [ ] Auto-escalation/de-escalation rules
  - [ ] Stage transition criteria checker
- [ ] **Weekend/Holiday Manager**
  - [ ] Friday close protocol
  - [ ] Sunday open protocol
  - [ ] Holiday calendar
- [ ] **Web Dashboard** (optional, Phase 2)
  - [ ] Real-time equity curve
  - [ ] Open positions table
  - [ ] Strategy performance cards
  - [ ] Risk metrics gauges
  - [ ] Circuit breaker status

### Infrastructure
- [ ] Object Storage setup (MinIO or S3)
- [ ] Inter-computer API (Computer 2 ↔ Computer 3)
- [ ] Secure credential management (no API keys in code)
- [ ] Backup strategy (database, configs, models)
- [ ] Logging infrastructure (structured JSON logs)
- [ ] Monitoring/alerting (system health, not just trading)

---

## 10. SUMMARY: YOUR EVOLVED ARCHITECTURE

### What Changed From Your Original Design

| Aspect | Your Original | Evolved Design | Reason |
|--------|-------------|----------------|--------|
| Computers | 2 (Train + Execute) | 3 (Train + Execute + AMS) | Account management needs dedicated resources |
| Risk control | Implied | Explicit Decision Gate with 11 layers | Prevents emotion-driven and system-driven blowups |
| Position sizing | Not defined | Quarter-Kelly with drawdown adjustment | Math-optimal growth with safety |
| Drawdown protection | Not defined | 4-tier circuit breaker system | Hard stops prevent ruin |
| Trade tracking | Not defined | Full journal + analytics | Required for continuous improvement |
| Demo→Live | Manual transition | Graduated auto-deployment | Proven performance before risking capital |
| Weekend handling | Not defined | Friday close protocol + gap management | Protects against gap risk |
| Notifications | Not defined | Multi-channel per event | You need to know what's happening |
| Correlations | Not defined | Correlation monitor with exposure limits | Prevents hidden concentration risk |

### The Three Computers' Roles

| Computer | Primary Role | Key Software | Always On? |
|----------|-------------|--------------|------------|
| **Computer 1** | Training & Research | Python, hmmlearn, backtrader, PostgreSQL | No (runs on schedule) |
| **Computer 2** | Signal Generation & Execution | Python, oandapyV20, WebSocket client | Yes (during market hours) |
| **Computer 3** | Risk Management & Accounting | Python, SQLite, Telegram Bot, Flask (dashboard) | Yes (always, monitors everything) |

**Note**: Computer 3 can be a lightweight machine (Raspberry Pi 4, old laptop, or small VPS). It doesn't need GPU or heavy compute — just reliability and 24/7 uptime.

### Key Data Flows

1. **Computer 1 → Object Storage**: Model artifacts (weekly)
2. **Object Storage → Computer 2**: Model download (on change, max 15 min delay)
3. **Computer 2 ↔ OANDA**: Price data + order execution (continuous)
4. **Computer 2 ↔ Computer 3**: Signal request ↔ Decision (every signal, ~seconds)
5. **Computer 3 → Computer 2**: Approved/Rejected signal (every signal)
6. **Computer 2 → Computer 3**: Trade fill confirmations (every trade)
7. **Computer 3 → Notifications**: Alerts to you (events as they happen)
8. **All computers → Logs**: Structured JSON logs (continuous)

This architecture gives you a **professional-grade, institutional-style trading system** with proper risk controls, comprehensive tracking, and a clear path from demo to live deployment. The Decision Gate is your safety net — no trade happens without AMS approval, and no blowup happens without multiple circuit breakers engaging first.
