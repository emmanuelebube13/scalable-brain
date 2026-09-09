# D3 — Entry Fill Timing

BacktestEngine._simulate_trades (backtest_engine.py:205-261):
  signal = signals.iloc[i] (line 207)
  entry_price = df['Close'].iloc[i] (line 229) — SAME bar that generated the signal.
FINDING: Entry fills at Close[i] where i is the signal-generating bar. This is 'fill at the signal bar close' — contemporaneous fill. The signal at bar i is evaluated at bar i's close, and filled at that same close ± slippage. This is OPTIMISTIC: in live trading a bar i signal can only be acted on at bar i+1 open. Consequence: every strategy effectively enters one bar early vs real execution. This does NOT explain negative R (it would make R more positive, not more negative). The v2 PositionEngine fixes this (fills at bar t+1 open), but the OOS trades in fact_trade_outcomes come from the v1 BacktestEngine (persist_trade_outcomes.py). The contemporaneous fill is an optimism that makes true R worse than reported.
