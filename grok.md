# ForexBrain Trading System – Complete Architecture & Power BI Dashboard Specification

## Layer 0: Strategy Qualification & Research (Completed)
- Researched and selected two core strategies:
  - Trend_EMA_ADX (EMA10/50 crossover + ADX > 25 confirmation)
  - Range_Bollinger (ADX ≤ 25 + price breaking Bollinger Bands)
- These are positional/swing trading focused (low frequency: 0–1 trade per week or less).

## Layer 1: Regime Detection (Fact_Market_Regime)
- Calculated 14-period ATR and ADX on H1 data.
- Derived Regime_Label: Trending (ADX > 25) or Ranging (ADX ≤ 25).
- Stored in Fact_Market_Regime table.

## Layer 2: Live Strategy Bank (live_pipeline.py)
- Connects to Oanda v20 API (practice/live) every hour via CRON.
- Fetches last 200 H1 candles for EUR_USD, GBP_USD, USD_JPY.
- Generates signals only on the most recently closed candle.
- Asset/Strategy ID mapping aligned with Dim_Asset and Dim_Strategy_Registry.

## Layer 3: AI Gatekeeper (RandomForest model)
- Trained on historical Fact_Live_Trades data.
- Approval threshold locked at **0.535** (CTO directive).
- Outputs confidence score (0–1).

## Layer 4: Trade Execution & Logging (Dynamic SL/TP + Veto Tracking)
- For every signal:
  - Dynamic SL/TP scaled by confidence + regime.
  - R:R = 2 + (prob – 0.535) × 10 (higher confidence = more aggressive).
  - Monte Carlo simulation estimates TP-hit % and SL-hit %.
- All signals (approved + vetoed) logged to **Fact_Live_Trades** with:
  - Timestamp, Asset_ID, Strategy_ID, Signal_Value, Entry_Price, Stop_Loss, Take_Profit, Confidence_Score, Is_Approved.
- Vetoed trades are stored for future forward validation.

## Power BI Dashboard Requirements (Layer 5 – Current Request)
**Goal**: Professional Bloomberg-style dashboard in Power BI Desktop (Fedora user will connect via Windows VM / dual-boot or remote desktop).

### Core Filters (Top of Dashboard)
- Date range picker (Start Date → End Date)
- Asset dropdown (multi-select: EUR_USD, GBP_USD, USD_JPY)
- Strategy dropdown (multi-select: Trend_EMA_ADX, Range_Bollinger)
- Toggle: Positional vs Day Trading view (future V2)

### KPI Cards (Top Row – 3 cards)
- Total Signals Generated
- AI Approval Rate (%)
- Average Confidence Score

### Visuals (Middle Section)
1. **Donut / Pie Chart** – Approved vs Vetoed breakdown (green/red)
2. **Candlestick Chart** (main chart)
   - H1 candles for selected asset
   - Overlay markers for every trade:
     - Green triangle = Entry
     - Red line = Stop Loss
     - Green line = Take Profit
   - Hover tooltip shows Confidence, R:R, TP/SL hit probability
3. **Confidence Over Time** (scatter or line)
   - X = Timestamp, Y = Confidence_Score
   - Dashed red line at 0.535 threshold
4. **Recent AI Decisions Table** (bottom)
   - 50 most recent rows
   - Conditional formatting: Approved = light green row, Vetoed = light red row
   - Columns: Timestamp, Asset, Strategy, Signal, Entry, SL, TP, Confidence, Status

### Forward Validation / Replay Feature (Future-Proof Section)
- “Replay Vetoed Trade” button on table row
- Shows historical candlestick from that timestamp forward
- Visual line tracing price path to see if TP or SL would have hit
- Aggregated metric: “Veto Accuracy” (% of vetoed trades that would have lost)

### Theme & Layout
- Bloomberg-inspired dark theme (black background, green/red accents)
- Fully interactive filters that refresh all visuals instantly
- Export button for CSV (for further analysis)

### Data Source in Power BI
- Connect via ODBC to ForexBrainDB
- Query joins Fact_Live_Trades + Dim_Asset + Dim_Strategy_Registry
- Scheduled refresh every 5 minutes (Power BI Gateway on Windows side)

### Future V2 Additions (Day Trading View)
- Toggle switch to show M15 or M5 signals
- Separate filter for day vs positional
- Higher-frequency candlestick view

This document is now saved as your official context anchor. Any future questions about Power BI or the system must reference this exact structure.