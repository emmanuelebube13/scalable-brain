// Layer 5 Dashboard — API client for the FastAPI backend.
// All endpoints are loosely coupled to the Python service layer.

import type {
  KPIData,
  Trade,
  Signal,
  RegimeData,
  RegimePerformance,
  RiskMetrics,
  LimitStatus,
  ModelMetadata,
  ModelPerformance,
  CalibrationPoint,
  FeatureImportance,
  DriftAlert,
  ConfidenceDecile,
  OpenPosition,
  Strategy,
  Asset,
  ApprovalTrendPoint,
  PerformanceAttribution,
  OHLCData,
  IndicatorResult,
  IndicatorInfo,
  AlertConfig,
  StrategyOverlayResponse,
} from '@/types';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';
const DEFAULT_TIMEOUT_MS = Number(import.meta.env.VITE_API_TIMEOUT_MS || 30000);
const DEFAULT_RETRIES = Number(import.meta.env.VITE_API_RETRIES || 1);

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function fetchJSON<T>(
  path: string,
  options?: RequestInit,
  timeoutMs = DEFAULT_TIMEOUT_MS,
  retries = DEFAULT_RETRIES
): Promise<T> {
  const { signal: callerSignal, headers: callerHeaders, ...requestOptions } = options || {};

  for (let attempt = 0; attempt <= retries; attempt++) {
    const controller = new AbortController();
    let abortedByCaller = false;

    const onCallerAbort = () => {
      abortedByCaller = true;
      controller.abort(callerSignal?.reason);
    };

    if (callerSignal) {
      if (callerSignal.aborted) {
        onCallerAbort();
      } else {
        callerSignal.addEventListener('abort', onCallerAbort, { once: true });
      }
    }

    const timeoutId = window.setTimeout(() => {
      controller.abort(new DOMException(`Request timed out after ${timeoutMs}ms`, 'TimeoutError'));
    }, timeoutMs);

    try {
      const res = await fetch(`${BASE_URL}${path}`, {
        ...requestOptions,
        headers: {
          'Content-Type': 'application/json',
          ...(callerHeaders || {}),
        },
        signal: controller.signal,
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(`API error ${res.status}: ${text}`);
      }

      return res.json() as Promise<T>;
    } catch (error) {
      const timedOut = controller.signal.aborted && !abortedByCaller;
      const networkError = error instanceof TypeError;
      const canRetry = attempt < retries;

      if (abortedByCaller) {
        throw error;
      }

      if ((timedOut || networkError) && canRetry) {
        await sleep(250 * (attempt + 1));
        continue;
      }

      if (timedOut) {
        throw new Error(`API timeout after ${timeoutMs}ms: ${path}`);
      }

      throw error;
    } finally {
      window.clearTimeout(timeoutId);
      callerSignal?.removeEventListener('abort', onCallerAbort);
    }
  }

  throw new Error(`API request failed after retries: ${path}`);
}

// ---------------------------------------------------------------------------
// KPI / Overview
// ---------------------------------------------------------------------------
export async function fetchKPI(): Promise<KPIData> {
  return fetchJSON<KPIData>('/kpi/');
}

export async function fetchApprovalTrend(): Promise<ApprovalTrendPoint[]> {
  return fetchJSON<ApprovalTrendPoint[]>('/kpi/trend');
}

export async function fetchAttribution(): Promise<PerformanceAttribution[]> {
  return fetchJSON<PerformanceAttribution[]>('/kpi/attribution');
}

export async function fetchEquityCurve(days = 30): Promise<Array<{ date: string; equity: number }>> {
  return fetchJSON<Array<{ date: string; equity: number }>>(`/kpi/equity-curve?days=${days}`);
}

// ---------------------------------------------------------------------------
// Trades & Signals
// ---------------------------------------------------------------------------
export async function fetchTrades(
  limit = 50,
  status?: string,
  asset?: string,
  strategy?: string
): Promise<Trade[]> {
  const params = new URLSearchParams();
  params.set('limit', String(limit));
  if (status) params.set('status', status);
  if (asset) params.set('asset', asset);
  if (strategy) params.set('strategy', strategy);
  return fetchJSON<Trade[]>(`/trades/?${params.toString()}`);
}

export async function fetchBlockedTrades(limit = 10): Promise<Partial<Trade>[]> {
  return fetchJSON<Partial<Trade>[]>(`/trades/blocked?limit=${limit}`);
}

export async function fetchOpenPositions(limit = 100): Promise<OpenPosition[]> {
  return fetchJSON<OpenPosition[]>(`/trades/open-positions?limit=${limit}`);
}

export async function fetchPendingSignals(limit = 5): Promise<Signal[]> {
  return fetchJSON<Signal[]>(`/trades/signals/pending?limit=${limit}`);
}

// ---------------------------------------------------------------------------
// Risk
// ---------------------------------------------------------------------------
export async function fetchRiskMetrics(): Promise<RiskMetrics> {
  return fetchJSON<RiskMetrics>('/risk/');
}

export async function fetchRiskLimits(): Promise<LimitStatus[]> {
  return fetchJSON<LimitStatus[]>('/risk/limits');
}

// ---------------------------------------------------------------------------
// Regimes
// ---------------------------------------------------------------------------
export async function fetchCurrentRegimes(): Promise<RegimeData[]> {
  return fetchJSON<RegimeData[]>('/regimes/current');
}

export async function fetchRegimePerformance(): Promise<RegimePerformance[]> {
  return fetchJSON<RegimePerformance[]>('/regimes/performance');
}

// ---------------------------------------------------------------------------
// Model
// ---------------------------------------------------------------------------
export async function fetchModelMetadata(): Promise<ModelMetadata> {
  return fetchJSON<ModelMetadata>('/model/metadata');
}

export async function fetchModelPerformance(): Promise<ModelPerformance[]> {
  return fetchJSON<ModelPerformance[]>('/model/performance');
}

export async function fetchCalibrationData(): Promise<CalibrationPoint[]> {
  return fetchJSON<CalibrationPoint[]>('/model/calibration');
}

export async function fetchFeatureImportance(): Promise<FeatureImportance[]> {
  return fetchJSON<FeatureImportance[]>('/model/features');
}

export async function fetchDriftAlerts(): Promise<DriftAlert[]> {
  return fetchJSON<DriftAlert[]>('/model/drift');
}

export async function fetchConfidenceDeciles(): Promise<ConfidenceDecile[]> {
  return fetchJSON<ConfidenceDecile[]>('/model/confidence-deciles');
}

// ---------------------------------------------------------------------------
// Strategies
// ---------------------------------------------------------------------------
export async function fetchStrategies(): Promise<Strategy[]> {
  return fetchJSON<Strategy[]>('/strategies/');
}

// ---------------------------------------------------------------------------
// Assets
// ---------------------------------------------------------------------------
export async function fetchAssets(): Promise<Asset[]> {
  return fetchJSON<Asset[]>('/assets/');
}

// ---------------------------------------------------------------------------
// Charts / Indicators / Alerts
// ---------------------------------------------------------------------------
export const chartAPI = {
  getOHLC: (symbol: string, timeframe: string, limit?: number) =>
    fetchJSON<OHLCData[]>(
      `/charts/ohlc?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}${
        limit ? `&limit=${limit}` : ''
      }`
    ),

  getPriceHistory: (symbol: string, lookbackDays?: number) =>
    fetchJSON<{ timestamp: string; price: number }[]>(
      `/charts/price-history?symbol=${encodeURIComponent(symbol)}${
        lookbackDays ? `&lookback_days=${lookbackDays}` : ''
      }`
    ),

  getVolumeProfile: (symbol: string, rows?: number) =>
    fetchJSON<Array<{ price: number; volume: number; priceRange: { min: number; max: number } }>>(
      `/charts/volume-profile?symbol=${encodeURIComponent(symbol)}${rows ? `&rows=${rows}` : ''}`
    ),

  getSymbols: () =>
    fetchJSON<Array<{ symbol: string; assetId: number; regime: string; atr: number; adx: number; lastPrice: number }>>(
      '/charts/symbols'
    ),

  getMultiTimeframe: (symbol: string, timeframes: string[]) =>
    fetchJSON<{ symbol: string; data: Record<string, OHLCData[]> }>(
      `/charts/multi-timeframe?symbol=${encodeURIComponent(symbol)}&timeframes=${encodeURIComponent(timeframes.join(','))}`
    ),
};

export const indicatorAPI = {
  getList: () => fetchJSON<IndicatorInfo[]>('/indicators/list'),

  calculate: (
    symbol: string,
    indicator: string,
    timeframe: string,
    params?: Record<string, number>
  ) =>
    fetchJSON<IndicatorResult>(
      `/indicators/calculate?symbol=${encodeURIComponent(symbol)}&indicator=${encodeURIComponent(indicator)}&timeframe=${encodeURIComponent(timeframe)}`,
      {
        method: 'POST',
        body: JSON.stringify(params || {}),
      }
    ),

  calculateBatch: (
    symbol: string,
    timeframe: string,
    indicators: { indicator: string; params?: Record<string, number> }[]
  ) =>
    fetchJSON<IndicatorResult[]>(
      `/indicators/calculate-batch?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}`,
      {
        method: 'POST',
        body: JSON.stringify(indicators),
      }
    ),
};

export const alertAPI = {
  getAll: (symbol?: string, status?: string) => {
    const params = new URLSearchParams();
    if (symbol) params.set('symbol', symbol);
    if (status) params.set('status', status);
    const qs = params.toString();
    return fetchJSON<AlertConfig[]>(`/alerts/${qs ? `?${qs}` : ''}`);
  },

  create: (alert: {
    name: string;
    type: string;
    symbol: string;
    condition: string;
    value: number;
    timeframe?: string;
    message?: string;
    expires_at?: string;
  }) =>
    fetchJSON<AlertConfig>('/alerts/', {
      method: 'POST',
      body: JSON.stringify(alert),
    }),

  updateStatus: (alertId: string, status: string) =>
    fetchJSON<{ success: boolean }>(`/alerts/${encodeURIComponent(alertId)}/status?status=${encodeURIComponent(status)}`, {
      method: 'PUT',
    }),

  delete: (alertId: string) =>
    fetchJSON<{ success: boolean }>(`/alerts/${encodeURIComponent(alertId)}`, {
      method: 'DELETE',
    }),

  getTriggered: (since?: string) =>
    fetchJSON<AlertConfig[]>(`/alerts/triggered${since ? `?since=${encodeURIComponent(since)}` : ''}`),

  evaluate: (symbol: string) =>
    fetchJSON<{ triggered_count: number }>(`/alerts/evaluate/${encodeURIComponent(symbol)}`, {
      method: 'POST',
    }),
};

// ---------------------------------------------------------------------------
// Strategy Overlay
// ---------------------------------------------------------------------------
export const strategyOverlayAPI = {
  getData: (symbol: string, strategyName: string, timeframe: string) => {
    const params = new URLSearchParams({
      strategy: strategyName,
      symbol,
      timeframe,
    });
    return fetchJSON<StrategyOverlayResponse>(`/chart/strategy-overlay?${params.toString()}`);
  },
};

// ---------------------------------------------------------------------------
// Analysis API
// ---------------------------------------------------------------------------
export const analysisAPI = {
  getSupportResistance: (symbol: string, timeframe: string, lookback?: number) => {
    const params = new URLSearchParams({
      symbol,
      timeframe,
      ...(lookback && { lookback: lookback.toString() }),
    });
    return fetchJSON<{
      support: Array<{ price: number; strength: number; touches: number }>;
      resistance: Array<{ price: number; strength: number; touches: number }>;
    }>(`/chart/support-resistance?${params.toString()}`);
  },

  getMetrics: (symbol: string, timeframe: string) => {
    const params = new URLSearchParams({
      symbol,
      timeframe,
    });
    return fetchJSON<import('@/types').AnalysisMetrics>(`/chart/analysis-metrics?${params.toString()}`);
  },

  getMultiTimeframe: (symbol: string, timeframes: string[]) => {
    const params = new URLSearchParams({
      symbol,
      timeframes: timeframes.join(','),
    });
    return fetchJSON<import('@/types').MultiTimeframeData>(`/chart/multi-timeframe?${params.toString()}`);
  },
};

// ---------------------------------------------------------------------------
// Volume API
// ---------------------------------------------------------------------------
export const volumeAPI = {
  getProfile: (symbol: string, timeframe: string, rows?: number) => {
    const params = new URLSearchParams({
      symbol,
      timeframe,
      ...(rows && { rows: rows.toString() }),
    });
    return fetchJSON<import('@/types').VolumeProfileData>(`/chart/volume-profile?${params.toString()}`);
  },

  getSessionVolume: (symbol: string, session: 'asian' | 'london' | 'ny' | 'all') => {
    const params = new URLSearchParams({
      symbol,
      session,
    });
    return fetchJSON<{
      session: string;
      totalVolume: number;
      buyVolume: number;
      sellVolume: number;
      delta: number;
    }>(`/chart/session-volume?${params.toString()}`);
  },
};

// ---------------------------------------------------------------------------
// Correlation API
// ---------------------------------------------------------------------------
export const correlationAPI = {
  getData: (symbol: string, period: '1W' | '1M' | '3M' = '1M') => {
    const params = new URLSearchParams({
      symbol,
      period,
    });
    return fetchJSON<{
      baseAsset: string;
      correlations: Array<{
        symbol: string;
        correlation: number;
        slope: 'converging' | 'diverging';
      }>;
      period: string;
    }>(`/chart/correlation?${params.toString()}`);
  },

  getMatrix: (symbols: string[], period?: string) => {
    const params = new URLSearchParams({
      symbols: symbols.join(','),
      ...(period && { period }),
    });
    return fetchJSON<{
      symbols: string[];
      matrix: number[][];
      period: string;
    }>(`/chart/correlation-matrix?${params.toString()}`);
  },
};

// ---------------------------------------------------------------------------
// WebSocket Connection Helper
// ---------------------------------------------------------------------------
export function createWebSocketConnection(
  endpoint: string,
  onMessage: (data: unknown) => void,
  onError?: (error: Event) => void,
  onClose?: (event: CloseEvent) => void
): WebSocket {
  const wsUrl = `${BASE_URL.replace(/^http/, 'ws')}${endpoint}`;
  const ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    console.log(`WebSocket connected: ${endpoint}`);
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onMessage(data);
    } catch (e) {
      console.error('Failed to parse WebSocket message:', e);
    }
  };

  ws.onerror = (error) => {
    console.error('WebSocket error:', error);
    onError?.(error);
  };

  ws.onclose = (event) => {
    console.log(`WebSocket closed: ${endpoint}`, event.code, event.reason);
    onClose?.(event);
  };

  return ws;
}
