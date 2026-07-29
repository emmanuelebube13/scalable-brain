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
  Strategy,
  Asset,
  ApprovalTrendPoint,
  PerformanceAttribution,
} from '@/types';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
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
