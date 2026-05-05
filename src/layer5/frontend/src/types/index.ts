// Layer 5 Dashboard - Type Definitions

export type ViewType = 'overview' | 'charts' | 'risk' | 'regimes' | 'model' | 'trades' | 'strategies' | 'assets' | 'alerts';

export type Theme = 'dark' | 'light' | 'system';

export type TradeStatus = 'approved' | 'vetoed' | 'pending' | 'executed' | 'closed';
export type TradeOutcome = 'win' | 'loss' | 'breakeven' | 'open';
export type StrategyStatus = 'active' | 'paused' | 'archived';
export type RegimeType = 'Trending_HighVol' | 'Trending_LowVol' | 'Ranging_HighVol' | 'Ranging_LowVol';

export interface KPIData {
  totalSignals: number;
  approvalRate: number;
  avgConfidence: number;
  livePositions: number;
  openTrades?: number;
  unrealizedPnL: number;
  positionSource?: 'oanda' | 'system';
  winRate24h: number;
  sharpeRatio: number;
  maxDrawdown: number;
  sortinoRatio: number;
  calmarRatio: number;
}

export interface OpenPosition {
  instrument: string;
  side: 'long' | 'short';
  units: number;
  avgPrice: number;
  unrealizedPnl: number;
  tradeIds: string[];
  source: 'oanda' | 'system';
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

export interface OHLCData {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface IndicatorResult {
  indicator: string;
  name?: string;
  timestamps?: string[];
  values: (number | null)[];
  signal?: (number | null)[];
  histogram?: (number | null)[];
  upper?: (number | null)[];
  middle?: (number | null)[];
  lower?: (number | null)[];
  k?: (number | null)[];
  d?: (number | null)[];
  plus_di?: (number | null)[];
  minus_di?: (number | null)[];
  overbought?: number;
  oversold?: number;
  error?: string;
}

export interface IndicatorInfo {
  id: string;
  name: string;
  category: 'trend' | 'momentum' | 'volatility' | 'volume';
  defaultParams: Record<string, number>;
}

export interface ActiveIndicator extends IndicatorInfo {
  instanceId: string;
  params: Record<string, number>;
}

export type AlertType = 'price' | 'indicator' | 'pattern' | 'volume';
export type AlertCondition = 'above' | 'below' | 'crosses_above' | 'crosses_below' | 'equals';
export type AlertStatus = 'active' | 'triggered' | 'paused' | 'expired';

export interface AlertConfig {
  id?: string;
  name: string;
  type: AlertType;
  symbol: string;
  condition: AlertCondition;
  value: number;
  timeframe?: string;
  message?: string;
  created_at?: string;
  expires_at?: string;
  status: AlertStatus;
  triggered_at?: string;
  triggered_price?: number;
}

export interface WatchlistItem {
  symbol: string;
  name: string;
  price: number;
  change24h: number;
  change24hPct: number;
  volume: number;
  high24h: number;
  low24h: number;
  regime: string;
  atr: number;
  isFavorite?: boolean;
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

// ---------------------------------------------------------------------------
// Strategy Overlay Types
// ---------------------------------------------------------------------------
export interface StrategyOverlayEntry {
  timestamp: string;
  signal: 1 | -1; // long | short
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  confidence: number; // 0-1, controls opacity/boldness
  regime: string;
}

export type StrategyOverlayExitReason = 'sl_hit' | 'tp_hit' | 'timeout' | 'manual';

export interface StrategyOverlayTrade {
  entry: StrategyOverlayEntry;
  exit_price: number;
  exit_reason: StrategyOverlayExitReason;
  pnl: number;
  pips_gained: number;
  r_multiple: number;
  exit_timestamp: string;
}

export interface StrategyOverlayResponse {
  entries: StrategyOverlayEntry[];
  trades: StrategyOverlayTrade[];
  win_rate: number;
  total_trades: number;
  wins: number;
  losses: number;
}

// =============================================================================
// Advanced Chart Types
// =============================================================================

export type Granularity = '1m' | '5m' | '15m' | '30m' | '1h' | '2h' | '4h' | '6h' | '8h' | '12h' | '1d' | '1w' | '1M';
export type ChartType = 'candlestick' | 'bar' | 'line';
export type DataSource = 'oanda' | 'database';
export type AnalysisToolType = 'trendline' | 'fibonacci' | 'horizontal' | 'ray' | 'rectangle' | 'text';

export const AnalysisTool = {
  TRENDLINE: 'trendline',
  SUPPORT_RESISTANCE: 'sr',
  FIBONACCI: 'fibonacci',
  PATTERN_DETECTION: 'patterns',
  DIVERGENCE: 'divergence',
  ORDER_BLOCKS: 'order_blocks',
  VOLUME_ANALYSIS: 'volume',
  CORRELATION: 'correlation',
  MTF_ANALYSIS: 'mtf',
} as const;

export type AnalysisTool = typeof AnalysisTool[keyof typeof AnalysisTool];

export interface StrategyEntry {
  timestamp: Date;
  signal: 1 | -1; // long | short
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  confidence: number; // 0-1, controls opacity/boldness
  regime: string;
}

export type ExitReason = 'sl_hit' | 'tp_hit' | 'timeout' | 'manual';

export interface TradeResult {
  entry: StrategyEntry;
  exit_price: number;
  exit_reason: ExitReason;
  pnl: number;
  pips_gained: number;
  r_multiple: number;
  exit_timestamp: Date;
}

export interface SupportResistanceLevel {
  price: number;
  strength: number; // 0-1
  type: 'support' | 'resistance';
  touches: number;
}

export interface VolumeProfileRow {
  price: number;
  volume: number;
  priceRange: { min: number; max: number };
}

export interface VolumeProfileData {
  rows: VolumeProfileRow[];
  vpoc: number; // Volume Point of Control
  valueAreaHigh: number;
  valueAreaLow: number;
  totalVolume: number;
}

export interface IndicatorSubpanelConfig {
  id: string;
  name: string;
  height?: number;
  collapsible?: boolean;
  defaultCollapsed?: boolean;
}

export interface AdvancedChartProps {
  // Data binding
  symbol: string;
  timeframe: Granularity;
  dataSource?: DataSource;

  // Data
  data: OHLCData[];
  isLoading?: boolean;

  // Indicators
  activeIndicators?: ExtendedIndicatorData[];
  subpanelConfigs?: IndicatorSubpanelConfig[];

  // Overlays
  showStrategy?: boolean;
  strategyName?: string;
  strategyTrades?: TradeResult[];
  showLiveTradeLines?: boolean;
  liveTradeLines?: TradeLine[];
  showSupportResistance?: boolean;
  supportResistanceLevels?: SupportResistanceLevel[];
  showVolumeProfile?: boolean;
  volumeProfileData?: VolumeProfileData;

  // Asset filtering
  correlatedAssets?: ChartCorrelatedAsset[];
  hideWeakCorrelations?: boolean;
  minCorrelation?: number;

  // Analysis mode
  analysisTools?: AnalysisTool[];

  // Appearance
  height?: number;
  className?: string;
  showToolbar?: boolean;
  allowFullscreen?: boolean;
  showLegend?: boolean;

  // Callbacks
  onTimeframeChange?: (timeframe: Granularity) => void;
  onSymbolChange?: (symbol: string) => void;
  onIndicatorChange?: (indicators: ExtendedIndicatorData[]) => void;
  onRangeChange?: (from: Date, to: Date) => void;
  onChartTypeChange?: (type: ChartType) => void;
  onAnalysisToolAdd?: (tool: AnalysisTool) => void;
  onAnalysisToolRemove?: (id: string) => void;

  // Options
  availableSymbols?: string[];
  availableTimeframes?: Granularity[];
}

export interface ExtendedIndicatorData {
  id: string;
  name: string;
  params: Record<string, number>;
  color: string;
  subpanel?: boolean;
  category?: 'trend' | 'momentum' | 'volatility' | 'volume';
  // Data fields
  values?: (number | null)[];
  upper?: (number | null)[];
  middle?: (number | null)[];
  lower?: (number | null)[];
  signal?: (number | null)[];
  histogram?: (number | null)[];
  timestamps?: string[];
  minValue?: number;
  maxValue?: number;
}

export interface ChartCorrelatedAsset {
  symbol: string;
  correlation: number;
  data: { timestamp: string; close: number }[];
  color: string;
  strength?: 'strong_positive' | 'moderate_positive' | 'weak' | 'moderate_negative' | 'strong_negative';
  slope?: 'converging' | 'diverging';
}

export interface TradeLine {
  id: string;
  type: 'entry' | 'sl' | 'tp';
  price: number;
  time: number;
  label?: string;
  color?: string;
}

// WebSocket Types
export interface OandaTick {
  instrument: string;
  time: string;
  bid: number;
  ask: number;
  mid: number;
}

export interface OandaCandle {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  complete: boolean;
}

export interface WebSocketMessage {
  type: 'tick' | 'candle' | 'heartbeat' | 'error';
  data: OandaTick | OandaCandle | Record<string, unknown>;
}

// Analysis API Types
export interface AnalysisMetrics {
  symbol: string;
  timeframe: string;
  trend: {
    direction: 'up' | 'down' | 'sideways';
    strength: number;
    adx: number;
  };
  volatility: {
    current: number;
    atr: number;
    percentile: number;
  };
  volume: {
    current: number;
    average: number;
    trend: 'increasing' | 'decreasing' | 'stable';
  };
  momentum: {
    rsi: number;
    macd: number;
    signal: number;
  };
}

export interface MultiTimeframeData {
  symbol: string;
  timeframes: Record<string, {
    trend: 'bullish' | 'bearish' | 'neutral';
    signal: 'buy' | 'sell' | 'hold';
    strength: number;
  }>;
  alignment: number; // -1 to 1
  recommendation: string;
}
