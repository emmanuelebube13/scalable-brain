"""WebSocket streaming routes for real-time OANDA market data.

This module provides WebSocket endpoints for streaming real-time price data,
candle updates, and indicators from OANDA, along with REST endpoints for
streaming management and monitoring.
"""

import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, WebSocket, HTTPException, Query
import logging

from layer5.services.oanda_stream_service import (
    OandaStreamManager,
    init_stream_manager,
    get_stream_manager,
    shutdown_stream_manager,
    Granularity,
)
from layer5.services.oanda_live_client import is_oanda_configured
from layer5.services.data_contracts import StreamingStatus, StreamingSubscription

logger = logging.getLogger(__name__)
router = APIRouter()
_startup_task: Optional[asyncio.Task] = None


async def _start_stream_manager_background() -> None:
    """Start stream manager asynchronously so app startup never blocks."""
    try:
        manager = init_stream_manager()
        # Guard startup with a timeout so health endpoints remain responsive.
        await asyncio.wait_for(manager.start(), timeout=5)
        logger.info("OANDA Stream Manager started successfully")
    except asyncio.TimeoutError:
        logger.error("Timed out starting OANDA Stream Manager; continuing without blocking API")
    except Exception as e:
        logger.error(f"Failed to start OANDA Stream Manager: {e}")


# =============================================================================
# Lifecycle Events
# =============================================================================

@router.on_event("startup")
async def startup_event():
    """Initialize the stream manager on startup."""
    global _startup_task

    if is_oanda_configured():
        _startup_task = asyncio.create_task(_start_stream_manager_background())
        logger.info("OANDA Stream Manager startup scheduled in background")
    else:
        logger.warning("OANDA not configured - streaming will be unavailable")


@router.on_event("shutdown")
async def shutdown_event():
    """Shutdown the stream manager on application shutdown."""
    global _startup_task

    try:
        if _startup_task and not _startup_task.done():
            _startup_task.cancel()
            try:
                await _startup_task
            except asyncio.CancelledError:
                pass

        await shutdown_stream_manager()
        logger.info("OANDA Stream Manager stopped")
    except Exception as e:
        logger.error(f"Error stopping OANDA Stream Manager: {e}")


# =============================================================================
# WebSocket Endpoint
# =============================================================================

@router.websocket("/ws/oanda")
async def oanda_websocket(websocket: WebSocket):
    """WebSocket endpoint for OANDA real-time streaming.
    
    This endpoint provides real-time price streaming, candle updates,
    and indicator calculations from OANDA.
    
    Client Protocol:
    ----------------
    
    Subscribe to a symbol:
        {"type": "subscribe", "symbol": "EUR_USD", "granularity": "M1"}
    
    Unsubscribe from a symbol:
        {"type": "unsubscribe", "symbol": "EUR_USD", "granularity": "M1"}
    
    Get historical candles:
        {"type": "get_candles", "symbol": "EUR_USD", "granularity": "M1", "count": 100}
    
    Get indicators:
        {"type": "get_indicators", "symbol": "EUR_USD", "granularity": "M1", 
         "indicators": [{"name": "sma", "params": {"period": 20}}]}
    
    Get stream metrics:
        {"type": "get_metrics"}
    
    Get active subscriptions:
        {"type": "get_subscriptions"}
    
    Ping/Pong:
        {"type": "ping"} -> {"type": "pong"}
    
    Server Messages:
    ----------------
    
    Price tick:
        {"type": "tick", "symbol": "EUR_USD", "data": {"time": "...", "bid": 1.0850, "ask": 1.0852, "mid": 1.0851}}
    
    Candle close:
        {"type": "candle", "symbol": "EUR_USD", "granularity": "M1", 
         "data": {"timestamp": "...", "open": 1.0850, "high": 1.0855, "low": 1.0848, "close": 1.0852, "volume": 120}}
    
    Historical data:
        {"type": "history", "symbol": "EUR_USD", "granularity": "M1", 
         "candles": [...]}
    
    Indicators:
        {"type": "indicators", "symbol": "EUR_USD", "granularity": "M1", 
         "data": {...}}
    
    Connection status:
        {"type": "connected", "client_id": "...", "message": "..."}
        {"type": "subscribed", "symbol": "...", "granularity": "..."}
        {"type": "error", "message": "..."}
    """
    manager = get_stream_manager()
    
    if manager is None or not manager.is_configured():
        await websocket.accept()
        await websocket.send_json({
            "type": "error",
            "message": "OANDA streaming is not configured"
        })
        await websocket.close(code=1011)
        return
    
    await manager.handle_websocket(websocket)


# =============================================================================
# Status & Health Endpoints
# =============================================================================

@router.get("/status", response_model=StreamingStatus)
async def get_streaming_status():
    """Get comprehensive streaming service status.
    
    Returns connection status, subscription counts, and health metrics
    for the OANDA streaming service.
    """
    manager = get_stream_manager()
    
    if manager is None:
        return StreamingStatus(
            isConnected=False,
            isConfigured=is_oanda_configured(),
            activeSubscriptions=0,
            totalMessages=0,
            reconnectCount=0,
            lastError="Stream manager not initialized",
            timestamp=datetime.now()
        )
    
    try:
        metrics = manager.get_metrics()
        subscriptions = manager.get_subscriptions()
        
        return StreamingStatus(
            isConnected=manager.is_connected() if hasattr(manager, 'is_connected') else True,
            isConfigured=manager.is_configured(),
            activeSubscriptions=len(subscriptions),
            totalMessages=metrics.get('messages_received', 0),
            reconnectCount=metrics.get('reconnect_count', 0),
            uptime=metrics.get('uptime'),
            lastError=metrics.get('last_error'),
            timestamp=datetime.now()
        )
    except Exception as e:
        logger.error(f"Error getting streaming status: {e}")
        return StreamingStatus(
            isConnected=False,
            isConfigured=is_oanda_configured(),
            activeSubscriptions=0,
            totalMessages=0,
            reconnectCount=0,
            lastError=str(e),
            timestamp=datetime.now()
        )


@router.get("/health")
async def get_streaming_health():
    """Quick health check for streaming service.
    
    Returns a simple health status for load balancers and monitoring.
    """
    manager = get_stream_manager()
    
    if manager is None:
        return {
            "status": "unavailable",
            "configured": is_oanda_configured(),
            "timestamp": datetime.now().isoformat()
        }
    
    return {
        "status": "healthy" if manager.is_configured() else "not_configured",
        "configured": manager.is_configured(),
        "timestamp": datetime.now().isoformat()
    }


@router.get("/config")
async def get_streaming_config():
    """Get streaming configuration (safe values only).
    
    Returns public configuration info without sensitive credentials.
    """
    configured = is_oanda_configured()
    
    config = {
        "configured": configured,
        "environment": "practice" if configured else None,
        "supported_granularities": [
            "S5", "S10", "S15", "S30",
            "M1", "M2", "M4", "M5", "M10", "M15", "M30",
            "H1", "H2", "H3", "H4", "H6", "H8", "H12",
            "D", "W", "M"
        ],
        "websocket_endpoint": "/api/v1/streaming/ws/oanda",
        "features": {
            "price_streaming": configured,
            "candle_streaming": configured,
            "indicator_calculation": configured,
            "historical_candles": configured
        }
    }
    
    return config


# =============================================================================
# Subscription Management Endpoints
# =============================================================================

@router.get("/subscriptions", response_model=Dict[str, List[StreamingSubscription]])
async def get_subscriptions():
    """Get all active symbol subscriptions.
    
    Returns:
        List of active subscriptions with symbol, granularity, and client count.
    """
    manager = get_stream_manager()
    
    if manager is None:
        raise HTTPException(status_code=503, detail="Stream manager not initialized")
    
    subscriptions = manager.get_subscriptions()
    
    return {
        "subscriptions": [
            StreamingSubscription(
                symbol=sub.symbol,
                granularity=sub.granularity.value,
                clientCount=sub.client_count,
                createdAt=sub.created_at,
                lastActivity=sub.last_activity
            )
            for sub in subscriptions.values()
        ]
    }


@router.get("/subscriptions/{symbol}")
async def get_symbol_subscriptions(symbol: str):
    """Get subscriptions for a specific symbol."""
    manager = get_stream_manager()
    
    if manager is None:
        raise HTTPException(status_code=503, detail="Stream manager not initialized")
    
    subscriptions = manager.get_subscriptions()
    symbol_subs = [
        {
            "symbol": sub.symbol,
            "granularity": sub.granularity.value,
            "clients": sub.client_count,
            "created_at": sub.created_at.isoformat(),
            "last_activity": sub.last_activity.isoformat(),
        }
        for sub in subscriptions.values()
        if sub.symbol == symbol
    ]
    
    return {
        "symbol": symbol,
        "subscriptions": symbol_subs,
        "count": len(symbol_subs)
    }


# =============================================================================
# Data Endpoints
# =============================================================================

@router.get("/candles/{symbol}")
async def get_candles(
    symbol: str,
    granularity: str = Query(default="M1", description="Candle granularity (M1, M5, H1, etc.)"),
    count: int = Query(default=100, ge=1, le=5000, description="Number of candles to fetch"),
):
    """Fetch historical candles for a symbol.
    
    Args:
        symbol: Trading instrument (e.g., EUR_USD)
        granularity: Candle granularity (M1, M5, M15, H1, etc.)
        count: Number of candles to fetch (max 5000)
    
    Returns:
        List of OHLCV candles.
    """
    manager = get_stream_manager()
    
    if manager is None:
        raise HTTPException(status_code=503, detail="Stream manager not initialized")
    
    try:
        candles = await manager.get_candles(symbol, granularity, count)
        return {
            "symbol": symbol,
            "granularity": granularity,
            "count": len(candles),
            "candles": [c.to_dict() for c in candles]
        }
    except Exception as e:
        logger.error(f"Failed to fetch candles for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch candles: {e}")


@router.get("/price/{symbol}")
async def get_current_price(symbol: str):
    """Get the current price for a symbol.
    
    Args:
        symbol: Trading instrument (e.g., EUR_USD)
    
    Returns:
        Current bid, ask, and mid prices.
    """
    manager = get_stream_manager()
    
    if manager is None:
        raise HTTPException(status_code=503, detail="Stream manager not initialized")
    
    tick = await manager.get_current_price(symbol)
    
    if tick is None:
        raise HTTPException(status_code=404, detail=f"No price data available for {symbol}")
    
    return {
        "symbol": symbol,
        "time": tick.time.isoformat(),
        "bid": tick.bid,
        "ask": tick.ask,
        "mid": tick.mid,
    }


@router.post("/indicators/{symbol}")
async def calculate_indicators(
    symbol: str,
    granularity: str = Query(default="M1", description="Candle granularity"),
    indicators: Optional[List[Dict[str, Any]]] = None,
):
    """Calculate technical indicators for a symbol.
    
    Args:
        symbol: Trading instrument (e.g., EUR_USD)
        granularity: Candle granularity
        indicators: List of indicator configurations
            Example: [{"name": "sma", "params": {"period": 20}}]
    
    Returns:
        Calculated indicator values.
    """
    manager = get_stream_manager()
    
    if manager is None:
        raise HTTPException(status_code=503, detail="Stream manager not initialized")
    
    indicators = indicators or []
    
    try:
        results = await manager.calculate_indicators_batch(symbol, granularity, indicators)
        return results
    except Exception as e:
        logger.error(f"Failed to calculate indicators for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to calculate indicators: {e}")


# =============================================================================
# Metrics & Management Endpoints
# =============================================================================

@router.get("/metrics")
async def get_stream_metrics():
    """Get stream connection metrics.
    
    Returns:
        Connection metrics including uptime, reconnects, and message counts.
    """
    manager = get_stream_manager()
    
    if manager is None:
        raise HTTPException(status_code=503, detail="Stream manager not initialized")
    
    return manager.get_metrics()


@router.post("/reconnect")
async def force_reconnect():
    """Force a reconnection to the OANDA streaming API.
    
    Use this if you suspect connection issues or data staleness.
    """
    manager = get_stream_manager()
    
    if manager is None:
        raise HTTPException(status_code=503, detail="Stream manager not initialized")
    
    try:
        await manager.reconnect()
        return {
            "status": "reconnected",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to reconnect: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reconnect: {e}")


@router.post("/reset")
async def reset_streaming():
    """Reset the streaming service completely.
    
    This will shutdown and restart the stream manager.
    All active subscriptions will be dropped.
    """
    try:
        await shutdown_stream_manager()
        
        if is_oanda_configured():
            manager = init_stream_manager()
            await manager.start()
            
        return {
            "status": "reset_complete",
            "configured": is_oanda_configured(),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to reset streaming: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reset: {e}")


# =============================================================================
# Available Instruments
# =============================================================================

@router.get("/instruments")
async def get_available_instruments():
    """Get list of available instruments for streaming.
    
    Returns the instruments that can be subscribed to via WebSocket.
    """
    # Limit to the 5 main currency pairs as per requirements
    instruments = [
        {"symbol": "EUR_USD", "name": "EUR/USD", "type": "forex", "displayName": "Euro / US Dollar"},
        {"symbol": "GBP_USD", "name": "GBP/USD", "type": "forex", "displayName": "British Pound / US Dollar"},
        {"symbol": "USD_JPY", "name": "USD/JPY", "type": "forex", "displayName": "US Dollar / Japanese Yen"},
        {"symbol": "AUD_USD", "name": "AUD/USD", "type": "forex", "displayName": "Australian Dollar / US Dollar"},
        {"symbol": "USD_CAD", "name": "USD/CAD", "type": "forex", "displayName": "US Dollar / Canadian Dollar"},
    ]
    
    manager = get_stream_manager()
    
    return {
        "instruments": instruments,
        "count": len(instruments),
        "streaming_available": manager is not None and manager.is_configured() if manager else False
    }


# =============================================================================
# Simplified WebSocket for Chart Streaming
# =============================================================================

@router.websocket("/ws/oanda/stream")
async def oanda_chart_stream(websocket: WebSocket, instrument: str = Query(...)):
    """Simplified WebSocket endpoint for chart streaming.
    
    Query Parameters:
        instrument: The currency pair to stream (e.g., EUR_USD)
    
    This endpoint provides a simplified protocol for the custom chart component.
    """
    manager = get_stream_manager()
    
    if manager is None or not manager.is_configured():
        await websocket.accept()
        await websocket.send_json({
            "type": "error",
            "message": "OANDA streaming is not configured"
        })
        await websocket.close(code=1011)
        return
    
    await websocket.accept()
    
    client_id = f"chart_{id(websocket)}"
    
    try:
        # Subscribe to the instrument
        await manager.subscribe_instrument(instrument, "M1", client_id)
        
        await websocket.send_json({
            "type": "connected",
            "message": f"Connected to {instrument}",
            "instrument": instrument
        })
        
        # Keep connection alive and handle client messages
        while True:
            try:
                message = await websocket.receive_json()
                msg_type = message.get("type")
                
                if msg_type == "subscribe":
                    symbol = message.get("symbol", instrument)
                    granularity = message.get("granularity", "M1")
                    await manager.subscribe_instrument(symbol, granularity, client_id)
                    await websocket.send_json({
                        "type": "subscribed",
                        "symbol": symbol,
                        "granularity": granularity
                    })
                
                elif msg_type == "unsubscribe":
                    symbol = message.get("symbol", instrument)
                    await manager.unsubscribe_instrument(symbol, "M1", client_id)
                
                elif msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
                    
            except Exception as e:
                logger.warning(f"WebSocket message error: {e}")
                break
                
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # Cleanup
        try:
            await manager.unsubscribe_instrument(instrument, "M1", client_id)
        except:
            pass
        try:
            await websocket.close()
        except:
            pass
