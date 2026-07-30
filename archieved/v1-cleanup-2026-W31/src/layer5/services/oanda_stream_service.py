"""OANDA Real-time Streaming WebSocket Service.

This module provides institutional-grade WebSocket streaming for OANDA market data,
supporting real-time price feeds, candle aggregation, and multi-client subscriptions.

Features:
    - Real-time price streaming via OANDA v20 API
    - Candle aggregation from tick data (OHLC construction)
    - Multi-symbol subscription management
    - WebSocket connection pooling for multiple clients
    - Automatic reconnection with exponential backoff
    - Historical candle fetching via REST API
    - Server-side indicator calculation and caching
    - Connection health monitoring and metrics

Example:
    >>> from layer5.services.oanda_stream_service import OandaStreamManager
    >>> 
    >>> # Initialize the manager
    >>> manager = OandaStreamManager(
    ...     api_key="your-api-key",
    ...     account_id="your-account-id",
    ...     environment="practice"
    ... )
    >>> 
    >>> # Subscribe to a symbol
    >>> await manager.subscribe_instrument("EUR_USD", granularity="M1")
    >>> 
    >>> # Use with FastAPI WebSocket
    >>> @app.websocket("/ws/chart/oanda-stream")
    >>> async def oanda_stream(websocket: WebSocket):
    >>>     await manager.handle_websocket(websocket)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import (
    Any,
    Callable,
    Coroutine,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)

import numpy as np
import pandas as pd
from dotenv import load_dotenv

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Load environment variables
load_dotenv()


# -----------------------------------------------------------------------------
# Constants and Configuration
# -----------------------------------------------------------------------------

class Granularity(str, Enum):
    """OANDA candle granularities."""
    SECOND_5 = "S5"
    SECOND_10 = "S10"
    SECOND_15 = "S15"
    SECOND_30 = "S30"
    MINUTE_1 = "M1"
    MINUTE_2 = "M2"
    MINUTE_4 = "M4"
    MINUTE_5 = "M5"
    MINUTE_10 = "M10"
    MINUTE_15 = "M15"
    MINUTE_30 = "M30"
    HOUR_1 = "H1"
    HOUR_2 = "H2"
    HOUR_4 = "H4"
    HOUR_6 = "H6"
    HOUR_8 = "H8"
    HOUR_12 = "H12"
    DAY_1 = "D"
    WEEK_1 = "W"
    MONTH_1 = "M"


# Granularity to timedelta mapping
GRANULARITY_INTERVALS: Dict[Granularity, timedelta] = {
    Granularity.SECOND_5: timedelta(seconds=5),
    Granularity.SECOND_10: timedelta(seconds=10),
    Granularity.SECOND_15: timedelta(seconds=15),
    Granularity.SECOND_30: timedelta(seconds=30),
    Granularity.MINUTE_1: timedelta(minutes=1),
    Granularity.MINUTE_2: timedelta(minutes=2),
    Granularity.MINUTE_4: timedelta(minutes=4),
    Granularity.MINUTE_5: timedelta(minutes=5),
    Granularity.MINUTE_10: timedelta(minutes=10),
    Granularity.MINUTE_15: timedelta(minutes=15),
    Granularity.MINUTE_30: timedelta(minutes=30),
    Granularity.HOUR_1: timedelta(hours=1),
    Granularity.HOUR_2: timedelta(hours=2),
    Granularity.HOUR_4: timedelta(hours=4),
    Granularity.HOUR_6: timedelta(hours=6),
    Granularity.HOUR_8: timedelta(hours=8),
    Granularity.HOUR_12: timedelta(hours=12),
    Granularity.DAY_1: timedelta(days=1),
    Granularity.WEEK_1: timedelta(weeks=1),
    Granularity.MONTH_1: timedelta(days=30),
}

DEFAULT_RECONNECT_DELAY = 1.0
MAX_RECONNECT_DELAY = 60.0
STREAM_HEARTBEAT_INTERVAL = 15.0  # seconds
CANDLE_CACHE_SIZE = 1000  # Maximum candles to keep in memory per symbol


# -----------------------------------------------------------------------------
# Data Classes
# -----------------------------------------------------------------------------

@dataclass
class OHLCV:
    """OHLCV candle data structure."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0
    complete: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "open": round(self.open, 6),
            "high": round(self.high, 6),
            "low": round(self.low, 6),
            "close": round(self.close, 6),
            "volume": self.volume,
            "complete": self.complete,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> OHLCV:
        """Create from dictionary."""
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            open=data["open"],
            high=data["high"],
            low=data["low"],
            close=data["close"],
            volume=data.get("volume", 0),
            complete=data.get("complete", False),
        )


@dataclass
class PriceTick:
    """Price tick data structure."""
    symbol: str
    time: datetime
    bid: float
    ask: float
    mid: float
    
    @classmethod
    def from_oanda_response(cls, data: Dict[str, Any]) -> Optional[PriceTick]:
        """Create PriceTick from OANDA streaming response."""
        try:
            symbol = data.get("instrument", "")
            time_str = data.get("time", "")
            bids = data.get("bids", [{}])
            asks = data.get("asks", [{}])
            
            if not symbol or not time_str:
                return None
            
            # Parse OANDA timestamp format
            time = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
            
            bid = float(bids[0].get("price", 0)) if bids else 0.0
            ask = float(asks[0].get("price", 0)) if asks else 0.0
            mid = (bid + ask) / 2 if bid and ask else 0.0
            
            return cls(symbol=symbol, time=time, bid=bid, ask=ask, mid=mid)
        except (KeyError, ValueError, TypeError) as e:
            logger.debug(f"Failed to parse tick: {e}")
            return None


@dataclass
class Subscription:
    """Symbol subscription metadata."""
    symbol: str
    granularity: Granularity
    clients: Set[str] = field(default_factory=set)
    last_tick: Optional[PriceTick] = None
    current_candle: Optional[OHLCV] = None
    candle_history: List[OHLCV] = field(default_factory=list)
    indicators: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    @property
    def is_active(self) -> bool:
        """Check if subscription has active clients."""
        return len(self.clients) > 0
    
    @property
    def client_count(self) -> int:
        """Get number of connected clients."""
        return len(self.clients)


@dataclass
class StreamMetrics:
    """Stream connection metrics."""
    connection_start: Optional[datetime] = None
    reconnect_count: int = 0
    ticks_received: int = 0
    candles_closed: int = 0
    last_tick_time: Optional[datetime] = None
    errors_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "connection_start": self.connection_start.isoformat() if self.connection_start else None,
            "uptime_seconds": (datetime.now(timezone.utc) - self.connection_start).total_seconds() 
                             if self.connection_start else 0,
            "reconnect_count": self.reconnect_count,
            "ticks_received": self.ticks_received,
            "candles_closed": self.candles_closed,
            "last_tick_time": self.last_tick_time.isoformat() if self.last_tick_time else None,
            "errors_count": self.errors_count,
        }


# -----------------------------------------------------------------------------
# Exceptions
# -----------------------------------------------------------------------------

class OandaStreamError(Exception):
    """Base exception for OANDA streaming errors."""
    pass


class OandaConnectionError(OandaStreamError):
    """Exception for connection-related errors."""
    pass


class OandaAuthenticationError(OandaStreamError):
    """Exception for authentication failures."""
    pass


class OandaSubscriptionError(OandaStreamError):
    """Exception for subscription errors."""
    pass


# -----------------------------------------------------------------------------
# WebSocket Connection Manager
# -----------------------------------------------------------------------------

class WebSocketConnectionManager:
    """Manages WebSocket connections for multiple clients.
    
    This class handles client connections, subscriptions, and broadcasting
    of messages to all connected clients.
    
    Attributes:
        active_connections: Dict mapping client_id to WebSocket object
        client_subscriptions: Dict mapping client_id to set of subscribed symbols
    """
    
    def __init__(self):
        self.active_connections: Dict[str, Any] = {}
        self.client_subscriptions: Dict[str, Set[str]] = defaultdict(set)
        self._lock = asyncio.Lock()
    
    async def connect(self, client_id: str, websocket: Any) -> None:
        """Register a new client connection.
        
        Args:
            client_id: Unique identifier for the client
            websocket: WebSocket object (FastAPI WebSocket or similar)
        """
        async with self._lock:
            self.active_connections[client_id] = websocket
            self.client_subscriptions[client_id] = set()
        logger.info(f"Client {client_id} connected. Total clients: {len(self.active_connections)}")
    
    async def disconnect(self, client_id: str) -> None:
        """Remove a client connection.
        
        Args:
            client_id: Unique identifier for the client to disconnect
        """
        async with self._lock:
            if client_id in self.active_connections:
                del self.active_connections[client_id]
            if client_id in self.client_subscriptions:
                del self.client_subscriptions[client_id]
        logger.info(f"Client {client_id} disconnected. Total clients: {len(self.active_connections)}")
    
    async def subscribe_client(self, client_id: str, symbol: str) -> None:
        """Subscribe a client to a symbol.
        
        Args:
            client_id: Client identifier
            symbol: Symbol to subscribe to (e.g., "EUR_USD")
        """
        async with self._lock:
            if client_id in self.client_subscriptions:
                self.client_subscriptions[client_id].add(symbol)
        logger.debug(f"Client {client_id} subscribed to {symbol}")
    
    async def unsubscribe_client(self, client_id: str, symbol: str) -> None:
        """Unsubscribe a client from a symbol.
        
        Args:
            client_id: Client identifier
            symbol: Symbol to unsubscribe from
        """
        async with self._lock:
            if client_id in self.client_subscriptions:
                self.client_subscriptions[client_id].discard(symbol)
        logger.debug(f"Client {client_id} unsubscribed from {symbol}")
    
    async def broadcast(self, message: Dict[str, Any], symbol: Optional[str] = None) -> None:
        """Broadcast a message to all connected clients or symbol subscribers.
        
        Args:
            message: Message dictionary to broadcast
            symbol: If provided, only broadcast to clients subscribed to this symbol
        """
        disconnected = []
        
        async with self._lock:
            connections = dict(self.active_connections)
            subscriptions = dict(self.client_subscriptions)
        
        for client_id, websocket in connections.items():
            # Skip if symbol filter is applied and client not subscribed
            if symbol and client_id in subscriptions:
                if symbol not in subscriptions[client_id]:
                    continue
            
            try:
                if hasattr(websocket, "send_json"):
                    await websocket.send_json(message)
                elif hasattr(websocket, "send"):
                    await websocket.send(json.dumps(message))
            except Exception as e:
                logger.warning(f"Failed to send to client {client_id}: {e}")
                disconnected.append(client_id)
        
        # Clean up disconnected clients
        for client_id in disconnected:
            await self.disconnect(client_id)
    
    def get_subscribed_symbols(self, client_id: str) -> Set[str]:
        """Get all symbols a client is subscribed to.
        
        Args:
            client_id: Client identifier
            
        Returns:
            Set of subscribed symbol strings
        """
        return self.client_subscriptions.get(client_id, set()).copy()
    
    def get_clients_for_symbol(self, symbol: str) -> Set[str]:
        """Get all clients subscribed to a symbol.
        
        Args:
            symbol: Symbol to check
            
        Returns:
            Set of client IDs subscribed to the symbol
        """
        clients = set()
        for client_id, symbols in self.client_subscriptions.items():
            if symbol in symbols:
                clients.add(client_id)
        return clients
    
    @property
    def client_count(self) -> int:
        """Get total number of connected clients."""
        return len(self.active_connections)


# -----------------------------------------------------------------------------
# Candle Builder
# -----------------------------------------------------------------------------

class CandleBuilder:
    """Builds OHLC candles from streaming price ticks.
    
    This class aggregates tick data into candles of specified granularity,
    handling candle opening, updating, and closing logic.
    
    Attributes:
        symbol: Trading instrument symbol
        granularity: Candle granularity (e.g., "M1", "H1")
        timezone: Timezone for candle timestamps
    """
    
    def __init__(self, symbol: str, granularity: Granularity):
        self.symbol = symbol
        self.granularity = granularity
        self.interval = GRANULARITY_INTERVALS.get(granularity, timedelta(minutes=1))
        self.current_candle: Optional[OHLCV] = None
        self.candle_history: List[OHLCV] = []
        self._lock = asyncio.Lock()
    
    def _get_candle_start(self, tick_time: datetime) -> datetime:
        """Calculate the start time for a candle containing the given tick time.
        
        Args:
            tick_time: Timestamp of the price tick
            
        Returns:
            Start time of the candle period
        """
        # Round down to the nearest interval
        if self.granularity in (Granularity.DAY_1, Granularity.WEEK_1, Granularity.MONTH_1):
            # For daily and above, align to midnight UTC
            if self.granularity == Granularity.DAY_1:
                return tick_time.replace(hour=0, minute=0, second=0, microsecond=0)
            elif self.granularity == Granularity.WEEK_1:
                days_since_monday = tick_time.weekday()
                monday = tick_time - timedelta(days=days_since_monday)
                return monday.replace(hour=0, minute=0, second=0, microsecond=0)
            else:  # MONTH_1
                return tick_time.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            # For intraday, calculate based on minutes
            total_seconds = int(self.interval.total_seconds())
            epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
            tick_epoch = tick_time.replace(tzinfo=timezone.utc) if tick_time.tzinfo is None else tick_time
            seconds_since_epoch = int((tick_epoch - epoch).total_seconds())
            period_start_seconds = (seconds_since_epoch // total_seconds) * total_seconds
            period_start = epoch + timedelta(seconds=period_start_seconds)
            return period_start.replace(tzinfo=None)
    
    async def process_tick(self, tick: PriceTick) -> Optional[OHLCV]:
        """Process a new price tick and update or close candles.
        
        Args:
            tick: Price tick to process
            
        Returns:
            Closed candle if a candle was completed, None otherwise
        """
        async with self._lock:
            candle_start = self._get_candle_start(tick.time)
            closed_candle = None
            
            # Check if we need to close the current candle
            if self.current_candle is not None:
                if candle_start > self.current_candle.timestamp:
                    # Close the current candle
                    self.current_candle.complete = True
                    closed_candle = self.current_candle
                    self.candle_history.append(closed_candle)
                    
                    # Trim history if needed
                    if len(self.candle_history) > CANDLE_CACHE_SIZE:
                        self.candle_history = self.candle_history[-CANDLE_CACHE_SIZE:]
                    
                    # Start a new candle
                    self.current_candle = OHLCV(
                        timestamp=candle_start,
                        open=tick.mid,
                        high=tick.mid,
                        low=tick.mid,
                        close=tick.mid,
                        volume=1,
                        complete=False
                    )
                else:
                    # Update current candle
                    self.current_candle.high = max(self.current_candle.high, tick.mid)
                    self.current_candle.low = min(self.current_candle.low, tick.mid)
                    self.current_candle.close = tick.mid
                    self.current_candle.volume += 1
            else:
                # Start first candle
                self.current_candle = OHLCV(
                    timestamp=candle_start,
                    open=tick.mid,
                    high=tick.mid,
                    low=tick.mid,
                    close=tick.mid,
                    volume=1,
                    complete=False
                )
            
            return closed_candle
    
    async def force_close(self) -> Optional[OHLCV]:
        """Force close the current candle (e.g., on disconnect).
        
        Returns:
            The closed candle, or None if no candle was open
        """
        async with self._lock:
            if self.current_candle is not None:
                self.current_candle.complete = True
                closed = self.current_candle
                self.candle_history.append(closed)
                self.current_candle = None
                return closed
            return None
    
    def get_current_candle(self) -> Optional[OHLCV]:
        """Get the current (incomplete) candle."""
        return self.current_candle
    
    def get_candles(self, count: Optional[int] = None) -> List[OHLCV]:
        """Get historical candles.
        
        Args:
            count: Maximum number of candles to return (most recent first)
            
        Returns:
            List of OHLCV candles
        """
        candles = self.candle_history.copy()
        if self.current_candle:
            candles.append(self.current_candle)
        
        if count:
            candles = candles[-count:]
        
        return candles


# -----------------------------------------------------------------------------
# Main Stream Manager
# -----------------------------------------------------------------------------

class OandaStreamManager:
    """Main manager for OANDA real-time streaming.
    
    This class provides comprehensive WebSocket streaming capabilities for OANDA,
    including multi-symbol subscriptions, candle aggregation, indicator calculation,
    and client connection management.
    
    Attributes:
        api_key: OANDA API key
        account_id: OANDA account ID
        environment: "practice" or "live"
        ws_manager: WebSocketConnectionManager instance
        subscriptions: Dict of active symbol subscriptions
        metrics: Stream connection metrics
    
    Example:
        >>> manager = OandaStreamManager.from_env()
        >>> await manager.start()
        >>> await manager.subscribe_instrument("EUR_USD", Granularity.MINUTE_1)
    """
    
    def __init__(
        self,
        api_key: str,
        account_id: str,
        environment: str = "practice",
        max_reconnect_delay: float = MAX_RECONNECT_DELAY,
    ):
        self.api_key = api_key
        self.account_id = account_id
        self.environment = environment if environment in ("practice", "live") else "practice"
        self.max_reconnect_delay = max_reconnect_delay
        
        # Initialize OANDA API client
        self._init_api_client()
        
        # Connection management
        self.ws_manager = WebSocketConnectionManager()
        self.subscriptions: Dict[str, Subscription] = {}
        self.candle_builders: Dict[str, CandleBuilder] = {}
        
        # Event callbacks
        self._candle_callbacks: List[Callable[[str, OHLCV], Coroutine]] = []
        self._tick_callbacks: List[Callable[[str, PriceTick], Coroutine]] = []
        
        # Async tasks
        self._stream_task: Optional[asyncio.Task] = None
        self._health_check_task: Optional[asyncio.Task] = None
        self._running = False
        self._shutdown_event = asyncio.Event()
        
        # Metrics and state
        self.metrics = StreamMetrics()
        self._reconnect_delay = DEFAULT_RECONNECT_DELAY
        self._lock = asyncio.Lock()
        
        logger.info(f"OandaStreamManager initialized for account {account_id}")
    
    def _init_api_client(self) -> None:
        """Initialize the OANDA API client."""
        try:
            from oandapyV20 import API
            from oandapyV20.endpoints.pricing import PricingStream
            from oandapyV20.endpoints.instruments import InstrumentsCandles
            
            self._api_class = API
            self._pricing_stream_class = PricingStream
            self._instruments_candles_class = InstrumentsCandles
            
            self.api_client = API(
                access_token=self.api_key,
                environment=self.environment
            )
            logger.debug("OANDA API client initialized")
        except ImportError:
            logger.error("oandapyV20 library not installed. Run: pip install oandapyV20")
            raise
    
    @classmethod
    def from_env(cls, **kwargs) -> OandaStreamManager:
        """Create manager from environment variables.
        
        Environment variables:
            OANDA_API_KEY: OANDA API access token
            OANDA_ACCOUNT_ID: OANDA account ID
            OANDA_ENV: "practice" or "live" (default: practice)
        
        Returns:
            Configured OandaStreamManager instance
        """
        api_key = os.getenv("OANDA_API_KEY", "").strip()
        account_id = (
            os.getenv("OANDA_ACCOUNT_ID_DEMO") 
            or os.getenv("OANDA_ACCOUNT_ID") 
            or ""
        ).strip()
        environment = os.getenv("OANDA_ENV", "practice").strip().lower() or "practice"
        
        if not api_key or not account_id:
            raise OandaAuthenticationError(
                "OANDA credentials not found. Set OANDA_API_KEY and OANDA_ACCOUNT_ID environment variables."
            )
        
        return cls(
            api_key=api_key,
            account_id=account_id,
            environment=environment,
            **kwargs
        )
    
    def is_configured(self) -> bool:
        """Check if OANDA credentials are configured."""
        return bool(self.api_key and self.account_id)
    
    # -------------------------------------------------------------------------
    # Lifecycle Methods
    # -------------------------------------------------------------------------
    
    async def start(self) -> None:
        """Start the stream manager and begin background tasks."""
        if self._running:
            logger.warning("Stream manager already running")
            return
        
        self._running = True
        self._shutdown_event.clear()
        self.metrics.connection_start = datetime.now(timezone.utc)
        
        # Start health check task
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        
        # Start streaming task if there are subscriptions
        if self.subscriptions:
            self._start_stream_task()
        
        logger.info("OandaStreamManager started")
    
    async def stop(self) -> None:
        """Stop the stream manager and cleanup resources."""
        if not self._running:
            return
        
        self._running = False
        self._shutdown_event.set()
        
        # Cancel tasks
        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
        
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        # Close any open candles
        for builder in self.candle_builders.values():
            await builder.force_close()
        
        logger.info("OandaStreamManager stopped")
    
    def _start_stream_task(self) -> None:
        """Start or restart the streaming task."""
        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()
        
        self._stream_task = asyncio.create_task(self._stream_loop())
    
    # -------------------------------------------------------------------------
    # Subscription Management
    # -------------------------------------------------------------------------
    
    async def subscribe_instrument(
        self,
        symbol: str,
        granularity: Union[str, Granularity] = Granularity.MINUTE_1,
        client_id: Optional[str] = None,
    ) -> bool:
        """Subscribe to real-time streaming for an instrument.
        
        Args:
            symbol: Trading instrument (e.g., "EUR_USD")
            granularity: Candle granularity for aggregation
            client_id: Optional client ID for subscription tracking
            
        Returns:
            True if subscription successful
            
        Raises:
            OandaSubscriptionError: If subscription fails
        """
        if isinstance(granularity, str):
            try:
                granularity = Granularity(granularity)
            except ValueError:
                raise OandaSubscriptionError(f"Invalid granularity: {granularity}")
        
        symbol = symbol.upper()
        sub_key = f"{symbol}_{granularity.value}"
        
        async with self._lock:
            # Create subscription if it doesn't exist
            if sub_key not in self.subscriptions:
                self.subscriptions[sub_key] = Subscription(
                    symbol=symbol,
                    granularity=granularity
                )
                self.candle_builders[sub_key] = CandleBuilder(symbol, granularity)
                
                # Load historical data
                try:
                    candles = await self._fetch_historical_candles(symbol, granularity, count=100)
                    self.candle_builders[sub_key].candle_history = candles
                    logger.info(f"Loaded {len(candles)} historical candles for {symbol}")
                except Exception as e:
                    logger.warning(f"Failed to load historical candles for {symbol}: {e}")
                
                logger.info(f"Created new subscription for {symbol} ({granularity.value})")
            
            # Add client to subscription
            if client_id:
                self.subscriptions[sub_key].clients.add(client_id)
                await self.ws_manager.subscribe_client(client_id, symbol)
            
            # Restart stream to include new symbol
            if self._running:
                self._start_stream_task()
        
        return True
    
    async def unsubscribe_instrument(
        self,
        symbol: str,
        granularity: Union[str, Granularity] = Granularity.MINUTE_1,
        client_id: Optional[str] = None,
    ) -> bool:
        """Unsubscribe from an instrument.
        
        Args:
            symbol: Trading instrument to unsubscribe
            granularity: Candle granularity
            client_id: Optional client ID to remove from subscription
            
        Returns:
            True if unsubscription successful
        """
        if isinstance(granularity, str):
            granularity = Granularity(granularity)
        
        symbol = symbol.upper()
        sub_key = f"{symbol}_{granularity.value}"
        
        async with self._lock:
            if sub_key not in self.subscriptions:
                return False
            
            subscription = self.subscriptions[sub_key]
            
            # Remove specific client
            if client_id:
                subscription.clients.discard(client_id)
                await self.ws_manager.unsubscribe_client(client_id, symbol)
                logger.debug(f"Removed client {client_id} from {symbol}")
            
            # Remove subscription if no clients remain
            if not subscription.is_active and not client_id:
                # Close any open candle
                if sub_key in self.candle_builders:
                    await self.candle_builders[sub_key].force_close()
                    del self.candle_builders[sub_key]
                
                del self.subscriptions[sub_key]
                logger.info(f"Removed subscription for {symbol}")
                
                # Restart stream to exclude symbol
                if self._running:
                    self._start_stream_task()
        
        return True
    
    def get_subscriptions(self) -> Dict[str, Subscription]:
        """Get all active subscriptions."""
        return self.subscriptions.copy()
    
    def get_subscribed_symbols(self) -> List[str]:
        """Get list of all subscribed symbols."""
        return list(set(sub.symbol for sub in self.subscriptions.values()))
    
    # -------------------------------------------------------------------------
    # Streaming Loop
    # -------------------------------------------------------------------------
    
    async def _stream_loop(self) -> None:
        """Main streaming loop with automatic reconnection."""
        while self._running and not self._shutdown_event.is_set():
            try:
                await self._connect_and_stream()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.metrics.errors_count += 1
                logger.error(f"Stream error: {e}")
                
                # Exponential backoff
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2,
                    self.max_reconnect_delay
                )
                self.metrics.reconnect_count += 1
    
    async def _connect_and_stream(self) -> None:
        """Connect to OANDA streaming API and process messages."""
        symbols = self.get_subscribed_symbols()
        
        if not symbols:
            logger.debug("No symbols to stream, waiting...")
            await asyncio.sleep(5)
            return
        
        logger.info(f"Connecting to OANDA stream for symbols: {symbols}")
        
        try:
            # Create pricing stream request
            params = {"instruments": ",".join(symbols)}
            request = self._pricing_stream_class(
                accountID=self.account_id,
                params=params
            )
            
            # Start the stream
            stream = self.api_client.request(request)
            
            # Reset reconnect delay on successful connection
            self._reconnect_delay = DEFAULT_RECONNECT_DELAY
            
            # Process stream messages
            for message in stream:
                if not self._running or self._shutdown_event.is_set():
                    break
                
                try:
                    await self._process_stream_message(message)
                except Exception as e:
                    logger.warning(f"Error processing message: {e}")
                    self.metrics.errors_count += 1
                
                # Small yield to prevent blocking
                await asyncio.sleep(0)
        
        except Exception as e:
            logger.error(f"Stream connection error: {e}")
            raise OandaConnectionError(f"Stream connection failed: {e}")
    
    async def _process_stream_message(self, message: Dict[str, Any]) -> None:
        """Process a message from the OANDA stream.
        
        Args:
            message: Raw message from OANDA stream
        """
        msg_type = message.get("type")
        
        if msg_type == "PRICE":
            await self._handle_price_message(message)
        elif msg_type == "HEARTBEAT":
            logger.debug("Received heartbeat")
        else:
            logger.debug(f"Received message type: {msg_type}")
    
    async def _handle_price_message(self, message: Dict[str, Any]) -> None:
        """Handle a price tick message.
        
        Args:
            message: PRICE message from OANDA
        """
        tick = PriceTick.from_oanda_response(message)
        if not tick:
            return
        
        self.metrics.ticks_received += 1
        self.metrics.last_tick_time = datetime.now(timezone.utc)
        
        symbol = tick.symbol
        
        # Update all subscriptions for this symbol
        for sub_key, subscription in self.subscriptions.items():
            if subscription.symbol == symbol:
                # Process tick in candle builder
                builder = self.candle_builders.get(sub_key)
                if builder:
                    closed_candle = await builder.process_tick(tick)
                    
                    if closed_candle:
                        self.metrics.candles_closed += 1
                        await self._on_candle_closed(symbol, subscription.granularity, closed_candle)
                
                # Update subscription state
                subscription.last_tick = tick
                subscription.last_activity = datetime.now(timezone.utc)
        
        # Notify tick callbacks
        for callback in self._tick_callbacks:
            try:
                await callback(symbol, tick)
            except Exception as e:
                logger.warning(f"Tick callback error: {e}")
        
        # Broadcast to WebSocket clients
        await self.ws_manager.broadcast({
            "type": "tick",
            "symbol": symbol,
            "data": {
                "time": tick.time.isoformat(),
                "bid": tick.bid,
                "ask": tick.ask,
                "mid": tick.mid,
            }
        }, symbol=symbol)
    
    async def _on_candle_closed(
        self,
        symbol: str,
        granularity: Granularity,
        candle: OHLCV
    ) -> None:
        """Handle a closed candle event.
        
        Args:
            symbol: Trading instrument
            granularity: Candle granularity
            candle: Closed OHLCV candle
        """
        logger.debug(f"Candle closed: {symbol} {granularity.value} @ {candle.close}")
        
        sub_key = f"{symbol}_{granularity.value}"
        
        # Calculate indicators if configured
        if sub_key in self.subscriptions:
            subscription = self.subscriptions[sub_key]
            await self._update_indicators(subscription)
        
        # Notify candle callbacks
        for callback in self._candle_callbacks:
            try:
                await callback(symbol, candle)
            except Exception as e:
                logger.warning(f"Candle callback error: {e}")
        
        # Broadcast to WebSocket clients
        await self.ws_manager.broadcast({
            "type": "candle",
            "symbol": symbol,
            "granularity": granularity.value,
            "data": candle.to_dict()
        }, symbol=symbol)
    
    # -------------------------------------------------------------------------
    # Health Check
    # -------------------------------------------------------------------------
    
    async def _health_check_loop(self) -> None:
        """Periodic health check for connections."""
        while self._running and not self._shutdown_event.is_set():
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=STREAM_HEARTBEAT_INTERVAL
                )
            except asyncio.TimeoutError:
                await self._perform_health_check()
    
    async def _perform_health_check(self) -> None:
        """Check stream health and reconnect if necessary."""
        if not self.metrics.last_tick_time:
            return
        
        time_since_last_tick = (
            datetime.now(timezone.utc) - self.metrics.last_tick_time
        ).total_seconds()
        
        # If no ticks for 60 seconds, there might be an issue
        if time_since_last_tick > 60:
            logger.warning(f"No ticks received for {time_since_last_tick:.0f}s")
            
            # Restart stream if needed
            if self._stream_task and self._stream_task.done():
                logger.info("Restarting stream task")
                self._start_stream_task()
    
    # -------------------------------------------------------------------------
    # Historical Data
    # -------------------------------------------------------------------------
    
    async def get_candles(
        self,
        symbol: str,
        granularity: Union[str, Granularity],
        count: int = 500,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
    ) -> List[OHLCV]:
        """Fetch historical candles from OANDA REST API.
        
        Args:
            symbol: Trading instrument (e.g., "EUR_USD")
            granularity: Candle granularity
            count: Number of candles to fetch (max 5000)
            from_time: Start time (optional)
            to_time: End time (optional)
            
        Returns:
            List of OHLCV candles
            
        Raises:
            OandaConnectionError: If API request fails
        """
        return await self._fetch_historical_candles(
            symbol, granularity, count, from_time, to_time
        )
    
    async def _fetch_historical_candles(
        self,
        symbol: str,
        granularity: Union[str, Granularity],
        count: int = 500,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
    ) -> List[OHLCV]:
        """Internal method to fetch historical candles."""
        if isinstance(granularity, str):
            granularity = Granularity(granularity)
        
        symbol = symbol.upper()
        count = min(count, 5000)  # OANDA limit
        
        params: Dict[str, Any] = {
            "granularity": granularity.value,
            "count": count,
            "price": "M",  # Midpoint prices
        }
        
        if from_time:
            params["from"] = from_time.isoformat()
        if to_time:
            params["to"] = to_time.isoformat()
        
        try:
            request = self._instruments_candles_class(
                instrument=symbol,
                params=params
            )
            
            response = self.api_client.request(request)
            candles = response.get("candles", [])
            
            ohlcv_list: List[OHLCV] = []
            for c in candles:
                if c.get("complete"):
                    try:
                        mid = c.get("mid", {})
                        ohlcv = OHLCV(
                            timestamp=datetime.fromisoformat(
                                c["time"].replace("Z", "+00:00")
                            ),
                            open=float(mid.get("o", 0)),
                            high=float(mid.get("h", 0)),
                            low=float(mid.get("l", 0)),
                            close=float(mid.get("c", 0)),
                            volume=int(c.get("volume", 0)),
                            complete=c.get("complete", True)
                        )
                        ohlcv_list.append(ohlcv)
                    except (KeyError, ValueError) as e:
                        logger.debug(f"Skipping invalid candle: {e}")
                        continue
            
            logger.info(f"Fetched {len(ohlcv_list)} candles for {symbol}")
            return ohlcv_list
        
        except Exception as e:
            logger.error(f"Failed to fetch candles for {symbol}: {e}")
            raise OandaConnectionError(f"Candle fetch failed: {e}")
    
    # -------------------------------------------------------------------------
    # Indicator Calculations
    # -------------------------------------------------------------------------
    
    async def calculate_indicators_batch(
        self,
        symbol: str,
        granularity: Union[str, Granularity],
        indicators: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Pre-calculate and cache indicators server-side.
        
        Args:
            symbol: Trading instrument
            granularity: Candle granularity
            indicators: List of indicator configurations
                Each dict should have:
                - name: Indicator name (e.g., "sma", "rsi", "macd")
                - params: Indicator parameters dict
                
        Returns:
            Dictionary with indicator results
        """
        if isinstance(granularity, str):
            granularity = Granularity(granularity)
        
        sub_key = f"{symbol.upper()}_{granularity.value}"
        
        # Get candles for calculation
        if sub_key in self.candle_builders:
            candles = self.candle_builders[sub_key].get_candles(count=500)
        else:
            candles = await self.get_candles(symbol, granularity, count=500)
        
        if not candles:
            return {"error": "No data available for indicators"}
        
        # Convert to pandas for calculation
        df = pd.DataFrame([
            {
                "timestamp": c.timestamp,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in candles
        ])
        
        results: Dict[str, Any] = {
            "symbol": symbol,
            "granularity": granularity.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "indicators": {}
        }
        
        for indicator_config in indicators:
            name = indicator_config.get("name", "").lower()
            params = indicator_config.get("params", {})
            
            try:
                indicator_result = self._calculate_indicator(df, name, params)
                results["indicators"][name] = indicator_result
            except Exception as e:
                results["indicators"][name] = {"error": str(e)}
        
        # Cache results in subscription
        if sub_key in self.subscriptions:
            self.subscriptions[sub_key].indicators = results["indicators"]
        
        return results
    
    def _calculate_indicator(
        self,
        df: pd.DataFrame,
        name: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calculate a single indicator.
        
        Args:
            df: DataFrame with OHLCV data
            name: Indicator name
            params: Indicator parameters
            
        Returns:
            Dictionary with indicator values
        """
        closes = df["close"].values
        
        if name == "sma":
            period = params.get("period", 20)
            values = df["close"].rolling(window=period).mean().values
            return {
                "values": [round(v, 6) if not pd.isna(v) else None for v in values],
                "period": period,
            }
        
        elif name == "ema":
            period = params.get("period", 20)
            values = df["close"].ewm(span=period, adjust=False).mean().values
            return {
                "values": [round(v, 6) if not pd.isna(v) else None for v in values],
                "period": period,
            }
        
        elif name == "rsi":
            period = params.get("period", 14)
            delta = df["close"].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            rs = gain / loss
            values = 100 - (100 / (1 + rs))
            return {
                "values": [round(v, 2) if not pd.isna(v) else None for v in values],
                "period": period,
                "overbought": params.get("overbought", 70),
                "oversold": params.get("oversold", 30),
            }
        
        elif name == "macd":
            fast = params.get("fast", 12)
            slow = params.get("slow", 26)
            signal = params.get("signal", 9)
            
            ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
            ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
            macd_line = ema_fast - ema_slow
            signal_line = macd_line.ewm(span=signal, adjust=False).mean()
            histogram = macd_line - signal_line
            
            return {
                "macd": [round(v, 6) if not pd.isna(v) else None for v in macd_line.values],
                "signal": [round(v, 6) if not pd.isna(v) else None for v in signal_line.values],
                "histogram": [round(v, 6) if not pd.isna(v) else None for v in histogram.values],
                "fast": fast,
                "slow": slow,
                "signal_period": signal,
            }
        
        elif name == "bollinger":
            period = params.get("period", 20)
            std_dev = params.get("stdDev", 2.0)
            
            sma = df["close"].rolling(window=period).mean()
            std = df["close"].rolling(window=period).std()
            upper = sma + (std * std_dev)
            lower = sma - (std * std_dev)
            
            return {
                "upper": [round(v, 6) if not pd.isna(v) else None for v in upper.values],
                "middle": [round(v, 6) if not pd.isna(v) else None for v in sma.values],
                "lower": [round(v, 6) if not pd.isna(v) else None for v in lower.values],
                "period": period,
                "stdDev": std_dev,
            }
        
        elif name == "atr":
            period = params.get("period", 14)
            high_low = df["high"] - df["low"]
            high_close = np.abs(df["high"] - df["close"].shift())
            low_close = np.abs(df["low"] - df["close"].shift())
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            values = tr.rolling(window=period).mean()
            
            return {
                "values": [round(v, 6) if not pd.isna(v) else None for v in values.values],
                "period": period,
            }
        
        else:
            return {"error": f"Indicator '{name}' not supported"}
    
    async def _update_indicators(self, subscription: Subscription) -> None:
        """Update cached indicators for a subscription."""
        # This is a placeholder for automatic indicator updates
        # Could be implemented to recalculate on each new candle
        pass
    
    # -------------------------------------------------------------------------
    # WebSocket Handler
    # -------------------------------------------------------------------------
    
    async def handle_websocket(self, websocket: Any, client_id: Optional[str] = None) -> None:
        """Handle a WebSocket connection.
        
        This method should be called from a FastAPI WebSocket endpoint.
        It manages the client lifecycle and handles incoming messages.
        
        Args:
            websocket: FastAPI WebSocket object
            client_id: Optional client identifier (auto-generated if not provided)
        """
        import uuid
        
        client_id = client_id or str(uuid.uuid4())[:8]
        
        try:
            # Accept connection
            if hasattr(websocket, "accept"):
                await websocket.accept()
            
            await self.ws_manager.connect(client_id, websocket)
            
            # Send welcome message
            await websocket.send_json({
                "type": "connected",
                "client_id": client_id,
                "message": "Connected to OANDA stream"
            })
            
            # Handle incoming messages
            while self._running:
                try:
                    # Receive message with timeout
                    if hasattr(websocket, "receive_json"):
                        message = await asyncio.wait_for(
                            websocket.receive_json(),
                            timeout=30.0
                        )
                    else:
                        raw = await asyncio.wait_for(
                            websocket.receive_text(),
                            timeout=30.0
                        )
                        message = json.loads(raw)
                    
                    await self._handle_client_message(client_id, message, websocket)
                
                except asyncio.TimeoutError:
                    # Send ping to keep connection alive
                    await websocket.send_json({"type": "ping"})
                
                except Exception as e:
                    logger.warning(f"WebSocket message error for {client_id}: {e}")
                    break
        
        except Exception as e:
            logger.error(f"WebSocket error for {client_id}: {e}")
        
        finally:
            # Cleanup
            await self.ws_manager.disconnect(client_id)
            
            # Unsubscribe from all symbols
            symbols = self.ws_manager.get_subscribed_symbols(client_id)
            for symbol in symbols:
                await self.unsubscribe_instrument(symbol, client_id=client_id)
    
    async def _handle_client_message(
        self,
        client_id: str,
        message: Dict[str, Any],
        websocket: Any
    ) -> None:
        """Handle a message from a WebSocket client.
        
        Args:
            client_id: Client identifier
            message: Message from client
            websocket: WebSocket object for responses
        """
        msg_type = message.get("type", "").lower()
        
        if msg_type == "subscribe":
            symbol = message.get("symbol", "").upper()
            granularity = message.get("granularity", "M1")
            
            if symbol:
                await self.subscribe_instrument(symbol, granularity, client_id)
                await websocket.send_json({
                    "type": "subscribed",
                    "symbol": symbol,
                    "granularity": granularity
                })
                
                # Send current candles
                sub_key = f"{symbol}_{granularity}"
                if sub_key in self.candle_builders:
                    candles = self.candle_builders[sub_key].get_candles(count=100)
                    await websocket.send_json({
                        "type": "history",
                        "symbol": symbol,
                        "granularity": granularity,
                        "candles": [c.to_dict() for c in candles]
                    })
        
        elif msg_type == "unsubscribe":
            symbol = message.get("symbol", "").upper()
            granularity = message.get("granularity", "M1")
            
            if symbol:
                await self.unsubscribe_instrument(symbol, granularity, client_id)
                await websocket.send_json({
                    "type": "unsubscribed",
                    "symbol": symbol,
                    "granularity": granularity
                })
        
        elif msg_type == "get_candles":
            symbol = message.get("symbol", "").upper()
            granularity = message.get("granularity", "M1")
            count = message.get("count", 100)
            
            if symbol:
                try:
                    candles = await self.get_candles(symbol, granularity, count)
                    await websocket.send_json({
                        "type": "candles",
                        "symbol": symbol,
                        "granularity": granularity,
                        "candles": [c.to_dict() for c in candles]
                    })
                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Failed to get candles: {e}"
                    })
        
        elif msg_type == "get_indicators":
            symbol = message.get("symbol", "").upper()
            granularity = message.get("granularity", "M1")
            indicators = message.get("indicators", [])
            
            if symbol and indicators:
                try:
                    results = await self.calculate_indicators_batch(
                        symbol, granularity, indicators
                    )
                    await websocket.send_json({
                        "type": "indicators",
                        "symbol": symbol,
                        "granularity": granularity,
                        "data": results
                    })
                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Failed to calculate indicators: {e}"
                    })
        
        elif msg_type == "ping":
            await websocket.send_json({"type": "pong"})
        
        elif msg_type == "get_metrics":
            await websocket.send_json({
                "type": "metrics",
                "data": self.metrics.to_dict()
            })
        
        elif msg_type == "get_subscriptions":
            subs = [
                {
                    "symbol": sub.symbol,
                    "granularity": sub.granularity.value,
                    "clients": sub.client_count
                }
                for sub in self.subscriptions.values()
            ]
            await websocket.send_json({
                "type": "subscriptions",
                "data": subs
            })
        
        else:
            await websocket.send_json({
                "type": "error",
                "message": f"Unknown message type: {msg_type}"
            })
    
    # -------------------------------------------------------------------------
    # Event Callbacks
    # -------------------------------------------------------------------------
    
    def on_candle(self, callback: Callable[[str, OHLCV], Coroutine]) -> None:
        """Register a callback for candle close events.
        
        Args:
            callback: Async function(symbol: str, candle: OHLCV) -> None
        """
        self._candle_callbacks.append(callback)
    
    def on_tick(self, callback: Callable[[str, PriceTick], Coroutine]) -> None:
        """Register a callback for tick events.
        
        Args:
            callback: Async function(symbol: str, tick: PriceTick) -> None
        """
        self._tick_callbacks.append(callback)
    
    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current stream metrics."""
        return self.metrics.to_dict()
    
    def get_candle_cache(
        self,
        symbol: str,
        granularity: Union[str, Granularity]
    ) -> List[OHLCV]:
        """Get cached candles for a symbol.
        
        Args:
            symbol: Trading instrument
            granularity: Candle granularity
            
        Returns:
            List of cached OHLCV candles
        """
        if isinstance(granularity, str):
            granularity = Granularity(granularity)
        
        sub_key = f"{symbol.upper()}_{granularity.value}"
        
        if sub_key in self.candle_builders:
            return self.candle_builders[sub_key].get_candles()
        return []
    
    async def get_current_price(self, symbol: str) -> Optional[PriceTick]:
        """Get the most recent price for a symbol.
        
        Args:
            symbol: Trading instrument
            
        Returns:
            Latest PriceTick or None if not available
        """
        symbol = symbol.upper()
        
        for sub in self.subscriptions.values():
            if sub.symbol == symbol and sub.last_tick:
                return sub.last_tick
        
        return None


# -----------------------------------------------------------------------------
# Singleton Instance
# -----------------------------------------------------------------------------

_stream_manager_instance: Optional[OandaStreamManager] = None


def get_stream_manager() -> Optional[OandaStreamManager]:
    """Get the singleton stream manager instance.
    
    Returns:
        OandaStreamManager instance or None if not initialized
    """
    global _stream_manager_instance
    return _stream_manager_instance


def init_stream_manager(
    api_key: Optional[str] = None,
    account_id: Optional[str] = None,
    environment: str = "practice"
) -> OandaStreamManager:
    """Initialize the singleton stream manager.
    
    Args:
        api_key: OANDA API key (from env if not provided)
        account_id: OANDA account ID (from env if not provided)
        environment: "practice" or "live"
        
    Returns:
        Initialized OandaStreamManager instance
    """
    global _stream_manager_instance
    
    if _stream_manager_instance is None:
        if api_key and account_id:
            _stream_manager_instance = OandaStreamManager(
                api_key=api_key,
                account_id=account_id,
                environment=environment
            )
        else:
            _stream_manager_instance = OandaStreamManager.from_env()
    
    return _stream_manager_instance


async def shutdown_stream_manager() -> None:
    """Shutdown the singleton stream manager."""
    global _stream_manager_instance
    
    if _stream_manager_instance:
        await _stream_manager_instance.stop()
        _stream_manager_instance = None


# -----------------------------------------------------------------------------
# FastAPI Integration Helper
# -----------------------------------------------------------------------------

async def oanda_websocket_endpoint(websocket: Any, client_id: Optional[str] = None) -> None:
    """FastAPI WebSocket endpoint handler.
    
    Usage in FastAPI:
        >>> from fastapi import FastAPI, WebSocket
        >>> from layer5.services.oanda_stream_service import oanda_websocket_endpoint
        >>> 
        >>> app = FastAPI()
        >>> 
        >>> @app.websocket("/ws/chart/oanda-stream")
        >>> async def oanda_stream(websocket: WebSocket):
        >>>     await oanda_websocket_endpoint(websocket)
    
    Args:
        websocket: FastAPI WebSocket object
        client_id: Optional client identifier
    """
    manager = get_stream_manager()
    
    if manager is None:
        try:
            manager = init_stream_manager()
            await manager.start()
        except Exception as e:
            await websocket.accept()
            await websocket.send_json({
                "type": "error",
                "message": f"Failed to initialize stream manager: {e}"
            })
            await websocket.close()
            return
    
    await manager.handle_websocket(websocket, client_id)
