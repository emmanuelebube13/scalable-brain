// Layer 5 Dashboard - Type Definitions

export type ViewType = 'overview' | 'risk' | 'regimes' | 'model' | 'trades' | 'strategies' | 'assets';

export type TradeStatus = 'approved' | 'vetoed' | 'pending' | 'executed' | 'closed';
export type TradeOutcome = 'win' | 'loss' | 'breakeven' | 'open';
export type StrategyStatus = 'active' | 'paused' | 'archived';
export type RegimeType = 'Trending_HighVol' | 'Trending_LowVol' | 'Ranging_HighVol' | 'Ranging_LowVol';

export interface KPIData {
  totalSignals: number;
  approvalRate: number;
  avgConfidence: number;
  livePositions: number;
  unrealizedPnL: number;
  winRate24h: number;
  sharpeRatio: number;
  maxDrawdown: number;
  sortinoRatio: number;
  calmarRatio: number;
}

export interface Trade {
  id: string;
  timestamp: Date;
  asset: string;
  strategy: string;
  entryPrice: number;
  exitPrice?: number;
  stopLoss: number;
  takeProfit: number;
  regime: RegimeType;
  confidence: number;
  status: TradeStatus;
  reason?: string;
  pnl?: number;
  slippage?: number;
  holdDuration?: string;
  outcome?: TradeOutcome;
  signalValue: 1 | -1;
  vetoReason?: string;
  // Forensics
  forensics?: TradeForensics;
}

export interface TradeForensics {
  marketContext: {
    atr: number;
    adx: number;
    nearestSupport: number;
    nearestResistance: number;
  };
  technicalSetup: string;
  mlReasoning: {
    confidenceBreakdown: Record<string, number>;
    regimeMatch: boolean;
  };
  execution: {
    brokerFillPrice: number;
    slippagePips: number;
    fillTime: Date;
  };
  exit: {
    reason: 'sl_hit' | 'tp_hit' | 'time_decay' | 'manual' | 'open';
    details: string;
  };
  pnlBreakdown: {
    gross: number;
    commission: number;
    slippage: number;
    net: number;
  };
}

export interface Signal {
  id: string;
  timestamp: Date;
  asset: string;
  strategy: string;
  signalValue: 1 | -1;
  confidence: number;
  regime: RegimeType;
  status: 'pending' | 'approved' | 'vetoed';
}

export interface RegimeData {
  asset: string;
  currentRegime: RegimeType;
  duration: string;
  atr: number;
  atr14DayAvg: number;
  adx: number;
  transitions: RegimeTransition[];
}

export interface RegimeTransition {
  timestamp: Date;
  from: RegimeType;
  to: RegimeType;
}

export interface RegimePerformance {
  regime: RegimeType;
  signalCount: number;
  approvalRate: number;
  winRate: number;
  avgExpectancyR: number;
  avgHold: string;
}

export interface RiskMetrics {
  netNotionalExposure: number;
  maxDrawdown: number;
  maxDrawdownDate: Date;
  maxConsecutiveLoss: number;
  correlationRiskScore: number;
  concentrationAlert: string;
  exposureByAsset: AssetExposure[];
  correlationMatrix: CorrelationData[];
  underwaterData: UnderwaterPoint[];
}

export interface AssetExposure {
  asset: string;
  long: number;
  short: number;
  net: number;
}

export interface CorrelationData {
  asset1: string;
  asset2: string;
  correlation: number;
}

export interface UnderwaterPoint {
  date: Date;
  drawdown: number;
}

export interface LimitStatus {
  name: string;
  limit: number;
  current: number;
  unit: string;
}

export interface ModelMetadata {
  modelName: string;
  trainingDate: Date;
  trainingDataSize: number;
  trainingDataRange: { start: Date; end: Date };
  threshold: number;
  supportedGranularities: string[];
  version: string;
}

export interface ModelPerformance {
  metric: string;
  training: number;
  live7d: number;
  live30d: number;
}

export interface CalibrationPoint {
  predicted: number;
  actual: number;
  count: number;
}

export interface FeatureImportance {
  feature: string;
  importance: number;
}

export interface DriftAlert {
  type: 'approval_rate' | 'calibration' | 'distribution';
  message: string;
  severity: 'warning' | 'critical';
  timestamp: Date;
}

export interface Strategy {
  id: string;
  name: string;
  description: string;
  winRate: number;
  expectancyR: number;
  profitFactor: number;
  totalSignals: number;
  approvalRate: number;
  status: StrategyStatus;
  equityCurve: EquityPoint[];
  winLossByGranularity: Record<string, { wins: number; losses: number }>;
  bestTrade: Trade;
  worstTrade: Trade;
  correlationWithOthers: Record<string, number>;
}

export interface EquityPoint {
  date: Date;
  equity: number;
}

export interface Asset {
  id: string;
  symbol: string;
  name: string;
  currentPrice: number;
  change24h: number;
  change24hPct: number;
  currentRegime: RegimeType;
  regimeDuration: string;
  atr: number;
  atr14DayAvg: number;
  openPositions: number;
  winRate: number;
  correlationToPortfolio: number;
  maxDrawdown: number;
  priceHistory: PricePoint[];
  signals: Signal[];
  correlationToOthers: Record<string, number>;
}

export interface PricePoint {
  timestamp: Date;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface ApprovalTrendPoint {
  date: Date;
  approvalRate: number;
  signalCount: number;
}

export interface PerformanceAttribution {
  layer: string;
  contribution: number;
}

export interface TimeOfDayHeatmap {
  hour: number;
  wins: number;
  losses: number;
  winRate: number;
}

export interface ConfidenceDecile {
  decile: number;
  minConfidence: number;
  maxConfidence: number;
  winRate: number;
  tradeCount: number;
  expectancy: number;
}
