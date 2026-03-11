# Scalable Brain: Quantitative Trading Architecture
**Document Version:** 1.0
**Deployment Target:** Microsoft SQL Server, Python, Oanda API, Power BI
**Core Philosophy:** Protect capital aggressively, execute dynamically, continuous feedback loop.

## System Overview
Scalable Brain is an institutional-grade, AI-gated algorithmic trading system. It utilizes mathematical technical strategies filtered by a Machine Learning gatekeeper (Random Forest) to execute trades with dynamic risk management.

## Layer 0: Strategy Qualification
* **Purpose:** Initial backtesting and viability phase.
* **Mechanism:** Python backtesting using historical data (2008-2025) to find edges in the market.

## Layer 1: Regime Detection
* **Purpose:** Understand the current market environment.
* **Indicators:** ADX (14), ATR (14).
* **Logic:** If ADX > 25, Market = `Trending`. If ADX <= 25, Market = `Ranging`.

## Layer 2: Live Strategy Bank
* **Purpose:** Generate pure technical signals.
* **Active Strategies:**
  * `Trend_EMA_ADX`: 10/50 EMA crossover confirmed by ADX.
  * `Range_Bollinger`: Mean-reversion using 20-period, 2-deviation Bollinger Bands.

## Layer 3: The AI Gatekeeper (Random Forest)
* **Purpose:** Act as the Chief Risk Officer to filter out false technical signals.
* **Model:** `.pkl` Random Forest Classifier trained on 15+ years of historical signal outcomes.
* **Threshold:** `0.535`. The AI must have >53.5% confidence of a winning outcome to Approve a trade. Otherwise, `[TRADE VETOED]`.

## Layer 4: Dynamic Risk Management
* **Purpose:** Calculate strict, dynamic pricing based on live volatility.
* **Logic:**
  * Stop Loss (SL) = Entry Price ± (1 * ATR)
  * Take Profit (TP) = Entry Price ∓ (3 * ATR)
  * Risk/Reward Ratio: Strictly 1:3.

## Layer 5: Telemetry & Storage (Long-Term Memory)
* **Purpose:** Record every AI heartbeat, decision, and metric.
* **Database:** Microsoft SQL Server (`ForexBrainDB`).
* **Star Schema:**
  * `Fact_Live_Trades`: Logs Timestamp, Asset, Strategy, Entry, SL, TP, Confidence Score, and Is_Approved boolean.
  * `Dim_Asset`: Maps Asset IDs (e.g., 5 = EUR_USD).
  * `Dim_Strategy_Registry`: Maps Strategy IDs (e.g., 1017 = Trend_EMA_ADX_EUR_USD).

## Layer 6: The Auditor (Forward-Testing Loop) - *In Development*
* **Purpose:** A continuous feedback loop.
* **Mechanism:** A CRON job that looks back at `Fact_Live_Trades` 48 hours later to determine the actual market outcome of Approved and Vetoed trades. 
* **Goal:** Create a dataset of "Live Mistakes" to retrain Model V2 and increase the baseline win rate.

## V2 Expansion Roadmap
* **Timeframe Shift:** Clone the H1 (Positional) architecture to create M5/M15 (Day Trading) pipelines.
* **Dashboarding:** Power BI connection via DirectQuery. Includes modular filters for Asset, Strategy, Date, and Trading Style (Positional vs. Day). Incorporates Plotly-rendered interactive candlestick charts for post-trade visual auditing.