"""
Layer 0: Data Ingestion & Strategy Qualification Engine
========================================================

This module serves dual purposes in the Scalable Brain architecture:

1. Data Ingestion (Legacy)
   ------------------------
   - ingest_oanda_prices.py    : Production ETL for OANDA -> Fact_Market_Prices
   - seed_dim_asset_test.py    : Dim_Asset seeding utilities

2. Strategy Qualification (New)
   -----------------------------
   - strategy_base.py          : Abstract base class for all strategies
   - strategies/               : Individual strategy implementations
   - backtest_engine.py        : Vectorized backtesting engine
   - strategy_analyzer.py      : Performance metrics calculation
   - multi_timeframe.py        : Multi-timeframe confluence support
   - qualify_strategies.py     : Main qualification script
   - data_loader.py            : DB-backed loader (Dim_Asset + Fact_Market_Prices)
   - layer2_config_adapter.py  : Automated Layer 2 promotion (SQL seed generator)

Integration Notes:
- Run `python qualify_strategies.py --use-db` to backtest against live DB data.
- Qualified strategies are promoted via `layer2_strategies.sql` which seeds
  Dim_Strategy, Dim_Strategy_Config, and Dim_Strategy_Asset_Mapping.
- See README_SWING_ENGINE.md for the original Swing Engine documentation.
"""

__version__ = "1.0.0"
__author__ = "Scalable Brain Team"
