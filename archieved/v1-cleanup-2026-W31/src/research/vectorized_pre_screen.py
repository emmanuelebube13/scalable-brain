import pandas as pd
import numpy as np

def run_vectorized_screening(
    prices_df: pd.DataFrame, 
    signals_dict: dict[str, pd.Series], 
    top_percentile: float = 0.80
) -> pd.DataFrame:
    """
    Rapidly screens an arbitrary number of strategies using vectorized backtesting.
    Scores strategies on a relative composite rank (Win Rate Percentile + Profit Factor Percentile).
    
    :param prices_df: OHLCV DataFrame containing the 'close' prices.
    :param signals_dict: Dictionary mapping strategy_id to a Pandas Series of signals (1, 0, -1).
    :param top_percentile: The threshold for passing a strategy (e.g., 0.80 means top 20%).
    :return: DataFrame of the top-ranking strategies ready for System 1.
    """
    print(f"Executing vectorized screening on {len(signals_dict)} registered strategies...")

    # 1. Calculate forward returns (shifted by -1 so signal at t captures return at t+1)
    returns = prices_df['close'].pct_change().shift(-1)
    
    results = []

    # 2. Vectorized calculation for each strategy
    for strategy_id, signals in signals_dict.items():
        # Align signal series with returns
        aligned_signals, aligned_returns = signals.align(returns, join='inner')
        strategy_returns = aligned_signals * aligned_returns
        
        # Filter for active trades only (where signal != 0)
        active_returns = strategy_returns[aligned_signals != 0].dropna()
        
        if len(active_returns) < 50:
            continue # Skip strategies with negligible sample sizes
            
        # Win Rate calculation
        wins = active_returns[active_returns > 0]
        losses = active_returns[active_returns < 0]
        win_rate = len(wins) / len(active_returns) if len(active_returns) > 0 else 0
        
        # Profit Factor calculation (Gross Profit / Gross Loss)
        gross_profit = wins.sum()
        gross_loss = abs(losses.sum())
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else np.nan
        
        results.append({
            'strategy_id': strategy_id,
            'trade_count': len(active_returns),
            'win_rate': win_rate,
            'profit_factor': profit_factor
        })

    # 3. Build the leaderboard
    leaderboard = pd.DataFrame(results).dropna()
    
    if leaderboard.empty:
        print("No strategies met the minimum trade count criteria.")
        return leaderboard

    # 4. Calculate Relative Percentile Ranking
    # Rank converts the absolute metric into a 0.0 to 1.0 percentile against the current roster
    leaderboard['win_rate_rank'] = leaderboard['win_rate'].rank(pct=True)
    leaderboard['pf_rank'] = leaderboard['profit_factor'].rank(pct=True)
    
    # Composite Score: equal weight to Win Rate and Profit Factor
    leaderboard['composite_score'] = (leaderboard['win_rate_rank'] + leaderboard['pf_rank']) / 2
    
    # 5. Sort and filter the top tier
    leaderboard = leaderboard.sort_values(by='composite_score', ascending=False)
    
    # Determine the cutoff threshold dynamically
    score_threshold = leaderboard['composite_score'].quantile(top_percentile)
    top_strategies = leaderboard[leaderboard['composite_score'] >= score_threshold]
    
    print("\n--- VECTORIZED SCREENING LEADERBOARD ---")
    print(leaderboard[['strategy_id', 'win_rate', 'profit_factor', 'composite_score']].head(10).to_string(index=False))
    print(f"\n{len(top_strategies)} strategies cleared the {top_percentile*100:.0f}th percentile cutoff.")
    
    return top_strategies

# ==========================================
# Example Execution (Mocking the Data Loader)
# ==========================================

# ==========================================
# Real Execution (Database Hookup)
# ==========================================
if __name__ == "__main__":
    import sys
    from sqlalchemy import text
    
    # Import your existing database engine
    try:
        from src.common.db import get_engine
        engine = get_engine()
    except ImportError:
        print("Error: Could not import get_engine from src.common.db.")
        print("Make sure you are running from the project root with the venv activated.")
        sys.exit(1)

    print("Fetching actual price and signal data from ForexBrainDB...")

    # 1. Load actual prices from the database
    # Assuming H1 or D1 granularity is standard in your fact_market_prices table
    prices_query = """
        SELECT timestamp as index, "Close" as close 
        FROM fact_market_prices 
        WHERE asset_id = 1 AND granularity = 'H4'
        ORDER BY timestamp ASC
    """
    try:
        prices = pd.read_sql(prices_query, engine, index_col='index')
        prices.index = pd.to_datetime(prices.index)
    except Exception as e:
        print(f"Failed to load prices: {e}")
        sys.exit(1)

    # 2. Load actual strategy signals from the database
    signals_query = """
        SELECT timestamp as index, strategy_id, signal_value as signal 
        FROM fact_signals 
        WHERE asset_id = 1 AND granularity = 'H4'
        ORDER BY timestamp ASC
    """
    try:
        signals_raw = pd.read_sql(signals_query, engine)
        signals_raw['index'] = pd.to_datetime(signals_raw['index'])
        
        # Pivot so each strategy_id becomes its own column
        signals_df = signals_raw.pivot(index='index', columns='strategy_id', values='signal').fillna(0)
        
        # Convert to dictionary format expected by our screener
        actual_signals = {col: signals_df[col] for col in signals_df.columns}
        
    except Exception as e:
        print(f"Failed to load signals: {e}")
        print("Note: If fact_signals is empty, you may need to run src.layer0.qualify_strategies first.")
        sys.exit(1)

    # 3. Run the screener on the REAL 18+ strategies (Top 20%)
    if not prices.empty and actual_signals:
        survivors = run_vectorized_screening(prices_df=prices, signals_dict=actual_signals, top_percentile=0.80)
    else:
        print("No data available to screen.")