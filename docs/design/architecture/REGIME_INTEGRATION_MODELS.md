# Regime Integration Models

This document outlines two distinct architectural methodologies for integrating market regime detection into algorithmic trading systems.

## 1. Regime-Aware Strategies (Integrated Execution)

**What it is:**
In this model, the market regime state is passed directly into the individual trading strategy as a first-class input variable alongside price, volume, and technical indicators. The strategy itself contains the logic that dictates how to behave under different market conditions.

**How it operates:**
- At each step in the simulation or live execution, the strategy receives the current regime label (e.g., "Trending-Up", "High-Vol").
- The strategy's internal rule set explicitly evaluates the regime before acting. For example, the code may contain conditions such as: "If the regime is 'Ranging', do not execute signals," or "If the regime is 'High-Vol', adjust the stop-loss."
- The output of the strategy is a finalized trading decision that has already accounted for the current market environment. 
- During backtesting, the regime labels must be available simultaneously with the price data for every historical bar, as the strategy's simulation cannot proceed without them.

## 2. The Gatekeeper Model / Meta-Labeling (Decoupled Execution)

**What it is:**
In this model, individual trading strategies operate in a vacuum, entirely unaware of market regimes. A separate, overarching layer—often called the Gatekeeper, Orchestrator, or Allocation Layer—holds the regime logic and acts as an independent filter over the strategies.

**How it operates:**
- Individual strategies generate continuous buy, sell, or hold signals based purely on their specific price or indicator algorithms. They do this across all market conditions without altering their internal rules.
- A separate regime detection model continuously analyzes the broader market to determine the current regime state.
- During backtesting, strategies are simulated independently of regimes, producing a raw, unconditioned log of all potential trades.
- In a subsequent step (Attribution), these raw trades are cross-referenced against historical regime data to map out how each strategy statistically performs in each regime.
- During live execution, the strategies generate their blind signals and pass them to the Gatekeeper. The Gatekeeper checks the current regime, references the attribution map, and decides whether to authorize, scale, or suppress the strategy's signal before it is executed.
