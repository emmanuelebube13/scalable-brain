#!/usr/bin/env python3
"""
Monte Carlo Trading Simulation Dashboard
========================================
A live, interactive web dashboard that simulates trading system expectancy
and risk of ruin using Monte Carlo methods.

This dashboard implements the institutional research methodology:
- 1000-trade sequences (representing 1-2 years of intraday trading)
- 1000+ independent simulation paths for probability distribution
- Risk of Ruin defined as 50% maximum peak-to-valley drawdown
- Execution friction modeling
- Multiple position sizing strategies

Framework: Streamlit (simpler deployment and interactivity)

Author: Trading System
"""

import numpy as np
import pandas as pd
import streamlit as st
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# =============================================================================
# CONFIGURATION & CONSTANTS
# =============================================================================

# Simulation Parameters
DEFAULT_STARTING_BALANCE = 10000
DEFAULT_WIN_RATE = 0.45
DEFAULT_RR_RATIO = 2.0
DEFAULT_FRICTION_PIPS = 1.5
DEFAULT_NUM_TRADES = 1000
DEFAULT_NUM_SIMULATIONS = 1000

# Risk of Ruin Definition (as per institutional mandate)
RUIN_DRAWDOWN_THRESHOLD = 0.50  # 50% peak-to-valley drawdown

# Position Sizing Strategies
SIZING_STRATEGIES = {
    "Fixed 1%": {"type": "fixed", "risk_percent": 0.01},
    "Fixed 2%": {"type": "fixed", "risk_percent": 0.02},
    "Full Kelly": {"type": "kelly", "fraction": 1.0},
    "Quarter-Kelly": {"type": "kelly", "fraction": 0.25}
}

# Visualization Parameters
EQUITY_CURVE_SAMPLE_SIZE = 100  # Number of paths to display on equity curve chart
HISTOGRAM_BINS = 50


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class SimulationParameters:
    """Container for simulation parameters."""
    starting_balance: float
    win_rate: float
    gross_rr_ratio: float
    friction_pips: float
    num_trades: int
    num_simulations: int
    sizing_strategy: str


@dataclass
class SimulationResults:
    """Container for simulation results."""
    equity_curves: np.ndarray  # Shape: (num_simulations, num_trades + 1)
    max_drawdowns: np.ndarray  # Shape: (num_simulations,)
    final_equities: np.ndarray  # Shape: (num_simulations,)
    ruin_count: int
    net_rr_ratio: float
    expected_value: float
    profit_factor: float
    median_final_equity: float
    probability_of_ruin: float


# =============================================================================
# MONTE CARLO SIMULATION ENGINE
# =============================================================================

def calculate_net_reward_risk(
    gross_rr_ratio: float,
    friction_pips: float,
    sl_distance_pips: float = 20.0
) -> float:
    """
    Calculate the Net Reward-to-Risk ratio after accounting for execution friction.
    
    Execution friction (slippage + spread) reduces the effective reward and 
    increases the effective risk. This models real-world trading conditions.
    
    Formula:
        Net R = (Gross Reward - Friction) / (Gross Risk + Friction)
    
    For simplicity, we assume:
        - Target distance = SL distance * R ratio
        - Friction is subtracted from target and added to stop
    
    Args:
        gross_rr_ratio: The gross reward-to-risk ratio before friction
        friction_pips: Execution friction in pips
        sl_distance_pips: Stop loss distance in pips (default 20)
    
    Returns:
        float: Net reward-to-risk ratio after friction
    """
    # Calculate gross distances
    gross_reward_pips = sl_distance_pips * gross_rr_ratio
    gross_risk_pips = sl_distance_pips
    
    # Apply friction
    # Friction reduces profit target and increases stop loss distance
    net_reward_pips = gross_reward_pips - friction_pips
    net_risk_pips = gross_risk_pips + friction_pips
    
    # Calculate net R:R ratio
    if net_risk_pips <= 0:
        return 0.0
    
    net_rr = net_reward_pips / net_risk_pips
    
    return max(net_rr, 0.0)  # Ensure non-negative


def calculate_kelly_fraction(win_rate: float, reward_risk_ratio: float) -> float:
    """
    Calculate the optimal Kelly fraction for position sizing.
    
    Kelly Criterion Formula:
        K = W - ((1 - W) / R)
    
    Where:
        K = Optimal Kelly fraction (proportion of capital to risk)
        W = Win rate (probability of winning)
        R = Reward-to-Risk ratio
    
    Args:
        win_rate: Historical win rate as decimal (e.g., 0.45 for 45%)
        reward_risk_ratio: R:R ratio (e.g., 2.0 for 2:1)
    
    Returns:
        float: The optimal Kelly fraction (clamped to reasonable bounds)
    """
    if reward_risk_ratio <= 0:
        return 0.0
    
    kelly = win_rate - ((1 - win_rate) / reward_risk_ratio)
    
    # Clamp Kelly to reasonable bounds
    # Negative Kelly means no edge - return 0
    # Kelly > 0.50 is extremely aggressive - clamp to 0.50
    return max(0.0, min(kelly, 0.50))


def calculate_risk_percent(
    sizing_strategy: str,
    win_rate: float,
    net_rr_ratio: float
) -> float:
    """
    Calculate the risk percentage based on the selected sizing strategy.
    
    Args:
        sizing_strategy: Name of the sizing strategy
        win_rate: Win rate as decimal
        net_rr_ratio: Net reward-to-risk ratio
    
    Returns:
        float: Risk percentage per trade
    """
    strategy = SIZING_STRATEGIES.get(sizing_strategy, SIZING_STRATEGIES["Fixed 1%"])
    
    if strategy["type"] == "fixed":
        return strategy["risk_percent"]
    
    elif strategy["type"] == "kelly":
        kelly = calculate_kelly_fraction(win_rate, net_rr_ratio)
        risk_percent = kelly * strategy["fraction"]
        
        # Apply hard cap of 2% for Kelly strategies
        return min(risk_percent, 0.02)
    
    return 0.01  # Default fallback


def calculate_expected_value(win_rate: float, net_rr_ratio: float) -> float:
    """
    Calculate the Expected Value (EV) per trade.
    
    EV = (Win Rate * Average Win) - (Loss Rate * Average Loss)
    
    When expressed in R multiples:
        EV = (W * R) - (1 - W)
    
    Args:
        win_rate: Probability of winning
        net_rr_ratio: Net reward-to-risk ratio
    
    Returns:
        float: Expected value in R multiples
    """
    ev = (win_rate * net_rr_ratio) - ((1 - win_rate) * 1.0)
    return ev


def calculate_profit_factor(win_rate: float, net_rr_ratio: float) -> float:
    """
    Calculate the Profit Factor.
    
    Profit Factor = Gross Profit / Gross Loss
                  = (Win Rate * Average Win) / (Loss Rate * Average Loss)
    
    Args:
        win_rate: Probability of winning
        net_rr_ratio: Net reward-to-risk ratio
    
    Returns:
        float: Profit factor (1.0 = breakeven)
    """
    loss_rate = 1 - win_rate
    
    if loss_rate == 0:
        return float('inf')
    
    pf = (win_rate * net_rr_ratio) / (loss_rate * 1.0)
    return pf


def run_single_simulation(
    starting_balance: float,
    win_rate: float,
    net_rr_ratio: float,
    risk_percent: float,
    num_trades: int
) -> Tuple[np.ndarray, float]:
    """
    Run a single Monte Carlo simulation path.
    
    This simulates a sequence of trades with random outcomes based on
    the win rate and reward-to-risk ratio.
    
    Args:
        starting_balance: Initial account balance
        win_rate: Probability of winning each trade
        net_rr_ratio: Net reward-to-risk ratio
        risk_percent: Percentage of capital to risk per trade
        num_trades: Number of trades in the sequence
    
    Returns:
        Tuple: (equity_curve array, max_drawdown)
    """
    # Initialize equity curve
    equity_curve = np.zeros(num_trades + 1)
    equity_curve[0] = starting_balance
    
    # Track peak equity for drawdown calculation
    peak_equity = starting_balance
    max_drawdown = 0.0
    
    # Run trade sequence
    for i in range(num_trades):
        current_equity = equity_curve[i]
        
        # Calculate risk amount for this trade
        risk_amount = current_equity * risk_percent
        
        # Determine trade outcome (win or loss)
        is_win = np.random.random() < win_rate
        
        # Calculate P&L
        if is_win:
            # Win: gain = risk_amount * R:R ratio
            pnl = risk_amount * net_rr_ratio
        else:
            # Loss: lose the risked amount
            pnl = -risk_amount
        
        # Update equity
        new_equity = current_equity + pnl
        equity_curve[i + 1] = new_equity
        
        # Update peak and drawdown
        if new_equity > peak_equity:
            peak_equity = new_equity
        
        current_drawdown = (peak_equity - new_equity) / peak_equity
        max_drawdown = max(max_drawdown, current_drawdown)
    
    return equity_curve, max_drawdown


def run_monte_carlo_simulation(
    params: SimulationParameters
) -> SimulationResults:
    """
    Run the complete Monte Carlo simulation with multiple paths.
    
    This is the main simulation engine that:
        1. Calculates net R:R after friction
        2. Determines risk percentage based on sizing strategy
        3. Runs 1000+ independent simulation paths
        4. Calculates aggregate statistics
    
    Args:
        params: SimulationParameters object
    
    Returns:
        SimulationResults: Complete simulation results
    """
    # Calculate net R:R ratio after friction
    net_rr_ratio = calculate_net_reward_risk(
        params.gross_rr_ratio,
        params.friction_pips
    )
    
    # Calculate risk percentage based on sizing strategy
    risk_percent = calculate_risk_percent(
        params.sizing_strategy,
        params.win_rate,
        net_rr_ratio
    )
    
    # Initialize result arrays
    equity_curves = np.zeros((params.num_simulations, params.num_trades + 1))
    max_drawdowns = np.zeros(params.num_simulations)
    
    # Run simulations
    for i in range(params.num_simulations):
        equity_curve, max_dd = run_single_simulation(
            params.starting_balance,
            params.win_rate,
            net_rr_ratio,
            risk_percent,
            params.num_trades
        )
        
        equity_curves[i] = equity_curve
        max_drawdowns[i] = max_dd
    
    # Calculate final equities
    final_equities = equity_curves[:, -1]
    
    # Calculate Risk of Ruin (paths that hit 50% drawdown)
    ruin_count = np.sum(max_drawdowns >= RUIN_DRAWDOWN_THRESHOLD)
    probability_of_ruin = ruin_count / params.num_simulations
    
    # Calculate key metrics
    expected_value = calculate_expected_value(params.win_rate, net_rr_ratio)
    profit_factor = calculate_profit_factor(params.win_rate, net_rr_ratio)
    median_final_equity = np.median(final_equities)
    
    return SimulationResults(
        equity_curves=equity_curves,
        max_drawdowns=max_drawdowns,
        final_equities=final_equities,
        ruin_count=ruin_count,
        net_rr_ratio=net_rr_ratio,
        expected_value=expected_value,
        profit_factor=profit_factor,
        median_final_equity=median_final_equity,
        probability_of_ruin=probability_of_ruin
    )


# =============================================================================
# VISUALIZATION FUNCTIONS
# =============================================================================

def create_equity_curve_chart(
    equity_curves: np.ndarray,
    starting_balance: float,
    sample_size: int = EQUITY_CURVE_SAMPLE_SIZE
) -> go.Figure:
    """
    Create the equity curve visualization showing sample paths.
    
    Args:
        equity_curves: Array of all equity curves
        starting_balance: Initial balance for reference line
        sample_size: Number of paths to display
    
    Returns:
        go.Figure: Plotly figure object
    """
    num_simulations, num_points = equity_curves.shape
    trade_numbers = np.arange(num_points)
    
    # Select random sample of paths to display
    if num_simulations > sample_size:
        sample_indices = np.random.choice(num_simulations, sample_size, replace=False)
    else:
        sample_indices = np.arange(num_simulations)
    
    # Calculate median path
    median_path = np.median(equity_curves, axis=0)
    
    # Create figure
    fig = go.Figure()
    
    # Add sample paths (faint lines)
    for idx in sample_indices:
        fig.add_trace(go.Scatter(
            x=trade_numbers,
            y=equity_curves[idx],
            mode='lines',
            line=dict(color='rgba(100, 100, 100, 0.1)', width=0.5),
            showlegend=False,
            hoverinfo='skip'
        ))
    
    # Add median path (bold)
    fig.add_trace(go.Scatter(
        x=trade_numbers,
        y=median_path,
        mode='lines',
        name='Median Path',
        line=dict(color='#FF6B6B', width=3),
        hovertemplate='Trade: %{x}<br>Equity: $%{y:,.2f}<extra></extra>'
    ))
    
    # Add starting balance reference line
    fig.add_hline(
        y=starting_balance,
        line_dash="dash",
        line_color="green",
        annotation_text="Starting Balance",
        annotation_position="right"
    )
    
    # Update layout
    fig.update_layout(
        title={
            'text': f'Equity Curves (Sample of {len(sample_indices)} Paths)',
            'x': 0.5,
            'xanchor': 'center'
        },
        xaxis_title='Trade Number',
        yaxis_title='Account Equity ($)',
        template='plotly_white',
        hovermode='x unified',
        showlegend=True,
        legend=dict(
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01
        ),
        height=500
    )
    
    # Format y-axis as currency
    fig.update_yaxes(tickprefix='$', tickformat=',.0f')
    
    return fig


def create_drawdown_histogram(max_drawdowns: np.ndarray) -> go.Figure:
    """
    Create the drawdown distribution histogram.
    
    Args:
        max_drawdowns: Array of maximum drawdowns from all simulations
    
    Returns:
        go.Figure: Plotly figure object
    """
    # Convert to percentages
    drawdowns_percent = max_drawdowns * 100
    
    # Create histogram
    fig = go.Figure()
    
    fig.add_trace(go.Histogram(
        x=drawdowns_percent,
        nbinsx=HISTOGRAM_BINS,
        marker_color='rgba(255, 107, 107, 0.7)',
        marker_line_color='rgba(255, 107, 107, 1)',
        marker_line_width=1,
        hovertemplate='Drawdown: %{x:.1f}%<br>Frequency: %{y}<extra></extra>'
    ))
    
    # Add vertical line at 50% (ruin threshold)
    fig.add_vline(
        x=50,
        line_dash="dash",
        line_color="red",
        line_width=2,
        annotation_text="Ruin Threshold (50%)",
        annotation_position="top"
    )
    
    # Update layout
    fig.update_layout(
        title={
            'text': 'Maximum Drawdown Distribution',
            'x': 0.5,
            'xanchor': 'center'
        },
        xaxis_title='Maximum Drawdown (%)',
        yaxis_title='Frequency (Number of Paths)',
        template='plotly_white',
        height=400,
        bargap=0.1
    )
    
    # Format x-axis as percentage
    fig.update_xaxes(ticksuffix='%')
    
    return fig


def create_metrics_panel(results: SimulationResults, params: SimulationParameters) -> None:
    """
    Create the key metrics display panel using Streamlit columns.
    
    Args:
        results: SimulationResults object
        params: SimulationParameters object
    """
    st.markdown("---")
    st.subheader("📊 Key Performance Metrics")
    
    # Create columns for metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="Net R:R Ratio",
            value=f"{results.net_rr_ratio:.2f}",
            delta=f"Gross: {params.gross_rr_ratio:.2f}"
        )
    
    with col2:
        st.metric(
            label="Expected Value",
            value=f"{results.expected_value:.3f}R",
            delta=f"PF: {results.profit_factor:.2f}"
        )
    
    with col3:
        st.metric(
            label="Median Final Equity",
            value=f"${results.median_final_equity:,.0f}",
            delta=f"${results.median_final_equity - params.starting_balance:+,.0f}"
        )
    
    with col4:
        # Color code based on risk level
        ruin_pct = results.probability_of_ruin * 100
        if ruin_pct < 5:
            delta_color = "normal"  # Green (low risk)
        elif ruin_pct < 15:
            delta_color = "off"     # Gray (moderate risk)
        else:
            delta_color = "inverse" # Red (high risk)
        
        st.metric(
            label="Probability of Ruin",
            value=f"{ruin_pct:.1f}%",
            delta=f"{results.ruin_count} paths",
            delta_color=delta_color
        )
    
    st.markdown("---")


def create_statistics_table(results: SimulationResults) -> None:
    """
    Create a detailed statistics table.
    
    Args:
        results: SimulationResults object
    """
    st.subheader("📈 Detailed Statistics")
    
    # Calculate additional statistics
    final_equities = results.final_equities
    
    stats_data = {
        "Metric": [
            "Mean Final Equity",
            "Std Dev Final Equity",
            "Min Final Equity",
            "Max Final Equity",
            "Mean Max Drawdown",
            "Median Max Drawdown",
            "95th Percentile Drawdown",
            "Paths Profitable",
            "Paths with >50% Gain"
        ],
        "Value": [
            f"${np.mean(final_equities):,.2f}",
            f"${np.std(final_equities):,.2f}",
            f"${np.min(final_equities):,.2f}",
            f"${np.max(final_equities):,.2f}",
            f"{np.mean(results.max_drawdowns) * 100:.1f}%",
            f"{np.median(results.max_drawdowns) * 100:.1f}%",
            f"{np.percentile(results.max_drawdowns, 95) * 100:.1f}%",
            f"{np.sum(final_equities > 10000) / len(final_equities) * 100:.1f}%",
            f"{np.sum(final_equities > 15000) / len(final_equities) * 100:.1f}%"
        ]
    }
    
    stats_df = pd.DataFrame(stats_data)
    st.table(stats_df)


# =============================================================================
# STREAMLIT UI
# =============================================================================

def setup_sidebar() -> SimulationParameters:
    """
    Set up the Streamlit sidebar with user input controls.
    
    Returns:
        SimulationParameters: User-configured parameters
    """
    st.sidebar.title("⚙️ Simulation Parameters")
    st.sidebar.markdown("---")
    
    # Starting Balance
    starting_balance = st.sidebar.number_input(
        "Starting Balance ($)",
        min_value=1000,
        max_value=1000000,
        value=DEFAULT_STARTING_BALANCE,
        step=1000,
        help="Initial account balance for the simulation"
    )
    
    st.sidebar.markdown("---")
    
    # Win Rate Slider
    win_rate = st.sidebar.slider(
        "Win Rate (%)",
        min_value=25,
        max_value=75,
        value=int(DEFAULT_WIN_RATE * 100),
        step=1,
        help="Historical win rate percentage"
    ) / 100
    
    # Reward-to-Risk Slider
    gross_rr_ratio = st.sidebar.slider(
        "Gross Reward-to-Risk Ratio",
        min_value=0.5,
        max_value=5.0,
        value=DEFAULT_RR_RATIO,
        step=0.1,
        help="Target profit vs risk ratio before friction"
    )
    
    # Execution Friction
    friction_pips = st.sidebar.number_input(
        "Execution Friction (pips)",
        min_value=0.0,
        max_value=10.0,
        value=DEFAULT_FRICTION_PIPS,
        step=0.1,
        help="Combined slippage and spread impact"
    )
    
    st.sidebar.markdown("---")
    
    # Sizing Strategy
    sizing_strategy = st.sidebar.selectbox(
        "Position Sizing Strategy",
        options=list(SIZING_STRATEGIES.keys()),
        index=3,  # Default to Quarter-Kelly
        help="Risk management approach for position sizing"
    )
    
    st.sidebar.markdown("---")
    
    # Simulation Parameters (advanced)
    with st.sidebar.expander("Advanced Settings"):
        num_trades = st.number_input(
            "Trades per Simulation",
            min_value=100,
            max_value=5000,
            value=DEFAULT_NUM_TRADES,
            step=100,
            help="Number of trades in each simulation path"
        )
        
        num_simulations = st.number_input(
            "Number of Simulations",
            min_value=100,
            max_value=10000,
            value=DEFAULT_NUM_SIMULATIONS,
            step=100,
            help="Number of independent simulation paths"
        )
    
    st.sidebar.markdown("---")
    
    # Information box
    st.sidebar.info(
        f"**Risk of Ruin Definition:**\n\n"
        f"A path is considered 'ruined' if it experiences a "
        f"**{RUIN_DRAWDOWN_THRESHOLD * 100:.0f}%** peak-to-valley drawdown "
        f"at any point during the simulation."
    )
    
    return SimulationParameters(
        starting_balance=starting_balance,
        win_rate=win_rate,
        gross_rr_ratio=gross_rr_ratio,
        friction_pips=friction_pips,
        num_trades=num_trades,
        num_simulations=num_simulations,
        sizing_strategy=sizing_strategy
    )


def main():
    """
    Main application entry point for the Monte Carlo Dashboard.
    """
    # Page configuration
    st.set_page_config(
        page_title="Monte Carlo Trading Simulator",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Header
    st.title("🎲 Monte Carlo Trading Simulation Dashboard")
    st.markdown(
        """
        This dashboard simulates trading system performance using Monte Carlo methods.
        
        **Key Features:**
        - 1000-trade sequences representing 1-2 years of intraday trading
        - 1000+ independent simulation paths for statistical significance
        - Risk of Ruin defined as 50% peak-to-valley drawdown
        - Execution friction modeling for realistic results
        """
    )
    
    # Setup sidebar and get parameters
    params = setup_sidebar()
    
    # Run simulation button
    st.markdown("---")
    run_col1, run_col2, run_col3 = st.columns([1, 2, 1])
    with run_col2:
        run_button = st.button(
            "🚀 Run Monte Carlo Simulation",
            use_container_width=True,
            type="primary"
        )
    
    # Run simulation when button is clicked
    if run_button:
        with st.spinner(f"Running {params.num_simulations:,} simulations... This may take a moment."):
            results = run_monte_carlo_simulation(params)
        
        # Display metrics panel
        create_metrics_panel(results, params)
        
        # Create two columns for charts
        chart_col1, chart_col2 = st.columns(2)
        
        with chart_col1:
            # Equity Curves Chart
            equity_fig = create_equity_curve_chart(
                results.equity_curves,
                params.starting_balance
            )
            st.plotly_chart(equity_fig, use_container_width=True)
        
        with chart_col2:
            # Drawdown Histogram
            drawdown_fig = create_drawdown_histogram(results.max_drawdowns)
            st.plotly_chart(drawdown_fig, use_container_width=True)
        
        # Detailed statistics
        create_statistics_table(results)
        
        # Final equity distribution
        st.subheader("📉 Final Equity Distribution")
        final_equity_fig = go.Figure()
        
        final_equity_fig.add_trace(go.Histogram(
            x=results.final_equities,
            nbinsx=50,
            marker_color='rgba(75, 192, 192, 0.7)',
            marker_line_color='rgba(75, 192, 192, 1)',
            marker_line_width=1,
            hovertemplate='Final Equity: $%{x:,.0f}<br>Frequency: %{y}<extra></extra>'
        ))
        
        final_equity_fig.add_vline(
            x=params.starting_balance,
            line_dash="dash",
            line_color="red",
            annotation_text="Starting Balance",
            annotation_position="top"
        )
        
        final_equity_fig.update_layout(
            title={
                'text': 'Distribution of Final Account Equity',
                'x': 0.5,
                'xanchor': 'center'
            },
            xaxis_title='Final Equity ($)',
            yaxis_title='Frequency',
            template='plotly_white',
            height=400,
            bargap=0.1
        )
        
        final_equity_fig.update_xaxes(tickprefix='$', tickformat=',.0f')
        
        st.plotly_chart(final_equity_fig, use_container_width=True)
        
        # Export option
        st.markdown("---")
        st.subheader("💾 Export Results")
        
        # Create DataFrame for export
        export_df = pd.DataFrame({
            'Simulation': range(1, params.num_simulations + 1),
            'Final_Equity': results.final_equities,
            'Max_Drawdown_Pct': results.max_drawdowns * 100,
            'Ruined': results.max_drawdowns >= RUIN_DRAWDOWN_THRESHOLD
        })
        
        csv = export_df.to_csv(index=False)
        st.download_button(
            label="Download Results as CSV",
            data=csv,
            file_name=f"monte_carlo_results_{params.num_simulations}runs.csv",
            mime="text/csv"
        )
    
    else:
        # Show placeholder when no simulation has run
        st.markdown("---")
        st.info(
            "👆 Click the **'Run Monte Carlo Simulation'** button above to start the analysis.\n\n"
            "Adjust parameters in the sidebar to explore different scenarios."
        )
        
        # Show formula explanations
        with st.expander("📚 Mathematical Formulas Used"):
            st.markdown(
                """
                ### Kelly Criterion
                ```
                K = W - ((1 - W) / R)
                
                Where:
                K = Optimal Kelly fraction
                W = Win rate
                R = Reward-to-Risk ratio
                ```
                
                ### Expected Value (per trade)
                ```
                EV = (W × R) - (1 - W)
                
                Where:
                EV = Expected value in R multiples
                W = Win rate
                R = Reward-to-Risk ratio
                ```
                
                ### Net Reward-to-Risk (after friction)
                ```
                Net R = (Gross Reward - Friction) / (Gross Risk + Friction)
                ```
                
                ### Risk of Ruin
                ```
                Ruin = Maximum drawdown ≥ 50% of peak equity
                ```
                """
            )


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    main()