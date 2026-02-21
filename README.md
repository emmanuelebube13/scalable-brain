#  Scalable Brain: Institutional Quantitative Trading Pipeline

An end-to-end, multi-asset quantitative trading architecture designed to evaluate, filter, and execute algorithmic strategies using Machine Learning meta-labeling and dynamic market regime detection.

Unlike traditional retail trading bots that blindly execute a single strategy, **Scalable Brain** operates like a professional quantitative desk. It requires strategies to mathematically prove their **Expectancy** offline, tags the current market "weather" (Regime), and uses an AI Meta-Labeler to approve or veto trades contextually.

---

##  The 6-Layer Architecture

This system is built on a strict, instrument-agnostic pipeline that evaluates every asset independently before aggregating risk at the portfolio level.

* **Layer 0: Strategy Qualification Engine (Offline)**
    * A rigid backtesting sandbox. Strategies are tested with standardized ATR-based risk profiles. Only strategies that prove a positive mathematical Expectancy, solid Sharpe Ratio, and low Max Drawdown are promoted to the live environment.
* **Layer 1: Market Regime Detection**
    * Tags the current market state independently for each symbol (e.g., `EUR_USD` might be *HighVol_Trending* while `USD_JPY` is *LowVol_Sideways*).
* **Layer 2: Live Strategy Bank**
    * Pre-qualified algorithms scan the market and generate raw, theoretical `BUY` or `SELL` signals.
* **Layer 3: The ML Meta-Labeler (AI Filter)**
    * An XGBoost classification model acts as the ultimate gatekeeper. It evaluates the raw signal against the current Market Regime and asks: *"Does this specific strategy historically win in this specific regime?"* It outputs a probability score to approve or kill the trade.
* **Layer 4 & 4.5: Dynamic Risk & Portfolio Correlation**
    * Calculates exact Stop Loss and Take Profit levels using real-time Average True Range (ATR). A 30-day rolling correlation matrix prevents over-exposure to highly correlated assets (e.g., blocking simultaneous longs on EURUSD and GBPUSD).
* **Layer 5: Telemetry & Visualization**
    * A Power BI / Python Streamlit terminal that visualizes active regimes, strategy execution, AI confidence scores, and live expectancy tracking.

---

## 🛠️ Tech Stack

* **Language:** Python 3.10+
* **Data & Math:** Pandas, NumPy, Pandas-TA (Technical Analysis)
* **Machine Learning:** Scikit-learn, XGBoost
* **Database:** SQL Server / PostgreSQL (Containerized)
* **Infrastructure:** Docker, Docker Compose, Linux (Fedora/Ubuntu)
* **Broker Integration:** Oanda v20 REST API
* **Visualization:** Power BI & Python Dashboards

---

##  Installation & Setup

### For Clients & Developers
If you want to run the Scalable Brain pipeline on your own machine or server, follow these steps:

**1. Clone the Repository**
```bash
git clone [https://github.com/emmanuelebube13/scalable-brain.git](https://github.com/emmanuelebube13/scalable-brain.git)
cd scalable-brain
