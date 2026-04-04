// Layer 5 Dashboard - Mock Data Service
// Simulates real-time data from Layers 0-4

import type {
  KPIData,
  Trade,
  Signal,
  RegimeData,
  RegimePerformance,
  RiskMetrics,
  AssetExposure,
  CorrelationData,
  UnderwaterPoint,
  LimitStatus,
  ModelMetadata,
  ModelPerformance,
  CalibrationPoint,
  FeatureImportance,
  DriftAlert,
  Strategy,
  Asset,
  ApprovalTrendPoint,
  PerformanceAttribution,
  RegimeType,
  TimeOfDayHeatmap,
  ConfidenceDecile,
} from '@/types';

import { subDays, subHours } from 'date-fns';

// Helper functions
const random = (min: number, max: number) => Math.random() * (max - min) + min;
const randomInt = (min: number, max: number) => Math.floor(random(min, max));
const randomChoice = <T,>(arr: T[]): T => arr[Math.floor(Math.random() * arr.length)];

const ASSETS = ['EUR_USD', 'GBP_USD', 'USD_JPY', 'AUD_USD', 'USD_CAD', 'EUR_GBP', 'EUR_JPY'];
const STRATEGIES = [
  'Trend_EMA_ADX_H1',
  'Trend_EMA_ADX_H4',
  'Trend_Donchian_H1',
  'Trend_Donchian_H4',
  'Range_Bollinger_H1',
  'Range_Bollinger_H4',
  'VCP_Breakout_H1',
  'VCP_Breakout_H4',
];
const REGIMES: RegimeType[] = ['Trending_HighVol', 'Trending_LowVol', 'Ranging_HighVol', 'Ranging_LowVol'];

// Generate KPI Data
export const getKPIData = (): KPIData => ({
  totalSignals: 1247,
  approvalRate: 58.3,
  avgConfidence: 0.623,
  livePositions: 12,
  unrealizedPnL: 2847.52,
  winRate24h: 64.7,
  sharpeRatio: 1.84,
  maxDrawdown: 8.2,
  sortinoRatio: 2.41,
  calmarRatio: 1.93,
});

// Generate Live Trades
export const getLiveTrades = (count: number = 10): Trade[] => {
  const trades: Trade[] = [];
  const now = new Date();

  for (let i = 0; i < count; i++) {
    const asset = randomChoice(ASSETS);
    const strategy = randomChoice(STRATEGIES);
    const regime = randomChoice(REGIMES);
    const confidence = random(0.45, 0.92);
    const isApproved = confidence > 0.535;
    const signalValue = Math.random() > 0.5 ? 1 : -1;
    const entryPrice = random(1.05, 150.0);
    const atr = random(0.001, 0.5);
    
    const trade: Trade = {
      id: `TRD-${Date.now()}-${i}`,
      timestamp: subMinutes(now, i * 15),
      asset,
      strategy,
      entryPrice,
      stopLoss: signalValue === 1 ? entryPrice - atr * 1.5 : entryPrice + atr * 1.5,
      takeProfit: signalValue === 1 ? entryPrice + atr * 4.5 : entryPrice - atr * 4.5,
      regime,
      confidence,
      status: isApproved ? 'approved' : 'vetoed',
      signalValue,
      reason: isApproved ? 'ML approval above threshold' : 'Confidence below threshold',
      pnl: isApproved ? random(-150, 350) : undefined,
      slippage: random(-0.5, 0.5),
      holdDuration: `${randomInt(1, 48)}h ${randomInt(0, 59)}m`,
      outcome: isApproved ? randomChoice(['win', 'loss', 'win', 'win', 'loss']) : undefined,
      vetoReason: !isApproved ? 'Confidence below 0.535 threshold' : undefined,
    };

    if (isApproved && trade.outcome) {
      trade.forensics = {
        marketContext: {
          atr: atr,
          adx: random(15, 45),
          nearestSupport: entryPrice * 0.995,
          nearestResistance: entryPrice * 1.005,
        },
        technicalSetup: `${strategy} signal with ADX confirmation`,
        mlReasoning: {
          confidenceBreakdown: {
            regime_match: random(0.15, 0.35),
            technical_alignment: random(0.2, 0.4),
            historical_performance: random(0.1, 0.25),
          },
          regimeMatch: true,
        },
        execution: {
          brokerFillPrice: entryPrice + random(-0.0005, 0.0005),
          slippagePips: random(-0.3, 0.3),
          fillTime: subMinutes(now, i * 15 + 2),
        },
        exit: {
          reason: trade.outcome === 'win' ? 'tp_hit' : 'sl_hit',
          details: trade.outcome === 'win' 
            ? 'Take profit triggered after 12 hours'
            : 'Stop loss triggered due to adverse move',
        },
        pnlBreakdown: {
          gross: trade.pnl || 0,
          commission: -2.5,
          slippage: (trade.slippage || 0) * -1,
          net: (trade.pnl || 0) - 2.5 - (trade.slippage || 0),
        },
      };
    }

    trades.push(trade);
  }

  return trades;
};

// Generate Pending Signals
export const getPendingSignals = (count: number = 5): Signal[] => {
  const signals: Signal[] = [];
  const now = new Date();

  for (let i = 0; i < count; i++) {
    signals.push({
      id: `SIG-${Date.now()}-${i}`,
      timestamp: subMinutes(now, i * 3),
      asset: randomChoice(ASSETS),
      strategy: randomChoice(STRATEGIES),
      signalValue: Math.random() > 0.5 ? 1 : -1,
      confidence: random(0.48, 0.75),
      regime: randomChoice(REGIMES),
      status: 'pending',
    });
  }

  return signals;
};

// Generate Regime Data
export const getRegimeData = (): RegimeData[] => {
  return ASSETS.map(asset => ({
    asset,
    currentRegime: randomChoice(REGIMES),
    duration: `${randomInt(2, 72)}h`,
    atr: random(0.001, 0.5),
    atr14DayAvg: random(0.0008, 0.45),
    adx: random(15, 45),
    transitions: Array.from({ length: 5 }, (_, i) => ({
      timestamp: subHours(new Date(), (i + 1) * 12),
      from: randomChoice(REGIMES),
      to: randomChoice(REGIMES),
    })),
  }));
};

// Generate Regime Performance
export const getRegimePerformance = (): RegimePerformance[] => [
  {
    regime: 'Trending_HighVol',
    signalCount: 45,
    approvalRate: 60,
    winRate: 65,
    avgExpectancyR: 0.35,
    avgHold: '12h',
  },
  {
    regime: 'Trending_LowVol',
    signalCount: 38,
    approvalRate: 55,
    winRate: 58,
    avgExpectancyR: 0.28,
    avgHold: '18h',
  },
  {
    regime: 'Ranging_HighVol',
    signalCount: 23,
    approvalRate: 35,
    winRate: 42,
    avgExpectancyR: -0.02,
    avgHold: '6h',
  },
  {
    regime: 'Ranging_LowVol',
    signalCount: 31,
    approvalRate: 42,
    winRate: 48,
    avgExpectancyR: 0.12,
    avgHold: '9h',
  },
];

// Generate Risk Metrics
export const getRiskMetrics = (): RiskMetrics => {
  const exposureByAsset: AssetExposure[] = ASSETS.map(asset => ({
    asset,
    long: random(0, 15),
    short: random(0, 10),
    net: 0,
  })).map(e => ({ ...e, net: e.long - e.short }));

  const correlationMatrix: CorrelationData[] = [];
  for (let i = 0; i < ASSETS.length; i++) {
    for (let j = i + 1; j < ASSETS.length; j++) {
      correlationMatrix.push({
        asset1: ASSETS[i],
        asset2: ASSETS[j],
        correlation: random(-0.3, 0.85),
      });
    }
  }

  const underwaterData: UnderwaterPoint[] = [];
  let peak = 100000;
  let current = 100000;
  for (let i = 90; i >= 0; i--) {
    current *= (1 + random(-0.02, 0.025));
    if (current > peak) peak = current;
    const drawdown = ((current - peak) / peak) * 100;
    underwaterData.push({
      date: subDays(new Date(), i),
      drawdown: Math.min(drawdown, 0),
    });
  }

  return {
    netNotionalExposure: 23.4,
    maxDrawdown: 8.2,
    maxDrawdownDate: subDays(new Date(), 23),
    maxConsecutiveLoss: 5,
    correlationRiskScore: 62,
    concentrationAlert: '3 correlated EUR trades pending',
    exposureByAsset,
    correlationMatrix,
    underwaterData,
  };
};

// Generate Limit Status
export const getLimitStatus = (): LimitStatus[] => [
  { name: 'Max Drawdown', limit: 10, current: 8.2, unit: '%' },
  { name: 'Concentration', limit: 25, current: 18.5, unit: '%' },
  { name: 'Leverage', limit: 5, current: 2.3, unit: 'x' },
  { name: 'Daily Loss', limit: 5000, current: 1247, unit: '$' },
];

// Generate Blocked Trades
export const getBlockedTrades = (count: number = 10): Partial<Trade>[] => {
  const vetoReasons = [
    'Confidence below threshold',
    'Correlation limit exceeded',
    'Exposure limit reached',
    'Risk parameters invalid',
    'Regime mismatch',
    'Duplicate signal',
  ];

  return Array.from({ length: count }, (_, i) => ({
    id: `BLK-${Date.now()}-${i}`,
    timestamp: subHours(new Date(), i * 2),
    asset: randomChoice(ASSETS),
    strategy: randomChoice(STRATEGIES),
    confidence: random(0.4, 0.53),
    status: 'vetoed' as const,
    vetoReason: randomChoice(vetoReasons),
  }));
};

// Generate Model Metadata
export const getModelMetadata = (): ModelMetadata => ({
  modelName: 'best_ml_gatekeeper_sklearn.pkl',
  trainingDate: subDays(new Date(), 2),
  trainingDataSize: 12543,
  trainingDataRange: {
    start: subDays(new Date(), 548),
    end: subDays(new Date(), 2),
  },
  threshold: 0.535,
  supportedGranularities: ['H1', 'H4'],
  version: 'v2.1.4',
});

// Generate Model Performance
export const getModelPerformance = (): ModelPerformance[] => [
  { metric: 'Precision', training: 0.72, live7d: 0.68, live30d: 0.64 },
  { metric: 'Recall', training: 0.58, live7d: 0.54, live30d: 0.51 },
  { metric: 'F1 Score', training: 0.64, live7d: 0.60, live30d: 0.57 },
  { metric: 'PR AUC', training: 0.71, live7d: 0.67, live30d: 0.63 },
  { metric: 'Brier Score', training: 0.18, live7d: 0.21, live30d: 0.24 },
  { metric: 'Expectancy (R)', training: 0.28, live7d: 0.24, live30d: 0.19 },
];

// Generate Calibration Data
export const getCalibrationData = (): CalibrationPoint[] => {
  const points: CalibrationPoint[] = [];
  for (let i = 0; i < 10; i++) {
    const predicted = 0.45 + i * 0.055;
    points.push({
      predicted,
      actual: predicted + random(-0.08, 0.08),
      count: randomInt(50, 200),
    });
  }
  return points;
};

// Generate Feature Importance
export const getFeatureImportance = (): FeatureImportance[] => [
  { feature: 'Regime_Label', importance: 0.234 },
  { feature: 'ATR_Value', importance: 0.187 },
  { feature: 'ADX_Value', importance: 0.156 },
  { feature: 'Signal_Value', importance: 0.134 },
  { feature: 'Asset_ID', importance: 0.098 },
  { feature: 'Strategy_ID', importance: 0.087 },
  { feature: 'Session_Volume_Z', importance: 0.045 },
  { feature: 'Price_Momentum', importance: 0.032 },
  { feature: 'Volatility_Regime', importance: 0.018 },
  { feature: 'Time_of_Day', importance: 0.009 },
];

// Generate Drift Alerts
export const getDriftAlerts = (): DriftAlert[] => [
  {
    type: 'approval_rate',
    message: 'Approval rate drifting down (train 60% → live 45%)',
    severity: 'warning',
    timestamp: subHours(new Date(), 4),
  },
  {
    type: 'distribution',
    message: '45 signals with confidence in 0.50-0.55 range (unusual)',
    severity: 'critical',
    timestamp: subHours(new Date(), 2),
  },
];

// Generate Strategies
export const getStrategies = (): Strategy[] => {
  return STRATEGIES.map((name, i) => {
    const equityCurve: { date: Date; equity: number }[] = [];
    let equity = 100000;
    for (let j = 90; j >= 0; j--) {
      equity *= (1 + random(-0.015, 0.02));
      equityCurve.push({ date: subDays(new Date(), j), equity });
    }

    const winRate = random(45, 68);
    const totalSignals = randomInt(80, 250);

    return {
      id: `STRAT-${i}`,
      name,
      description: `${name.replace(/_/g, ' ')} strategy with ATR-based risk management`,
      winRate,
      expectancyR: random(-0.05, 0.45),
      profitFactor: random(0.9, 1.8),
      totalSignals,
      approvalRate: random(45, 65),
      status: randomChoice(['active', 'active', 'active', 'paused']) as Strategy['status'],
      equityCurve,
      winLossByGranularity: {
        H1: { wins: Math.floor(totalSignals * winRate / 100 * 0.6), losses: Math.floor(totalSignals * (100 - winRate) / 100 * 0.6) },
        H4: { wins: Math.floor(totalSignals * winRate / 100 * 0.4), losses: Math.floor(totalSignals * (100 - winRate) / 100 * 0.4) },
      },
      bestTrade: {
        id: `BEST-${i}`,
        timestamp: subDays(new Date(), 15),
        asset: randomChoice(ASSETS),
        strategy: name,
        entryPrice: 1.0850,
        stopLoss: 1.0800,
        takeProfit: 1.0950,
        regime: 'Trending_HighVol',
        confidence: 0.78,
        status: 'closed',
        signalValue: 1,
        pnl: random(250, 500),
        outcome: 'win',
      } as Trade,
      worstTrade: {
        id: `WORST-${i}`,
        timestamp: subDays(new Date(), 20),
        asset: randomChoice(ASSETS),
        strategy: name,
        entryPrice: 1.0950,
        stopLoss: 1.0900,
        takeProfit: 1.1050,
        regime: 'Ranging_HighVol',
        confidence: 0.52,
        status: 'closed',
        signalValue: 1,
        pnl: random(-350, -150),
        outcome: 'loss',
      } as Trade,
      correlationWithOthers: STRATEGIES.reduce((acc, other) => {
        if (other !== name) acc[other] = random(-0.2, 0.6);
        return acc;
      }, {} as Record<string, number>),
    };
  });
};

// Generate Assets
export const getAssets = (): Asset[] => {
  return ASSETS.map((symbol, i) => {
    const basePrice = symbol.includes('JPY') ? 110 : 1.1;
    const currentPrice = basePrice * (1 + random(-0.05, 0.05));
    const change24h = random(-0.008, 0.012);
    
    const priceHistory: { timestamp: Date; open: number; high: number; low: number; close: number; volume: number }[] = [];
    for (let j = 30; j >= 0; j--) {
      const open = basePrice * (1 + random(-0.03, 0.03));
      const close = open * (1 + random(-0.005, 0.005));
      priceHistory.push({
        timestamp: subHours(new Date(), j * 4),
        open,
        high: Math.max(open, close) * (1 + random(0, 0.003)),
        low: Math.min(open, close) * (1 - random(0, 0.003)),
        close,
        volume: randomInt(1000, 10000),
      });
    }

    return {
      id: `ASSET-${i}`,
      symbol,
      name: symbol.replace('_', '/'),
      currentPrice,
      change24h: currentPrice * change24h,
      change24hPct: change24h * 100,
      currentRegime: randomChoice(REGIMES),
      regimeDuration: `${randomInt(2, 72)}h`,
      atr: random(0.001, 0.5),
      atr14DayAvg: random(0.0008, 0.45),
      openPositions: randomInt(0, 3),
      winRate: random(45, 65),
      correlationToPortfolio: random(-0.1, 0.5),
      maxDrawdown: random(5, 15),
      priceHistory,
      signals: [],
      correlationToOthers: ASSETS.reduce((acc, other) => {
        if (other !== symbol) acc[other] = random(-0.3, 0.7);
        return acc;
      }, {} as Record<string, number>),
    };
  });
};

// Generate Approval Trend
export const getApprovalTrend = (): ApprovalTrendPoint[] => {
  return Array.from({ length: 7 }, (_, i) => ({
    date: subDays(new Date(), 6 - i),
    approvalRate: random(52, 66),
    signalCount: randomInt(40, 80),
  }));
};

// Generate Performance Attribution
export const getPerformanceAttribution = (): PerformanceAttribution[] => [
  { layer: 'Layer 0 (Strategy Selection)', contribution: 12.4 },
  { layer: 'Layer 1 (Regime Detection)', contribution: 8.7 },
  { layer: 'Layer 2 (Signal Generation)', contribution: 23.5 },
  { layer: 'Layer 3 (ML Gatekeeper)', contribution: 31.2 },
  { layer: 'Layer 4 (Risk Management)', contribution: 15.8 },
  { layer: 'Layer 5 (Execution)', contribution: 8.4 },
];

// Generate Time of Day Heatmap
export const getTimeOfDayHeatmap = (): TimeOfDayHeatmap[] => {
  return Array.from({ length: 24 }, (_, hour) => {
    const wins = randomInt(5, 25);
    const losses = randomInt(3, 20);
    return {
      hour,
      wins,
      losses,
      winRate: (wins / (wins + losses)) * 100,
    };
  });
};

// Generate Confidence Deciles
export const getConfidenceDeciles = (): ConfidenceDecile[] => {
  return Array.from({ length: 10 }, (_, i) => ({
    decile: i + 1,
    minConfidence: 0.5 + i * 0.05,
    maxConfidence: 0.55 + i * 0.05,
    winRate: random(40 + i * 3, 50 + i * 4),
    tradeCount: randomInt(30, 120),
    expectancy: random(-0.1 + i * 0.03, 0.05 + i * 0.04),
  }));
};

// Generate Equity Curve Data
export const getEquityCurve = () => {
  const data: { date: Date; equity: number; drawdown: number }[] = [];
  let equity = 100000;
  let peak = equity;
  
  for (let i = 180; i >= 0; i--) {
    equity *= (1 + random(-0.012, 0.018));
    if (equity > peak) peak = equity;
    const drawdown = ((equity - peak) / peak) * 100;
    data.push({
      date: subDays(new Date(), i),
      equity,
      drawdown: Math.min(drawdown, 0),
    });
  }
  
  return data;
};

// Helper for subMinutes (not in date-fns)
function subMinutes(date: Date, minutes: number): Date {
  return new Date(date.getTime() - minutes * 60000);
}

// Real-time update simulation
export const simulateRealtimeUpdate = () => {
  return {
    newSignal: Math.random() > 0.7 ? getPendingSignals(1)[0] : null,
    priceUpdate: ASSETS.map(asset => ({
      asset,
      price: random(1.05, 150),
      change: random(-0.002, 0.002),
    })),
    timestamp: new Date(),
  };
};
