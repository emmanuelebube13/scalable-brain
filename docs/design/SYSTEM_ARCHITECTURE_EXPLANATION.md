# Scalable Brain: System Architecture & Regime Paradigms

## How the Current Live System Runs (Post-Trade Filtering)
The live production pipeline operates under a "Strategy First, Gatekeeper Vetoes" architecture. Here is the exact step-by-step process:

1. **Model 001 (Blind Strategies):** The system runs all 51 strategies across the entire historical price data. At this stage, the strategies have *no idea* what the regime is. They execute purely on mechanical price rules (e.g., "buy if price crosses the moving average") and the system records every single trade.
2. **Model 003 (Regime Brain):** Completely separately, the HMM (Hidden Markov Model) scans the exact same historical price data and mathematically labels every single historical bar as Trending, Ranging, or High-Vol.
3. **Model 004 (Attribution Engine):** The system takes the giant list of trades from Step 1, looks at the timestamp of each trade, and tags it with the regime label from Step 2. It groups the trades into buckets (e.g., "Strategy 36 took 100 trades during Ranging markets, and 50 trades during High-Vol markets").
4. **Model 005 (Vetting Engine):** The system calculates the Profit Factor, Sharpe Ratio, Maximum Drawdown, etc., for each strategy *inside each bucket separately*. This is how it discovers a strategy might be highly profitable in Ranging, but lose money in Trending.
5. **Model 006 (Gatekeeper AI):** In real-time live trading, when a strategy says "I want to buy!", the Gatekeeper looks at the current regime. If the regime is Ranging, and the vetting engine proved the strategy is profitable in Ranging, it approves the trade and sends it to the broker. If the current regime is High-Vol, it vetoes the trade and protects your capital.

## The "Regime First" Paradigm (The `regime_aware` Experiment)
You correctly identified a second, completely different way to build the system: what if the strategy looks at the regime *first*, before it even decides to trade? 

This is exactly what the `src/regime_aware/` experiment folder in the codebase is doing. 

In the "Regime First" (or pre-trade) architecture:
1. The strategy is no longer blind. It consumes the HMM Regime labels in real-time as a direct input, exactly like it consumes Price or Volume.
2. The strategy's internal logic changes based on the regime. For example, it might use a 20-period moving average when the regime says "Trending", but automatically switch to a 50-period moving average when the regime says "High-Vol". Or it might completely pause its own execution if it detects "Ranging".
3. Because the strategy itself is intelligent and context-aware, it generates far fewer "bad" trades to begin with, meaning it doesn't need a Gatekeeper to babysit it and veto its trades.

### Why do we have both?
The **Live Pipeline (Post-trade filtering)** is easier to scale. You can throw hundreds of dumb, blind strategies at the wall, and the Gatekeeper will mathematically figure out which ones work in which regimes without you having to code complex logic into every single strategy.

The **Regime First Experiment (`src/regime_aware`)** is much harder to build, because you have to hand-code complex context-switching logic into the strategies themselves. However, it can theoretically achieve much higher returns because the strategies are adapting their internal math to the market in real-time, rather than just being turned on or off by a Gatekeeper.
