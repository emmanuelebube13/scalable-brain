# Scalable Brain: Automated Market Regime & Prediction Pipeline

An end-to-end data engineering and predictive analytics system designed to validate algorithmic trading strategies against real-world market constraints.

##  Project Overview
The **Scalable Brain** is a modular pipeline that ingests financial data, classifies market regimes (volatility/trend), and simulates trade execution. Unlike basic ML models, this system accounts for spread, swap fees, and liquidity to provide a realistic assessment of profitability.

## 🛠️ Tech Stack
* **Language:** Python 3.x
* **Database:** SQL Server (running via Docker)
* **Infrastructure:** Fedora Linux / Docker
* **API Integration:** Oanda v20 REST API
* **Analysis:** Pandas, NumPy, Scikit-learn
* **Visualization:** Power BI

##  Key Features
* **Market Regime Detection:** Classifies market conditions to filter out low-probability trade setups.
* **Automated Data Ingestion:** Real-time polling of Oanda API with automated SQL storage.
* **Execution Simulator:** A custom backtesting engine that calculates "True PnL" by factoring in transaction costs.
* **Containerized Environment:** Fully portable setup using Docker Compose for consistent deployment.

##  Prerequisites
- Docker & Docker Compose
- Python 3.10+
- Oanda Demo/Live Account API Key

##  Installation & Setup
1. Clone the repo:
   ```bash
   git clone [https://github.com/your-username/scalable-brain-pipeline.git](https://github.com/your-username/scalable-brain-pipeline.git)
   git clone [https://github.com/your-username/scalable-brain-pipeline.git](https://github.com/your-username/scalable-brain-pipeline.git)


   gantt
    title Scalable Brain Development Timeline
    dateFormat  YYYY-MM-DD
    axisFormat  %b %d

    section Phase 1: Planning
    Project Charter       :done,    p1, 2026-01-15, 2026-01-25
    Strategy Research     :done,    p2, 2026-01-20, 2026-01-30

    section Phase 2: Design
    Database ERD          :done,    d1, 2026-01-25, 2026-01-31
    Data Flow Diagrams    :done,    d2, 2026-01-28, 2026-02-02

    section Phase 3: Infra (Current)
    Docker & SQL Setup    :active,  i1, 2026-02-01, 2026-02-08
    Fedora Environment    :active,  i2, 2026-02-03, 2026-02-10

    section Phase 4: Dev
    Python API Connect    :         dev1, 2026-02-11, 2026-02-18
    Regime Detection Logic:         dev2, 2026-02-15, 2026-02-28

    section Phase 5: Viz
    Power BI Dashboard    :         viz1, 2026-03-01, 2026-03-10
