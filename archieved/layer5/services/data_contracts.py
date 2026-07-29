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


# ---------------------------------------------------------------------------
# KPI
# ---------------------------------------------------------------------------
class KPIData(BaseModel):
    totalSignals: int
    approvalRate: float
    avgConfidence: float
    livePositions: int
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
