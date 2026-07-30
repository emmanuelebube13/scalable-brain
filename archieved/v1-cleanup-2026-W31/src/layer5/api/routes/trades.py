"""Trade blotter & forensics routes."""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
import sqlalchemy as sa

from layer5.api.dependencies import get_db
from layer5.services import layer4_client, layer2_client
from layer5.services.data_contracts import Trade, Signal, OpenPosition

router = APIRouter()


@router.get("/", response_model=List[Trade])
def get_trades(
    limit: int = Query(50, ge=1, le=500, description="Maximum number of trades to return"),
    status: Optional[str] = Query(None, description="Filter by status (approved, vetoed, pending, closed)"),
    asset: Optional[str] = Query(None, description="Filter by asset symbol"),
    strategy: Optional[str] = Query(None, description="Filter by strategy key"),
    conn: sa.engine.Connection = Depends(get_db),
):
    """Get trades with optional filtering.
    
    Returns trades sorted by timestamp (newest first).
    """
    rows = layer4_client.get_live_trades(
        conn.engine, 
        limit=limit, 
        status=status, 
        asset=asset, 
        strategy=strategy
    )
    return [Trade(**r) for r in rows]


@router.get("/history", response_model=List[Trade])
def get_trade_history(
    limit: int = Query(100, ge=1, le=500, description="Maximum number of trades to return"),
    asset: Optional[str] = Query(None, description="Filter by asset symbol"),
    strategy: Optional[str] = Query(None, description="Filter by strategy key"),
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    conn: sa.engine.Connection = Depends(get_db),
):
    """Get closed trade history.
    
    Returns only completed/closed trades with outcome data.
    """
    rows = layer4_client.get_trade_history(
        conn.engine,
        limit=limit,
        asset=asset,
        strategy=strategy,
        days=days
    )
    return [Trade(**r) for r in rows]


@router.get("/open-positions", response_model=List[OpenPosition])
def get_open_positions(
    limit: int = Query(100, ge=1, le=500, description="Maximum number of positions to return"),
    conn: sa.engine.Connection = Depends(get_db),
):
    """Get currently open positions.
    
    Returns positions that are currently active in the market.
    """
    rows = layer4_client.get_open_positions(conn.engine, limit=limit)
    return [OpenPosition(**r) for r in rows]


@router.get("/blocked", response_model=List[Trade])
def get_blocked(
    limit: int = Query(10, ge=1, le=100, description="Maximum number of blocked trades to return"),
    conn: sa.engine.Connection = Depends(get_db),
):
    """Get recently vetoed/blocked trades with reasons."""
    rows = layer4_client.get_blocked_trades(conn.engine, limit=limit)
    return [Trade(**r) for r in rows]


@router.get("/signals/pending", response_model=List[Signal])
def get_pending(
    limit: int = Query(5, ge=1, le=50, description="Maximum number of pending signals to return"),
    conn: sa.engine.Connection = Depends(get_db),
):
    """Get pending signals awaiting approval."""
    rows = layer2_client.get_pending_signals(conn.engine, limit=limit)
    return [Signal(**r) for r in rows]


@router.get("/statistics")
def get_trade_statistics(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    asset: Optional[str] = Query(None, description="Filter by asset symbol"),
    strategy: Optional[str] = Query(None, description="Filter by strategy key"),
    conn: sa.engine.Connection = Depends(get_db),
):
    """Get trade statistics and performance metrics.
    
    Returns aggregated statistics including win rate, P&L, etc.
    """
    return layer4_client.get_trade_statistics(
        conn.engine,
        days=days,
        asset=asset,
        strategy=strategy
    )


@router.get("/performance/by-asset")
def get_asset_performance(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    conn: sa.engine.Connection = Depends(get_db),
):
    """Get performance breakdown by asset.
    
    Returns P&L and win rate for each asset.
    """
    return layer4_client.get_asset_performance(conn.engine, days=days)


@router.get("/performance/by-strategy")
def get_strategy_performance(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    conn: sa.engine.Connection = Depends(get_db),
):
    """Get performance breakdown by strategy.
    
    Returns P&L and win rate for each strategy.
    """
    return layer4_client.get_strategy_performance(conn.engine, days=days)
