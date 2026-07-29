#!/usr/bin/env python3
"""
Oanda Trade Executor Module
============================
A standalone execution module that receives approved trade signals and executes
live market orders on Oanda's Practice API using the oandapyV20 library.

This module implements:
- Fractional Kelly position sizing (Quarter-Kelly with 2% hard cap)
- Oanda API integration via oandapyV20
- Robust error handling for API failures
- Detailed trade logging

Author: Trading System
"""

import os
import sys
import logging
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

# Third-party imports
from dotenv import load_dotenv
from oandapyV20 import API
from oandapyV20.exceptions import V20Error
from oandapyV20.endpoints.orders import OrderCreate
from oandapyV20.contrib.requests import (
    MarketOrderRequest,
    StopLossDetails,
    TakeProfitDetails
)

# =============================================================================
# CONFIGURATION & SETUP
# =============================================================================

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Oanda API Configuration
OANDA_API_KEY = os.getenv('OANDA_API_KEY')
OANDA_ACCOUNT_ID = os.getenv('OANDA_ACCOUNT_ID_DEMO')
OANDA_ENV = os.getenv('OANDA_ENV', 'practice')

# Trading Parameters
ASSUMED_BALANCE = Decimal('10000.00')  # Hardcoded $10,000 for prop-firm simulation
FIXED_WIN_RATE = Decimal('0.45')        # Fixed 45% historical win rate
FRACTIONAL_KELLY = Decimal('0.25')      # Quarter-Kelly multiplier
MAX_RISK_PERCENT = Decimal('0.02')      # 2% hard cap on risk per trade
MAX_RISK_DOLLARS = ASSUMED_BALANCE * MAX_RISK_PERCENT  # $200 max risk

# Validate configuration on module load
if not OANDA_API_KEY:
    logger.warning("OANDA_API_KEY not found in environment variables")
if not OANDA_ACCOUNT_ID:
    logger.warning("OANDA_ACCOUNT_ID_DEMO not found in environment variables")


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class TradeParameters:
    """Container for trade parameter validation and storage."""
    instrument: str
    entry_price: Decimal
    sl_price: Decimal
    tp_price: Decimal
    direction: int  # 1 for Long, -1 for Short
    
    def __post_init__(self):
        """Validate trade parameters after initialization."""
        if self.direction not in (1, -1):
            raise ValueError(f"Direction must be 1 (Long) or -1 (Short), got {self.direction}")
        
        if self.entry_price <= 0 or self.sl_price <= 0 or self.tp_price <= 0:
            raise ValueError("All prices must be positive")
        
        # Validate stop loss is on the correct side of entry for the direction
        if self.direction == 1:  # Long
            if self.sl_price >= self.entry_price:
                raise ValueError(f"For Long trades, SL ({self.sl_price}) must be below entry ({self.entry_price})")
            if self.tp_price <= self.entry_price:
                raise ValueError(f"For Long trades, TP ({self.tp_price}) must be above entry ({self.entry_price})")
        else:  # Short
            if self.sl_price <= self.entry_price:
                raise ValueError(f"For Short trades, SL ({self.sl_price}) must be above entry ({self.entry_price})")
            if self.tp_price >= self.entry_price:
                raise ValueError(f"For Short trades, TP ({self.tp_price}) must be below entry ({self.entry_price})")


@dataclass
class PositionSizeResult:
    """Container for position sizing calculation results."""
    kelly_fraction: Decimal
    quarter_kelly_percent: Decimal
    final_risk_percent: Decimal
    risk_capital: Decimal
    sl_distance: Decimal
    units: int
    reward_risk_ratio: Decimal


# =============================================================================
# POSITION SIZING LOGIC
# =============================================================================

def calculate_reward_risk_ratio(
    entry_price: Decimal,
    sl_price: Decimal,
    tp_price: Decimal,
    direction: int
) -> Decimal:
    """
    Calculate the Reward-to-Risk ratio based on entry, SL, and TP prices.
    
    R = Potential Reward / Potential Risk
    
    Args:
        entry_price: The entry price for the trade
        sl_price: The stop loss price
        tp_price: The take profit price
        direction: 1 for Long, -1 for Short
    
    Returns:
        Decimal: The R:R ratio (e.g., 2.0 means 2:1 reward-to-risk)
    """
    if direction == 1:  # Long
        potential_reward = tp_price - entry_price
        potential_risk = entry_price - sl_price
    else:  # Short
        potential_reward = entry_price - tp_price
        potential_risk = sl_price - entry_price
    
    if potential_risk == 0:
        raise ValueError("Stop loss distance cannot be zero")
    
    return potential_reward / potential_risk


def calculate_kelly_fraction(win_rate: Decimal, reward_risk_ratio: Decimal) -> Decimal:
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
        Decimal: The optimal Kelly fraction
    """
    if reward_risk_ratio <= 0:
        raise ValueError("Reward-to-risk ratio must be positive")
    
    # K = W - ((1 - W) / R)
    kelly = win_rate - ((Decimal('1') - win_rate) / reward_risk_ratio)
    
    # Kelly can be negative if edge is negative (W < 0.5 and R < 1)
    # In such cases, we return 0 (no trade)
    return max(kelly, Decimal('0'))


def calculate_position_size(
    entry_price: Decimal,
    sl_price: Decimal,
    tp_price: Decimal,
    direction: int,
    win_rate: Decimal = FIXED_WIN_RATE,
    fractional_kelly: Decimal = FRACTIONAL_KELLY,
    max_risk_dollars: Decimal = MAX_RISK_DOLLARS,
    assumed_balance: Decimal = ASSUMED_BALANCE
) -> PositionSizeResult:
    """
    Calculate the position size using Fractional Kelly Criterion with hard caps.
    
    Algorithm:
        1. Calculate Reward-to-Risk ratio (R)
        2. Calculate optimal Kelly fraction: K = W - ((1 - W) / R)
        3. Apply fractional multiplier: Quarter-Kelly = K * 0.25
        4. Apply hard cap: max 2% of $10,000 = $200
        5. Calculate units: Risk Capital / SL Distance
    
    Args:
        entry_price: The entry price for the trade
        sl_price: The stop loss price
        tp_price: The take profit price
        direction: 1 for Long, -1 for Short
        win_rate: Historical win rate (default 45%)
        fractional_kelly: Kelly multiplier (default 0.25 for Quarter-Kelly)
        max_risk_dollars: Maximum dollar risk per trade (default $200)
        assumed_balance: Assumed account balance (default $10,000)
    
    Returns:
        PositionSizeResult: Complete position sizing calculation
    """
    # Step 1: Calculate Reward-to-Risk ratio
    rr_ratio = calculate_reward_risk_ratio(entry_price, sl_price, tp_price, direction)
    
    # Step 2: Calculate optimal Kelly fraction
    kelly_fraction = calculate_kelly_fraction(win_rate, rr_ratio)
    
    # Step 3: Apply fractional Kelly (Quarter-Kelly)
    quarter_kelly_percent = kelly_fraction * fractional_kelly
    
    # Step 4: Calculate risk capital and apply hard cap
    # Convert percentage to dollars
    kelly_risk_dollars = assumed_balance * quarter_kelly_percent
    
    # Apply hard cap: maximum $200 risk per trade
    risk_capital = min(kelly_risk_dollars, max_risk_dollars)
    
    # Also ensure we don't risk more than the calculated Kelly percentage
    # This handles the case where Kelly suggests > 2%
    final_risk_percent = (risk_capital / assumed_balance) * Decimal('100')
    
    # Step 5: Calculate stop loss distance in price terms
    if direction == 1:  # Long
        sl_distance = entry_price - sl_price
    else:  # Short
        sl_distance = sl_price - entry_price
    
    # Step 6: Calculate units
    # Units = Risk Capital / SL Distance
    if sl_distance == 0:
        raise ValueError("Stop loss distance cannot be zero")
    
    units_decimal = risk_capital / sl_distance
    
    # Round down to ensure we don't exceed risk limit
    # Oanda requires integer units
    units = int(units_decimal.quantize(Decimal('1'), rounding=ROUND_DOWN))
    
    # Ensure minimum trade size (Oanda typically requires at least 1 unit)
    if units < 1:
        logger.warning(f"Calculated units ({units}) below minimum. Setting to 1 unit.")
        units = 1
    
    return PositionSizeResult(
        kelly_fraction=kelly_fraction,
        quarter_kelly_percent=quarter_kelly_percent,
        final_risk_percent=final_risk_percent,
        risk_capital=risk_capital,
        sl_distance=sl_distance,
        units=units,
        reward_risk_ratio=rr_ratio
    )


# =============================================================================
# OANDA API INTEGRATION
# =============================================================================

def create_oanda_client() -> API:
    """
    Create and configure an Oanda API client.
    
    Returns:
        API: Configured oandapyV20 API client
    
    Raises:
        ValueError: If API credentials are not configured
    """
    if not OANDA_API_KEY:
        raise ValueError("OANDA_API_KEY not configured. Please set it in your .env file.")
    
    # Determine environment
    environment = OANDA_ENV.lower()
    if environment not in ('practice', 'live'):
        logger.warning(f"Unknown OANDA_ENV '{environment}', defaulting to 'practice'")
        environment = 'practice'
    
    # Create API client
    # For practice environment, use the practice URL
    # oandapyV20 handles the base URL based on environment parameter
    client = API(
        access_token=OANDA_API_KEY,
        environment=environment
    )
    
    return client


def build_market_order(
    instrument: str,
    units: int,
    direction: int,
    sl_price: Decimal,
    tp_price: Decimal
) -> Dict[str, Any]:
    """
    Build a MarketOrderRequest payload for Oanda API.
    
    Args:
        instrument: The currency pair (e.g., "EUR_USD")
        units: Number of units to trade
        direction: 1 for Long, -1 for Short
        sl_price: Stop loss price
        tp_price: Take profit price
    
    Returns:
        Dict: OrderCreate request payload
    """
    # Adjust units based on direction
    # Positive units = Long, Negative units = Short
    signed_units = units if direction == 1 else -units
    
    # Create stop loss and take profit details
    sl_details = StopLossDetails(price=float(sl_price))
    tp_details = TakeProfitDetails(price=float(tp_price))
    
    # Build the market order request
    order_request = MarketOrderRequest(
        instrument=instrument,
        units=signed_units,
        stopLossOnFill=sl_details.data,
        takeProfitOnFill=tp_details.data
    )
    
    return order_request.data


def execute_trade(
    instrument: str,
    entry_price: float,
    sl_price: float,
    tp_price: float,
    direction: int
) -> Optional[Dict[str, Any]]:
    """
    Execute a market order on Oanda with calculated position sizing.
    
    This is the main entry point for trade execution. It:
        1. Validates trade parameters
        2. Calculates position size using Fractional Kelly
        3. Constructs and sends the order to Oanda
        4. Logs detailed execution information
        5. Handles errors gracefully
    
    Args:
        instrument: The currency pair to trade (e.g., "EUR_USD")
        entry_price: The entry price for the trade
        sl_price: The stop loss price
        tp_price: The take profit price
        direction: 1 for Long, -1 for Short
    
    Returns:
        Optional[Dict]: The API response if successful, None if failed
    """
    # ==========================================================================
    # STEP 1: Validate Inputs
    # ==========================================================================
    try:
        # Convert to Decimal for precise calculations
        params = TradeParameters(
            instrument=instrument.upper(),
            entry_price=Decimal(str(entry_price)),
            sl_price=Decimal(str(sl_price)),
            tp_price=Decimal(str(tp_price)),
            direction=direction
        )
    except ValueError as e:
        logger.error(f"Trade parameter validation failed: {e}")
        return None
    
    # ==========================================================================
    # STEP 2: Calculate Position Size
    # ==========================================================================
    try:
        sizing = calculate_position_size(
            entry_price=params.entry_price,
            sl_price=params.sl_price,
            tp_price=params.tp_price,
            direction=params.direction
        )
    except Exception as e:
        logger.error(f"Position sizing calculation failed: {e}")
        return None
    
    # ==========================================================================
    # STEP 3: Log Pre-Trade Information
    # ==========================================================================
    direction_str = "LONG" if direction == 1 else "SHORT"
    pip_distance = sizing.sl_distance * Decimal('10000')  # Approximate pips for forex
    
    print("\n" + "=" * 70)
    print("TRADE EXECUTION REQUEST")
    print("=" * 70)
    print(f"Instrument:        {params.instrument}")
    print(f"Direction:         {direction_str}")
    print(f"Entry Price:       {params.entry_price}")
    print(f"Stop Loss:         {params.sl_price}")
    print(f"Take Profit:       {params.tp_price}")
    print("-" * 70)
    print("POSITION SIZING CALCULATION")
    print("-" * 70)
    print(f"Assumed Balance:   ${ASSUMED_BALANCE:,.2f}")
    print(f"Win Rate (W):      {FIXED_WIN_RATE * 100}%")
    print(f"R:R Ratio (R):     {sizing.reward_risk_ratio:.2f}")
    print(f"Kelly Fraction:    {sizing.kelly_fraction:.4f}")
    print(f"Quarter-Kelly:     {sizing.quarter_kelly_percent * 100:.2f}%")
    print(f"Final Risk %:      {sizing.final_risk_percent:.2f}%")
    print(f"Risk Capital:      ${sizing.risk_capital:,.2f}")
    print(f"SL Distance:       {sizing.sl_distance}")
    print(f"Pip Distance:      ~{pip_distance:.1f} pips")
    print(f"Final Units:       {sizing.units}")
    print("=" * 70)
    
    # ==========================================================================
    # STEP 4: Create Oanda Client
    # ==========================================================================
    try:
        client = create_oanda_client()
    except ValueError as e:
        logger.error(f"Failed to create Oanda client: {e}")
        print(f"\n[ERROR] Oanda client configuration failed: {e}")
        return None
    
    # ==========================================================================
    # STEP 5: Build and Send Order
    # ==========================================================================
    try:
        # Build the order payload
        order_data = build_market_order(
            instrument=params.instrument,
            units=sizing.units,
            direction=params.direction,
            sl_price=params.sl_price,
            tp_price=params.tp_price
        )
        
        logger.debug(f"Order payload: {order_data}")
        
        # Create the OrderCreate request
        if not OANDA_ACCOUNT_ID:
            raise ValueError("OANDA_ACCOUNT_ID_DEMO not configured")
        
        request = OrderCreate(accountID=OANDA_ACCOUNT_ID, data=order_data)
        
        # Execute the order
        print(f"\nSending order to Oanda ({OANDA_ENV})...")
        response = client.request(request)
        
        # ==========================================================================
        # STEP 6: Process Response
        # ==========================================================================
        if response and 'orderFillTransaction' in response:
            fill_tx = response['orderFillTransaction']
            print(f"\n[SUCCESS] Order executed successfully!")
            print(f"Order ID:          {fill_tx.get('id', 'N/A')}")
            print(f"Filled Units:      {fill_tx.get('units', 'N/A')}")
            print(f"Filled Price:      {fill_tx.get('price', 'N/A')}")
            print(f"PL:                {fill_tx.get('pl', '0')}")
            print("=" * 70 + "\n")
            
            logger.info(f"Trade executed: {params.instrument} {direction_str} {sizing.units} units")
            return response
        
        elif response and 'orderCancelTransaction' in response:
            cancel_tx = response['orderCancelTransaction']
            reason = cancel_tx.get('reason', 'Unknown')
            print(f"\n[REJECTED] Order was cancelled by Oanda")
            print(f"Reason: {reason}")
            print("=" * 70 + "\n")
            
            logger.warning(f"Order cancelled: {reason}")
            return response
        
        else:
            print(f"\n[WARNING] Unexpected response structure")
            print(f"Response: {response}")
            print("=" * 70 + "\n")
            
            logger.warning(f"Unexpected API response: {response}")
            return response
    
    # ==========================================================================
    # STEP 7: Error Handling
    # ==========================================================================
    except V20Error as e:
        # Oanda API specific errors (e.g., market closed, insufficient margin)
        error_code = getattr(e, 'code', 'Unknown')
        error_msg = str(e)
        
        print(f"\n[OANDA API ERROR] Code: {error_code}")
        print(f"Message: {error_msg}")
        print("=" * 70 + "\n")
        
        logger.error(f"Oanda API error (code {error_code}): {error_msg}")
        return None
    
    except Exception as e:
        # General exceptions (network, configuration, etc.)
        print(f"\n[ERROR] Unexpected error during trade execution: {e}")
        print("=" * 70 + "\n")
        
        logger.error(f"Trade execution failed: {e}", exc_info=True)
        return None


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_account_summary() -> Optional[Dict[str, Any]]:
    """
    Retrieve account summary from Oanda (for verification purposes).
    
    Returns:
        Optional[Dict]: Account summary if successful, None otherwise
    """
    try:
        from oandapyV20.endpoints.accounts import AccountSummary
        
        client = create_oanda_client()
        if not OANDA_ACCOUNT_ID:
            raise ValueError("OANDA_ACCOUNT_ID_DEMO not configured")
        
        request = AccountSummary(accountID=OANDA_ACCOUNT_ID)
        response = client.request(request)
        
        return response
    
    except Exception as e:
        logger.error(f"Failed to get account summary: {e}")
        return None


def test_connection() -> bool:
    """
    Test the Oanda API connection and credentials.
    
    Returns:
        bool: True if connection is successful, False otherwise
    """
    print("\n" + "=" * 70)
    print("TESTING OANDA API CONNECTION")
    print("=" * 70)
    
    try:
        client = create_oanda_client()
        
        if not OANDA_ACCOUNT_ID:
            print("[FAIL] OANDA_ACCOUNT_ID_DEMO not configured")
            return False
        
        from oandapyV20.endpoints.accounts import AccountSummary
        request = AccountSummary(accountID=OANDA_ACCOUNT_ID)
        response = client.request(request)
        
        account = response.get('account', {})
        print(f"[SUCCESS] Connected to Oanda ({OANDA_ENV})")
        print(f"Account ID:    {account.get('id', 'N/A')}")
        print(f"Account Alias: {account.get('alias', 'N/A')}")
        print(f"Currency:      {account.get('currency', 'N/A')}")
        print(f"Balance:       {account.get('balance', 'N/A')}")
        print("=" * 70 + "\n")
        
        return True
    
    except Exception as e:
        print(f"[FAIL] Connection test failed: {e}")
        print("=" * 70 + "\n")
        return False


# =============================================================================
# MAIN EXECUTION (for testing)
# =============================================================================

if __name__ == "__main__":
    """
    Example usage and testing of the Oanda executor module.
    
    To test:
        1. Create a .env file with your Oanda credentials
        2. Run: python oanda_executor.py
    
    Example .env file:
        OANDA_API_KEY=your_api_key_here
        OANDA_ACCOUNT_ID_DEMO=your_account_id_here
        OANDA_ENV=practice
    """
    
    print("\n" + "=" * 70)
    print("OANDA TRADE EXECUTOR - TEST MODE")
    print("=" * 70)
    
    # Test API connection first
    if not test_connection():
        print("\nPlease configure your Oanda credentials in a .env file:")
        print("  OANDA_API_KEY=your_api_key")
        print("  OANDA_ACCOUNT_ID_DEMO=your_account_id")
        print("  OANDA_ENV=practice")
        sys.exit(1)
    
    # Example trade parameters (modify for your testing)
    # These are example values - adjust for current market conditions
    test_instrument = "EUR_USD"
    test_entry = 1.0850
    test_sl = 1.0830      # 20 pip stop loss
    test_tp = 1.0890      # 40 pip take profit (2:1 R:R)
    test_direction = 1    # Long
    
    print("\nExecuting test trade with parameters:")
    print(f"  Instrument: {test_instrument}")
    print(f"  Entry: {test_entry}")
    print(f"  SL: {test_sl}")
    print(f"  TP: {test_tp}")
    print(f"  Direction: {'LONG' if test_direction == 1 else 'SHORT'}")
    print("\n" + "=" * 70)
    
    # Execute the trade
    result = execute_trade(
        instrument=test_instrument,
        entry_price=test_entry,
        sl_price=test_sl,
        tp_price=test_tp,
        direction=test_direction
    )
    
    if result:
        print("\nTrade execution completed. Check Oanda portal for details.")
    else:
        print("\nTrade execution failed. Check logs for details.")