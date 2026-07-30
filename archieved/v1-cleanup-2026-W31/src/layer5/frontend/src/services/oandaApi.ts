/**
 * OANDA API client for direct data access
 */

import type { OHLCData, IndicatorResult } from '@/types';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';
const OANDA_TIMEOUT_MS = 3000; // 3 second timeout for OANDA endpoints

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

// Fetch with timeout helper
async function fetchJSONWithTimeout<T>(path: string, timeoutMs: number, options?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  
  try {
    return await fetchJSON<T>(path, {
      ...options,
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeoutId);
  }
}

// =============================================================================
// Chart Data API
// =============================================================================

export const oandaChartAPI = {
  /**
   * Get OHLC data from database or OANDA
   */
  getOHLC: async (symbol: string, timeframe: string, limit?: number): Promise<OHLCData[]> => {
    return fetchJSON<OHLCData[]>(
      `/charts/ohlc?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}${
        limit ? `&limit=${limit}` : ''
      }`
    );
  },

  /**
   * Get OHLC data directly from OANDA
   */
  getOandaCandles: async (symbol: string, granularity: string, count = 500): Promise<OHLCData[]> => {
    const response = await fetchJSONWithTimeout<{
      symbol: string;
      granularity: string;
      count: number;
      candles: Array<{
        timestamp: string;
        open: number;
        high: number;
        low: number;
        close: number;
        volume: number;
        complete: boolean;
      }>;
    }>(`/streaming/candles/${encodeURIComponent(symbol)}?granularity=${granularity}&count=${count}`, OANDA_TIMEOUT_MS);
    
    return response.candles.map(c => ({
      timestamp: c.timestamp,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
      volume: c.volume,
    }));
  },

  /**
   * Get current price for a symbol
   */
  getCurrentPrice: async (symbol: string): Promise<{ bid: number; ask: number; mid: number; time: string }> => {
    return fetchJSONWithTimeout<{ bid: number; ask: number; mid: number; time: string }>(
      `/streaming/price/${encodeURIComponent(symbol)}`,
      OANDA_TIMEOUT_MS
    );
  },

  /**
   * Get available instruments
   */
  getInstruments: async (): Promise<Array<{
    symbol: string;
    name: string;
    type: string;
    displayName: string;
  }>> => {
    const response = await fetchJSONWithTimeout<{
      instruments: Array<{
        symbol: string;
        name: string;
        type: string;
        displayName: string;
      }>;
      count: number;
    }>(`/streaming/instruments`, OANDA_TIMEOUT_MS);
    return response.instruments;
  },

  /**
   * Get streaming status
   */
  getStreamingStatus: async (): Promise<{
    isConnected: boolean;
    isConfigured: boolean;
    activeSubscriptions: number;
  }> => {
    return fetchJSON(`/streaming/status`);
  },
};

// =============================================================================
// Indicators API
// =============================================================================

export const oandaIndicatorAPI = {
  /**
   * Get list of available indicators
   */
  getList: () => fetchJSON<Array<{
    id: string;
    name: string;
    category: string;
    defaultParams: Record<string, number>;
  }>>('/indicators/list'),

  /**
   * Calculate a single indicator
   */
  calculate: async (
    symbol: string,
    indicator: string,
    timeframe: string,
    params?: Record<string, number>
  ): Promise<IndicatorResult> => {
    return fetchJSON<IndicatorResult>(
      `/indicators/calculate?symbol=${encodeURIComponent(symbol)}&indicator=${encodeURIComponent(indicator)}&timeframe=${encodeURIComponent(timeframe)}`,
      {
        method: 'POST',
        body: JSON.stringify(params || {}),
      }
    );
  },

  /**
   * Calculate multiple indicators in batch
   */
  calculateBatch: async (
    symbol: string,
    timeframe: string,
    indicators: { indicator: string; params?: Record<string, number> }[]
  ): Promise<IndicatorResult[]> => {
    return fetchJSONWithTimeout<IndicatorResult[]>(
      `/indicators/calculate-batch?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}`,
      8000, // 8 second timeout for batch calculations
      {
        method: 'POST',
        body: JSON.stringify(indicators),
      }
    );
  },
};

// =============================================================================
// Trade Overlay API
// =============================================================================

export const oandaTradeAPI = {
  /**
   * Get trade markers for chart overlay
   */
  getTradeMarkers: async (symbol: string): Promise<Array<{
    id: string;
    type: 'entry' | 'sl' | 'tp' | 'win' | 'loss';
    price: number;
    timestamp: string;
    side?: 'long' | 'short';
  }>> => {
    const response = await fetchJSON<{
      entries: Array<{
        timestamp: string;
        price: number;
        side: string;
        strategy: string;
        confidence: number;
      }>;
      trades: Array<{
        entryTime: string;
        exitTime: string;
        entryPrice: number;
        exitPrice: number;
        side: string;
        pnl: number;
        outcome: string;
      }>;
    }>(`/charts/strategy-overlay?symbol=${encodeURIComponent(symbol)}&strategy=default`);

    const markers: Array<{
      id: string;
      type: 'entry' | 'sl' | 'tp' | 'win' | 'loss';
      price: number;
      timestamp: string;
      side?: 'long' | 'short';
    }> = [];

    // Add entry markers
    response.entries.forEach((entry, i) => {
      markers.push({
        id: `entry_${i}`,
        type: 'entry',
        price: entry.price,
        timestamp: entry.timestamp,
        side: entry.side as 'long' | 'short',
      });
    });

    // Add completed trade markers
    response.trades.forEach((trade, i) => {
      markers.push({
        id: `trade_${i}`,
        type: trade.outcome === 'win' ? 'win' : 'loss',
        price: trade.exitPrice,
        timestamp: trade.exitTime,
        side: trade.side as 'long' | 'short',
      });
    });

    return markers;
  },

  /**
   * Get support/resistance levels
   */
  getSupportResistance: async (symbol: string, timeframe: string) => {
    return fetchJSON<{
      support: Array<{ price: number; strength: number; touches: number }>;
      resistance: Array<{ price: number; strength: number; touches: number }>;
    }>(`/charts/support-resistance?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}`);
  },
};

export default {
  chart: oandaChartAPI,
  indicators: oandaIndicatorAPI,
  trades: oandaTradeAPI,
};
