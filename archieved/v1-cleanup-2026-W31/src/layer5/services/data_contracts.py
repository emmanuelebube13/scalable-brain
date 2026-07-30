"""Pydantic data contracts for Layer 5 API.

These models mirror the TypeScript interfaces in
frontend/src/types/index.ts so the React UI and Python backend
stay in sync.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Shared enums / literals
# ---------------------------------------------------------------------------
TradeStatus = Literal["approved", "vetoed", "pending", "executed", "closed"]
TradeOutcome = Literal["win", "loss", "breakeven", "open"]
StrategyStatus = Literal["active", "paused", "archived"]
RegimeType = Literal[
    "Trending_HighVol",
    "Trending_LowVol",
    "Ranging_HighVol",
    "Ranging_LowVol",
]
AlertType = Literal["price", "indicator", "pattern", "volume"]
AlertCondition = Literal["above", "below", "crosses_above", "crosses_below", "equals"]
AlertStatus = Literal["active", "triggered", "paused", "expired"]
IndicatorCategory = Literal["trend", "momentum", "volatility", "volume", "trend_strength"]


# ---------------------------------------------------------------------------
# KPI
# ---------------------------------------------------------------------------
class KPIData(BaseModel):
    totalSignals: int
    approvalRate: float
    avgConfidence: float
    livePositions: int
    openTrades: Optional[int] = None
    unrealizedPnL: float
    positionSource: Literal["oanda", "system"] = "system"
    winRate24h: float
    sharpeRatio: float
    maxDrawdown: float
    sortinoRatio: float
    calmarRatio: float


class OpenPosition(BaseModel):
    instrument: str
    side: Literal["long", "short"]
    units: int
    avgPrice: float
    unrealizedPnl: float
    tradeIds: List[str] = Field(default_factory=list)
    source: Literal["oanda", "system"] = "system"


# ---------------------------------------------------------------------------
# Trades & Forensics
# ---------------------------------------------------------------------------
class TradeForensics(BaseModel):
    marketContext: Dict[str, float]
    technicalSetup: str
    mlReasoning: Dict[str, Any]
    execution: Dict[str, Any]
    exit: Dict[str, Any]
    pnlBreakdown: Dict[str, float]


class Trade(BaseModel):
    id: str
    timestamp: datetime
    asset: str
    strategy: str
    entryPrice: float
    exitPrice: Optional[float] = None
    stopLoss: float
    takeProfit: float
    regime: RegimeType
    confidence: float
    status: TradeStatus
    reason: Optional[str] = None
    pnl: Optional[float] = None
    slippage: Optional[float] = None
    holdDuration: Optional[str] = None
    outcome: Optional[TradeOutcome] = None
    signalValue: Literal[1, -1]
    vetoReason: Optional[str] = None
    forensics: Optional[TradeForensics] = None


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------
class Signal(BaseModel):
    id: str
    timestamp: datetime
    asset: str
    strategy: str
    signalValue: Literal[1, -1]
    confidence: float
    regime: RegimeType
    status: Literal["pending", "approved", "vetoed"]


# ---------------------------------------------------------------------------
# Regimes
# ---------------------------------------------------------------------------
class RegimeTransition(BaseModel):
    timestamp: datetime
    from_: RegimeType = Field(alias="from")
    to: RegimeType

    class Config:
        populate_by_name = True


class RegimeData(BaseModel):
    asset: str
    currentRegime: RegimeType
    duration: str
    atr: float
    atr14DayAvg: float
    adx: float
    transitions: List[RegimeTransition] = Field(default_factory=list)


class RegimePerformance(BaseModel):
    regime: RegimeType
    signalCount: int
    approvalRate: float
    winRate: float
    avgExpectancyR: float
    avgHold: str


# ---------------------------------------------------------------------------
# Risk
# ---------------------------------------------------------------------------
class AssetExposure(BaseModel):
    asset: str
    long: float
    short: float
    net: float


class CorrelationData(BaseModel):
    asset1: str
    asset2: str
    correlation: float
    timestamp: Optional[datetime] = None
    period: Optional[str] = None


class UnderwaterPoint(BaseModel):
    date: datetime
    drawdown: float


class RiskMetrics(BaseModel):
    netNotionalExposure: float
    maxDrawdown: float
    maxDrawdownDate: datetime
    maxConsecutiveLoss: int
    correlationRiskScore: float
    concentrationAlert: str
    exposureByAsset: List[AssetExposure]
    correlationMatrix: List[CorrelationData]
    underwaterData: List[UnderwaterPoint]


class LimitStatus(BaseModel):
    name: str
    limit: float
    current: float
    unit: str


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
class ModelMetadata(BaseModel):
    modelName: str
    trainingDate: datetime
    trainingDataSize: int
    trainingDataRange: Dict[str, Optional[datetime]]
    threshold: float
    supportedGranularities: List[str]
    version: str


class ModelPerformance(BaseModel):
    metric: str
    training: float
    live7d: float
    live30d: float


class CalibrationPoint(BaseModel):
    predicted: float
    actual: float
    count: int


class FeatureImportance(BaseModel):
    feature: str
    importance: float


class DriftAlert(BaseModel):
    type: Literal["approval_rate", "calibration", "distribution"]
    message: str
    severity: Literal["warning", "critical"]
    timestamp: datetime


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------
class EquityPoint(BaseModel):
    date: datetime
    equity: float


class Strategy(BaseModel):
    id: str
    name: str
    description: str
    winRate: float
    expectancyR: float
    profitFactor: float
    totalSignals: int
    approvalRate: float
    status: StrategyStatus
    equityCurve: List[EquityPoint]
    winLossByGranularity: Dict[str, Dict[str, int]]
    bestTrade: Optional[Trade] = None
    worstTrade: Optional[Trade] = None
    correlationWithOthers: Dict[str, float]


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------
class PricePoint(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class Asset(BaseModel):
    id: str
    symbol: str
    name: str
    currentPrice: float
    change24h: float
    change24hPct: float
    currentRegime: RegimeType
    regimeDuration: str
    atr: float
    atr14DayAvg: float
    openPositions: int
    winRate: float
    correlationToPortfolio: float
    maxDrawdown: float
    priceHistory: List[PricePoint]
    signals: List[Signal]
    correlationToOthers: Dict[str, float]


# ---------------------------------------------------------------------------
# Chart Data
# ---------------------------------------------------------------------------
class OHLCData(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class SimplePricePoint(BaseModel):
    timestamp: datetime
    price: float


class VolumeProfilePoint(BaseModel):
    price: float
    volume: int
    priceRange: Dict[str, float]
    isVPOC: Optional[bool] = False
    bidVolume: Optional[int] = None
    askVolume: Optional[int] = None


class SymbolInfo(BaseModel):
    symbol: str
    assetId: int
    regime: RegimeType
    atr: float
    adx: float
    lastPrice: float


class MultiTimeframeData(BaseModel):
    symbol: str
    data: Dict[str, List[OHLCData]]


# ---------------------------------------------------------------------------
# Support / Resistance Levels
# ---------------------------------------------------------------------------
class SupportResistanceLevel(BaseModel):
    """Support or resistance level with metadata."""
    price: float
    type: Literal["support", "resistance"]
    strength: float = Field(ge=0.0, le=1.0, description="Strength score 0-1")
    touches: int = Field(ge=1, description="Number of times price touched this level")
    firstTouch: datetime
    lastTouch: datetime
    isActive: bool = True
    distancePct: Optional[float] = None


# ---------------------------------------------------------------------------
# Analysis Metrics
# ---------------------------------------------------------------------------
class AnalysisMetric(BaseModel):
    """Single analysis metric with value and metadata."""
    name: str
    value: float
    unit: Optional[str] = None
    description: Optional[str] = None
    timestamp: Optional[datetime] = None
    threshold: Optional[float] = None
    signal: Optional[Literal["bullish", "bearish", "neutral"]] = None


class AnalysisMetricsResponse(BaseModel):
    """Response model for analysis metrics endpoint."""
    symbol: str
    period: str
    timestamp: datetime
    metrics: List[AnalysisMetric]


# ---------------------------------------------------------------------------
# Strategy Overlay
# ---------------------------------------------------------------------------
class StrategyEntryPoint(BaseModel):
    """Strategy entry point for chart overlay."""
    timestamp: datetime
    price: float
    side: Literal["long", "short"]
    strategy: str
    confidence: float
    regime: Optional[RegimeType] = None
    stopLoss: Optional[float] = None
    takeProfit: Optional[float] = None


class StrategyTradeResult(BaseModel):
    """Completed trade result for chart overlay."""
    entryTime: datetime
    exitTime: datetime
    entryPrice: float
    exitPrice: float
    side: Literal["long", "short"]
    pnl: float
    pnlPct: float
    strategy: str
    outcome: TradeOutcome
    maxFavorableExcursion: Optional[float] = None
    maxAdverseExcursion: Optional[float] = None


class StrategyOverlayData(BaseModel):
    """Strategy overlay data for chart visualization."""
    symbol: str
    strategy: str
    timeframe: str
    entries: List[StrategyEntryPoint]
    trades: List[StrategyTradeResult]
    winRate: float
    totalTrades: int
    avgPnL: float


# ---------------------------------------------------------------------------
# Enhanced Volume Profile
# ---------------------------------------------------------------------------
class VolumeProfileVPOC(BaseModel):
    """Volume Point of Control data."""
    price: float
    volume: int
    timestamp: datetime
    profileType: Literal["session", "daily", "weekly"]


class EnhancedVolumeProfile(BaseModel):
    """Enhanced volume profile with VPOC and additional metrics."""
    symbol: str
    timeframe: str
    lookbackDays: int
    rows: int
    points: List[VolumeProfilePoint]
    vpoc: VolumeProfileVPOC
    valueAreaHigh: float
    valueAreaLow: float
    valueAreaVolume: int
    totalVolume: int
    timestamp: datetime


# ---------------------------------------------------------------------------
# Correlation Data (Enhanced)
# ---------------------------------------------------------------------------
class CorrelationMatrixRow(BaseModel):
    """Single row in correlation matrix."""
    asset: str
    correlations: Dict[str, float]


class CorrelationHeatmapData(BaseModel):
    """Correlation heatmap data for multiple assets."""
    baseAsset: str
    period: str
    timestamp: datetime
    matrix: List[CorrelationMatrixRow]
    assets: List[str]


# ---------------------------------------------------------------------------
# Technical Indicators
# ---------------------------------------------------------------------------
class IndicatorInfo(BaseModel):
    id: str
    name: str
    category: IndicatorCategory
    defaultParams: Dict[str, Any]
    description: Optional[str] = None


class IndicatorResult(BaseModel):
    indicator: str
    name: Optional[str] = None
    timestamps: Optional[List[datetime]] = None
    values: List[Optional[float]]
    params: Optional[Dict[str, Any]] = None
    signal: Optional[List[Optional[float]]] = None
    histogram: Optional[List[Optional[float]]] = None
    upper: Optional[List[Optional[float]]] = None
    middle: Optional[List[Optional[float]]] = None
    lower: Optional[List[Optional[float]]] = None
    k: Optional[List[Optional[float]]] = None
    d: Optional[List[Optional[float]]] = None
    plus_di: Optional[List[Optional[float]]] = None
    minus_di: Optional[List[Optional[float]]] = None
    overbought: Optional[float] = None
    oversold: Optional[float] = None
    error: Optional[str] = None


class IndicatorBatchRequest(BaseModel):
    """Batch calculation request."""
    indicator: str
    params: Optional[Dict[str, Any]] = None


class IndicatorMetadata(BaseModel):
    """Detailed indicator metadata."""
    id: str
    name: str
    category: IndicatorCategory
    description: str
    formula: Optional[str] = None
    interpretation: Optional[str] = None
    defaultParams: Dict[str, Any]
    paramRanges: Optional[Dict[str, Dict[str, Any]]] = None
    returnType: str
    signals: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------
class AlertConfig(BaseModel):
    id: Optional[str] = None
    name: str
    type: AlertType
    symbol: str
    condition: AlertCondition
    value: float
    timeframe: Optional[str] = "1h"
    message: Optional[str] = None
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    status: AlertStatus = "active"
    triggered_at: Optional[datetime] = None
    triggered_price: Optional[float] = None


class AlertCreateRequest(BaseModel):
    name: str
    type: AlertType = "price"
    symbol: str
    condition: AlertCondition
    value: float
    timeframe: Optional[str] = "1h"
    message: Optional[str] = None
    expires_at: Optional[datetime] = None


class AlertResponse(BaseModel):
    id: str
    name: str
    type: AlertType
    symbol: str
    condition: AlertCondition
    value: float
    timeframe: str
    message: Optional[str] = None
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    status: AlertStatus
    triggered_at: Optional[datetime] = None
    triggered_price: Optional[float] = None


class TriggeredAlert(BaseModel):
    id: str
    name: str
    type: AlertType
    symbol: str
    condition: AlertCondition
    target_value: float
    triggered_price: float
    triggered_at: datetime
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------
class StreamingStatus(BaseModel):
    """Streaming service status."""
    isConnected: bool
    isConfigured: bool
    activeSubscriptions: int
    totalMessages: int
    reconnectCount: int
    uptime: Optional[str] = None
    lastError: Optional[str] = None
    timestamp: datetime


class StreamingSubscription(BaseModel):
    """Streaming subscription info."""
    symbol: str
    granularity: str
    clientCount: int
    createdAt: datetime
    lastActivity: datetime


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------
class ApprovalTrendPoint(BaseModel):
    date: datetime
    approvalRate: float
    signalCount: int


class PerformanceAttribution(BaseModel):
    layer: str
    contribution: float


class TimeOfDayHeatmap(BaseModel):
    hour: int
    wins: int
    losses: int
    winRate: float


class ConfidenceDecile(BaseModel):
    decile: int
    minConfidence: float
    maxConfidence: float
    winRate: float
    tradeCount: int
    expectancy: float


class RealtimeUpdate(BaseModel):
    newSignal: Optional[Signal] = None
    priceUpdate: List[Dict[str, Any]]
    timestamp: datetime
