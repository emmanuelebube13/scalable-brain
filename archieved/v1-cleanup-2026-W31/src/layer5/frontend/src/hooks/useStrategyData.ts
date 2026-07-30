/**
 * useStrategyData - Hook for fetching strategy overlay data from the API.
 * 
 * Fetches strategy entries and completed trades for visualization on charts.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { toast } from 'sonner';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';

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

export interface StrategyOverlayData {
  entries: StrategyEntry[];
  trades: TradeResult[];
  winRate: number;
  totalTrades: number;
  wins: number;
  losses: number;
}

interface UseStrategyDataReturn extends StrategyOverlayData {
  isLoading: boolean;
  error: Error | null;
  refresh: () => void;
}

/**
 * Parse API response dates into proper Date objects
 */
function parseStrategyData(data: {
  entries: Array<{
    timestamp: string;
    signal: 1 | -1;
    entry_price: number;
    stop_loss: number;
    take_profit: number;
    confidence: number;
    regime: string;
  }>;
  trades: Array<{
    entry: {
      timestamp: string;
      signal: 1 | -1;
      entry_price: number;
      stop_loss: number;
      take_profit: number;
      confidence: number;
      regime: string;
    };
    exit_price: number;
    exit_reason: ExitReason;
    pnl: number;
    pips_gained: number;
    r_multiple: number;
    exit_timestamp: string;
  }>;
  win_rate: number;
  total_trades: number;
  wins: number;
  losses: number;
}): StrategyOverlayData {
  return {
    entries: data.entries.map(e => ({
      ...e,
      timestamp: new Date(e.timestamp),
    })),
    trades: data.trades.map(t => ({
      entry: {
        ...t.entry,
        timestamp: new Date(t.entry.timestamp),
      },
      exit_price: t.exit_price,
      exit_reason: t.exit_reason,
      pnl: t.pnl,
      pips_gained: t.pips_gained,
      r_multiple: t.r_multiple,
      exit_timestamp: new Date(t.exit_timestamp),
    })),
    winRate: data.win_rate,
    totalTrades: data.total_trades,
    wins: data.wins,
    losses: data.losses,
  };
}

/**
 * Hook for fetching strategy overlay data from the API.
 * 
 * @param symbol - The trading symbol (e.g., 'EUR_USD')
 * @param strategyName - The name of the strategy
 * @param timeframe - The timeframe (e.g., '1h', '4h', '1d')
 * @param refreshInterval - Optional auto-refresh interval in milliseconds (default: 30000)
 */
export function useStrategyData(
  symbol: string,
  strategyName: string,
  timeframe: string,
  refreshInterval = 30000
): UseStrategyDataReturn {
  const [data, setData] = useState<StrategyOverlayData>({
    entries: [],
    trades: [],
    winRate: 0,
    totalTrades: 0,
    wins: 0,
    losses: 0,
  });
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  
  // Use ref to track if component is mounted
  const isMountedRef = useRef(true);
  
  // Track previous params to avoid unnecessary fetches
  const prevParamsRef = useRef({ symbol: '', strategyName: '', timeframe: '' });

  const fetchData = useCallback(async (showLoading = true) => {
    // Skip if params are empty
    if (!symbol || !strategyName || !timeframe) {
      return;
    }

    // Check if params actually changed
    const currentParams = { symbol, strategyName, timeframe };
    const prevParams = prevParamsRef.current;
    const paramsChanged = 
      prevParams.symbol !== symbol ||
      prevParams.strategyName !== strategyName ||
      prevParams.timeframe !== timeframe;

    if (!paramsChanged && !showLoading) {
      return; // Skip refresh if params unchanged and it's a background refresh
    }

    if (showLoading) {
      setIsLoading(true);
    }
    setError(null);

    try {
      const params = new URLSearchParams({
        strategy: strategyName,
        symbol,
        timeframe,
      });

      const response = await fetch(
        `${BASE_URL}/chart/strategy-overlay?${params.toString()}`,
        {
          headers: { 'Content-Type': 'application/json' },
        }
      );

      if (!response.ok) {
        const text = await response.text();
        throw new Error(`API error ${response.status}: ${text}`);
      }

      const rawData = await response.json();
      const parsedData = parseStrategyData(rawData);

      if (isMountedRef.current) {
        setData(parsedData);
        prevParamsRef.current = currentParams;
      }
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err));
      if (isMountedRef.current) {
        setError(error);
        // Only show toast on manual refresh or first load
        if (showLoading) {
          toast.error('Failed to load strategy data', {
            description: error.message,
          });
        }
      }
    } finally {
      if (isMountedRef.current) {
        setIsLoading(false);
      }
    }
  }, [symbol, strategyName, timeframe]);

  // Initial fetch and when params change
  useEffect(() => {
    isMountedRef.current = true;
    void fetchData(true);

    return () => {
      isMountedRef.current = false;
    };
  }, [fetchData]);

  // Auto-refresh interval
  useEffect(() => {
    if (refreshInterval <= 0) return;

    const intervalId = setInterval(() => {
      void fetchData(false);
    }, refreshInterval);

    return () => clearInterval(intervalId);
  }, [fetchData, refreshInterval]);

  const refresh = useCallback(() => {
    void fetchData(true);
  }, [fetchData]);

  return {
    ...data,
    isLoading,
    error,
    refresh,
  };
}

export default useStrategyData;
